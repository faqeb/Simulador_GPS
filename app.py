from flask import Flask, request, jsonify
import math
import time
import datetime
import random
import requests
from gevent import monkey
import gevent
from decimal import Decimal
import urllib
import http.client as httplib
import pyodbc
from requests.auth import HTTPBasicAuth

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
# Configuración de la conexión a la base de datos
app.config['ConnectionStrings'] = {
    "DNS": "DRIVER={ODBC Driver 17 for SQL Server};SERVER=stockControllerDB.mssql.somee.com;DATABASE=stockControllerDB;UID=gastonsanchez_SQLLogin_1;PWD=f27j5danim;TrustServerCertificate=yes;"
}

def get_db_connection():
    conn = pyodbc.connect(app.config['ConnectionStrings']['DNS'])
    return conn
#Endpoint principal para simular un viaje cargado nuestro proyecto, simula los tramos que realizaria una persona segun los estados del viaje, 
#por ejemplo de  predio a inicio hasta que cambie a un estado que requiera un tramo diferente
@app.route('/simulate-viaje/<int:viaje_id>', methods=['GET'])
def simulate_viaje(viaje_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Consulta actualizada
        query = """
        SELECT v.*, ve.Patente, ve.DeviceId, v.LatitudPredio, v.LongitudPredio
        FROM Viajes v
        JOIN Vehiculos ve ON v.VehiculoId = ve.VehiculoId
        WHERE v.ViajeId = ? ;
        """
        
        cursor.execute(query, (viaje_id,))
        viaje_info = cursor.fetchone()
        
        if viaje_info:
            estado_viaje = viaje_info.EstadoViaje
            
            # Inicializa las coordenadas de inicio y fin
            start = end = None

            # Obtener la ubicación actual del vehículo usando el nuevo endpoint
            device_id = int(viaje_info.DeviceId)
            url = f'https://simulador-gps.onrender.com/ubicacion-vehiculo/{device_id}'  
            start_response = requests.get(url)
            start_data = start_response.json()

            # Verifica si hubo un error al obtener la ubicación
            if 'error' in start_data:
                return jsonify({'error': start_data['error']}), 400
            
            # Asigna las coordenadas a start como una lista
            start = [float(start_data['latitud']), float(start_data['longitud'])]

            # Define el punto final según el estado del viaje
            if estado_viaje == "En camino al punto de partida":
                end = [float(viaje_info.LatitudPuntoDePartida), float(viaje_info.LongitudPuntoDePartida)]
                
            elif estado_viaje == "Comienzo del viaje":
                end = [float(viaje_info.LatitudPuntoDeLlegada), float(viaje_info.LongitudPuntoDeLlegada)]
                
            elif "vuelta al predio" in estado_viaje or "Regreso al predio" in estado_viaje:
                end = [float(viaje_info.LatitudPredio), float(viaje_info.LongitudPredio)]
                
            elif estado_viaje == "Finalizado":
                return jsonify({'error': 'Este viaje ya se ha finalizado.'}), 400
                
            elif "En espera asistencia" in estado_viaje:
                return jsonify({'error': 'Este viaje está suspendido.'}), 400

            # Llamar al endpoint de generate_route
            data = {
                'start': start,
                'end': end,
                'id': viaje_info.Patente
            }
            
            response = requests.post('https://simulador-gps.onrender.com/generate-route', json=data)
            
            if response.status_code != 200:
                return jsonify({'error': 'Error al generar la ruta', 'details': response.json()}), response.status_code

            # Preparar datos para iniciar la simulación
            data2 = {
                'id': viaje_info.Patente
            }
            
            # Llamar al endpoint de start-simulation
            response2 = requests.post('https://simulador-gps.onrender.com/start-simulation', json=data2)
            
            if response2.status_code != 200:
                return jsonify({'error': 'Error al iniciar la simulación', 'details': response2.json()}), response2.status_code

            return jsonify({'message': 'Simulación iniciada exitosamente', 'data': data}), 200
        else:
            return jsonify({'error': 'Viaje no encontrado'}), 404

    finally:
        cursor.close()
        conn.close()


#Obtenemos la ultima ubicacion conocida del vehiculo, para disminuir errores y dar versatilidad simulate_viaje
@app.route('/ubicacion-vehiculo/<int:device_id>', methods=['GET'])
def obtener_ubicacion_actual_vehiculo(device_id):
    # Inicializa coordenadas como un diccionario
    coordenadas = {'latitud': None, 'longitud': None}

    try:
        url = f"https://demo.traccar.org/api/positions?deviceId={device_id}"
        
        # Realiza la solicitud GET con autenticación básica
        response = requests.get(url, auth=HTTPBasicAuth(user, password))

        if response.status_code == 200:
            posiciones = response.json()
            
            for posicion in posiciones:
                if posicion['deviceId'] == device_id:
                    coordenadas['latitud'] = posicion['latitude']
                    coordenadas['longitud'] = posicion['longitude']
                    break
        else:
            return jsonify({'error': f"Error al obtener datos de Traccar: {response.status_code}"}), response.status_code
    
    except Exception as ex:
        return jsonify({'error': f"Excepción: {ex}"}), 500

    return jsonify(coordenadas)

#Actualiza la ultima ubicacion del vehiculo de la patente dada a la ubicacion del predio del cliente
@app.route('/ubicar_vehiculo_en_predio', methods=['GET'])
def ubicar_vehiculo_en_predio():
    # Obtener el parámetro 'patente' desde los argumentos de la URL
    patente = request.args.get('patente', type=str)
    if not patente:
        return jsonify({'error': 'Se requiere el parámetro patente'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Consulta para obtener las coordenadas del taller
        query = """
        SELECT p.LongitudTaller, p.LatitudTaller
        FROM Properties p
        JOIN Vehiculos ve ON p.ClienteId = ve.ClienteId
        WHERE ve.Patente = ?
        AND p.LongitudTaller IS NOT NULL;
        """
        cursor.execute(query, (patente,))
        ubicacion_taller = cursor.fetchone()
        
        if ubicacion_taller:
            lat = ubicacion_taller[1]  # Latitud en el índice 1
            lon = ubicacion_taller[0]  # Longitud en el índice 0

            # Construir la URL para el simulador GPS
            url = f'https://simulador-gps.onrender.com/update-gps-location?lat={lat}&lon={lon}&id={patente}'

            # Realizar la solicitud GET
            response = requests.get(url)

            # Manejar la respuesta del simulador
            if response.status_code != 200:
                try:
                    error_details = response.json()
                except ValueError:
                    error_details = {'message': 'Error del servidor'}
                return jsonify({'error': 'Error al actualizar la ubicacion', 'details': error_details}), response.status_code

            return jsonify({
                'message': 'Ubicacion actualizada correctamente',
                'data': {'lat': lat, 'lon': lon}
            }), 200
        else:
            return jsonify({'error': 'Patente o ubicacion del predio no registrada'}), 404

    except Exception as e:
        return jsonify({'error': 'Error interno del servidor', 'details': str(e)}), 500

    finally:
        cursor.close()
        conn.close()


# Funcion para generar ruta con OSRM (Open Source Routing Machine)
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

# calcular direccionamiento
def calculate_course(lat1, lon1, lat2, lon2):
    lat1 = lat1 * math.pi / 180
    lon1 = lon1 * math.pi / 180
    lat2 = lat2 * math.pi / 180
    lon2 = lon2 * math.pi / 180
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.atan2(y, x) % (2 * math.pi)) * 180 / math.pi

# Endpoint para generar ruta a partir de dos pares de coordenadas, y con patente para asociarlo a un vehiculo OSRM
@app.route('/generate-route', methods=['POST'])
def generate_route():
    data = request.get_json()
    start = data.get('start')  # Coordenadas de inicio (lat, lon)
    end = data.get('end')      # Coordenadas de destino (lat, lon)
    id = data.get('id')        # ID del vehículo/patente

    missing_data = []
    if not start:
        missing_data.append('start (coordenadas de inicio)')
    if not end:
        missing_data.append('end (coordenadas de destino)')
    if not id:
        missing_data.append('id (ID del vehículo)')

    if missing_data:
        return jsonify({'error': f'Faltan los siguientes datos: {", ".join(missing_data)}'}), 400

    # Obtener la ruta usando OSRM
    points = obtener_ruta_osrm(start, end)

    if points is None:
        return jsonify({'error': 'Fallo al generar la ruta con OSRM'}), 500

    # Almacenar la ruta para este ID
    routes[id] = points

    return jsonify({'route': points})

# Endpoint para empezar simulación de una ruta ya generada
@app.route('/start-simulation', methods=['POST'])
def start_simulation():
    data = request.get_json()
    id = data.get('id')  # patente del vehiculo

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

def calculate_distance(lat1, lon1, lat2, lon2):
    # Fórmula de Haversine para calcular la distancia entre dos puntos
    R = 6371.0  # Radio de la Tierra en km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * 
         math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

#cargar puntos en el historial de traccar, sirvió para testear la visual viajes en fechas pasadas sin la necesidad de esperar
def send_trip(id, timestamp, lat, lon, speed):
    params = {
        'id': id,
        'timestamp': int(timestamp),
        'lat': lat,
        'lon': lon,
        'speed': speed
    }

    # Hacer la solicitud POST con autenticación
    requests.get(server,  params=params)

#realiza los envíos de todos los puntos de un ruta generada, con la misma función obtener_ruta_osrm, en la fecha introducida, también debe pasar la patente
@app.route('/upload-trip', methods=['GET'])
def upload_trip():
    id = request.args.get('id', type=str)
    time_str = request.args.get('start_time', type=str)  # Fecha en formato legible "YYYY-MM-DD HH:mm:ss"

    if not id or id not in routes:
        return jsonify({'error': 'Proporcionar un ID que tenga asociado una ruta'}), 400

    # Convertir el string de fecha a un objeto datetime y luego a UNIX timestamp
    try:
        time_unix = time.mktime(datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").timetuple())
    except ValueError:
        return jsonify({'error': 'Formato de fecha incorrecto. Usar "YYYY-MM-DD HH:mm:ss"'}), 400

    points = routes[id]
    index = 0
    max_points = len(points)

    while index < max_points:
        (lon, lat) = points[index]
        speed = device_speed if index != 0 else 0  # Velocidad 0 para el primer punto

        # Calcular la distancia entre dos puntos (lat1, lon1) y (lat2, lon2) 
        if index < max_points - 1:
            (lon2, lat2) = points[index + 1]
            distance_km = calculate_distance(lat, lon, lat2, lon2)
            time_to_next_point = distance_km / speed if speed > 0 else 0  # Tiempo en horas
            time_to_next_point_seconds = time_to_next_point * 3600  # Convertir a segundos
        else:
            time_to_next_point_seconds = 0  # Último punto

        # Enviar el punto al servidor
        send_trip(id, time_unix, lat, lon, speed)

        # Actualizar el tiempo para el siguiente punto
        time_unix += time_to_next_point_seconds
        index += 1

    return jsonify({"status": "success", "message": "Ruta subida exitosamente"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

#actualiza la ubicacion actual de todos los dispositivos registrardos en nuestro traccar a una ubicacion estipulada en la funcion, sirvio para que todos los dispositvos tuvieran una ubicacion registrada
@app.route('/update-devices-location', methods=['POST'])
def update_devices_location():
    traccar_url = 'http://demo.traccar.org/api/devices'
    traccar_auth = (user, password) 

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

# Endpoint para actulizar la ubicacion de un dispositivo, segun la patente y las coordenadas lat y lon
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

#genera una ruta y la carga para todos los dispositivos segun la fecha introducida
@app.route('/upload-and-generate', methods=['POST'])
def upload_and_generate():
    start = request.json.get('start')  # Coordenadas de inicio (lat, lon)
    end = request.json.get('end')      # Coordenadas de destino (lat, lon)
    time_str = request.json.get('start_time')  # Fecha en formato "YYYY-MM-DD HH:mm:ss"
    
    if not start or not end or not time_str:
        return jsonify({'error': 'Se necesita start, end y start_time'}), 400

    traccar_url = 'http://demo.traccar.org/api/devices'
    traccar_auth = (user, password) 

    # Hacer solicitud para obtener todos los dispositivos de Traccar
    try:
        response = requests.get(traccar_url, auth=traccar_auth)
        if response.status_code != 200:
            return jsonify({'error': 'No se pudieron obtener los dispositivos de Traccar'}), 500
        
        devices = response.json()
    except Exception as e:
        return jsonify({'error': f'Error al obtener dispositivos: {e}'}), 500

    for device in devices:
        device_id = device['uniqueId']
        
        # Llamar al endpoint de generación de ruta
        route_response = generate_route(start, end)
        if route_response[1] != 200:
            return route_response  # Retornar el error de generate_route

        # Llamar al endpoint de subida de viaje
        upload_response = upload_trip(device_id, time_str)
        if upload_response[1] != 200:
            return upload_response  # Retornar el error de upload_trip

    return jsonify({"status": "success", "message": "Rutas generadas y subidas exitosamente para todos los vehículos."}), 200

    

if __name__ == '__main__':
    app.run(debug=True)
