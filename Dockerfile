# Imagen oficial de Playwright: ya trae Chromium + todas las librerías
# del sistema necesarias preinstaladas. Evita el problema de permisos
# de "apt-get"/"sudo" que no funciona en el plan gratuito de Render.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render inyecta el puerto real en la variable $PORT en tiempo de ejecución.
CMD gunicorn app:app --timeout 180 --workers 1 --bind 0.0.0.0:$PORT
