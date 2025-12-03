# crawler_pool.py  (new file)
import asyncio, json, hashlib, time, psutil, os
from contextlib import suppress
from typing import Dict
from crawl4ai import AsyncWebCrawler, BrowserConfig
from typing import Dict
from utils import load_config 

CONFIG = load_config()

POOL: Dict[str, AsyncWebCrawler] = {}
LAST_USED: Dict[str, float] = {}
LOCK = asyncio.Lock()

MEM_LIMIT  = CONFIG.get("crawler", {}).get("memory_threshold_percent", 95.0)   # % RAM – refuse new browsers above this
IDLE_TTL  = CONFIG.get("crawler", {}).get("pool", {}).get("idle_ttl_sec", 1800)   # close if unused for 30 min

def _sig(cfg: BrowserConfig) -> str:
    payload = json.dumps(cfg.to_dict(), sort_keys=True, separators=(",",":"))
    return hashlib.sha1(payload.encode()).hexdigest()

async def get_crawler(cfg: BrowserConfig) -> AsyncWebCrawler:
    try:
        sig = _sig(cfg)
        async with LOCK:
            if sig in POOL:
                LAST_USED[sig] = time.time();  
                return POOL[sig]
            try:
                # Heroku specific memory handling
                if 'DYNO' in os.environ:
                    import resource
                    mem_limit_bytes = os.environ.get('MEMORY_AVAILABLE', None)
                    if mem_limit_bytes:
                        mem_limit_mb = int(mem_limit_bytes) / (1024 * 1024)
                        usage = resource.getrusage(resource.RUSAGE_SELF)
                        current_mem_mb = usage.ru_maxrss / 1024  # Convert KB to MB
                        if current_mem_mb > (mem_limit_mb * MEM_LIMIT / 100):
                            raise MemoryError(f"Heroku memory limit reached: {current_mem_mb}MB/{mem_limit_mb}MB")
                elif psutil.virtual_memory().percent >= MEM_LIMIT:
                    raise MemoryError("RAM pressure – new browser denied")
            except Exception as e:
                import logging
                logging.warning(f"Memory check failed: {e}. Continuing anyway.")
            crawler = AsyncWebCrawler(config=cfg, thread_safe=False)
            await crawler.start()
            POOL[sig] = crawler; LAST_USED[sig] = time.time()
            return crawler
    except MemoryError as e:
        raise MemoryError(f"RAM pressure – new browser denied: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to start browser: {e}")
    finally:
        if sig in POOL:
            LAST_USED[sig] = time.time()
        else:
            # If we failed to start the browser, we should remove it from the pool
            POOL.pop(sig, None)
            LAST_USED.pop(sig, None)
        # If we failed to start the browser, we should remove it from the pool
async def close_all():
    async with LOCK:
        await asyncio.gather(*(c.close() for c in POOL.values()), return_exceptions=True)
        POOL.clear(); LAST_USED.clear()

async def janitor():
    while True:
        await asyncio.sleep(60)
        now = time.time()
        async with LOCK:
            for sig, crawler in list(POOL.items()):
                if now - LAST_USED[sig] > IDLE_TTL:
                    with suppress(Exception): await crawler.close()
                    POOL.pop(sig, None); LAST_USED.pop(sig, None)
