import cv2
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import pyaudio
import json
import time
import threading
from queue import Queue

app = FastAPI()

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

# ----- SERVO CONTROL (unchanged) -----
@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            servo = data.get("servo")
            angle = data.get("angle")
            print(f"🔧 Move servo {servo} → {angle}°")
            await ws.send_text(json.dumps({"status": "ok", "servo": servo, "angle": angle}))
    except WebSocketDisconnect:
        print("Control client disconnected")

# ----- STARTUP -----
@app.on_event("startup")
async def startup_event():
    audio.start()
    asyncio.create_task(send_camera_frames())
    asyncio.create_task(send_audio_frames())

@app.on_event("shutdown")
async def shutdown_event():
    camera.stop()
    audio.stop()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="uvloop")
