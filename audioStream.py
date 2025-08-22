import cv2
import pyaudio
import threading
import queue
import time
from flask import Flask, Response, render_template_string

app = Flask(__name__)

# Video setup - optimized
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 320)  # Lower resolution for speed
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
camera.set(cv2.CAP_PROP_FPS, 30)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimal buffering

# Audio setup - OPTIMIZED FOR LOW LATENCY
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 22050  # Lower sample rate = less latency
CHUNK = 256   # MUCH smaller chunks = lower latency
BUFFER_SIZE = 2  # Very small buffer

audio = pyaudio.PyAudio()
audio_queue = queue.Queue(maxsize=BUFFER_SIZE)

def audio_recorder():
    """Ultra-low latency audio capture"""
    stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        input_device_index=None  # Use default device
    )
    
    while True:
        try:
            # Read smaller chunks more frequently
            data = stream.read(CHUNK, exception_on_overflow=False)
            
            # Drop old data immediately if queue is full
            while audio_queue.full():
                try:
                    audio_queue.get_nowait()
                except queue.Empty:
                    break
            
            audio_queue.put(data)
            
        except Exception as e:
            print(f"Audio error: {e}")
            time.sleep(0.001)

def generate_video():
    """Fast video generation"""
    while True:
        success, frame = camera.read()
        if not success:
            continue
        
        # Fast encoding
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 70]
        _, buffer = cv2.imencode('.jpg', frame, encode_params)
        
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

def generate_audio():
    """Ultra-low latency audio generation"""
    # Minimal WAV header for streaming
    def minimal_wav_header():
        yield b'RIFF'
        yield (2000000000).to_bytes(4, 'little')
        yield b'WAVE'
        yield b'fmt '
        yield (16).to_bytes(4, 'little')
        yield (1).to_bytes(2, 'little')  # PCM
        yield (CHANNELS).to_bytes(2, 'little')
        yield (RATE).to_bytes(4, 'little')
        yield (RATE * CHANNELS * 2).to_bytes(4, 'little')
        yield (CHANNELS * 2).to_bytes(2, 'little')
        yield (16).to_bytes(2, 'little')
        yield b'data'
        yield (2000000000).to_bytes(4, 'little')
    
    # Send header
    for chunk in minimal_wav_header():
        yield chunk
    
    # Stream audio with minimal delay
    while True:
        try:
            data = audio_queue.get(timeout=0.01)  # Very short timeout
            yield data
        except queue.Empty:
            # Send silence to keep stream alive
            yield b'\x00' * (CHUNK * 2)

@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Low-Latency Stream</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin: 20px; background: #222; color: #fff; }
        .container { max-width: 600px; margin: 0 auto; }
        img { border: 2px solid #fff; }
        .info { background: #333; padding: 15px; margin: 10px; border-radius: 8px; }
        .latency { color: #0f0; font-size: 18px; font-weight: bold; }
        audio { width: 100%; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>⚡ Ultra-Low Latency Stream</h1>
        
        <div class="info">
            <div class="latency">🎯 Optimized for Speed</div>
            <p>📹 Video: 320x240 @ 30fps</p>
            <p>🔊 Audio: 22kHz, 256-sample chunks</p>
            <p>⚡ Buffer: 2-frame maximum</p>
        </div>
        
        <div>
            <h2>Live Video</h2>
            <img src="/video" width="320" height="240" id="videoStream">
        </div>
        
        <div>
            <h2>Live Audio</h2>
            <audio controls autoplay>
                <source src="/audio" type="audio/wav">
            </audio>
        </div>
        
        <div class="info">
            <p><strong>Video URL:</strong> {{ request.host }}/video</p>
            <p><strong>Audio URL:</strong> {{ request.host }}/audio</p>
        </div>
    </div>
    
    <script>
        // Auto-refresh video on error
        document.getElementById('videoStream').onerror = function() {
            setTimeout(() => {
                this.src = '/video?' + Date.now();
            }, 100);  // Very fast retry
        };
    </script>
</body>
</html>
    ''')

@app.route('/video')
def video_feed():
    return Response(generate_video(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/audio')
def audio_feed():
    return Response(generate_audio(),
                    mimetype='audio/wav',
                    headers={
                        'Cache-Control': 'no-cache, no-store, must-revalidate',
                        'Pragma': 'no-cache',
                        'Expires': '0'
                    })

if __name__ == "__main__":
    print("⚡ Ultra-Low Latency Server Starting...")
    print(f"🎯 Audio latency: ~{(CHUNK/RATE)*1000:.1f}ms")
    print(f"📊 Buffer size: {BUFFER_SIZE} chunks")
    print(f"🔊 Sample rate: {RATE}Hz")
    print(f"🌐 Server: http://0.0.0.0:5000")
    
    # Start audio thread
    audio_thread = threading.Thread(target=audio_recorder, daemon=True)
    audio_thread.start()
    
    # Run with minimal threading overhead
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True, processes=1)
