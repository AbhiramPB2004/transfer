from flask import Flask, Response
import cv2
import time

app = Flask(__name__)

class WebcamStreamer:
    def __init__(self, camera_id=0):
        self.camera = cv2.VideoCapture(camera_id)
        
        # Optimize camera settings for speed
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
        
        if not self.camera.isOpened():
            raise Exception("Could not open webcam")
        
        print("✅ Webcam initialized successfully")
    
    def generate_frames(self):
        """Generate video frames for streaming"""
        while True:
            success, frame = self.camera.read()
            if not success:
                break
            
            # Encode frame as JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frame_bytes = buffer.tobytes()
            
            # Yield frame in multipart format
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    def release(self):
        self.camera.release()

# Global webcam instance
webcam = WebcamStreamer()

@app.route('/')
def index():
    """Home page with video stream"""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🚀 Simple Flask Webcam Stream</title>
        <style>
            body { 
                font-family: Arial, sans-serif; 
                text-align: center; 
                margin: 50px; 
                background: #f0f0f0;
            }
            .container { 
                max-width: 800px; 
                margin: 0 auto; 
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            img { 
                border: 3px solid #333; 
                border-radius: 10px; 
                max-width: 100%; 
                height: auto;
            }
            .info { 
                background: #e8f5e8; 
                padding: 15px; 
                margin: 20px 0; 
                border-radius: 5px; 
                border-left: 5px solid #4CAF50;
            }
            h1 { color: #333; }
            .url { 
                background: #f8f8f8; 
                padding: 10px; 
                border-radius: 5px; 
                font-family: monospace; 
                margin: 10px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Simple Flask Webcam Stream</h1>
            
            <div class="info">
                <p><strong>✅ Status:</strong> Live Stream Active</p>
                <p><strong>📡 Stream URL:</strong> <span class="url">/video_feed</span></p>
                <p><strong>🔗 OpenCV Compatible:</strong> Yes!</p>
            </div>
            
            <h2>📹 Live Webcam Feed</h2>
            <img src="/video_feed" alt="Live Webcam Feed">
            
            <div class="info">
                <h3>For OpenCV Access:</h3>
                <div class="url">cv2.VideoCapture('http://192.168.137.96:5000/video_feed')</div>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(
        webcam.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/status')
def status():
    """Status endpoint"""
    return {
        "status": "active",
        "camera": "working" if webcam.camera.isOpened() else "error",
        "endpoints": {
            "home": "/",
            "stream": "/video_feed", 
            "status": "/status"
        }
    }

if __name__ == '__main__':
    print("🚀 Starting Simple Flask Webcam Server")
    print("📱 Access at: http://192.168.137.96:5000")
    print("🎥 Stream URL: http://192.168.137.96:5000/video_feed")
    print("⚡ Fast and OpenCV compatible!")
    
    try:
        app.run(
            host='0.0.0.0',    # Listen on all interfaces
            port=5000,         # Port 5000
            debug=False,       # Disable debug for performance
            threaded=True      # Enable threading for better performance
        )
    except KeyboardInterrupt:
        print("\n👋 Shutting down server...")
    finally:
        webcam.release()
        print("📹 Camera released")
