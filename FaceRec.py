from flask import Flask, request, jsonify
from adafruit_servokit import ServoKit

app = Flask(__name__)
kit = ServoKit(channels=16)

# Initialize to center positions
kit.servo[2].angle = 90
kit.servo[3].angle = 90
kit.servo[4].angle = 90

@app.route('/move_servo', methods=['POST'])
def move_servo():
    try:
        data = request.get_json()
        angles = data.get('angles', {})
        
        for channel_str, angle in angles.items():
            channel = int(channel_str)
            if 0 <= channel <= 15 and 0 <= angle <= 180:
                kit.servo[channel].angle = angle
                print(f"Moved channel {channel} to {angle}°")
        
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"? Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
