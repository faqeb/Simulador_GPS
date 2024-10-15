from flask import Flask, request, jsonify
import math
import time
import random
import requests

app = Flask(__name__)

server = 'http://demo.traccar.org:5055'
period = 1
device_speed = 40

# Global storage for routes generated by user ids
routes = {}

# Function to generate points using OSRM (Open Source Routing Machine)
def obtener_ruta_osrm(start, end):
    url = f"http://router.project-osrm.org/route/v1/driving/{start[1]},{start[0]};{end[1]},{end[0]}?overview=full&geometries=geojson"
    
    response = requests.get(url)
    
    if response.status_code == 200:
        ruta = response.json()
        # Devuelve la geometría (puntos de la ruta) en formato GeoJSON
        return ruta['routes'][0]['geometry']['coordinates']
    else:
        return None

# Send data to Traccar server
def send(id, lat, lon, altitude, course, speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId):
    params = {
        'id': id,
        'timestamp': int(time.time()),
        'lat': lat,
        'lon': lon,
        'altitude': altitude,
        'bearing': course,
        'speed': speed,
        'batt': battery,
        'alarm': 'sos' if alarm else None,
        'ignition': 'true' if ignition else 'false',
        'accuracy': accuracy if accuracy else None,
        'rpm': rpm if rpm else None,
        'fuel': fuel if fuel else None,
        'driverUniqueId': driverUniqueId if driverUniqueId else None
    }
    # Filtrar parámetros vacíos
    params = {k: v for k, v in params.items() if v is not None}
    requests.get(server, params=params)

# Calculate course between two points
def calculate_course(lat1, lon1, lat2, lon2):
    lat1 = lat1 * math.pi / 180
    lon1 = lon1 * math.pi / 180
    lat2 = lat2 * math.pi / 180
    lon2 = lon2 * math.pi / 180
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.atan2(y, x) % (2 * math.pi)) * 180 / math.pi

# Endpoint to generate a route between two points using OSRM
@app.route('/generate-route', methods=['POST'])
def generate_route():
    data = request.get_json()
    start = data.get('start')  # Coordenadas de inicio (lat, lon)
    end = data.get('end')      # Coordenadas de destino (lat, lon)
    id = data.get('id')        # ID del vehículo

    if not start or not end or not id:
        return jsonify({'error': 'Se necesita start, end, y id'}), 400

    # Obtener la ruta usando OSRM
    points = obtener_ruta_osrm(start, end)

    if points is None:
        return jsonify({'error': 'Fallo al generar la ruta con OSRM'}), 500

    # Almacenar la ruta para este ID
    routes[id] = points

    return jsonify({'route': points})

# Endpoint to start the simulation
@app.route('/start-simulation', methods=['POST'])
def start_simulation():
    data = request.get_json()
    id = data.get('id')  # The ID of the vehicle

    if not id or id not in routes:
        return jsonify({'error': 'Please provide a valid ID with a generated route'}), 400

    points = routes[id]
    index = 0
    max_points = len(points)

    while index < max_points:
        (lat1, lon1) = points[index]
        (lat2, lon2) = points[(index + 1) % max_points]  # Usar % para evitar índice fuera de rango
        altitude = 50
        speed = device_speed if (index % max_points) != 0 else 0
        
        # Fijar valores según lo solicitado
        alarm = False
        battery = 100  # Fijar batería al 100%
        ignition = None  # O fijar en False si prefieres
        accuracy = 100 if (index % 10) == 0 else 0

        rpm = None
        fuel = 80
        driverUniqueId = None  # Optional driver unique ID

        try:
            send(id, lat1, lon1, altitude, calculate_course(lat1, lon1, lat2, lon2), speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId)
        except Exception as e:
            print(f"Error sending data: {e}")
            break  # Salir del bucle si hay un error

        time.sleep(period)
        index += 1

    return "Simulacion completada"


if __name__ == '__main__':
    app.run(debug=True)
