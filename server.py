import cv2
import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimize buffer
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Lower resolution
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        # JPEG encoding settings for speed
        self.encode_params = [cv2.IMWRITE_JPEG_QUALITY, 60]  # Lower quality = faster
        
        self.frame_queue = Queue(maxsize=2)  # Small queue
        self.thread = threading.Thread(target=self.update)
        self.thread.daemon = True
        self.running = True
        self.thread.start()
    
    def update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                # Clear old frames to prevent accumulation
                if not self.frame_queue.empty():
                    try:
                        self.frame_queue.get_nowait()
                    except:
                        pass
                
                # Encode immediately in thread
                _, buffer = cv2.imencode('.jpg', frame, self.encode_params)
                
                try:
                    self.frame_queue.put(buffer.tobytes(), block=False)
                except:
                    pass  # Drop frame if queue full
            time.sleep(0.01)  # Prevent CPU overload
    
    def get_frame(self):
        try:
            return self.frame_queue.get_nowait()
        except:
            return None
    
    def stop(self):
        self.running = False

camera = ThreadedCamera(0)
clients_video = []

async def send_camera_frames():
    while True:
        frame_bytes = camera.get_frame()
        if frame_bytes:
            dead_clients = []
            for ws in clients_video:
                try:
                    await ws.send_bytes(frame_bytes)  # Send raw bytes, not base64
                except:
                    dead_clients.append(ws)
            
            # Cleanup disconnected clients
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
            # Remove unnecessary keep-alive messages
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        if ws in clients_video:
            clients_video.remove(ws)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(send_camera_frames())

@app.on_event("shutdown")
async def shutdown_event():
    camera.stop()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, loop="uvloop")  # Use uvloop for better performance
