import time
import math
import random
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# URL de la API de Traccar (usa la demo en este caso)
TRACCAR_URL = "https://demo.traccar.org/api/positions"

# Credenciales de Traccar
TRACCAR_USERNAME = "combilabo@gmail.com"
TRACCAR_PASSWORD = "123456"

# Device ID en Traccar
device_id = 5700

# Definir puntos preestablecidos (ejemplo)
waypoints = [
    (48.853780, 2.344347),
    (48.855235, 2.345852),
    (48.857238, 2.347153),
    (48.858509, 2.342563),
    (48.856066, 2.340432),
    (48.854780, 2.342230)
]

# Configurar pasos entre los puntos
step = 0.001  # Puedes ajustar este valor para definir la distancia entre los puntos intermedios

# Generar puntos entre cada waypoint
def generate_interpolated_points(waypoints, step):
    points = []
    for i in range(0, len(waypoints)):
        (lat1, lon1) = waypoints[i]
        (lat2, lon2) = waypoints[(i + 1) % len(waypoints)]
        length = math.sqrt((lat2 - lat1) ** 2 + (lon2 - lon1) ** 2)
        count = int(math.ceil(length / step))
        for j in range(0, count):
            lat = lat1 + (lat2 - lat1) * j / count
            lon = lon1 + (lon2 - lon1) * j / count
            points.append((lat, lon))
    return points

# Función para calcular el rumbo (dirección)
def calculate_course(lat1, lon1, lat2, lon2):
    lat1 = lat1 * math.pi / 180
    lon1 = lon1 * math.pi / 180
    lat2 = lat2 * math.pi / 180
    lon2 = lon2 * math.pi / 180
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.atan2(y, x) % (2 * math.pi)) * 180 / math.pi

# Función para enviar coordenadas a Traccar
def send_to_traccar(device_id, lat, lon, course, speed, battery):
    try:
        # Autenticación básica
        response = requests.post(
            TRACCAR_URL,
            json={
                "deviceId": device_id,
                "latitude": lat,
                "longitude": lon,
                "altitude": 50,
                "bearing": course,
                "speed": speed,
                "batt": battery
            },
            auth=(TRACCAR_USERNAME, TRACCAR_PASSWORD)
        )
        response.raise_for_status()  # Verificar errores HTTP
        return response.json()
    except requests.RequestException as e:
        return {"error": str(e)}

# Endpoint para iniciar el envío de datos a Traccar
@app.route('/start_gps', methods=['GET'])
def start_sending_data():
    try:
        points = generate_interpolated_points(waypoints, step)
        index = 0
        total_points = len(points)

        while index < total_points:
            (lat1, lon1) = points[index % total_points]
            (lat2, lon2) = points[(index + 1) % total_points]
            course_angle = calculate_course(lat1, lon1, lat2, lon2)
            speed = random.uniform(20, 40)  # Velocidad simulada
            battery = random.randint(0, 100)  # Batería simulada

            print(f"Enviando coordenadas: lat={lat1}, lon={lon1}, course={course_angle}, speed={speed}, battery={battery}")
            response = send_to_traccar(device_id, lat1, lon1, course_angle, speed, battery)
            print(f"Respuesta de Traccar: {response}")

            time.sleep(10)  # Espera 10 segundos entre cada envío
            index += 1

        return jsonify({"message": "Datos enviados a Traccar"})
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
