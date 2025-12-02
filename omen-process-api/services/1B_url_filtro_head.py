#!/usr/bin/env python3

import asyncio
import aiohttp
import json
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
import random  # Para introducir retrasos aleatorios entre solicitudes
import time

# === CONFIGURACION ===
# Definir la ruta base dentro de la estructura de carpetas
BASE_DIR = Path(__file__).resolve().parent  # Directorio "codigos"
OMENIQ_DIR = BASE_DIR.parent.parent  # Directorio "OMENIQ"
FASE_1_DIR = OMENIQ_DIR / "fase_1"  # Directorio "fase_1"
CODIGOS_DIR = FASE_1_DIR / "codigos"  # Directorio "codigos"
OPERACIONES_DIR = CODIGOS_DIR / "operaciones"  # Directorio "operaciones" dentro de "codigos"

# Definir las rutas para logs y operaciones
OPERACIONES_DIR = CODIGOS_DIR / "operaciones"

# Rutas completas para los archivos de salida
RUTA_ENTRADA = OPERACIONES_DIR / "date_goalerts.json"  # Entrada: OMEN_IQ/fase_1/codigos/operaciones/date_goalerts.json
RUTA_SALIDA = OPERACIONES_DIR / "valid_urls_goalerts.json"  # Salida: OMEN_IQ/fase_1/codigos/operaciones/valid_urls_goalerts.json

MAX_CONCURRENT_REQUESTS = 50  # Aumento de solicitudes concurrentes
TIMEOUT = 10  # segundos
MAX_RETRIES = 3  # Número máximo de reintentos por URL

# User-Agent para evitar bloqueos por parte de los servidores
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

# === FUNCIONES ===
async def verificar_url(session, url, reintentos=MAX_RETRIES):
    """Verifica si una URL es válida enviando una solicitud GET con reintentos y manejo de redirecciones."""
    for _ in range(reintentos):
        try:
            # Introducir un retraso aleatorio entre solicitudes para evitar ser bloqueado
            await asyncio.sleep(random.uniform(0.5, 2.0))  # Retraso entre 0.5 y 2 segundos
            async with session.get(url, timeout=TIMEOUT, allow_redirects=True, headers={"User-Agent": USER_AGENT}) as response:
                if response.status < 400:  # Solo validamos si el código de estado es menor a 400
                    return url
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"⚠️ Error con URL {url}: {e}")
            pass
    return None  # Retorna None si todos los intentos fallaron

async def filtrar_urls_validas(urls_data):
    """Filtra las URLs válidas de la lista de URLs."""
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)  # Limitar concurrencia
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(verificar_url(session, item["url"]))
            for item in urls_data if item.get("url")
        ]
        
        # Usar tqdm para el progreso
        resultados = []
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Verificando URLs", unit="url"):
            resultado = await future
            if resultado:
                # Añadir el item completo, no solo la URL
                valid_url_item = next(item for item in urls_data if item["url"] == resultado)
                resultados.append(valid_url_item)

        return resultados

# === EJECUCION ===
if __name__ == "__main__":
    if not RUTA_ENTRADA.exists():
        print(f"❌ Archivo no encontrado: {RUTA_ENTRADA}")
        exit(1)

    # Leer datos de URLs
    with open(RUTA_ENTRADA, "r", encoding="utf-8") as f:
        urls_data = json.load(f)

    # Filtrar URLs válidas
    urls_validas = asyncio.run(filtrar_urls_validas(urls_data))

    # Crear directorio de salida si no existe
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)

    # Guardar las URLs válidas en el archivo de salida
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(urls_validas, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(urls_validas)} URLs validadas guardadas en {RUTA_SALIDA}")
    print(f"🌐 URLs válidas:")
    for url in urls_validas[:10]:  # Solo mostrando las primeras 10 para no saturar la salida
        print(url["url"])
