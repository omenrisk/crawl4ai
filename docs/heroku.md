# Deploying Crawl4AI to Heroku

This repo now ships with the files Heroku expects (`Procfile`, `runtime.txt`, `Aptfile`, and `bin/post_compile`). Follow the steps below to run the FastAPI crawler API on a Heroku dyno.

## 1. Prepare the app

1. Install the Heroku CLI and authenticate.
2. Create an app and add buildpacks **in this exact order**:
   1. `heroku-community/apt`
   2. `https://github.com/microsoft/playwright-buildpack`
   3. `heroku/python`
3. Push this repository to the Heroku remote (`git push heroku main`).

`runtime.txt` pins Python 3.12.3, `Aptfile` installs the system libraries Chromium/Playwright require, and `bin/post_compile` downloads the browser plus runs `crawl4ai-setup`.

## 2. Provide secrets and config

Set these config vars before releasing:

| Var | Purpose |
| --- | --- |
| `PORT` | Supplied automatically by Heroku; no action needed. |
| `REDIS_URL` | Connection string for Heroku Redis (required for jobs + rate limiting). |
| `LLM_PROVIDER` | Optional override for the default provider. |
| `OPENAI_API_KEY`, `GROQ_API_KEY`, etc. | Any API keys you plan to use. |
| `PLAYWRIGHT_BROWSERS_PATH=0` | (Recommended) Forces Playwright to keep browsers inside the slug. |
| `SECURITY_ENABLED` | `"true"` to enable the security middleware from `config.yml`. |

`deploy/docker/utils.py` now reads these environment variables and automatically wires them into the FastAPI server config (port binding, Redis URI, rate limiting backend, security, and LLM settings).

## 3. Procfile & process model

The `Procfile` defines a single `web` dyno that bootstraps the Docker server module via Gunicorn/Uvicorn:

```
web: PYTHONPATH=deploy/docker:$PYTHONPATH \
     gunicorn deploy.docker.server:app --bind 0.0.0.0:$PORT
```

Tune concurrency with the optional `WEB_CONCURRENCY`, `WEB_THREADS`, and `WEB_TIMEOUT` vars. A `release` phase is not required because `bin/post_compile` handles browser installation during slug compilation.

## 4. Redis & rate limiting

The API requires Redis for background crawling jobs, webhook state, and SlowAPI rate limiting. Provision **Heroku Redis** (Standard tier recommended) and expose its URL via `REDIS_URL`. When this value is present the server will also point the rate limiter at the same Redis instance; otherwise it falls back to in-memory limits (not suitable for production).

## 5. Validating the deployment

1. Run `heroku local` to test the Procfile and confirm the playground at `http://localhost:5000/playground`.
2. Deploy to a staging app: `git push heroku main`.
3. Tail logs with `heroku logs --tail` and look for:
   - `-> Installing Playwright Chromium browser` (from `bin/post_compile`)
   - `MCP server running on 0.0.0.0:<port>`
4. Hit `/health` and `/metrics` to verify observability endpoints (disable Prometheus via `config.yml` if these should not be public).

You can now promote the slug to production or scale dynos via `heroku ps:scale web=1`.

## 6. Troubleshooting

- **Playwright fails to start**: confirm the apt buildpack is first, `bin/post_compile` is executable, and `PLAYWRIGHT_BROWSERS_PATH=0` is set so browsers are part of the slug.
- **Redis connection errors**: check that `REDIS_URL` is present and whitelisted, or override `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, and `REDIS_DB`.
- **30s request timeout**: long jobs should use `/crawl/job` or `/llm/job` so the dyno responds immediately while work continues in the background queue.

That's it - pushing new commits will rebuild the slug with all dependencies needed for a fully hosted Crawl4AI deployment on Heroku.

## 7. Container-based alternative

If you prefer to ship the exact Docker image (Playwright browsers included) like `omen-process-api`, switch your app to the container stack and use the bundled `heroku.yml`:

1. `heroku stack:set container -a <app>`
2. `heroku container:login`
3. `heroku container:push web -a <app>`
4. `heroku container:release web -a <app>`

The Dockerfile already sets `PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers`, installs all Chromium dependencies, and starts the API with `supervisord`. Config vars such as `REDIS_URL`, `LLM_PROVIDER`, and API keys are still required. This approach mirrors the workflow used in `omen-process-api` while keeping the codebase identical between slug and container deployments.
