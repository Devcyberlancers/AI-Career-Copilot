import asyncio
import logging
import random
from typing import Dict, List, Optional

from playwright.async_api import async_playwright

logger = logging.getLogger("job-search-service.public")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

CARD_SELECTORS = [
    "[data-testid*='job']",
    "[class*='job-card']",
    "[class*='JobCard']",
    "[class*='jobTuple']",
    "[class*='job-result']",
    "[class*='jobsearch']",
    "article",
    "li",
]

TITLE_SELECTORS = [
    "h1",
    "h2",
    "h3",
    "a[title]",
    "a[href*='job']",
    "[class*='title']",
    "[class*='Title']",
]

COMPANY_SELECTORS = [
    "[class*='company']",
    "[class*='Company']",
    "[data-testid*='company']",
    "h4",
]

LOCATION_SELECTORS = [
    "[class*='location']",
    "[class*='Location']",
    "[data-testid*='location']",
]

DESCRIPTION_SELECTORS = [
    "[class*='description']",
    "[class*='Description']",
    "[data-testid*='description']",
    "section",
    "article",
]


async def _text(element) -> str:
    if not element:
        return ""
    try:
        return " ".join((await element.inner_text()).split())
    except Exception:
        return ""


async def _first_text(card, selectors: List[str]) -> str:
    for selector in selectors:
        element = await card.query_selector(selector)
        value = await _text(element)
        if value:
            return value
    return ""


async def _first_href(card, base_url: str) -> str:
    anchors = []
    own_href = await card.get_attribute("href")
    if own_href:
        anchors.append(card)
    anchors.extend(await card.query_selector_all("a[href]"))
    for anchor in anchors:
        href = await anchor.get_attribute("href")
        if not href:
            continue
        href = href.strip()
        if href.startswith("//"):
            href = f"https:{href}"
        elif href.startswith("/"):
            href = f"{base_url.rstrip('/')}{href}"
        if href.startswith("https://") and ("job" in href.lower() or "career" in href.lower()):
            return href.split("#")[0]
    return ""


def _looks_like_noise(title: str) -> bool:
    cleaned = title.strip().lower()
    return (
        len(cleaned) < 3
        or cleaned in {"jobs", "search", "apply", "login", "sign in", "home"}
        or len(cleaned) > 160
    )


async def search_public_job_board(
    *,
    source: str,
    query: str,
    location: str,
    max_results: int,
    search_urls: List[str],
    base_url: str,
    blocked_markers: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    query = (query or "").strip()
    location = (location or "").strip()
    if not query:
        raise ValueError("Query cannot be empty")

    max_results = max(1, min(max_results or 20, 100))
    blocked_markers = [marker.lower() for marker in (blocked_markers or [])]
    jobs: List[Dict[str, str]] = []
    seen_urls = set()

    try:
        if hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

    async with async_playwright() as p:
        logger.info("Launching Chromium for %s public job search.", source)
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()
        detail_page = await context.new_page()

        try:
            for search_url in search_urls:
                if len(jobs) >= max_results:
                    break

                logger.info("%s search URL: %s", source, search_url)
                try:
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2500)
                except Exception as exc:
                    logger.warning("%s search navigation failed: %s", source, exc)
                    continue

                page_text = (await page.content()).lower()
                if any(marker in page_text for marker in blocked_markers):
                    logger.warning("%s presented a block/login wall. Returning visible results only.", source)
                    continue

                for _ in range(5):
                    await page.mouse.wheel(0, 1600)
                    await page.wait_for_timeout(500)

                cards = []
                for selector in CARD_SELECTORS:
                    found = await page.query_selector_all(selector)
                    if len(found) >= 3:
                        cards = found
                        logger.info("%s found %s cards via selector %s", source, len(cards), selector)
                        break

                if not cards:
                    anchors = await page.query_selector_all("a[href*='job'], a[href*='career']")
                    cards = anchors

                for card in cards:
                    if len(jobs) >= max_results:
                        break

                    title = await _first_text(card, TITLE_SELECTORS)
                    if _looks_like_noise(title):
                        title = await _text(card)
                        title = title.split("\n")[0].strip()
                    if _looks_like_noise(title):
                        continue

                    apply_url = await _first_href(card, base_url)
                    if not apply_url or apply_url in seen_urls:
                        continue
                    seen_urls.add(apply_url)

                    company = await _first_text(card, COMPANY_SELECTORS) or "N/A"
                    job_location = await _first_text(card, LOCATION_SELECTORS) or location or "N/A"
                    description = ""

                    try:
                        await detail_page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)
                        await detail_page.wait_for_timeout(1000)
                        for selector in DESCRIPTION_SELECTORS:
                            element = await detail_page.query_selector(selector)
                            candidate = await _text(element)
                            if len(candidate) > len(description):
                                description = candidate
                    except Exception as exc:
                        logger.warning("%s detail load failed for %s: %s", source, apply_url, exc)

                    if not description:
                        description = f"{title} at {company} in {job_location}."

                    jobs.append({
                        "title": title,
                        "company": company,
                        "location": job_location,
                        "description": description,
                        "apply_url": apply_url,
                        "source": source,
                    })
        finally:
            await detail_page.close()
            await browser.close()

    logger.info("%s search finished. Extracted %s jobs.", source, len(jobs))
    return jobs
