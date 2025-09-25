# server_with_servo_control.py
import cv2
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import pyaudio
import json
import time
import threading
from queue import Queue

# Servo control imports
try:
    from adafruit_servokit import ServoKit
    SERVO_AVAILABLE = True
    print("✅ ServoKit imported successfully")
except ImportError:
    SERVO_AVAILABLE = False
    print("❌ ServoKit not available - servo control disabled")

app = FastAPI()

# ----- SERVO CONTROL INTEGRATION -----
class ServoController:
    def __init__(self):
        self.servo_available = SERVO_AVAILABLE
        if self.servo_available:
            try:
                self.kit = ServoKit(channels=16)
                print("🎛️ Servo controller initialized")
                
                # Define safe servo ranges
                self.SERVO_RANGES = {
                    0: {'min': 40, 'max': 140, 'default': 90},
                    1: {'min': 90, 'max': 140, 'default': 120}, 
                    2: {'min': 50, 'max': 130, 'default': 90},   # Neck sideways
                    3: {'min': 0, 'max': 180, 'default': 90},   # Up/down neck
                    4: {'min': 40, 'max': 170, 'default': 90},  # Up/down neck 2
                    5: {'min': 0, 'max': 180, 'default': 30},   # Left arm
                    6: {'min': 0, 'max': 180, 'default': 150},  # Right arm
                }
                
                # Initialize servos to safe default positions
                self.initialize_servos()
            except Exception as e:
                print(f"❌ Servo initialization error: {e}")
                self.servo_available = False
        else:
            # Simulation mode for testing
            print("🔧 Running in SIMULATION mode - no hardware required")
            self.SERVO_RANGES = {
                2: {'min': 50, 'max': 130, 'default': 90},   # Neck sideways
                3: {'min': 0, 'max': 180, 'default': 90},   # Up/down neck
            }
            self.simulated_positions = {2: 90, 3: 90}  # Track simulated positions
    
    def initialize_servos(self):
        """Initialize servos to safe positions"""
        if not self.servo_available:
            return
            
        print("🔄 Initializing servos to safe positions...")
        for channel, config in self.SERVO_RANGES.items():
            try:
                self.kit.servo[channel].angle = config['default']
                time.sleep(0.1)
                print(f"   Servo {channel}: {config['default']}°")
            except Exception as e:
                print(f"❌ Error initializing servo {channel}: {e}")
    
    def move_servo(self, servo_channel, angle):
        """Move servo to specified angle with safety checks"""
        try:
            # Validate servo channel
            if servo_channel not in self.SERVO_RANGES:
                print(f"❌ Invalid servo channel: {servo_channel}")
                return False, f"Invalid servo channel: {servo_channel}"
            
            # Safety check
            servo_range = self.SERVO_RANGES[servo_channel]
            if not (servo_range['min'] <= angle <= servo_range['max']):
                print(f"❌ Unsafe angle {angle}° for servo {servo_channel}. Safe range: {servo_range['min']}-{servo_range['max']}°")
                return False, f"Angle {angle}° out of safe range {servo_range['min']}-{servo_range['max']}°"
            
            if self.servo_available:
                # Real hardware control
                self.kit.servo[servo_channel].angle = angle
                print(f"🎛️ Servo {servo_channel} moved to {angle}°")
            else:
                # Simulation mode
                self.simulated_positions[servo_channel] = angle
                print(f"🔧 SIMULATION: Servo {servo_channel} moved to {angle}°")
            
            return True, f"Servo {servo_channel} moved to {angle}°"
            
        except Exception as e:
            error_msg = f"Servo {servo_channel} movement error: {e}"
            print(f"❌ {error_msg}")
            return False, error_msg

# Initialize servo controller
servo_controller = ServoController()

# ----- OPTIMIZED CAMERA -----
class ThreadedCamera:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        
        # Critical optimizations
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # JPEG encoding settings for speed
        self.encode_params = [cv2.IMWRITE_JPEG_QUALITY, 60]
        
        self.frame_queue = Queue(maxsize=2)
        self.thread = threading.Thread(target=self.update)
        self.thread.daemon = True
        self.running = True
        self.thread.start()
    
    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                # Clear old frames
                if not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except:
                        pass
                
                _, buffer = cv2.imencode('.jpg', frame, self.encode_params)
                
                try:
                    self.frame_queue.put(buffer.tobytes(), block=False)
                except:
                    pass
            time.sleep(0.01)
    
    def get_frame(self):
        try:
            return self.frame_queue.get_nowait()
        except:
            return None
    
    def stop(self):
        self.running = False

# ----- OPTIMIZED AUDIO -----
# ----- OPTIMIZED AUDIO (DROP-IN REPLACEMENT) -----
class ThreadedAudio:
    def __init__(self, device_index=None):  # Default mic unless specified
        self.CHUNK = 1024        # Set this to 512 or 1024, but must match client CHUNK
        self.RATE = 16000
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1

        self.pa = pyaudio.PyAudio()
        # Try to get default input device if not specified
        if device_index is None:
            device_index = self.pa.get_default_input_device_info()['index']
            print(f"🎙️ Using default input device: {device_index}")

        # Open stream with minimal buffering for real-time
        self.stream = self.pa.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.audio_callback
        )

        self.audio_queue = Queue(maxsize=2)  # Only allow 2 most recent chunks
        self.running = True

    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.running:
            # ALWAYS keep only the latest, drop old
            while not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except Exception:
                    pass
            try:
                self.audio_queue.put(in_data, block=False)
            except Exception:
                pass
        return (in_data, pyaudio.paContinue)

    def get_audio_chunk(self):
        try:
            return self.audio_queue.get_nowait()
        except Exception:
            return None

    def start(self):
        self.stream.start_stream()

    def stop(self):
        self.running = False
        if self.stream.is_active():
            self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()


# Initialize hardware
camera = ThreadedCamera(0)
audio = ThreadedAudio(0)

# Client lists
clients_video = []
clients_audio = []

# ----- VIDEO STREAMING -----
async def send_camera_frames():
    while True:
        frame_bytes = camera.get_frame()
        if frame_bytes and clients_video:
            dead_clients = []
            for ws in clients_video:
                try:
                    await ws.send_bytes(frame_bytes)
                except:
                    dead_clients.append(ws)
            
            for ws in dead_clients:
                if ws in clients_video:
                    clients_video.remove(ws)
        
        await asyncio.sleep(0.033)

@app.websocket("/ws/video")
async def ws_video(ws: WebSocket):
    await ws.accept()
    clients_video.append(ws)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if ws in clients_video:
            clients_video.remove(ws)

# ----- AUDIO STREAMING -----
async def send_audio_frames():
    while True:
        audio_chunk = audio.get_audio_chunk()
        if audio_chunk and clients_audio:
            dead_clients = []
            for ws in clients_audio:
                try:
                    await ws.send_bytes(audio_chunk)
                except:
                    dead_clients.append(ws)
            
            for ws in dead_clients:
                if ws in clients_audio:
                    clients_audio.remove(ws)
        
        await asyncio.sleep(0.01)

@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    clients_audio.append(ws)
    try:
        while True:
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if ws in clients_audio:
            clients_audio.remove(ws)

# ----- ENHANCED SERVO CONTROL -----
@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await ws.accept()
    print("🎛️ Control client connected")
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            
            # Handle different command types
            if "servo" in data and "angle" in data:
                # Individual servo control
                servo = data.get("servo")
                angle = data.get("angle")
                
                success, message = servo_controller.move_servo(servo, angle)
                
                response = {
                    "status": "ok" if success else "error",
                    "servo": servo,
                    "angle": angle,
                    "message": message
                }
                
            elif "action" in data:
                # Special actions
                action = data.get("action")
                
                if action == "get_ranges":
                    response = {
                        "status": "ok", 
                        "action": action, 
                        "ranges": servo_controller.SERVO_RANGES,
                        "servo_available": servo_controller.servo_available
                    }
                elif action == "reset_all":
                    if servo_controller.servo_available:
                        servo_controller.initialize_servos()
                        response = {"status": "ok", "action": action, "message": "All servos reset"}
                    else:
                        # Reset simulation
                        servo_controller.simulated_positions = {2: 90, 3: 90}
                        response = {"status": "ok", "action": action, "message": "Simulation reset"}
                else:
                    response = {"status": "error", "message": f"Unknown action: {action}"}
            
            else:
                response = {"status": "error", "message": "Invalid command format"}
            
            await ws.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        print("🎛️ Control client disconnected")
    except Exception as e:
        print(f"❌ Control error: {e}")

# ----- STARTUP -----
@app.on_event("startup")
async def startup_event():
    print("🚀 Starting WALL-E server with servo control")
    print(f"🎛️ Servo mode: {'HARDWARE' if servo_controller.servo_available else 'SIMULATION'}")
    audio.start()
    asyncio.create_task(send_camera_frames())
    asyncio.create_task(send_audio_frames())

@app.on_event("shutdown")
async def shutdown_event():
    print("🔄 Shutting down...")
    camera.stop()
    audio.stop()

if __name__ == "__main__":
    print("🤖 WALL-E Server with Integrated Servo Control")
    print("=" * 50)
    if SERVO_AVAILABLE:
        print("✅ ServoKit available - Hardware mode")
        print("🔧 Make sure your PCA9685 is connected")
    else:
        print("🔧 ServoKit not available - Simulation mode")
        print("📦 Install: pip install adafruit-circuitpython-servokit")
    print("=" * 50)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
