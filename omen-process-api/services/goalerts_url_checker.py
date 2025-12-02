#!/usr/bin/env python3

import asyncio
import logging
import random
from typing import List, Dict, Any, Optional

import aiohttp
from pydantic import BaseModel, Field, HttpUrl

# === CONFIGURATION ===
# These can be further configured via environment variables or a config file
MAX_CONCURRENT_REQUESTS = 20  # Max number of concurrent URL checks
MAX_RETRIES = 3  # Max retries for a failing URL
REQUEST_TIMEOUT = 10  # Timeout in seconds for each HTTP request
USER_AGENT = "URLValidatorService/1.0 (Python/aiohttp)"  # Custom User-Agent

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('goalerts_url_checker')


# === PYDANTIC MODELS ===
class CheckUrlsRequest(BaseModel):
    items: List[Dict[str, Any]] = Field(..., description="List of items (dictionaries) to check.")
    url_field: str = Field(default="url", description="The key in each item dictionary that contains the URL string.")


class ValidatedItem(BaseModel):
    original_item: Dict[str, Any]
    is_valid: bool
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    final_url: Optional[str] = None  # To store the URL after redirects


class CheckUrlsResponse(BaseModel):
    results: List[ValidatedItem]


# === CORE URL VALIDATION LOGIC ===
async def verify_url_async(
        session: aiohttp.ClientSession,
        item: Dict[str, Any],
        url_field: str
) -> ValidatedItem:
    """
    Asynchronously verifies a single URL from an item.
    """
    url_to_check_str = item.get(url_field)

    if not url_to_check_str or not isinstance(url_to_check_str, str):
        logger.warning(f"URL field '{url_field}' missing or not a string in item: {item}")
        return ValidatedItem(original_item=item, is_valid=False,
                             error_message=f"URL field '{url_field}' missing, empty, or not a string.")

    try:
        # Basic validation of URL structure before attempting HTTP request
        HttpUrl(url_to_check_str)
    except ValueError:
        logger.warning(f"Invalid URL format: {url_to_check_str}")
        return ValidatedItem(original_item=item, is_valid=False,
                             error_message=f"Invalid URL format: {url_to_check_str}")

    headers = {"User-Agent": USER_AGENT}
    last_exception_message = "Unknown error"

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(url_to_check_str, timeout=REQUEST_TIMEOUT, headers=headers,
                                   allow_redirects=True) as response:
                final_url_after_redirects = str(response.url)
                if response.status < 400:
                    logger.info(
                        f"URL {url_to_check_str} -> {final_url_after_redirects} is VALID (Status: {response.status})")
                    return ValidatedItem(original_item=item, is_valid=True, status_code=response.status,
                                         final_url=final_url_after_redirects)
                else:
                    last_exception_message = f"HTTP status {response.status}"
                    logger.warning(
                        f"URL {url_to_check_str} -> {final_url_after_redirects} FAILED (Status: {response.status}) - Attempt {attempt + 1}/{MAX_RETRIES}")
                    # For 4xx errors, retrying might not be useful, but we follow MAX_RETRIES for consistency
                    # For 5xx errors, retrying is generally good.
                    if attempt == MAX_RETRIES - 1:
                        return ValidatedItem(original_item=item, is_valid=False, status_code=response.status,
                                             error_message=last_exception_message, final_url=final_url_after_redirects)

        except aiohttp.ClientConnectorError as e:  # DNS resolution, connection refused
            last_exception_message = f"Connection error: {type(e).__name__}"
            logger.warning(
                f"URL {url_to_check_str} FAILED ({last_exception_message}) - Attempt {attempt + 1}/{MAX_RETRIES}")
        except aiohttp.ClientResponseError as e:  # HTTP errors not caught by status < 400 (should be rare here)
            last_exception_message = f"Client response error: {e.status} {e.message}"
            logger.warning(
                f"URL {url_to_check_str} FAILED ({last_exception_message}) - Attempt {attempt + 1}/{MAX_RETRIES}")
        except asyncio.TimeoutError:
            last_exception_message = "Request timed out"
            logger.warning(f"URL {url_to_check_str} FAILED (Timeout) - Attempt {attempt + 1}/{MAX_RETRIES}")
        except aiohttp.ClientError as e:  # Catch other aiohttp client errors
            last_exception_message = f"Client error: {type(e).__name__}"
            logger.warning(
                f"URL {url_to_check_str} FAILED ({last_exception_message}) - Attempt {attempt + 1}/{MAX_RETRIES}")
        except Exception as e:  # Catch any other unexpected errors
            last_exception_message = f"Unexpected error: {str(e)}"
            logger.error(
                f"URL {url_to_check_str} FAILED with unexpected error: {e} - Attempt {attempt + 1}/{MAX_RETRIES}",
                exc_info=True)
            # For truly unexpected errors, perhaps stop retrying immediately
            return ValidatedItem(original_item=item, is_valid=False, error_message=last_exception_message)

        if attempt < MAX_RETRIES - 1:
            # Exponential backoff with jitter
            delay = (2 ** attempt) + random.uniform(0, 1)
            logger.debug(f"Retrying URL {url_to_check_str} in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

    logger.error(
        f"URL {url_to_check_str} ultimately FAILED after {MAX_RETRIES} attempts. Last error: {last_exception_message}")
    return ValidatedItem(original_item=item, is_valid=False,
                         error_message=f"Failed after {MAX_RETRIES} attempts. Last error: {last_exception_message}")


async def process_items_concurrently(
        items_to_check: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Manages concurrent validation of URLs from the items list.

    Args:
        items_to_check: List of dictionaries containing 'url' and 'fecha' keys
        jwt_token: Optional JWT token for authentication

    Returns:
        List of dictionaries with validation results merged with original data
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    tasks = []

    async with aiohttp.ClientSession() as session:
        for item in items_to_check:
            async def task_with_semaphore(data: Dict[str, Any]):
                async with semaphore:
                    result = await verify_url_async(session, {"url": data["url"]}, "url")
                    # Merge the validation result with the original item data
                    return {
                        **data,  # Keep original data (including 'fecha')
                        "is_valid": result.is_valid,
                        "status_code": result.status_code,
                        "error_message": result.error_message,
                        "final_url": result.final_url
                    }

            tasks.append(task_with_semaphore(item))

        # Gather results with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error processing URL: {str(result)}")
                continue
            processed_results.append(result)

        return processed_results


# # === FASTAPI APP & ENDPOINT ===
# app = FastAPI(
#     title="GoAlerts URL Checker Service",
#     description="An API service to asynchronously validate a list of URLs.",
#     version="1.0.0"
# )




# # @app.get("/health", summary="Health check endpoint")
# # async def health_check():
# #     """
# #     Simple health check endpoint.
# #     """
# #     return {"status": "healthy"}


# # === MAIN (for running with Uvicorn) ===
# if __name__ == "__main__":
#     import uvicorn

#     logger.info("Starting GoAlerts URL Checker Service with Uvicorn...")
#     # For development, you might want to enable reload=True
#     uvicorn.run(app, host="0.0.0.0", port=8000)
