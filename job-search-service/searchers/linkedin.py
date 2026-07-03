import asyncio
import logging
import random
import sys
from urllib.parse import urlencode

from playwright.async_api import async_playwright

logger = logging.getLogger("job-search-service.linkedin")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]


def build_linkedin_search_url(query: str, location: str = "", start: int = 0) -> str:
    params = {
        "keywords": query,
        "position": "1",
        "pageNum": "0",
        "start": str(start),
    }
    if location:
        params["location"] = location
    return f"https://www.linkedin.com/jobs/search/?{urlencode(params)}"


async def safe_inner_text(element) -> str:
    if not element:
        return ""
    try:
        return (await element.inner_text()).strip()
    except Exception:
        return ""


async def first_text(card, selectors: list[str]) -> str:
    for selector in selectors:
        element = await card.query_selector(selector)
        text = await safe_inner_text(element)
        if text:
            return text
    return ""


async def first_attribute(card, selectors: list[str], attribute: str) -> str:
    for selector in selectors:
        element = await card.query_selector(selector)
        if not element:
            continue
        value = await element.get_attribute(attribute)
        if value:
            return value.strip()
    return ""


async def search_linkedin(query: str, location: str = "", max_results: int = 20) -> list[dict]:
    """
    Search public LinkedIn job listings.
    LinkedIn may show auth walls or rate limits; in those cases this returns
    the jobs already visible on the public results page instead of attempting
    to bypass access controls.
    """
    query = (query or "").strip()
    location = (location or "").strip()
    if not query:
        raise ValueError("Query cannot be empty")

    max_results = max(1, min(max_results, 100))
    logger.info("Starting LinkedIn search for Query: '%s', Location: '%s'", query, location)

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    jobs = []
    seen_urls = set()
    max_pages = max(2, min(5, (max_results // 10) + 2))

    async with async_playwright() as p:
        logger.info("Playwright initialized. Launching Chromium for LinkedIn search...")
        browser = await p.chromium.launch(headless=True)
        ua = random.choice(USER_AGENTS)
        context = await browser.new_context(
            user_agent=ua,
            viewport={"width": 1366, "height": 900},
            locale="en-US",
        )
        page = await context.new_page()

        try:
            for page_index in range(max_pages):
                if len(jobs) >= max_results:
                    break

                start = page_index * 25
                url = build_linkedin_search_url(query, location, start)
                logger.info("Navigating to LinkedIn search page %s: %s", page_index + 1, url)

                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    await page.wait_for_timeout(2500)
                except Exception as nav_error:
                    logger.warning("LinkedIn navigation failed: %s", nav_error)
                    break

                content = (await page.content()).lower()
                title = (await page.title()).lower()
                if "authwall" in content or "sign in" in title or "login" in title:
                    logger.warning("LinkedIn presented a login/auth wall. Returning public results found so far.")
                    break

                for _ in range(4):
                    await page.mouse.wheel(0, 1600)
                    await page.wait_for_timeout(700)

                card_selectors = [
                    "ul.jobs-search__results-list li",
                    "div.base-card",
                    "li[class*='jobs-search-results']",
                    "a.base-card__full-link",
                ]

                cards = []
                for selector in card_selectors:
                    found = await page.query_selector_all(selector)
                    if found:
                        logger.info("Found %s LinkedIn cards using selector '%s'", len(found), selector)
                        cards = found
                        break

                if not cards:
                    logger.info("No LinkedIn job cards found on this page.")
                    break

                for card in cards:
                    if len(jobs) >= max_results:
                        break

                    title_text = await first_text(card, [
                        "h3.base-search-card__title",
                        "h3",
                        "[class*='title']",
                    ])
                    company = await first_text(card, [
                        "h4.base-search-card__subtitle",
                        "a.hidden-nested-link",
                        "[class*='subtitle']",
                        "[class*='company']",
                    ])
                    job_location = await first_text(card, [
                        "span.job-search-card__location",
                        "[class*='location']",
                    ])
                    apply_url = await first_attribute(card, [
                        "a.base-card__full-link",
                        "a[href*='/jobs/view/']",
                        "a",
                    ], "href")

                    if not title_text or not apply_url:
                        continue
                    if apply_url.startswith("//"):
                        apply_url = f"https:{apply_url}"
                    apply_url = apply_url.split("?")[0]
                    if "linkedin.com" not in apply_url or apply_url in seen_urls:
                        continue
                    seen_urls.add(apply_url)

                    jobs.append({
                        "title": title_text,
                        "company": company or "N/A",
                        "location": job_location or location or "N/A",
                        "description": "",
                        "apply_url": apply_url,
                        "source": "LinkedIn",
                    })

                if len(cards) == 0:
                    break

            logger.info("Loading LinkedIn detail pages for %s jobs.", len(jobs))
            detail_page = await context.new_page()
            description_selectors = [
                "div.show-more-less-html__markup",
                "section.description",
                "div.description__text",
                "[class*='description']",
            ]

            for job in jobs:
                try:
                    await detail_page.goto(job["apply_url"], wait_until="domcontentloaded", timeout=30000)
                    await detail_page.wait_for_timeout(1200)
                    full_description = ""
                    for selector in description_selectors:
                        element = await detail_page.query_selector(selector)
                        text = await safe_inner_text(element)
                        if len(text) > len(full_description):
                            full_description = text
                    if full_description:
                        job["description"] = full_description
                    else:
                        job["description"] = f"{job['title']} at {job['company']} in {job['location']}."
                    logger.info(
                        "LinkedIn detail loaded for '%s' at '%s': %s characters.",
                        job["title"],
                        job["company"],
                        len(job["description"]),
                    )
                except Exception as detail_error:
                    logger.warning(
                        "Could not load LinkedIn detail for '%s' at '%s': %s",
                        job["title"],
                        job["company"],
                        detail_error,
                    )
                    if not job["description"]:
                        job["description"] = f"{job['title']} at {job['company']} in {job['location']}."

            await detail_page.close()
        finally:
            await browser.close()

    logger.info("LinkedIn search finished. Extracted %s jobs.", len(jobs))
    return jobs
