import re
import json
import unicodedata
from pathlib import Path

# === CONFIGURACIÓN ===
BASE_DIR = Path(__file__).resolve().parent
OMENIQ_DIR = BASE_DIR.parent.parent
FASE_1_DIR = OMENIQ_DIR / "fase_1"
CODIGOS_DIR = FASE_1_DIR / "codigos"
RESULTADOS_DIR = CODIGOS_DIR / "resultados"

RUTA_ENTRADA = RESULTADOS_DIR / "articles_scraped.json"
RUTA_SALIDA = RESULTADOS_DIR / "noticias_limpias.json"

# === FUNCIONES ===
def limpiar_texto(texto):
    if not texto:
        return ""
    # Primera limpieza general: Normalizar saltos de línea y caracteres no imprimibles
    texto = texto.replace('\xa0', ' ').replace('\r', ' ').replace('\t', ' ')
    texto = unicodedata.normalize("NFKC", texto)
    texto = re.sub(r'\n+', '\n', texto)  # Unir saltos de línea excesivos
    texto = re.sub(r'\s+', ' ', texto)  # Normalizar espacios
    texto = ''.join(c for c in texto if c.isprintable())  # Eliminar caracteres no imprimibles
    return texto.strip()

def remover_bloques_comunes(texto):
    patrones = [
        r"Síguenos en [^\n]+",              # Eliminar enlaces o llamadas a seguir
        r"Lee también:[^\n]+",              # Enlaces recomendados
        r"Suscríbete.*",                    # Eliminación de suscripciones
        r"Publicidad.*",                    # Remover bloques de publicidad
        r"\[.*?\]",                         # Remover contenido entre corchetes []
        r"[\*]{2,}.*?[\*]{2,}",             # Eliminar textos con asteriscos para resaltar
        r'(Fuente:|Lea más en|Recibir por Whatsapp).*',  # Eliminar menciones a fuentes y CTA
        r'\b(https?|ftp)://[^\s]+',         # Eliminar URLs
        r'\bwww\.[^\s]+',                   # Eliminar URLs sin esquema
        r'[\d]{1,2}/[\d]{1,2}/[\d]{4}',     # Eliminar fechas en formato dd/mm/yyyy
        r'\b\d{10,}\b',                     # Eliminar números de teléfono
        r'(.*)horarios.*',                  # Eliminar menciones a horarios o rutinas
        r'(.*)servicios.*',                 # Eliminar menciones a servicios
        r'[\w-]+@[\w-]+\.[\w-]+',           # Eliminar emails
    ]
    for patron in patrones:
        texto = re.sub(patron, '', texto, flags=re.IGNORECASE)
    return texto

def dividir_en_parrafos(texto):
    parrafos = texto.split('\n')
    parrafos_limpios = [p.strip() for p in parrafos if len(p.strip()) > 40]  # Evitar párrafos muy cortos
    return parrafos_limpios

def detectar_dos_noticias(parrafos):
    conteo_titulos = sum(1 for p in parrafos if p.isupper() and len(p) > 30)
    return conteo_titulos > 1  # Si hay más de un título, puede ser que haya dos noticias
    with open(path_entrada, 'r', encoding='utf-8') as f:
        noticias = json.load(f)

    noticias_limpias = []

    for noticia in noticias:
        texto = noticia.get('texto', '')  # Cambiar a 'contenido' si es necesario
        titulo = noticia.get('titulo', '')
        url = noticia.get('url', '')
        fecha = noticia.get('fecha', '')
        fuente = noticia.get('fuente', '')

        # Limpieza de texto - primera pasada
        texto = limpiar_texto(texto)
        
        # Segunda pasada: eliminar contenido no deseado
        texto = remover_bloques_comunes(texto)
        
        # Tercera pasada: dividir en parrafos limpios
        parrafos = dividir_en_parrafos(texto)

        if detectar_dos_noticias(parrafos):
            print(f"[!] Posible doble noticia detectada: {titulo}")

        contenido_limpio = "\n".join(parrafos)

        noticia_limpia = {
            "url": url,
            "fecha": fecha,
            "titulo": titulo,
            "fuente": fuente,
            "contenido_limpio": contenido_limpio
        }
        noticias_limpias.append(noticia_limpia)

    with open(path_salida, 'w', encoding='utf-8') as f_out:
        json.dump(noticias_limpias, f_out, ensure_ascii=False, indent=2)

    print(f"[✓] Archivo limpio guardado en: {path_salida}")

def procesar_noticias(noticias):
    """
    Procesa una lista de noticias y devuelve una lista de noticias limpias (no escribe archivo).
    """
    noticias_limpias = []

    for noticia in noticias:
        texto = noticia.get('texto', '')  # Cambiar a 'contenido' si es necesario
        titulo = noticia.get('titulo', '')
        url = noticia.get('url', '')
        fecha = noticia.get('fecha', '')
        fuente = noticia.get('fuente', '')

        # Limpieza de texto - primera pasada
        texto = limpiar_texto(texto)
        
        # Segunda pasada: eliminar contenido no deseado
        texto = remover_bloques_comunes(texto)
        
        # Tercera pasada: dividir en parrafos limpios
        parrafos = dividir_en_parrafos(texto)

        if detectar_dos_noticias(parrafos):
            print(f"[!] Posible doble noticia detectada: {titulo}")

        contenido_limpio = "\n".join(parrafos)

        noticia_limpia = {
            "url": url,
            "fecha": fecha,
            "titulo": titulo,
            "fuente": fuente,
            "contenido_limpio": contenido_limpio
        }
        noticias_limpias.append(noticia_limpia)

    return noticias_limpias


def clean_noticia(noticia):
    """
    Limpia una noticia y devuelve la noticia limpia.
    """
    texto = noticia.get('texto', '')  # Cambiar a 'contenido' si es necesario
    titulo = noticia.get('titulo', '')
    url = noticia.get('url', '')
    fecha = noticia.get('fecha', '')
    fuente = noticia.get('fuente', '')

    # Limpieza de texto - primera pasada
    texto = limpiar_texto(texto)
    
    # Segunda pasada: eliminar contenido no deseado
    texto = remover_bloques_comunes(texto)
    
    # Tercera pasada: dividir en parrafos limpios
    parrafos = dividir_en_parrafos(texto)

    if detectar_dos_noticias(parrafos):
        print(f"[!] Posible doble noticia detectada: {titulo}")

    contenido_limpio = "\n".join(parrafos)

    noticia_limpia = {
        "url": url,
        "fecha": fecha,
        "titulo": titulo,
        "fuente": fuente,
        "contenido_limpio": contenido_limpio
    }
    return noticia_limpia
