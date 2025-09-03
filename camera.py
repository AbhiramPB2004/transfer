import cv2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import time
import os

app = FastAPI(title="FastAPI Webcam Streaming")

# Create templates directory if it doesn't exist
os.makedirs("templates", exist_ok=True)

# Initialize templates
templates = Jinja2Templates(directory="templates")

class WebcamStreamer:
    def __init__(self, camera_id=0):
        self.camera = None
        self.camera_id = camera_id
        self.initialize_camera()
    
    def initialize_camera(self):
        """Initialize webcam with optimal settings"""
        try:
            self.camera = cv2.VideoCapture(self.camera_id)
            
            # Optimize camera settings for streaming
            self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.camera.set(cv2.CAP_PROP_FPS, 30)
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            
            if not self.camera.isOpened():
                raise Exception("Could not open webcam")
                
            print(f"✅ Webcam initialized: {self.camera_id}")
            
        except Exception as e:
            print(f"❌ Camera initialization error: {e}")
            self.camera = None
    
    def get_frame(self):
        """Get single frame from webcam"""
        if self.camera is None or not self.camera.isOpened():
            return None
            
        success, frame = self.camera.read()
        if success:
            return frame
        return None
    
    def generate_frames(self):
        """Generate frames for streaming"""
        while True:
            frame = self.get_frame()
            if frame is None:
                print("❌ Failed to get frame")
                time.sleep(0.1)
                continue
            
            # Encode frame to JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not ret:
                continue
                
            frame_bytes = buffer.tobytes()
            
            # Yield frame in multipart format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
            # Small delay to control frame rate
            time.sleep(0.033)  # ~30 FPS
    
    def release(self):
        """Release camera resources"""
        if self.camera:
            self.camera.release()
            print("📹 Camera released")

# Global webcam instance
webcam = WebcamStreamer()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main page"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>FastAPI Webcam Stream</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; margin: 50px; }
            .container { max-width: 800px; margin: 0 auto; }
            img { border: 3px solid #333; border-radius: 10px; max-width: 100%; }
            .info { background: #f0f0f0; padding: 20px; margin: 20px 0; border-radius: 5px; }
            .controls { margin: 20px 0; }
            button { padding: 10px 20px; margin: 5px; font-size: 16px; cursor: pointer; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 FastAPI Webcam Streaming</h1>
            <div class="info">
                <p><strong>Stream URL:</strong> <code>/video_feed</code></p>
                <p><strong>OpenCV Compatible:</strong> ✅</p>
                <p><strong>Status:</strong> <span style="color: green;">Live Stream Active</span></p>
            </div>
            
            <h2>📹 Live Webcam Feed</h2>
            <img src="/video_feed" alt="Webcam Feed">
            
            <div class="controls">
                <button onclick="location.reload()">🔄 Refresh</button>
                <button onclick="window.open('/video_feed', '_blank')">🎥 Open Stream Only</button>
            </div>
            
            <div class="info">
                <h3>For OpenCV Access:</h3>
                <code>cv2.VideoCapture('http://YOUR_SERVER_IP:8000/video_feed')</code>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get('/video_feed')
def video_feed():
    """Video streaming endpoint"""
    return StreamingResponse(
        webcam.generate_frames(), 
        media_type='multipart/x-mixed-replace; boundary=frame'
    )

@app.get('/snapshot')
def get_snapshot():
    """Get single frame as JPEG"""
    frame = webcam.get_frame()
    if frame is None:
        return {"error": "Could not capture frame"}
    
    ret, buffer = cv2.imencode('.jpg', frame)
    if ret:
        return StreamingResponse(
            iter([buffer.tobytes()]), 
            media_type="image/jpeg"
        )
    return {"error": "Could not encode frame"}

@app.get('/status')
def get_status():
    """Get camera status"""
    return {
        "camera_active": webcam.camera is not None and webcam.camera.isOpened(),
        "camera_id": webcam.camera_id,
        "endpoints": {
            "stream": "/video_feed",
            "snapshot": "/snapshot",
            "status": "/status"
        }
    }

@app.on_event("shutdown")
def shutdown_event():
    """Clean up on shutdown"""
    webcam.release()

if __name__ == '__main__':
    print("🚀 Starting FastAPI Webcam Streaming Server")
    print("📱 Access at: http://localhost:8000")
    print("🎥 Stream URL: http://localhost:8000/video_feed")
    print("📷 Snapshot URL: http://localhost:8000/snapshot")
    print("⚡ OpenCV Compatible streaming ready!")
    
    uvicorn.run(
        app, 
        host='0.0.0.0',  # Listen on all interfaces 
        port=8000, 
        reload=False
    )
