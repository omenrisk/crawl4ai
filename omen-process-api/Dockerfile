# Imagen base con Python
FROM python:3.10-slim

# Variables de entorno
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers

# Establece el directorio de trabajo
WORKDIR /app

# Instala dependencias del sistema necesarias para playwright y otros paquetes
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    ca-certificates \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libxshmfence1 \
    libgbm-dev \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxrandr2 \
    libappindicator3-1 \
    fonts-liberation \
    lsb-release \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Copia el requirements.txt e instala las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala los navegadores de Playwright
RUN playwright install --with-deps

# Copia todo el código de la app
COPY . .

ENV BASIC_AUTH_USERNAME="?4(n{oSpo?Yb£808k/8^i\M%,6tH~bM"
ENV BASIC_AUTH_PASSWORD="78aVS@H]0\Es60kvC+732Pb5M.@727~x"
ENV MAX_CONCURRENT_REQUESTS=2
ENV VERCEL_URL="https://omen-omenrisks-projects.vercel.app"

# Expone el puerto de Flask
EXPOSE 5328

# Usa gunicorn para ejecutar la app como en Heroku
CMD gunicorn -b 0.0.0.0:$PORT index:app --timeout 120
