from flask import Flask, Response
import cv2
import threading

app = Flask(__name__)

class WebcamStreamer:
    def __init__(self, camera_id=0):
        self.camera = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)  # CAP_DSHOW reduces latency on Windows

        # Optimize camera settings
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.camera.set(cv2.CAP_PROP_FPS, 30)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))

        if not self.camera.isOpened():
            raise Exception("Could not open webcam")

        self.latest_frame = None
        self.lock = threading.Lock()
        self.running = True

        # Start background thread
        self.thread = threading.Thread(target=self.update_frame, daemon=True)
        self.thread.start()
        print("✅ Webcam initialized & background capture started")

    def update_frame(self):
        """Continuously capture frames in the background"""
        while self.running:
            success, frame = self.camera.read()
            if not success:
                continue

            # Encode once and store latest JPEG
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            with self.lock:
                self.latest_frame = buffer.tobytes()

    def generate_frames(self):
        """Yield the latest frame"""
        while True:
            if self.latest_frame is None:
                continue
            with self.lock:
                frame = self.latest_frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    def release(self):
        self.running = False
        self.thread.join()
        self.camera.release()

# Global webcam instance
webcam = WebcamStreamer()

@app.route('/')
def index():
    return """
    <html><body style="text-align:center;">
        <h1>🚀 Ultra-Fast Flask Webcam Stream</h1>
        <img src="/video_feed" width="80%">
    </body></html>
    """

@app.route('/video_feed')
def video_feed():
    return Response(
        webcam.generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

if __name__ == '__main__':
    print("🚀 Starting Flask Webcam Stream")
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        webcam.release()
        print("📹 Camera released")
