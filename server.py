import cv2
import asyncio
import base64
import pyaudio
import json
import threading
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

# ----- CAMERA -----
cap = cv2.VideoCapture(0)
clients_video = []

async def send_camera_frames():
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        _, buffer = cv2.imencode('.jpg', frame)
        frame_b64 = base64.b64encode(buffer).decode("utf-8")
        for ws in clients_video:
            try:
                await ws.send_text(frame_b64)
            except Exception:
                pass
        await asyncio.sleep(0.03)  # ~30 FPS

@app.websocket("/ws/video")
async def ws_video(ws: WebSocket):
    await ws.accept()
    clients_video.append(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        clients_video.remove(ws)

# ----- AUDIO -----
clients_audio = []
CHUNK = 1024
RATE = 16000
FORMAT = pyaudio.paInt16
CHANNELS = 1

def audio_loop():
    pa = pyaudio.PyAudio()
    stream = pa.open(format=FORMAT, channels=CHANNELS,
                     rate=RATE, input=True, frames_per_buffer=CHUNK)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def send_audio():
        while True:
            data = stream.read(CHUNK)
            b64_data = base64.b64encode(data).decode("utf-8")
            for ws in clients_audio:
                try:
                    await ws.send_text(b64_data)
                except Exception:
                    pass
            await asyncio.sleep(0.01)

    loop.run_until_complete(send_audio())

@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    clients_audio.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        clients_audio.remove(ws)

threading.Thread(target=audio_loop, daemon=True).start()

# ----- SERVO CONTROL -----
@app.websocket("/ws/control")
async def ws_control(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            servo = data.get("servo")
            angle = data.get("angle")

            # TODO: integrate your servo driver (e.g., PCA9685, GPIO)
            print(f"🔧 Move servo {servo} → {angle}°")

            await ws.send_text(json.dumps({"status": "ok", "servo": servo, "angle": angle}))
    except WebSocketDisconnect:
        print("Control client disconnected")

# ----- START -----
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(send_camera_frames())
    uvicorn.run(app, host="0.0.0.0", port=8000)
