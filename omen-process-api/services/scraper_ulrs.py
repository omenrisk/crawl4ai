import asyncio
import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm_asyncio
from urllib.parse import urlparse
import os
from playwright.async_api import async_playwright
import base64

from services.scraper_cleaner import clean_noticia

# === CONFIGURACIÓN DE LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('scraper_urls')

# === CONFIGURACIÓN ===
TIMEOUT = 10000
MAX_CONCURRENT_REQUESTS = int(os.environ.get("MAX_CONCURRENT_REQUESTS", 2))
CHROME_PATH = os.environ.get("GOOGLE_CHROME_BIN", "/app/.apt/opt/chrome/chrome")


def obtener_fuente_desde_url(url):
    dominio = urlparse(url).netloc.lower().replace("www.", "")
    return dominio if dominio else "Fuente desconocida"
async def scrapear_url(context, item):
    url = item.get("url")
    fecha = item.get("fecha", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not url:
        return None

    hash_url = hashlib.md5(url.encode()).hexdigest()

    try:
        page = await context.new_page()
        await page.goto(url, timeout=TIMEOUT, wait_until="domcontentloaded")
        html = await page.content()
        await page.close()
        
        soup = BeautifulSoup(html, "html.parser")
        titulo = soup.title.string.strip() if soup.title and soup.title.string else "Sin titulo"

        if soup.find("article"):
            texto = soup.find("article").get_text(separator="\n").strip()
        else:
            parrafos = [p.get_text().strip() for p in soup.find_all("p") if p.get_text().strip()]
            texto = "\n".join(parrafos)

        # === Filtros de calidad ===
        if len(texto.split()) < 50:
            print(f"[⛔ DESCARTADO] Muy corto: {url}")
            return None
        if "404" in titulo.lower() or "error" in titulo.lower():
            print(f"[⛔ DESCARTADO] Página rota: {url}")
            return None

        print(f"[✅ OK] {url}")

        return {
            "url": url,
            "fecha": fecha,
            "titulo": titulo,
            "texto": texto,
            "fuente": obtener_fuente_desde_url(url)
        }

    except Exception as e:
        print(f"[⚠️ ERROR] {url} → {e}")
        return None
    
async def scrapear_urls(urls_data):
    logger = logging.getLogger("scraper_urls")
    logger.setLevel(logging.INFO)
    logger.info("Iniciando el scraping de URLs...")
    resultados = []
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        async def tarea(item):
            async with sem:
                return await scrapear_url(context, item)

        tareas = [tarea(item) for item in urls_data]

        for f in tqdm_asyncio.as_completed(tareas, total=len(tareas), desc="Scrapeando artículos", unit="url"):
            resultado = await f
            if resultado:
                resultados.append(clean_noticia(resultado))
                # resultados.append((resultado))

        await browser.close()

    return resultados


def store_content_in_database(urls, jwt_token):
    """
    Almacena las URLs directamente en la base de datos llamando al endpoint de 
    omeniq.com/process/scraping/content/add
    
    Args:
        urls (list): Lista de contendios scrapeados con sus detalles
        
    Returns:
        dict: Resultado de la operación de almacenamiento
    """
    try:
        # Log the exact structure being sent
        logger.info(f"URLs structure before storing: {json.dumps(urls, indent=2)}")
        
        import requests
        
        # URL del endpoint de Next.js para almacenar feeds
        vercel_url = os.environ.get('VERCEL_URL')
        if vercel_url:
            next_api_url = f"{vercel_url}/api/sources/process/scraping/content/add"
        else:
            next_api_url = "http://localhost:3000/api/sources/process/scraping/content/add"
        
        # Log the data being sent
        logger.info(f"Enviando {len(urls)} scraped content al endpoint {next_api_url}")
        logger.debug(f"Datos a enviar: {json.dumps(urls, indent=2)}")
        
        # Preparar los datos para enviar
        payload = {"urls": urls}
        BASIC_AUTH_USERNAME = os.environ.get("BASIC_AUTH_USERNAME")
        BASIC_AUTH_PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD")
        auth_str = f"{BASIC_AUTH_USERNAME}:{BASIC_AUTH_PASSWORD}"
        auth_bytes = auth_str.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')  # Remove the .rstrip('=')
        auth_header = f"Basic {auth_b64}"
        headers = {
            'Authorization': f"{auth_header}",
            'Content-Type': 'application/json'
        }
        
        # Llamar al endpoint de Next.js
        response = requests.post(next_api_url, json=payload, headers=headers) # CORRECTO: token en headers
        # Verificar la respuesta
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Datos guardados exitosamente. Respuesta: {json.dumps(result, indent=2)}")
            return {
                "success": True,
                "count": result.get("count", 0),
                "message": "Datos almacenados correctamente en la base de datos"
            }
        else:
            logger.error(f"Error al guardar datos. Código: {response.status_code}, Respuesta: {response.text}")
            return {
                "success": False,
                "error": f"Error al guardar datos: {response.text}"
            }
    except Exception as e:
        logger.error(f"Excepción al guardar datos: {str(e)}")
        return {
            "success": False,
            "error": f"Excepción al guardar datos: {str(e)}"
        }