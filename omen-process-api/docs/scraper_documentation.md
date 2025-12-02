# Scraper Project Documentation

## Overview

This document provides an overview of the Python scripts used for web scraping, data processing, and application state management.

---

## `scraper_url.py`

### Description

The `scraper_url.py` script is designed to scrape web pages. It takes a list of URLs, fetches their HTML content, parses the relevant data, and saves it to a structured output file.

Based on analysis, it appears to use a hybrid approach. It may first attempt a **traditional scrape** (e.g., using Playwright/BeautifulSoup). If that fails, it can fall back to an **AI-powered scrape** (e.g., using ScrapeGraph).

After scraping and cleaning the data, the script sends the results to an external API endpoint for storage.


### Functions

#### `fetch_urls(urls)`

*   **Description**: Fetches the HTML content from a list of URLs.
*   **Parameters**:
    *   `urls` (list): A list of string URLs to be fetched.
*   **Returns**: `None`.
*   **Note**: It is recommended to implement robust error handling in this function to manage network issues or invalid URLs gracefully.

#### `parse_data(html)`

*   **Description**: Parses the raw HTML content of a page to extract relevant data.
*   **Parameters**:
    *   `html` (str): The HTML content to be parsed.
*   **Returns**: A dictionary containing the extracted data.

### Usage

```bash
python scraper_url.py urls.txt output.json
```

---

## `scraper_clear.py`

### Description

The `scraper_clear.py` script is a utility for cleaning up scraped data or resetting the application's state.

### Functions

#### `clear_data(data)`

*   **Description**: Cleans the provided dataset by removing unnecessary fields or formatting values.
*   **Parameters**:
    *   `data` (list or dict): The scraped data to be cleaned.
*   **Returns**: The cleaned data.