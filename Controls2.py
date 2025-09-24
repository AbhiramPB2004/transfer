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
                
                # Define safe servo ranges from your Flask code
                self.SERVO_RANGES = {
                    0: {'min': 40, 'max': 140, 'default': 90},   # From your reset functions
                    1: {'min': 90, 'max': 140, 'default': 120}, # From your reset functions  
                    2: {'min': 50, 'max': 130, 'default': 90},  # Neck sideways
                    3: {'min': 0, 'max': 180, 'default': 90},   # Up/down neck
                    4: {'min': 40, 'max': 170, 'default': 90},  # Up/down neck 2
                    5: {'min': 0, 'max': 180, 'default': 30},   # Left arm (from reset_back_servos)
                    6: {'min': 0, 'max': 180, 'default': 150},  # Right arm (from reset_back_servos)
                }
                
                # Initialize servos to safe default positions
                self.reset_all_servos()
            except Exception as e:
                print(f"❌ Servo initialization error: {e}")
                self.servo_available = False
    
    def is_angle_safe(self, servo_channel, angle):
        """Check if angle is within safe range for servo"""
        if servo_channel not in self.SERVO_RANGES:
            return False
        
        servo_range = self.SERVO_RANGES[servo_channel]
        return servo_range['min'] <= angle <= servo_range['max']
    
    def move_servo(self, servo_channel, angle):
        """Move servo to specified angle with safety checks"""
        if not self.servo_available:
            print(f"⚠️ Servo {servo_channel} command ignored - hardware not available")
            return False
        
        try:
            # Validate servo channel
            if not (0 <= servo_channel < 16):
                print(f"❌ Invalid servo channel: {servo_channel}")
                return False
            
            # Safety check
            if not self.is_angle_safe(servo_channel, angle):
                servo_range = self.SERVO_RANGES.get(servo_channel, {'min': 0, 'max': 180})
                print(f"❌ Unsafe angle {angle}° for servo {servo_channel}. Safe range: {servo_range['min']}-{servo_range['max']}°")
                return False
            
            # Move servo
            self.kit.servo[servo_channel].angle = angle
            print(f"🎛️ Servo {servo_channel} moved to {angle}°")
            return True
            
        except Exception as e:
            print(f"❌ Servo {servo_channel} movement error: {e}")
            return False
    
    def reset_all_servos(self):
        """Reset all servos to default positions"""
        if not self.servo_available:
            return
        
        print("🔄 Resetting all servos to default positions")
        for channel, config in self.SERVO_RANGES.items():
            try:
                self.kit.servo[channel].angle = config['default']
                time.sleep(0.1)  # Small delay between moves
            except Exception as e:
                print(f"❌ Error resetting servo {channel}: {e}")
    
    def execute_preset(self, preset_name):
        """Execute predefined servo movements from your Flask code"""
        if not self.servo_available:
            return False
        
        presets = {
            "RESET": {i: 90 for i in range(16)},  # All servos to 90°
            "RESET_BACK": {0: 40, 1: 120, 2: 90, 3: 90, 4: 90, 5: 30, 6: 150},
            "SLEEP": {0: 90, 1: 90, 2: 90, 3: 0, 4: 40, 5: 0, 6: 180},
            "DOWN": {0: 90, 1: 90, 2: 90, 3: 180, 4: 40, 5: 0, 6: 180},
            "STANDING_TALL": {0: 90, 1: 90, 2: 90, 3: 180, 4: 170, 5: 0, 6: 180},
        }
        
        if preset_name not in presets:
            print(f"❌ Unknown preset: {preset_name}")
            return False
        
        print(f"🎭 Executing preset: {preset_name}")
        servo_positions = presets[preset_name]
        
        for servo_channel, angle in servo_positions.items():
            if self.is_angle_safe(servo_channel, angle):
                self.move_servo(servo_channel, angle)
                time.sleep(0.05)  # Small delay between moves
            else:
                print(f"⚠️ Skipping unsafe angle for servo {servo_channel} in preset {preset_name}")
        
        return True

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
class ThreadedAudio:
    def __init__(self, device_index=0):
        # Optimized settings for low latency
        self.CHUNK = 512  # Smaller chunk = lower latency
        self.RATE = 16000  # Lower rate = less data
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        
        self.pa = pyaudio.PyAudio()
        
        # Open stream with minimal buffering
        self.stream = self.pa.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.audio_callback
        )
        
        self.audio_queue = Queue(maxsize=3)  # Very small queue
        self.running = True
        
    def audio_callback(self, in_data, frame_count, time_info, status):
        # Process audio in callback for lowest latency
        if self.running:
            # Clear old audio to prevent accumulation
            if not self.audio_queue.empty():
                try:
                    self.audio_queue.get_nowait()
                except:
                    pass
            
            try:
                self.audio_queue.put(in_data, block=False)
            except:
                pass  # Drop if queue full
        
        return (in_data, pyaudio.paContinue)
    
    def get_audio_chunk(self):
        try:
            return self.audio_queue.get_nowait()
        except:
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
audio = ThreadedAudio(0)  # Your mic device index

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
        
        await asyncio.sleep(0.033)  # ~30 FPS

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
                    await ws.send_bytes(audio_chunk)  # Send raw binary audio
                except:
                    dead_clients.append(ws)
            
            for ws in dead_clients:
                if ws in clients_audio:
                    clients_audio.remove(ws)
        
        await asyncio.sleep(0.01)  # Very frequent audio updates

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
                
                success = servo_controller.move_servo(servo, angle)
                
                response = {
                    "status": "ok" if success else "error",
                    "servo": servo,
                    "angle": angle,
                    "message": f"Servo {servo} moved to {angle}°" if success else f"Failed to move servo {servo}"
                }
                
            elif "preset" in data:
                # Preset execution
                preset_name = data.get("preset")
                success = servo_controller.execute_preset(preset_name)
                
                response = {
                    "status": "ok" if success else "error",
                    "preset": preset_name,
                    "message": f"Preset {preset_name} executed" if success else f"Failed to execute preset {preset_name}"
                }
                
            elif "action" in data:
                # Special actions
                action = data.get("action")
                
                if action == "reset_all":
                    servo_controller.reset_all_servos()
                    response = {"status": "ok", "action": action, "message": "All servos reset"}
                    
                elif action == "get_ranges":
                    response = {
                        "status": "ok", 
                        "action": action, 
                        "ranges": servo_controller.SERVO_RANGES,
                        "servo_available": servo_controller.servo_available
                    }
                    
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
    print("🚀 Starting WALL-E server with integrated servo control")
    audio.start()
    asyncio.create_task(send_camera_frames())
    asyncio.create_task(send_audio_frames())

@app.on_event("shutdown")
async def shutdown_event():
    print("🔄 Shutting down...")
    camera.stop()
    audio.stop()
    if servo_controller.servo_available:
        servo_controller.reset_all_servos()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="uvloop")
