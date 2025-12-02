# /home/nicolai/workspaces/omen/omen/api/index.py

from http.client import HTTPException


from flask import Flask, request, jsonify, Response
from datetime import datetime
import logging
import sys
from flask_cors import CORS  # Import CORS
import os  # Import os to access environment variables
from functools import wraps  # Import wraps for decorator
import requests
from services import goalerts
from services.goalerts_url_checker import CheckUrlsRequest, CheckUrlsResponse, process_items_concurrently
from services.scraper_cleaner import clean_noticia
from services.scraper_ulrs import scrapear_url, scrapear_urls, store_content_in_database
import asyncio
import os
import aiohttp
from playwright.async_api import async_playwright

# Import the goalerts service

# Configuración de logging para la API
# Ensure logs go to stdout as well
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[handler]
)

logger = logging.getLogger('api')
logger.setLevel(logging.DEBUG)
#logger.addHandler(handler)  # This will cause duplicate logs for 'api' logger if root also has this handler.
# Consider removing this line if root logger's handler is sufficient.
print("API Logger initialized at DEBUG level")
logger.debug("API module initialized and logger configured")

if "DYNO" in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/app/.playwright-browsers"

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# --- Basic Auth Setup ---
BASIC_AUTH_USERNAME = os.environ.get('BASIC_AUTH_USERNAME')
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD')


def check_auth(username, password):
    """This function is called to check if a username /
    password combination is valid."""
    return username == BASIC_AUTH_USERNAME and password == BASIC_AUTH_PASSWORD


def authenticate():
    """Sends a 401 response that enables basic auth"""
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        logger.debug("Checking authentication for request")
        logger.debug(f"Request headers: {request.headers}")
        logger.info(f"Request method: {request.method}, URL: {request.url}, User: {request.authorization.username if request.authorization else None } password: {request.authorization.password if request.authorization else None }")
        
        # Check if the request has basic auth credentials
        
        # Skip auth if credentials are not set in environment (e.g., for local dev without auth)
        if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
            logger.warning("Basic Auth credentials not set in environment. Skipping authentication.")
            return f(*args, **kwargs)

        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            logger.warning(f"Authentication failed for user: {auth.username if auth else 'None'}")
            return authenticate()
        logger.info(f"User {auth.username} authenticated successfully.")
        return f(*args, **kwargs)

    return decorated


# --- End Basic Auth Setup ---

@app.route("/")
def root():
    logger.info("Root endpoint called")
    return "Flask API is running. Try /api/health or /api/feeds", 200


@app.route("/api/health")
def health():
    # return a timestamp
    logger.info("Health check endpoint called")
    return f"I'm a live {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 200


@app.route("/api/ping")
def ping():
    # return a timestamp
    logger.info("Ping endpoint called")
    return jsonify({"status": "success", "data": datetime.now().strftime('%Y-%m-%d %H:%M:%S')}), 200


@app.route("/api/test")
def test():
    # Simple test endpoint
    logger.info("Test endpoint called")
    return jsonify({
        "status": "success",
        "message": "Test endpoint working",
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route("/api/feeds")
@requires_auth  # Apply the authentication decorator
def feed():
    # obtain X-User-Token
    logger.info("Feed endpoint called")
    jwt_token = request.headers.get('X-User-Token')
    if not jwt_token:
        logger.error("X-User-Token header not found in request /api/feeds")
        return jsonify({"status": "error", "error": "X-User-Token header not found in request"}), 401
    # Get the hours parameter from the request, default to 24 if not provided
    hours = request.args.get('hours', default=24, type=int)
    # Get the max_emails parameter from the request, default to 100 if not provided
    max_emails = request.args.get('max_emails', default=100, type=int)
    # Using logger.info instead of print for consistency
    logger.info(f"Feed endpoint called with hours={hours}, max_emails={max_emails}")

    # return goalerts
    logger.debug("About to call goalerts.get_feeds")
    response = goalerts.get_feeds(hours, max_emails=max_emails, jwt_token=jwt_token)
    logger.debug("Returned from goalerts.get_feeds")

    # Log the result
    if response.get("status") == "success":
        logger.info(f"Feed endpoint returned successfully with {len(response.get('data', []))} URLs")
    else:
        logger.error(f"Feed endpoint returned with error: {response.get('error', 'Unknown error')}")

    return jsonify(response)


@app.route("/api/validate-url", methods=['POST'])
@requires_auth
async def validate_one_url_endpoint():
    """
    Accepts a single URL in the request body and returns validation results.
    """
    request_data = request.get_json()
    if not request_data or 'url' not in request_data:
        return jsonify({"error": "Invalid request format - 'url' field is required"}), 400

    url_to_check = request_data.get('url')
    if not url_to_check or not isinstance(url_to_check, str):
        return jsonify({"error": "Invalid URL format"}), 400

    logger.info(f"Received URL to validate: {url_to_check}")

    try:
        validation_result = await process_items_concurrently(
            items_to_check=[{"url": url_to_check}],
            url_field='url'
        )
        result = validation_result[0] if validation_result else None
        if result:
            logger.info(f"Finished processing URL: {url_to_check}")
            return jsonify(result.dict())
        else:
            return jsonify({"error": "No validation result returned"}), 500
    except Exception as e:
        logger.error(f"An unexpected error occurred during /validate-urls processing: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route("/api/validate-urls", methods=['POST'])
@requires_auth
async def validate_urls_endpoint():
    """
    Accepts a list of items, each containing a URL (specified by `url_field`),
    and returns validation results for each URL.
    """
    jwt_token = request.headers.get('X-User-Token')
    if not jwt_token:
        logger.error("X-User-Token header not found in request /api/feeds")
        return jsonify({"status": "error", "error": "X-User-Token header not found in request"}), 401
    logger.info("Validate URLs endpoint called")
    request_data = request.get_json()
    if not request_data or 'items' not in request_data:
        return jsonify({"error": "Invalid request format - 'items' field is required"}), 400

    items = request_data.get('items', [])
    url_field = request_data.get('url_field', 'url')

    if not items:
        logger.info("Received empty list of items to validate.")
        return jsonify({"results": []})

    logger.info(f"Received {len(items)} items to validate with URL field '{url_field}'.")

    try:
        validation_results = await process_items_concurrently(
            items_to_check=items,
            url_field=url_field
        )
        logger.info(f"Finished processing {len(items)} items.")
        return jsonify({"results": [result.dict() for result in validation_results]})
    except Exception as e:
        logger.error(f"An unexpected error occurred during /validate-urls processing: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/api/scrape-urls", methods=['POST'])
@requires_auth
def scrape_urls_endpoint():
    """
    Accepts a list of objects in the request body, each with 'url' and 'fecha'.
    If the 'test' query parameter is true, only scrape the first record.
    """
    logger.info("Scrape URLs endpoint called")
    try:
        request_data = request.get_json()
        logger.debug(f"Request data received for /scrape-urls: {request_data}")
        if not isinstance(request_data, list):
            logger.error("Request data is not a list")
            return jsonify({"error": "Request body must be a list of objects"}), 400
    except Exception:
        logger.info("Response body is not JSON for /scrape-urls endpoint.")
        return jsonify({"error": "Response body must be JSON"}), 400

    if not request_data or not all(isinstance(item, dict) and 'url' in item and 'fecha' in item for item in request_data):
        logger.error("Invalid request format - each item must have 'url' and 'fecha'")
        return jsonify({"error": "Each item must have 'url' and 'fecha' fields"}), 400

    # Handle test query parameter
    test_param = request.args.get('test', 'false').lower()
    if test_param == 'true':
        logger.info("Test mode enabled: scraping only the first record.")
        urls_to_scrape = request_data[:1]
    else:
        urls_to_scrape = request_data

    logger.info(f"Received {len(urls_to_scrape)} URLs to scrape.")

    try:
        # If scrapear_urls is async, run it in the event loop
        scraped_data = asyncio.run(scrapear_urls(urls_to_scrape))
        logger.info(f"Scraped data for {len(urls_to_scrape)} URLs.")
        #logger.debug(f"Scraped data: {scraped_data}")
        return jsonify({"status": "success", "data": scraped_data})
    except Exception as e:
        logger.error(f"An unexpected error occurred during /scrape-urls processing: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route("/api/scrape-urls-step", methods=['POST'])
def scrape_urls_by_step_endpoint():
    """
    Accepts a list of objects in the request body, each with 'url' and 'fecha'.
    If the 'test' query parameter is true, only scrape the first record.
    """
    logger.info("Scrape-step URLs endpoint called")
    jwt_token = request.headers.get('X-User-Token')
    try:
        request_data = request.get_json()
        if not isinstance(request_data, list):
            logger.error("Request data is not a list")
            return jsonify({"error": "Request body must be a list of objects"}), 400
    except Exception:
        logger.info("Response body is not JSON for /scrape-urls-step endpoint.")
        return jsonify({"error": "Response body must be JSON"}), 400

    if not request_data or not all(isinstance(item, dict) and 'url' in item and 'fecha' in item for item in request_data):
        logger.error("Invalid request format - each item must have 'url' and 'fecha'")
        return jsonify({"error": "Each item must have 'url' and 'fecha' fields"}), 400

    test_param = request.args.get('test', 'false').lower()
    urls_to_scrape = request_data[:1] if test_param == 'true' else request_data

    logger.info(f"Received {len(urls_to_scrape)} URLs to scrape.")

    try:
        scraped_results = []
        async def scrape_all():
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                for url_to_scrape in urls_to_scrape:
                    scraped_data = await scrapear_url(context, url_to_scrape)
                    if scraped_data:
                        clean_scraped_data = clean_noticia(scraped_data)  # Clean the scraped data
                        
                        store_content_response = store_content_in_database([clean_scraped_data], jwt_token=jwt_token)
                        logger.info(f"Stored clean scraped content for URL {url_to_scrape['url']}: {store_content_response}")
                        scraped_results.append(scraped_data)
                    else:
                        logger.error(f"Failed to scrape URL {url_to_scrape['url']}")
                await browser.close()
        asyncio.run(scrape_all())
        logger.info(f"Scraped data for {len(scraped_results)} URLs.")
        return jsonify({"status": "success", "data": scraped_results})
    except Exception as e:
        logger.error(f"An unexpected error occurred during /scrape-urls-step processing: {e}", exc_info=True)
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

async def scrapear_urls(urls_data):
    logger = logging.getLogger("scraper_urls")
    logger.setLevel(logging.INFO)
    logger.info("Iniciando el scraping de URLs...")
    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        for item in urls_data:
            try:
                resultado = await scrapear_url(context, item)
                if resultado:
                    resultados.append(clean_noticia(resultado))
                    # Aquí puedes llamar a store_content_in_database si lo necesitas:
                    # store_content_in_database([resultado], jwt_token=...)
            except Exception as e:
                logger.error(f"Error scraping {item.get('url')}: {e}")

        await browser.close()

    return resultados

# Add this to ensure the app runs when executed directly
if __name__ == "__main__":
    if not BASIC_AUTH_USERNAME or not BASIC_AUTH_PASSWORD:
        logger.warning(
            "BASIC_AUTH_USERNAME or BASIC_AUTH_PASSWORD environment variables are not set. /api/feeds will be unprotected if accessed.")
    else:
        logger.info("Basic Auth credentials loaded from environment.")
    vercel_url = os.environ.get('VERCEL_URL')
    if vercel_url:
        next_api_url = f"{vercel_url}/api/sources/process/scraping/content/add"
    else:
        next_api_url = "http://localhost:3000/api/sources/process/scraping/content/add"
    logger.info(f"Next.js API URL for storing scraped content: {next_api_url}")    
    logger.info("Starting Flask app directly on http://0.0.0.0:5328")
    port = int(os.environ.get("PORT", 5328))  # fallback para local
    app.run(debug=True, host='0.0.0.0', port=port)