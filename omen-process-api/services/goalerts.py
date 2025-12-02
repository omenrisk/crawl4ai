#!/usr/bin/env python3

# === IMPORTACIONES ===
import os
import json
import datetime
import logging
import imaplib
import email
from bs4 import BeautifulSoup
import urllib.parse
from pathlib import Path
import requests
from urllib.parse import urlparse, parse_qs
import concurrent.futures
import asyncio

from services.goalerts_url_checker import process_items_concurrently

# === CONFIGURACIÓN DE LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('goalerts_service')

# === CONFIGURACIÓN ===
# Credenciales de Gmail para autenticar con IMAP (sin OAuth2)
USERNAME = "omen.pulse.bolivia2025@gmail.com"  # Tu usuario de Gmail
PASSWORD = "ywtt tnmp pjkv zsqu"  # Tu contraseña de Gmail (aunque **NO se recomienda usar contraseñas directamente en el código**)

# === FUNCIONES ===
def GmailURLDecoder(url):
    """
    Decodifica las URL de Google Alerts, que tienen el formato:
    'https://www.google.com/url?url=...' para obtener la URL original.
    """
    parsed_url = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed_url.query)
    
    if 'url' in query:
        return query['url'][0]  # Devuelve la URL original contenida en 'url'
    return None

def obtener_html(mensaje):
    """Extrae el contenido HTML de un correo"""
    for part in mensaje.walk():
        if part.get_content_type() == "text/html":
            body = part.get_payload(decode=True)
            if body:
                return body.decode('utf-8', errors='ignore')
    return None

def obtener_urls_google_alerts(html, fecha_email):
    soup = BeautifulSoup(html, "html.parser")
    urls_finales = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if "https://www.google.com/url" in href:
            decoded_url = GmailURLDecoder(href)  # Usar el decodificador
            if decoded_url:
                urls_finales.append({"url": decoded_url, "feedDate": fecha_email})  # <-- Cambia aquí
    return urls_finales

# Función para autenticar con IMAP usando las credenciales directamente (sin OAuth2)
def authenticate_imap():
    logger.info("Iniciando autenticación IMAP")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")  # Usamos IMAP sobre SSL
    mail.login(USERNAME, PASSWORD)  # Autenticación con las credenciales proporcionadas
    logger.info("Autenticación IMAP exitosa")
    return mail

# === FUNCIÓN PRINCIPAL PARA API ===
def get_feeds(hours=24, store_in_db=True, max_emails=100, jwt_token=None):
    """
    Obtiene las URLs de Google Alerts desde Gmail
    
    Args:
        hours (int): Número de horas hacia atrás para buscar correos
        store_in_db (bool): Si es True, almacena las URLs en la base de datos
        max_emails (int): Número máximo de correos a procesar (0 para no limitar)
        
    Returns:
        dict: Diccionario con las URLs detectadas y metadata
    """
    import concurrent.futures
    
    logger.info(f"Iniciando extracción de Google Alerts para las últimas {hours} horas (máximo {max_emails} correos)")
    
    # Inicializar variables
    urls_detectadas = []
    correos_procesados = 0
    total_correos = 0
    
    try:
        # Conectar a Gmail mediante IMAP
        logger.info("Conectando a Gmail mediante IMAP")
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        
        # Autenticar con las credenciales
        logger.info("Iniciando autenticación IMAP")
        mail.login(USERNAME, PASSWORD)
        logger.info("Autenticación IMAP exitosa")
        
        # Seleccionar la bandeja de entrada
        mail.select("inbox")
        logger.info("Conexión exitosa a Gmail")
        
        # Calcular la fecha desde la que buscar correos
        fecha_desde = (datetime.datetime.now() - datetime.timedelta(hours=hours)).strftime("%d-%b-%Y")
        logger.info(f"Buscando correos desde {fecha_desde}")
        
        # Buscar correos de Google Alerts
        result, data = mail.search(None, f'(FROM "googlealerts-noreply@google.com" SINCE "{fecha_desde}")')
        mail_ids = data[0].split()
        total_correos = len(mail_ids)
        
        # Limitar el número de correos si se especifica
        if max_emails > 0 and len(mail_ids) > max_emails:
            logger.info(f"Limitando procesamiento a {max_emails} de {len(mail_ids)} correos")
            mail_ids = mail_ids[-max_emails:]  # Take most recent emails
        
        logger.info(f"Se encontraron {len(mail_ids)} correos para procesar")
        
        # Función para procesar un correo individual
        def process_email(mail_id):
            try:
                # Crear una nueva conexión IMAP para cada hilo
                thread_mail = imaplib.IMAP4_SSL("imap.gmail.com")
                thread_mail.login(USERNAME, PASSWORD)
                thread_mail.select("inbox")
                
                result, data = thread_mail.fetch(mail_id, "(RFC822)")
                raw_email = data[0][1]
                
                # Cerrar la conexión IMAP del hilo
                try:
                    thread_mail.close()
                    thread_mail.logout()
                except Exception as e:
                    logger.warning(f"Error al cerrar conexión IMAP del hilo: {e}")
                
                # Parsear el correo
                email_message = email.message_from_bytes(raw_email)
                
                # Obtener la fecha del correo
                date_tuple = email.utils.parsedate_tz(email_message['Date'])
                if date_tuple:
                    local_date = datetime.datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                    fecha = local_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logger.info(f"Procesando correo ID {mail_id.decode()} con fecha {fecha}")
                
                # Procesar el cuerpo del correo
                if email_message.is_multipart():
                    for part in email_message.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/html":
                            body = part.get_payload(decode=True).decode()
                            soup = BeautifulSoup(body, 'html.parser')
                            
                            # Extraer URLs de los enlaces
                            urls_email = []
                            for a in soup.find_all('a', href=True):
                                href = a['href']
                                # Filtrar URLs de Google Alerts
                                if "google.com/alerts/share" in href or "google.com/url" in href:
                                    # Extraer la URL real
                                    parsed_url = urlparse(href)
                                    if "google.com/url" in href:
                                        url_param = parse_qs(parsed_url.query).get('url')
                                        if url_param:
                                            urls_email.append({
                                                "url": url_param[0],
                                                "feedDate": fecha,
                                                "source": "goalerts"  # Inicializa en False
                                            })
                                    elif "google.com/alerts/share" in href:
                                        url_param = parse_qs(parsed_url.query).get('url')
                                        if url_param:
                                            urls_email.append({
                                                "url": url_param[0],
                                                "feedDate": fecha,
                                                "source": "goalerts"  # Inicializa en False
                                            })
                
                # Add this logging in process_email function after creating urls_email
                #logger.info(f"URLs found in email: {json.dumps(urls_email, indent=2)}")
                
                logger.info(f"Se encontraron {len(urls_email)} URLs en el correo")
                return urls_email
            except Exception as e:
                logger.error(f"Error al procesar correo: {e}")
                return []
        
        # Procesar correos en paralelo
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # Mapear la función de procesamiento a cada ID de correo
            futures = []
            for mail_id in mail_ids:
                futures.append(executor.submit(process_email, mail_id))
            
            # Combinar los resultados
            for future in concurrent.futures.as_completed(futures):
                try:
                    urls_email = future.result()
                    # Verify structure before extending
                    for url in urls_email:
                        if "feedDate" not in url:
                            logger.warning(f"Missing feedDate in URL: {json.dumps(url, indent=2)}")
                    # Add this logging before extending urls_detectadas
                    logger.debug(f"Adding to urls_detectadas: {json.dumps(urls_email, indent=2)}")
                    urls_detectadas.extend(urls_email)
                    correos_procesados += 1
                    logger.debug(f"Procesado correo {correos_procesados}/{len(mail_ids)}")
                except Exception as e:
                    logger.error(f"Error al procesar correo: {e}", exc_info=True)
        
        # Cerrar la conexión IMAP de forma segura
        try:
            logger.info("Cerrando conexión IMAP")
            mail.close()
            mail.logout()
        except Exception as e:
            logger.warning(f"Error al cerrar conexión IMAP: {e}")
            # Intentar solo logout si close falló
            try:
                mail.logout()
            except:
                pass
        
        # Almacenar las URLs en la base de datos si se solicita
        logger.info(f"Almacenando URLs primer dato: {urls_detectadas[0]}")
        if store_in_db and urls_detectadas:
            logger.info(f"Almacenando {len(urls_detectadas)} URLs en la base de datos")
            #verified_urls = asyncio.run(process_items_concurrently(urls_detectadas))
            logger.info(f"URLs verificadas y almacenadas: {len(urls_detectadas)}")
            store_result = store_in_database(urls_detectadas, jwt_token)
            logger.info(f"Resultado de almacenamiento en DB: {store_result}")
        
        # Add this logging before preparing the response
        logger.info(f"Final urls_detectadas: {json.dumps(urls_detectadas, indent=2)}")
        
        # Preparar la respuesta
        response = {
            "status": "success",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": urls_detectadas,
            "metadata": {
                "total_emails": total_correos,
                "processed_emails": correos_procesados,
                "hours_range": hours,
                "urls_found": len(urls_detectadas),
                "limited": len(mail_ids) < total_correos
            }
        }
        
        # Add this logging after preparing the response
        logger.info(f"Final response payload: {json.dumps(response, indent=2)}")
        
        return response
    except Exception as e:
        logger.error(f"Error durante la extracción de Google Alerts: {e}", exc_info=True)
        # En caso de error, devolver una respuesta de error
        error_response = {
            "status": "error",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": str(e)
        }
        return error_response

def store_in_database(urls, jwt_token):
    """
    Almacena las URLs directamente en la base de datos llamando al endpoint de Next.js
    
    Args:
        urls (list): Lista de diccionarios con las URLs y fechas
        
    Returns:
        dict: Resultado de la operación de almacenamiento
    """
    try:
        # Log the exact structure being sent
        logger.info(f"URLs structure before storing: {json.dumps(urls, indent=2)}")
        
        import requests
        
        # URL del endpoint de Next.js para almacenar feeds
        next_api_url = f"{os.environ.get('VERCEL_URL')}/api/feeds/store" if os.environ.get('VERCEL_URL') else "http://localhost:3000/api/feeds/store"
        
        # Log the data being sent
        logger.info(f"Enviando {len(urls)} URLs al endpoint {next_api_url}")
        logger.debug(f"Datos a enviar: {json.dumps(urls, indent=2)}")
        
        # Preparar los datos para enviar
        payload = {"urls": urls}
        headers = {'Authorization': f'Basic {jwt_token}'} if jwt_token else {}
        
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