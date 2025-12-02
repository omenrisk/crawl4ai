# Crawl4AI Single-URL Scrape Integration Plan

## Goal
Expose a Flask endpoint under `omen-process-api/index.py` that proxies a single URL scrape through Crawl4AI’s `AsyncWebCrawler`, returning cleaned content and optionally storing results via the existing pipeline.

## Current State Review
- `omen-process-api/index.py` already serves Flask routes for health, feeds, validation, and scraping.
- Authentication is enforced through `@requires_auth`, with optional `X-User-Token` headers used for downstream storage.
- Scraping endpoints rely on Playwright helpers (`scrapear_url`, `scrapear_urls`, `clean_noticia`, `store_content_in_database`) defined under `services/`.
- Crawl4AI FastAPI exists elsewhere in the repo but is not yet leveraged inside `omen-process-api`.

## Integration Strategy
1. **Helper Module**
   - Add `services/crawl4ai_client.py` exporting:
     - `async def crawl_single_url(url: str, browser_cfg: dict | None = None, crawler_cfg: dict | None = None) -> dict`
     - `def crawl_single_url_sync(...) -> dict` for synchronous reuse.
   - Inside, normalize the URL, load configs via `BrowserConfig.load` and `CrawlerRunConfig.load`, and run `AsyncWebCrawler.arun`.
   - Convert the `CrawlResult` (`result.model_dump()`) into JSON-safe payloads (base64 encode PDFs, drop non-serializable fields) similar to `deploy/docker/server.py:575-603`.

2. **New Endpoint**
   - Route: `@app.route("/api/crawl4ai/scrape", methods=["POST"])` with `@requires_auth`.
   - Request body schema:
     ```json
     {
       "url": "https://example.com",
       "browser_config": { ... },      // optional overrides
       "crawler_config": { ... },      // optional overrides
       "store": true,                  // optional flag to persist via store_content_in_database
       "clean": true                   // optional flag to run clean_noticia
     }
     ```
   - Validation:
     - Ensure JSON body.
     - Require `url` string; prepend `https://` when scheme missing (mirrors `deploy/docker/api.py:251-254`).
     - When `store` is true, require `X-User-Token` header since storage already depends on it.

3. **Execution Flow**
   1. Parse body and headers.
   2. Await `crawl_single_url(...)`.
   3. If `clean` flag is set, run `clean_noticia` on the Crawl4AI payload.
   4. When `store` is true, call `store_content_in_database([clean_result], jwt_token)` exactly like `/api/scrape-urls-step`.
   5. Return:
      ```json
      {
        "status": "success",
        "data": cleaned_or_raw_payload,
        "raw": crawl4ai_result,
        "stored": true/false
      }
      ```
   6. On failures (validation, Crawl4AI error, storage error) reuse the existing error response format with appropriate HTTP status codes.

4. **Error Handling & Logging**
   - Wrap Crawl4AI calls in try/except; log errors with stack traces via the existing `logger`.
   - Map Crawl4AI validation issues to `400`, runtime issues to `500`.
   - Include partial context (URL, user) in logs but never dump secrets.

5. **Testing & Validation**
   - Manual: hit the new endpoint with a known article URL; verify cleaned content + optional storage.
   - Automated (optional but recommended): write a unit test that mocks `crawl_single_url` to ensure the endpoint handles success and error paths without invoking Playwright.

## Open Questions
1. Should the endpoint enforce Basic Auth only, or also require `X-User-Token` even when `store` is false?
2. Is there a need to throttle requests (rate limiting) or will upstream auth suffice?
3. Should responses include Crawl4AI markdown, links, and metadata verbatim, or be trimmed to a safer subset?

Clarifying these ahead of implementation will avoid rework.
