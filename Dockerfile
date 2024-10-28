# Usa una imagen base de Python
FROM python:3.11

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos de requisitos y la aplicación
COPY requirements.txt .
COPY app.py .

# Instala las dependencias del sistema y el controlador ODBC
RUN apt-get update && apt-get install -y \
    unixodbc \
    unixodbc-dev \
    msodbcsql17 \
    && pip install --no-cache-dir -r requirements.txt

# Expone el puerto que usará la aplicación
EXPOSE 8000

# Comando para iniciar la aplicación
CMD ["gunicorn", "-k", "gevent", "-w", "4", "app:app", "-b", "0.0.0.0:8000"]
