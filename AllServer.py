import cv2
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
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
        self.is_dancing = False  # Flag to prevent concurrent dance routines
        if self.servo_available:
            try:
                self.kit = ServoKit(channels=16)
                print("🎛️ Servo controller initialized")
                self.SERVO_RANGES = {
                    0: {'min': 40, 'max': 140, 'default': 90},
                    1: {'min': 90, 'max': 140, 'default': 120},
                    2: {'min': 50, 'max': 130, 'default': 90},
                    3: {'min': 0, 'max': 180, 'default': 90},
                    4: {'min': 40, 'max': 170, 'default': 90},
                    5: {'min': 0, 'max': 180, 'default': 30},
                    6: {'min': 0, 'max': 180, 'default': 150},
                }
                self.initialize_servos()
            except Exception as e:
                print(f"❌ Servo initialization error: {e}")
                self.servo_available = False
        else:
            print("🔧 Running in SIMULATION mode - no hardware required")
            self.SERVO_RANGES = {
                2: {'min': 50, 'max': 130, 'default': 90},
                3: {'min': 0, 'max': 180, 'default': 90},
            }
            self.simulated_positions = {2: 90, 3: 90}
    
    def initialize_servos(self):
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
        try:
            if servo_channel not in self.SERVO_RANGES:
                print(f"❌ Invalid servo channel: {servo_channel}")
                return False, f"Invalid servo channel: {servo_channel}"
            servo_range = self.SERVO_RANGES[servo_channel]
            if not (servo_range['min'] <= angle <= servo_range['max']):
                print(f"❌ Unsafe angle {angle}° for servo {servo_channel}. Safe range: {servo_range['min']}-{servo_range['max']}°")
                return False, f"Angle {angle}° out of safe range {servo_range['min']}-{servo_range['max']}°"
            if self.servo_available:
                self.kit.servo[servo_channel].angle = angle
                print(f"🎛️ Servo {servo_channel} moved to {angle}°")
            else:
                self.simulated_positions[servo_channel] = angle
                print(f"🔧 SIMULATION: Servo {servo_channel} moved to {angle}°")
            return True, f"Servo {servo_channel} moved to {angle}°"
        except Exception as e:
            print(f"❌ Servo {servo_channel} movement error: {e}")
            return False, f"{e}"
    
    async def smooth_move(self, servo_channel, target_angle, duration=0.5, steps=20):
        """Smoothly move servo from current position to target angle"""
        if servo_channel not in self.SERVO_RANGES:
            return False
        
        servo_range = self.SERVO_RANGES[servo_channel]
        current_angle = servo_range['default'] if not hasattr(self, 'current_positions') else self.current_positions.get(servo_channel, servo_range['default'])
        
        # Initialize current positions dict if not exists
        if not hasattr(self, 'current_positions'):
            self.current_positions = {ch: cfg['default'] for ch, cfg in self.SERVO_RANGES.items()}
        
        step_delay = duration / steps
        angle_step = (target_angle - current_angle) / steps
        
        for i in range(steps):
            new_angle = current_angle + (angle_step * (i + 1))
            self.move_servo(servo_channel, int(new_angle))
            await asyncio.sleep(step_delay)
        
        self.current_positions[servo_channel] = target_angle
        return True
    
    async def wave_dance(self):
        """Perform a waving motion - back and forth movement"""
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("👋 Starting wave dance...")
        
        try:
            # Wave motion using servo 2 (horizontal movement)
            for _ in range(3):  # Wave 3 times
                await self.smooth_move(2, 120, duration=0.4)
                await self.smooth_move(2, 60, duration=0.4)
            
            # Return to center
            await self.smooth_move(2, 90, duration=0.5)
            print("✅ Wave dance completed")
            return True, "Wave dance completed successfully"
        
        except Exception as e:
            print(f"❌ Wave dance error: {e}")
            return False, f"Error during wave dance: {e}"
        finally:
            self.is_dancing = False
    
    async def nod_dance(self):
        """Perform a nodding motion - up and down movement"""
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("🤖 Starting nod dance...")
        
        try:
            # Nod motion using servo 3 (vertical movement)
            for _ in range(3):  # Nod 3 times
                await self.smooth_move(3, 120, duration=0.3)
                await self.smooth_move(3, 60, duration=0.3)
            
            # Return to center
            await self.smooth_move(3, 90, duration=0.5)
            print("✅ Nod dance completed")
            return True, "Nod dance completed successfully"
        
        except Exception as e:
            print(f"❌ Nod dance error: {e}")
            return False, f"Error during nod dance: {e}"
        finally:
            self.is_dancing = False
    
    async def full_dance(self):
        """Perform a complex dance routine combining multiple servos"""
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("💃 Starting full dance routine...")
        
        try:
            # Sequence 1: Wave
            await self.smooth_move(2, 120, duration=0.4)
            await self.smooth_move(2, 60, duration=0.4)
            await self.smooth_move(2, 90, duration=0.3)
            
            # Sequence 2: Nod
            await self.smooth_move(3, 120, duration=0.3)
            await self.smooth_move(3, 60, duration=0.3)
            await self.smooth_move(3, 90, duration=0.3)
            
            # Sequence 3: Combined movement
            await asyncio.gather(
                self.smooth_move(2, 110, duration=0.5),
                self.smooth_move(3, 110, duration=0.5)
            )
            await asyncio.gather(
                self.smooth_move(2, 70, duration=0.5),
                self.smooth_move(3, 70, duration=0.5)
            )
            
            # Sequence 4: Figure-8 pattern
            for _ in range(2):
                await self.smooth_move(2, 120, duration=0.3)
                await self.smooth_move(3, 120, duration=0.3)
                await self.smooth_move(2, 60, duration=0.3)
                await self.smooth_move(3, 60, duration=0.3)
            
            # Return to neutral position
            await asyncio.gather(
                self.smooth_move(2, 90, duration=0.5),
                self.smooth_move(3, 90, duration=0.5)
            )
            
            print("✅ Full dance completed")
            return True, "Full dance routine completed successfully"
        
        except Exception as e:
            print(f"❌ Full dance error: {e}")
            return False, f"Error during full dance: {e}"
        finally:
            self.is_dancing = False
    
    async def custom_dance(self, movements):
        """Execute custom dance sequence from provided movements array"""
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("🎭 Starting custom dance...")
        
        try:
            for move in movements:
                servo = move.get('servo')
                angle = move.get('angle')
                duration = move.get('duration', 0.5)
                
                if servo is None or angle is None:
                    continue
                
                await self.smooth_move(servo, angle, duration=duration)
            
            print("✅ Custom dance completed")
            return True, "Custom dance completed successfully"
        
        except Exception as e:
            print(f"❌ Custom dance error: {e}")
            return False, f"Error during custom dance: {e}"
        finally:
            self.is_dancing = False
    
    def stop_dance(self):
        """Emergency stop for dance routines"""
        self.is_dancing = False
        print("🛑 Dance routine stopped")

servo_controller = ServoController()

# ---------- CAMERA ----------
class ThreadedCamera:
    def __init__(self, src=0):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
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
                while not self.frame_queue.empty():
                    try: self.frame_queue.get_nowait()
                    except: pass
                _, buffer = cv2.imencode('.jpg', frame, self.encode_params)
                try: self.frame_queue.put(buffer.tobytes(), block=False)
                except: pass
            time.sleep(0.005)
    def get_frame(self):
        try: return self.frame_queue.get_nowait()
        except: return None
    def stop(self):
        self.running = False

# ---------- AUDIO ----------
class ThreadedAudio:
    def __init__(self, device_index=None):
        self.CHUNK = 1024
        self.RATE = 16000
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1

        self.pa = pyaudio.PyAudio()
        if device_index is None:
            device_index = self.pa.get_default_input_device_info()['index']
            print(f"🎙️ Using default mic device: {device_index}")
        self.stream = self.pa.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.CHUNK,
            stream_callback=self.audio_callback
        )

        self.audio_queue = Queue(maxsize=2)
        self.running = True

    def audio_callback(self, in_data, frame_count, time_info, status):
        if self.running:
            while not self.audio_queue.empty():
                try: self.audio_queue.get_nowait()
                except: pass
            try: self.audio_queue.put_nowait(in_data)
            except: pass
        return (in_data, pyaudio.paContinue)

    def get_audio_chunk(self):
        try: return self.audio_queue.get_nowait()
        except: return None
    def start(self):
        self.stream.start_stream()
    def stop(self):
        self.running = False
        if self.stream.is_active():
            self.stream.stop_stream()
        self.stream.close()
        self.pa.terminate()

camera = ThreadedCamera(0)
audio = ThreadedAudio()

clients_video = []
clients_audio = []

# -------------- VIDEO STREAMING ---------------
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
        await asyncio.sleep(0.005)

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

# -------------- AUDIO STREAMING ---------------
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
        await asyncio.sleep(0.001)

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

# -------------- SERVO CONTROL ---------------
@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await ws.accept()
    print("🎛️ Control client connected")
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            if "servo" in data and "angle" in data:
                servo = data.get("servo")
                angle = data.get("angle")
                success, message = servo_controller.move_servo(servo, angle)
                response = {
                    "status": "ok" if success else "error",
                    "servo": servo, "angle": angle, "message": message}
            elif "action" in data:
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

# -------------- DANCE ROUTES (NEW) ---------------

@app.post("/api/dance/wave")
async def dance_wave():
    """HTTP endpoint to trigger wave dance"""
    success, message = await servo_controller.wave_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/nod")
async def dance_nod():
    """HTTP endpoint to trigger nod dance"""
    success, message = await servo_controller.nod_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/full")
async def dance_full():
    """HTTP endpoint to trigger full dance routine"""
    success, message = await servo_controller.full_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/custom")
async def dance_custom(movements: list):
    """
    HTTP endpoint for custom dance sequence
    Example: [{"servo": 2, "angle": 120, "duration": 0.5}, {"servo": 3, "angle": 60, "duration": 0.3}]
    """
    success, message = await servo_controller.custom_dance(movements)
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/stop")
async def dance_stop():
    """Emergency stop for dance routines"""
    servo_controller.stop_dance()
    return JSONResponse(content={"status": "success", "message": "Dance stopped"})

@app.websocket("/ws/dance")
async def ws_dance(ws: WebSocket):
    """WebSocket endpoint for real-time dance control"""
    await ws.accept()
    print("💃 Dance client connected")
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            
            dance_type = data.get("type", "wave")
            
            if dance_type == "wave":
                success, message = await servo_controller.wave_dance()
            elif dance_type == "nod":
                success, message = await servo_controller.nod_dance()
            elif dance_type == "full":
                success, message = await servo_controller.full_dance()
            elif dance_type == "custom":
                movements = data.get("movements", [])
                success, message = await servo_controller.custom_dance(movements)
            elif dance_type == "stop":
                servo_controller.stop_dance()
                success, message = True, "Dance stopped"
            else:
                success, message = False, f"Unknown dance type: {dance_type}"
            
            response = {
                "status": "success" if success else "error",
                "type": dance_type,
                "message": message
            }
            await ws.send_text(json.dumps(response))
            
    except WebSocketDisconnect:
        print("💃 Dance client disconnected")
    except Exception as e:
        print(f"❌ Dance WebSocket error: {e}")

@app.get("/api/dance/status")
async def dance_status():
    """Get current dance status"""
    return JSONResponse(content={
        "is_dancing": servo_controller.is_dancing,
        "servo_available": servo_controller.servo_available
    })

# -------------- STARTUP/SHUTDOWN ---------------

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting WALL-E server with servo control & dance routines")
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
    print("🤖 WALL-E Server with Dance & Wave Control")
    print("=" * 50)
    if SERVO_AVAILABLE:
        print("✅ ServoKit available - Hardware mode")
        print("🔧 Make sure your PCA9685 is connected")
    else:
        print("🔧 ServoKit not available - Simulation mode")
        print("📦 Install: pip install adafruit-circuitpython-servokit")
    print("=" * 50)
    print("📡 Available Endpoints:")
    print("   POST /api/dance/wave   - Trigger wave dance")
    print("   POST /api/dance/nod    - Trigger nod dance")
    print("   POST /api/dance/full   - Trigger full dance")
    print("   POST /api/dance/custom - Custom dance sequence")
    print("   POST /api/dance/stop   - Stop dance")
    print("   GET  /api/dance/status - Get dance status")
    print("   WS   /ws/dance         - Real-time dance control")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
