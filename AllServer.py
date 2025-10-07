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
        self.is_dancing = False
        
        if self.servo_available:
            try:
                self.kit = ServoKit(channels=16)
                print("🎛️ Servo controller initialized")
                
                # WALL-E servo configuration (based on standard WALL-E builds)
                # Servo 0: Head rotation
                # Servo 1: Neck top
                # Servo 2: Neck bottom
                # Servo 3: Eye right
                # Servo 4: Eye left
                # Servo 5: Arm left
                # Servo 6: Arm right
                
                self.SERVO_RANGES = {
                    0: {'min': 40, 'max': 140, 'default': 90, 'name': 'Head Rotation'},
                    1: {'min': 90, 'max': 140, 'default': 120, 'name': 'Neck Top'},
                    2: {'min': 50, 'max': 130, 'default': 90, 'name': 'Neck Bottom'},
                    3: {'min': 0, 'max': 180, 'default': 90, 'name': 'Eye Right'},
                    4: {'min': 40, 'max': 170, 'default': 90, 'name': 'Eye Left'},
                    5: {'min': 0, 'max': 180, 'default': 30, 'name': 'Arm Left'},
                    6: {'min': 0, 'max': 180, 'default': 150, 'name': 'Arm Right'},
                }
                
                self.initialize_servos()
            except Exception as e:
                print(f"❌ Servo initialization error: {e}")
                self.servo_available = False
        else:
            print("🔧 Running in SIMULATION mode")
            self.SERVO_RANGES = {
                0: {'min': 40, 'max': 140, 'default': 90, 'name': 'Head Rotation'},
                1: {'min': 90, 'max': 140, 'default': 120, 'name': 'Neck Top'},
                2: {'min': 50, 'max': 130, 'default': 90, 'name': 'Neck Bottom'},
                3: {'min': 0, 'max': 180, 'default': 90, 'name': 'Eye Right'},
                4: {'min': 40, 'max': 170, 'default': 90, 'name': 'Eye Left'},
                5: {'min': 0, 'max': 180, 'default': 30, 'name': 'Arm Left'},
                6: {'min': 0, 'max': 180, 'default': 150, 'name': 'Arm Right'},
            }
            self.simulated_positions = {i: cfg['default'] for i, cfg in self.SERVO_RANGES.items()}
        
        # Initialize current positions tracker
        self.current_positions = {ch: cfg['default'] for ch, cfg in self.SERVO_RANGES.items()}
    
    def initialize_servos(self):
        """Set all servos to their default safe positions"""
        if not self.servo_available:
            return
        
        print("🔄 Initializing servos to safe positions...")
        for channel, config in self.SERVO_RANGES.items():
            try:
                self.kit.servo[channel].angle = config['default']
                self.current_positions[channel] = config['default']
                time.sleep(0.1)
                print(f"   Servo {channel} ({config['name']}): {config['default']}°")
            except Exception as e:
                print(f"❌ Error initializing servo {channel}: {e}")
    
    def move_servo(self, servo_channel, angle):
        """Move a single servo to specified angle"""
        try:
            if servo_channel not in self.SERVO_RANGES:
                return False, f"Invalid servo channel: {servo_channel}"
            
            servo_range = self.SERVO_RANGES[servo_channel]
            
            if not (servo_range['min'] <= angle <= servo_range['max']):
                return False, f"Angle {angle}° out of range {servo_range['min']}-{servo_range['max']}°"
            
            if self.servo_available:
                self.kit.servo[servo_channel].angle = angle
                print(f"🎛️ Servo {servo_channel} ({servo_range['name']}) → {angle}°")
            else:
                self.simulated_positions[servo_channel] = angle
                print(f"🔧 SIM: Servo {servo_channel} ({servo_range['name']}) → {angle}°")
            
            self.current_positions[servo_channel] = angle
            return True, f"Servo {servo_channel} moved to {angle}°"
            
        except Exception as e:
            return False, f"{e}"
    
    async def smooth_move(self, servo_channel, target_angle, duration=0.5, steps=20):
        """Smoothly move servo from current position to target"""
        if servo_channel not in self.SERVO_RANGES:
            return False
        
        servo_range = self.SERVO_RANGES[servo_channel]
        target_angle = max(servo_range['min'], min(servo_range['max'], target_angle))
        
        current_angle = self.current_positions.get(servo_channel, servo_range['default'])
        step_delay = duration / steps
        angle_step = (target_angle - current_angle) / steps
        
        for i in range(steps):
            new_angle = current_angle + (angle_step * (i + 1))
            self.move_servo(servo_channel, int(new_angle))
            await asyncio.sleep(step_delay)
        
        return True
    
    async def wave_dance(self):
        """
        Proper wave dance with ARM movement!
        Wave right arm while looking at it
        """
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("👋 Starting WAVE dance with ARM movement...")
        
        try:
            # 1. Turn head slightly to look at right arm
            await asyncio.gather(
                self.smooth_move(0, 110, duration=0.6),  # Head turn right
                self.smooth_move(2, 100, duration=0.6),  # Neck slightly up
            )
            
            await asyncio.sleep(0.2)
            
            # 2. Raise right arm up (servo 6)
            await self.smooth_move(6, 90, duration=0.8)  # Arm up position
            
            await asyncio.sleep(0.1)
            
            # 3. Wave the arm back and forth (3 times)
            for _ in range(3):
                await self.smooth_move(6, 60, duration=0.3)   # Wave left
                await self.smooth_move(6, 120, duration=0.3)  # Wave right
            
            # 4. Return arm to rest position
            await self.smooth_move(6, 150, duration=0.8)
            
            # 5. Return head to center
            await asyncio.gather(
                self.smooth_move(0, 90, duration=0.6),
                self.smooth_move(2, 90, duration=0.6),
            )
            
            print("✅ Wave dance completed")
            return True, "Wave dance completed successfully"
        
        except Exception as e:
            print(f"❌ Wave dance error: {e}")
            return False, f"Error during wave dance: {e}"
        finally:
            self.is_dancing = False
    
    async def nod_dance(self):
        """
        Nodding motion with eyes and neck
        """
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("🤖 Starting NOD dance...")
        
        try:
            # Nod with neck and eyes following
            for _ in range(3):
                # Nod down
                await asyncio.gather(
                    self.smooth_move(2, 70, duration=0.4),   # Neck down
                    self.smooth_move(3, 120, duration=0.4),  # Eyes down
                    self.smooth_move(4, 120, duration=0.4),
                )
                
                await asyncio.sleep(0.1)
                
                # Nod up
                await asyncio.gather(
                    self.smooth_move(2, 110, duration=0.4),  # Neck up
                    self.smooth_move(3, 60, duration=0.4),   # Eyes up
                    self.smooth_move(4, 60, duration=0.4),
                )
                
                await asyncio.sleep(0.1)
            
            # Return to neutral
            await asyncio.gather(
                self.smooth_move(2, 90, duration=0.5),
                self.smooth_move(3, 90, duration=0.5),
                self.smooth_move(4, 90, duration=0.5),
            )
            
            print("✅ Nod dance completed")
            return True, "Nod dance completed successfully"
        
        except Exception as e:
            print(f"❌ Nod dance error: {e}")
            return False, f"Error during nod dance: {e}"
        finally:
            self.is_dancing = False
    
    async def curious_look(self):
        """
        Curious looking around animation (from WALL-E movie)
        """
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("👀 Starting CURIOUS LOOK animation...")
        
        try:
            # Look left
            await asyncio.gather(
                self.smooth_move(0, 60, duration=0.7),   # Head left
                self.smooth_move(3, 110, duration=0.7),  # Eyes follow
                self.smooth_move(4, 110, duration=0.7),
            )
            await asyncio.sleep(0.5)
            
            # Look right
            await asyncio.gather(
                self.smooth_move(0, 120, duration=0.9),
                self.smooth_move(3, 70, duration=0.9),
                self.smooth_move(4, 70, duration=0.9),
            )
            await asyncio.sleep(0.5)
            
            # Look up
            await asyncio.gather(
                self.smooth_move(0, 90, duration=0.5),
                self.smooth_move(2, 110, duration=0.6),
                self.smooth_move(3, 60, duration=0.6),
                self.smooth_move(4, 60, duration=0.6),
            )
            await asyncio.sleep(0.5)
            
            # Return to neutral
            await asyncio.gather(
                self.smooth_move(0, 90, duration=0.6),
                self.smooth_move(2, 90, duration=0.6),
                self.smooth_move(3, 90, duration=0.6),
                self.smooth_move(4, 90, duration=0.6),
            )
            
            print("✅ Curious look completed")
            return True, "Curious look completed successfully"
        
        except Exception as e:
            print(f"❌ Curious look error: {e}")
            return False, f"Error: {e}"
        finally:
            self.is_dancing = False
    
    async def excited_dance(self):
        """
        Excited celebration with both arms!
        """
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("🎉 Starting EXCITED dance...")
        
        try:
            # Raise both arms
            await asyncio.gather(
                self.smooth_move(5, 90, duration=0.5),   # Left arm up
                self.smooth_move(6, 90, duration=0.5),   # Right arm up
                self.smooth_move(2, 110, duration=0.5),  # Neck up
            )
            
            # Shake arms excitedly (4 times)
            for _ in range(4):
                await asyncio.gather(
                    self.smooth_move(5, 60, duration=0.2),
                    self.smooth_move(6, 120, duration=0.2),
                )
                await asyncio.gather(
                    self.smooth_move(5, 120, duration=0.2),
                    self.smooth_move(6, 60, duration=0.2),
                )
            
            # Lower arms
            await asyncio.gather(
                self.smooth_move(5, 30, duration=0.6),
                self.smooth_move(6, 150, duration=0.6),
                self.smooth_move(2, 90, duration=0.6),
            )
            
            print("✅ Excited dance completed")
            return True, "Excited dance completed"
        
        except Exception as e:
            print(f"❌ Excited dance error: {e}")
            return False, f"Error: {e}"
        finally:
            self.is_dancing = False
    
    async def full_dance(self):
        """
        Complete choreographed dance routine combining all movements
        """
        if self.is_dancing:
            return False, "Another dance routine is already running"
        
        self.is_dancing = True
        print("💃 Starting FULL DANCE routine...")
        
        try:
            # === Part 1: Greeting Wave ===
            print("  Part 1: Greeting wave")
            await asyncio.gather(
                self.smooth_move(0, 110, duration=0.6),
                self.smooth_move(6, 90, duration=0.8),
            )
            
            for _ in range(2):
                await self.smooth_move(6, 60, duration=0.25)
                await self.smooth_move(6, 120, duration=0.25)
            
            await self.smooth_move(6, 150, duration=0.6)
            
            # === Part 2: Curious Look Around ===
            print("  Part 2: Looking around")
            await self.smooth_move(0, 60, duration=0.7)
            await asyncio.sleep(0.3)
            await self.smooth_move(0, 120, duration=0.9)
            await asyncio.sleep(0.3)
            await self.smooth_move(0, 90, duration=0.5)
            
            # === Part 3: Nod ===
            print("  Part 3: Nodding")
            for _ in range(2):
                await asyncio.gather(
                    self.smooth_move(2, 70, duration=0.35),
                    self.smooth_move(3, 120, duration=0.35),
                    self.smooth_move(4, 120, duration=0.35),
                )
                await asyncio.gather(
                    self.smooth_move(2, 110, duration=0.35),
                    self.smooth_move(3, 60, duration=0.35),
                    self.smooth_move(4, 60, duration=0.35),
                )
            
            # === Part 4: Excited Arm Waves ===
            print("  Part 4: Excited celebration")
            await asyncio.gather(
                self.smooth_move(5, 90, duration=0.5),
                self.smooth_move(6, 90, duration=0.5),
            )
            
            for _ in range(3):
                await asyncio.gather(
                    self.smooth_move(5, 60, duration=0.2),
                    self.smooth_move(6, 120, duration=0.2),
                )
                await asyncio.gather(
                    self.smooth_move(5, 120, duration=0.2),
                    self.smooth_move(6, 60, duration=0.2),
                )
            
            # === Part 5: Bow (arms down, neck forward) ===
            print("  Part 5: Bow")
            await asyncio.gather(
                self.smooth_move(2, 70, duration=0.8),
                self.smooth_move(5, 30, duration=0.8),
                self.smooth_move(6, 150, duration=0.8),
            )
            
            await asyncio.sleep(0.5)
            
            # === Part 6: Return to neutral ===
            print("  Part 6: Return to rest")
            await asyncio.gather(
                self.smooth_move(0, 90, duration=0.7),
                self.smooth_move(2, 90, duration=0.7),
                self.smooth_move(3, 90, duration=0.7),
                self.smooth_move(4, 90, duration=0.7),
                self.smooth_move(5, 30, duration=0.7),
                self.smooth_move(6, 150, duration=0.7),
            )
            
            print("✅ Full dance routine completed!")
            return True, "Full dance routine completed successfully"
        
        except Exception as e:
            print(f"❌ Full dance error: {e}")
            return False, f"Error during full dance: {e}"
        finally:
            self.is_dancing = False
    
    async def custom_dance(self, movements):
        """Execute custom dance from movement array"""
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
            return False, f"Error: {e}"
        finally:
            self.is_dancing = False
    
    def stop_dance(self):
        """Emergency stop"""
        self.is_dancing = False
        print("🛑 Dance routine stopped")
        return True, "Dance stopped"

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
                    "servo": servo, "angle": angle, "message": message
                }
            
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
                    servo_controller.initialize_servos()
                    response = {"status": "ok", "action": action, "message": "All servos reset"}
                else:
                    response = {"status": "error", "message": f"Unknown action: {action}"}
            else:
                response = {"status": "error", "message": "Invalid command"}
            
            await ws.send_text(json.dumps(response))
    
    except WebSocketDisconnect:
        print("🎛️ Control client disconnected")

# -------------- DANCE API ROUTES ---------------

@app.post("/api/dance/wave")
async def dance_wave():
    """Trigger wave dance with ARM movement"""
    success, message = await servo_controller.wave_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/nod")
async def dance_nod():
    """Trigger nod dance"""
    success, message = await servo_controller.nod_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/full")
async def dance_full():
    """Trigger full choreographed dance routine"""
    success, message = await servo_controller.full_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/curious")
async def dance_curious():
    """Trigger curious looking animation"""
    success, message = await servo_controller.curious_look()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/excited")
async def dance_excited():
    """Trigger excited celebration dance"""
    success, message = await servo_controller.excited_dance()
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/custom")
async def dance_custom(movements: list):
    """
    Custom dance sequence
    Example: [{"servo": 6, "angle": 90, "duration": 0.5}, {"servo": 5, "angle": 90, "duration": 0.3}]
    """
    success, message = await servo_controller.custom_dance(movements)
    if success:
        return JSONResponse(content={"status": "success", "message": message})
    else:
        raise HTTPException(status_code=409, detail=message)

@app.post("/api/dance/stop")
async def dance_stop():
    """Emergency stop for dances"""
    success, message = servo_controller.stop_dance()
    return JSONResponse(content={"status": "success", "message": message})

@app.get("/api/dance/status")
async def dance_status():
    """Get dance status"""
    return JSONResponse(content={
        "is_dancing": servo_controller.is_dancing,
        "servo_available": servo_controller.servo_available,
        "current_positions": servo_controller.current_positions
    })

@app.websocket("/ws/dance")
async def ws_dance(ws: WebSocket):
    """WebSocket for real-time dance control"""
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
            elif dance_type == "curious":
                success, message = await servo_controller.curious_look()
            elif dance_type == "excited":
                success, message = await servo_controller.excited_dance()
            elif dance_type == "custom":
                movements = data.get("movements", [])
                success, message = await servo_controller.custom_dance(movements)
            elif dance_type == "stop":
                success, message = servo_controller.stop_dance()
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

# -------------- STARTUP/SHUTDOWN ---------------

@app.on_event("startup")
async def startup_event():
    print("🚀 Starting WALL-E server with complete dance routines")
    print(f"🎛️ Mode: {'HARDWARE' if servo_controller.servo_available else 'SIMULATION'}")
    audio.start()
    asyncio.create_task(send_camera_frames())
    asyncio.create_task(send_audio_frames())

@app.on_event("shutdown")
async def shutdown_event():
    print("🔄 Shutting down...")
    camera.stop()
    audio.stop()

if __name__ == "__main__":
    print("🤖 WALL-E Server with Complete Dance Routines & ARM Control")
    print("=" * 60)
    print("🎭 Dance Routines Available:")
    print("   1. WAVE - Proper arm waving with head tracking")
    print("   2. NOD - Head nodding with eye movement")
    print("   3. CURIOUS - Looking around curiously")
    print("   4. EXCITED - Celebration with both arms")
    print("   5. FULL - Complete choreographed performance")
    print("=" * 60)
    print("📡 API Endpoints:")
    print("   POST /api/dance/wave     - Wave with arm")
    print("   POST /api/dance/nod      - Nod head")
    print("   POST /api/dance/full     - Full dance routine")
    print("   POST /api/dance/curious  - Curious look")
    print("   POST /api/dance/excited  - Excited celebration")
    print("   POST /api/dance/custom   - Custom sequence")
    print("   POST /api/dance/stop     - Emergency stop")
    print("   GET  /api/dance/status   - Get status")
    print("=" * 60)
    
    if not SERVO_AVAILABLE:
        print("💡 TIP: Install ServoKit for hardware control:")
        print("   pip install adafruit-circuitpython-servokit")
        print("=" * 60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
