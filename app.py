import time
import random
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# URL de la API de Traccar (usa la demo en este caso)
TRACCAR_URL = "https://demo.traccar.org/api/positions"

# Credenciales de Traccar
TRACCAR_USERNAME = "combilabo@gmail.com"
TRACCAR_PASSWORD = "123456"

# Función para generar coordenadas GPS aleatorias (simuladas)
def generate_fake_gps_data():
    latitude = random.uniform(-90, 90)  # Rango de latitudes válidas
    longitude = random.uniform(-180, 180)  # Rango de longitudes válidas
    return {
        "latitude": latitude,
        "longitude": longitude
    }

# Función para enviar coordenadas a Traccar
def send_to_traccar(device_id, data):
    try:
        # Autenticación básica
        response = requests.post(
            TRACCAR_URL,
            json={
                "deviceId": device_id,
                "latitude": data["latitude"],
                "longitude": data["longitude"]
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
    device_id = 5700  # ID del dispositivo en Traccar

    for _ in range(10):  # Simular 10 posiciones (cambiar según necesidad)
        gps_data = generate_fake_gps_data()
        print(f"Generando coordenadas: {gps_data}")
        response = send_to_traccar(device_id, gps_data)
        print(f"Respuesta de Traccar: {response}")
        time.sleep(10)  # Espera 10 segundos entre cada envío

    return jsonify({"message": "Datos enviados a Traccar"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
