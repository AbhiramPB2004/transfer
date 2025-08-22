import cv2
import pyaudio
import threading
import queue
import base64
from flask import Flask, Response, render_template_string
import json

app = Flask(__name__)

# Video setup - optimized for speed
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
camera.set(cv2.CAP_PROP_FPS, 30)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# Audio setup
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024

audio = pyaudio.PyAudio()
audio_queue = queue.Queue(maxsize=10)

def audio_recorder():
    """Continuous audio recording"""
    stream = audio.open(format=FORMAT,
                       channels=CHANNELS,
                       rate=RATE,
                       input=True,
                       frames_per_buffer=CHUNK)
    
    while True:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if audio_queue.full():
                try:
                    audio_queue.get_nowait()  # Remove old data
                except queue.Empty:
                    pass
            audio_queue.put(data)
        except Exception as e:
            print(f"Audio error: {e}")

def generate_video():
    """Generate video frames"""
    while True:
        success, frame = camera.read()
        if not success:
            break
        
        # Optimize for speed
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_data = buffer.tobytes()
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')

def generate_audio():
    """Generate raw audio stream"""
    while True:
        try:
            data = audio_queue.get(timeout=1)
            yield data
        except queue.Empty:
            yield b'\x00' * CHUNK * 2  # Silent audio if no data

@app.route('/')
def index():
    """Simple viewer page"""
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Simple Stream</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        img { border: 2px solid #333; margin: 10px; }
        .info { background: #f0f0f0; padding: 10px; margin: 10px; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📡 Simple Audio/Video Stream</h1>
        
        <div class="info">
            <strong>Video:</strong> {{ request.host }}/video<br>
            <strong>Audio:</strong> {{ request.host }}/audio<br>
            <strong>Raw Data:</strong> {{ request.host }}/data
        </div>
        
        <h2>Live Video</h2>
        <img src="/video" width="640" height="480" id="video">
        
        <h2>Direct Stream URLs</h2>
        <p><a href="/video" target="_blank">Video Stream</a></p>
        <p><a href="/audio" target="_blank">Audio Stream</a></p>
        <p><a href="/data" target="_blank">JSON Data Stream</a></p>
        
        <script>
            // Auto-refresh video if it stops
            document.getElementById('video').onerror = function() {
                setTimeout(() => {
                    this.src = '/video?' + new Date().getTime();
                }, 1000);
            };
        </script>
    </div>
</body>
</html>
    ''')

@app.route('/video')
def video_feed():
    """Raw video stream - use this URL in your laptop code"""
    return Response(generate_video(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/audio')
def audio_feed():
    """Raw audio stream - use this URL in your laptop code"""
    def audio_with_header():
        # Simple WAV header
        yield b'RIFF'
        yield (2000000000).to_bytes(4, 'little')  # File size
        yield b'WAVE'
        yield b'fmt '
        yield (16).to_bytes(4, 'little')  # Format chunk size
        yield (1).to_bytes(2, 'little')   # PCM format
        yield (CHANNELS).to_bytes(2, 'little')
        yield (RATE).to_bytes(4, 'little')
        yield (RATE * CHANNELS * 2).to_bytes(4, 'little')  # Byte rate
        yield (CHANNELS * 2).to_bytes(2, 'little')  # Block align
        yield (16).to_bytes(2, 'little')  # Bits per sample
        yield b'data'
        yield (2000000000).to_bytes(4, 'little')  # Data size
        
        # Stream audio data
        for chunk in generate_audio():
            yield chunk
    
    return Response(audio_with_header(), mimetype='audio/wav')

@app.route('/data')
def data_feed():
    """JSON data stream with both audio and video as base64"""
    def generate_data():
        frame_count = 0
        while True:
            # Get video frame
            success, frame = camera.read()
            video_data = ""
            if success:
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                video_data = base64.b64encode(buffer).decode('utf-8')
            
            # Get audio chunk
            audio_data = ""
            try:
                audio_chunk = audio_queue.get_nowait()
                audio_data = base64.b64encode(audio_chunk).decode('utf-8')
            except queue.Empty:
                pass
            
            # Create JSON response
            data = {
                'timestamp': frame_count,
                'video': video_data,
                'audio': audio_data,
                'audio_rate': RATE,
                'audio_channels': CHANNELS,
                'video_size': [640, 480]
            }
            
            yield f"data: {json.dumps(data)}\n\n"
            frame_count += 1

    return Response(generate_data(), mimetype='text/plain')

if __name__ == "__main__":
    # Start audio recording thread
    audio_thread = threading.Thread(target=audio_recorder, daemon=True)
    audio_thread.start()
    
    print("🚀 Simple Stream Server Started")
    print(f"📺 Video URL: http://0.0.0.0:5000/video")
    print(f"🔊 Audio URL: http://0.0.0.0:5000/audio") 
    print(f"📊 Data URL: http://0.0.0.0:5000/data")
    print(f"🌐 Web View: http://0.0.0.0:5000/")
    
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
