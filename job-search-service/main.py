import sys
import asyncio
import os
import logging
import time
import urllib.request
import urllib.error
import json
import threading
import re
from fastapi import FastAPI
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from pydantic import BaseModel
from typing import List, Optional, Union
from fastapi.responses import JSONResponse
from searchers.manager import job_search_manager

# Set Windows asyncio event loop policy to ProactorEventLoop to support subprocesses (Playwright)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Request & Response schemas for jobs search
class JobSearchRequest(BaseModel):
    user_id: int = 1
    query: str
    location: str = ""
    max_results: int = 20
    source: str = "Naukri"

class JobSearchResult(BaseModel):
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    source: str

class JobSearchErrorResponse(BaseModel):
    success: bool = False
    error: str

class JobSearchSuccessResponse(BaseModel):
    success: bool = True
    query: str
    location: str
    source: str
    max_results: int
    jobs_found: int
    jobs_stored: int
    jobs_skipped: int
    jobs: List[JobSearchResult]

# Setup logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("job-search-service")

# Load env variables
load_dotenv()

app = FastAPI(
    title="AI Career Copilot - Job Search Service",
    description="Playwright-powered web scraping and job search microservice.",
    version="1.0.0"
)

def run_async_in_worker_loop(coro_factory):
    """
    Run Playwright work in a fresh event loop.
    On Windows this avoids Uvicorn/reload selector-loop subprocess issues.
    """
    result = {}

    def runner():
        loop = None
        try:
            if sys.platform == 'win32':
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result["value"] = loop.run_until_complete(coro_factory())
        except Exception as exc:
            result["error"] = exc
        finally:
            if loop:
                loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    return result.get("value")

async def run_playwright_task(coro_factory):
    return await asyncio.to_thread(run_async_in_worker_loop, coro_factory)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "job-search-service",
        "message": "Playwright Job Search Service is running"
    }

@app.get("/test-browser")
async def test_browser():
    logger.info("Browser verification requested.")
    async def verify_browser():
        async with async_playwright() as p:
            logger.info("Playwright framework initialized.")
            logger.info("Launching Chromium in headless mode...")
            browser = await p.chromium.launch(headless=True)
            logger.info("Browser launched.")
            try:
                page = await browser.new_page()
                logger.info("New browser page opened.")
                
                url = "https://example.com"
                logger.info(f"Navigating to: {url}")
                await page.goto(url, wait_until="load")
                logger.info("Navigation successful.")
                
                title = await page.title()
                logger.info(f"Title extracted: '{title}'")
                
                return {
                    "success": True,
                    "title": title,
                    "message": "Playwright browser verification successful"
                }
            finally:
                await browser.close()
                logger.info("Browser closed.")

    try:
        return await run_playwright_task(verify_browser)
    except Exception as e:
        logger.error(f"Browser verification failed: {e}")
        return {
            "success": False,
            "error": repr(e)
        }

@app.post("/search")
def search_jobs(query: str, location: str = ""):
    return {
        "message": "Use /search-jobs for multi-platform search results",
        "query": query,
        "location": location,
        "results": []
    }

# In-memory query cache: (query_lower, location_lower) -> (timestamp, list_of_jobs)
QUERY_CACHE = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache expiry

# Lock to serialize concurrent scraping requests
scraper_lock = asyncio.Lock()

# Rate limiting minimum interval between consecutive scraper runs
MIN_SCRAPE_INTERVAL = 2.0
last_scrape_timestamp = 0.0

def normalize_job_text(value: Optional[str]) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return " ".join(normalized.split())

def dedupe_jobs(jobs: List[dict]) -> List[dict]:
    seen = set()
    unique_jobs = []

    for job in jobs:
        key = (
            normalize_job_text(job.get("title")),
            normalize_job_text(job.get("company")),
            normalize_job_text(job.get("location")),
        )
        if key in seen:
            logger.info("Duplicate scraped job skipped by fingerprint: %s", key)
            continue
        seen.add(key)
        unique_jobs.append(job)

    return unique_jobs

def normalize_source(source: Optional[str]) -> str:
    return job_search_manager.normalize_source(source)

def post_job_to_db(job_payload: dict) -> tuple[int, dict]:
    url = "http://localhost:8001/api/jobs/store"
    req = urllib.request.Request(
        url,
        data=json.dumps(job_payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            resp_body = response.read().decode('utf-8')
            return response.status, json.loads(resp_body)
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode('utf-8') if e else ""
        try:
            err_json = json.loads(resp_body)
        except Exception:
            err_json = {"error": resp_body}
        return e.code, err_json
    except Exception as e:
        return 500, {"success": False, "error": str(e)}

@app.post("/search-jobs", response_model=Union[JobSearchSuccessResponse, JobSearchErrorResponse])
async def search_jobs_endpoint(payload: JobSearchRequest):
    global last_scrape_timestamp
    logger.info("Search started")
    logger.info(f"User ID: {payload.user_id}")
    logger.info(f"Query: {payload.query}")
    logger.info(f"Location: {payload.location}")
    source = normalize_source(payload.source)
    logger.info(f"Source: {source}")
    max_results = max(1, min(payload.max_results or 20, 100))
    logger.info(f"Max Results: {max_results}")
    
    query_clean = payload.query.lower().strip()
    loc_clean = payload.location.lower().strip()
    cache_key = (source.lower(), query_clean, loc_clean)
    
    current_time = time.time()
    
    results = None

    # 1. Check in-memory query cache (read-only check before locking)
    if cache_key in QUERY_CACHE:
        cache_time, cached_results = QUERY_CACHE[cache_key]
        if current_time - cache_time < CACHE_TTL_SECONDS:
            logger.info(f"Cache hit for query: '{payload.query}' / location: '{payload.location}'. Returning {len(cached_results)} cached jobs.")
            results = cached_results[:max_results]
            
    # 2. Cache miss, acquire lock to serialize scraper execution
    if results is None:
        async with scraper_lock:
        # Double-check cache inside the lock
            current_time = time.time()
            if cache_key in QUERY_CACHE:
                cache_time, cached_results = QUERY_CACHE[cache_key]
                if current_time - cache_time < CACHE_TTL_SECONDS:
                    logger.info(f"Cache hit (after lock) for query: '{payload.query}' / location: '{payload.location}'. Returning {len(cached_results)} jobs.")
                    results = cached_results[:max_results]
                    
            if results is None:
                # Enforce minimum interval rate limiting between scraper runs
                time_since_last_scrape = current_time - last_scrape_timestamp
                if time_since_last_scrape < MIN_SCRAPE_INTERVAL:
                    cooldown_sleep = MIN_SCRAPE_INTERVAL - time_since_last_scrape
                    logger.info(f"Polite scraper cooldown active. Sleeping for {cooldown_sleep:.2f}s...")
                    await asyncio.sleep(cooldown_sleep)
                    
                logger.info(f"Cache miss. Launching Playwright scraper for {source}...")
                try:
                    if source == "All":
                        scraped_results = await run_playwright_task(lambda: job_search_manager.search_all(payload.query, payload.location, max_results=max_results))
                    else:
                        scraped_results = await run_playwright_task(lambda: job_search_manager.search_source(source, payload.query, payload.location, max_results=max_results))
                    deduped_results = dedupe_jobs(scraped_results)
                    results = deduped_results[:max_results]
                    last_scrape_timestamp = time.time()
                    logger.info(
                        "Scraper completed. Found %s jobs on %s, %s after de-duplication, %s selected.",
                        len(scraped_results),
                        source,
                        len(deduped_results),
                        len(results)
                    )
                    
                    # Cache the de-duplicated list of jobs. Storage still runs for each requesting user.
                    QUERY_CACHE[cache_key] = (last_scrape_timestamp, deduped_results)
                except Exception as e:
                    logger.error(f"Search failed during scraping: {e}")
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "error": f"Search failed: {repr(e)}"}
                    )
            
    # 3. Store results in backend database
    jobs_found = len(results)
    jobs_stored = 0
    jobs_skipped = 0
    
    logger.info(f"Beginning automatic job storage for {jobs_found} discovered jobs...")
    
    for job in results:
        # Construct payload for POST /api/jobs/store.
        store_payload = {
            "user_id": payload.user_id,
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "description": job["description"],
            "apply_url": job["apply_url"],
            "source": job.get("source") or source,
            "status": "Discovered"
        }
        
        # Execute blocking POST request in an async-safe thread pool
        status_code, response_data = await asyncio.to_thread(post_job_to_db, store_payload)
        
        logger.info(f"POST /api/jobs/store for '{job['title']}' at '{job['company']}' returned status code: {status_code}")
        logger.info(f"Response details: {response_data}")
        
        if status_code == 200:
            if response_data.get("status") == "stored":
                jobs_stored += 1
            else:
                jobs_skipped += 1
        else:
            logger.error(f"Failed to store job '{job['title']}': HTTP {status_code} - {response_data}")
            
    logger.info(f"=== JOB STORAGE SUMMARY ===")
    logger.info(f"Jobs Found: {jobs_found}")
    logger.info(f"Jobs Stored: {jobs_stored}")
    logger.info(f"Jobs Skipped: {jobs_skipped}")
    logger.info(f"===========================")
    
    return {
        "success": True,
        "query": payload.query,
        "location": payload.location,
        "source": source,
        "max_results": max_results,
        "jobs_found": jobs_found,
        "jobs_stored": jobs_stored,
        "jobs_skipped": jobs_skipped,
        "jobs": results
    }
