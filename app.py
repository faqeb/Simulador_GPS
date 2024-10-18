from flask import Flask, request, jsonify
import math
import time
import random
import requests
from gevent import monkey
import gevent

# Realiza el parcheo para que las operaciones sean no bloqueantes
monkey.patch_all()

app = Flask(__name__)

server = 'http://demo.traccar.org:5055'
period = 1
device_speed = 40

user = "combilabo@gmail.com"
password = "123456"

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
def send(id, _time, lat, lon, altitude, course, speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId):
    params = {
        'id': id,
        'timestamp': _time,
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
        return jsonify({'error': 'Proporcionar un ID que tenga asociado una ruta'}), 400

    points = routes[id]
    index = 0
    max_points = len(points)

    while index < max_points:
        _time =  int(time.time())
        (lon1, lat1) = points[index]
        (lon2, lat2) = points[(index + 1) % max_points]  # Usar % para evitar índice fuera de rango
        altitude = 50
        speed = device_speed if (index % max_points) != 0 else 0
        
        # Fijar valores según lo solicitado
        alarm = False
        battery = 100  # Fijar batería al 100%
        ignition = False  # O fijar en None si prefieres
        accuracy = 100 if (index % 10) == 0 else 0

        rpm = None  # Puede eliminarse si no es necesario
        fuel = 80
        driverUniqueId = None  # ID único del conductor opcional

        try:
            send(id, _time, lat1, lon1, altitude, calculate_course(lat1, lon1, lat2, lon2), speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId)
        except Exception as e:
            print(f"Error sending data: {e}")
            return jsonify({'error': 'fallo al enviar información a Traccar.'}), 500

        gevent.sleep(period)
        index += 1

    return jsonify({'message': 'Simulación completada'}), 200

@app.route('/upload-trip', methods=['POST'])
def upload_trip():
    data = request.get_json()
    id = data.get('id')  # ID del vehículo
    time_str = data.get('time')  # Fecha en formato legible "YYYY-MM-DD HH:mm:ss"

    if not id or id not in routes:
        return jsonify({'error': 'Proporcionar un ID que tenga asociado una ruta'}), 400

  # Convertir el string de fecha a un objeto datetime y luego a UNIX timestamp
    try:
        start_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        time_unix = time.mktime(start_time.timetuple())  # Convertir a UNIX timestamp
    except ValueError:
        return jsonify({'error': 'Formato de fecha incorrecto. Usar "YYYY-MM-DD HH:mm:ss"'}), 400

    points = routes[id]
    index = 0
    max_points = len(points)

    while index < max_points:
        (lon1, lat1) = points[index]
        (lon2, lat2) = points[(index + 1) % max_points]  # Usar % para evitar índice fuera de rango
        altitude = 50
        speed = device_speed if (index % max_points) != 0 else 0

        # Calcular la distancia entre dos puntos (lat1, lon1) y (lat2, lon2)
        distance_km = calculate_distance(lat1, lon1, lat2, lon2)

        # Si el dispositivo está en movimiento, calcular el tiempo para el siguiente punto
        if speed > 0:
            time_to_next_point = distance_km / speed  # Tiempo en horas
            time_to_next_point_seconds = time_to_next_point * 3600  # Convertir a segundos
        else:
            time_to_next_point_seconds = 0  # Si no hay velocidad, no se incrementa el tiempo

        # Actualizar el tiempo simulado para el siguiente punto
        simulated_time = time_unix + time_to_next_point_seconds

        alarm = False
        battery = 100
        ignition = False
        accuracy = 100 if (index % 10) == 0 else 0
        rpm = None
        fuel = 80
        driverUniqueId = None

        try:
            # Enviar la información con el tiempo calculado
            send(id, simulated_time, lat1, lon1, altitude, calculate_course(lat1, lon1, lat2, lon2), speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId)
        except Exception as e:
            print(f"Error sending data: {e}")
            return jsonify({'error': 'Fallo al enviar información a Traccar.'}), 500

        gevent.sleep(period)
        index += 1

    return jsonify({'message': 'Simulación completada'}), 200

@app.route('/update-devices-location', methods=['POST'])
def update_devices_location():
    traccar_url = 'http://demo.traccar.org/api/devices'
    traccar_auth = (user, password)  # Sustituir con tus credenciales de Traccar

    # Hacer solicitud para obtener todos los dispositivos de Traccar
    try:
        response = requests.get(traccar_url, auth=traccar_auth)
        if response.status_code != 200:
            return jsonify({'error': 'No se pudieron obtener los dispositivos de Traccar'}), 500
        
        devices = response.json()
    except Exception as e:
        return jsonify({'error': f'Error al obtener dispositivos: {e}'}), 500

    # Última ubicación fija
    lat = -34.532911
    lon = -58.703249

    # Actualizar cada dispositivo con la nueva ubicación
    for device in devices:
        try:
            send(
                id=device['uniqueId'],
                _time=int(time.time()),
                lat=lat,
                lon=lon,
                altitude=50,            # Valor de altitud predeterminado
                course=0,               # Valor de curso predeterminado
                speed=0,                # Sin movimiento
                battery=100,            # Nivel de batería al 100%
                alarm=False,            # Sin alarma
                ignition=False,         # Ignición apagada
                accuracy=100,           # Precisión fija
                rpm=None,               # Sin RPM
                fuel=80,                # Combustible al 80%
                driverUniqueId=None     # Sin conductor asignado
            )
        except Exception as e:
            print(f"Error actualizando el dispositivo {device['id']}: {e}")
    
    return jsonify({'message': 'Ubicación actualizada para todos los dispositivos'}), 200

    from decimal import Decimal

# Endpoint to update device location via GET request
@app.route('/update-gps-location', methods=['GET'])
def update_location():
    # Obtener los parámetros de la URL
    lat = request.args.get('lat', type=str)
    lon = request.args.get('lon', type=str)
    id = request.args.get('id', type=str)

    # Validar los parámetros
    if not lat or not lon or not id:
        return jsonify({'error': 'Faltan parámetros lat, lon o id'}), 400
    _time =  int(time.time())
    # Valores fijos o de ejemplo para la actualización
    altitude = 50  # Altitud por defecto
    speed = 0      # Velocidad fija, ajustable según necesidad
    battery = 100  # Batería al 100%
    alarm = False
    ignition = False
    accuracy = 100
    rpm = None
    fuel = 80
    driverUniqueId = None  # ID único del conductor opcional

    try:
        # Llamada a la función send() para actualizar la ubicación en Traccar
        send(id, _time, lat, lon, altitude, 0, speed, battery, alarm, ignition, accuracy, rpm, fuel, driverUniqueId)
    except Exception as e:
        print(f"Error al enviar los datos a Traccar: {e}")
        return jsonify({'error': 'Fallo al enviar la ubicación a Traccar.'}), 500

    return jsonify({'message': f'Ubicación del dispositivo {id} actualizada a lat: {lat}, lon: {lon}'}), 200


if __name__ == '__main__':
    app.run(debug=True)
