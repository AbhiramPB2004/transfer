import cv2
import asyncio
import base64
import pyaudio
import json
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
            await asyncio.sleep(0.01)
            continue

        _, buffer = cv2.imencode('.jpg', frame)
        frame_b64 = base64.b64encode(buffer).decode("utf-8")

        dead_clients = []
        for ws in clients_video:
            try:
                await ws.send_text(frame_b64)
            except Exception:
                dead_clients.append(ws)

        # remove disconnected clients
        for ws in dead_clients:
            if ws in clients_video:
                clients_video.remove(ws)

        await asyncio.sleep(0.03)  # ~30 FPS

@app.websocket("/ws/video")
async def ws_video(ws: WebSocket):
    await ws.accept()
    clients_video.append(ws)
    try:
        while True:
            await ws.receive_text()  # keep connection alive
    except WebSocketDisconnect:
        if ws in clients_video:
            clients_video.remove(ws)

# ----- AUDIO -----
clients_audio = []
CHUNK = 1024
RATE = 16000
FORMAT = pyaudio.paInt16
CHANNELS = 1
MIC_INDEX = 0  # 🎤 Your camera mic (Brio 100)

pa = pyaudio.PyAudio()
stream = pa.open(format=FORMAT, channels=CHANNELS,
                 rate=RATE, input=True,
                 input_device_index=MIC_INDEX,
                 frames_per_buffer=CHUNK)

async def send_audio_frames():
    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        b64_data = base64.b64encode(data).decode("utf-8")

        dead_clients = []
        for ws in clients_audio:
            try:
                await ws.send_text(b64_data)
            except Exception:
                dead_clients.append(ws)

        for ws in dead_clients:
            if ws in clients_audio:
                clients_audio.remove(ws)

        await asyncio.sleep(0.01)

@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    clients_audio.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in clients_audio:
            clients_audio.remove(ws)

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

            # TODO: integrate your servo driver (PCA9685, GPIO, etc.)
            print(f"🔧 Move servo {servo} → {angle}°")

            await ws.send_text(json.dumps({"status": "ok", "servo": servo, "angle": angle}))
    except WebSocketDisconnect:
        print("Control client disconnected")

# ----- START -----
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(send_camera_frames())
    asyncio.create_task(send_audio_frames())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
