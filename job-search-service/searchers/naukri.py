import logging
import sys
import asyncio
import random
from playwright.async_api import async_playwright

logger = logging.getLogger("job-search-service.naukri")

# Approved modern desktop browser User-Agents for compatibility testing and rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

def format_slug(val: str) -> str:
    """Helper to convert string into Naukri URL-friendly slug."""
    # Remove special characters, keep alphanumeric and spaces
    cleaned = "".join([c if c.isalnum() or c == " " else "" for c in val])
    # Lowercase and replace spaces with single hyphen
    slug = "-".join(cleaned.lower().split())
    return slug

async def search_naukri(query: str, location: str = "", max_results: int = 20) -> list[dict]:
    """
    Search Naukri.com for jobs matching the query and location using headless Firefox.
    Raises Exception if the search fails.
    """
    logger.info(f"Starting Naukri search for Query: '{query}', Location: '{location}'")
    
    query_slug = format_slug(query)
    location_slug = format_slug(location)
    
    if not query_slug:
        logger.error("Empty query provided. Search aborted.")
        raise ValueError("Query cannot be empty")
        
    max_results = max(1, min(max_results, 100))

    def build_search_url(page_number: int = 1) -> str:
        page_suffix = "" if page_number == 1 else f"-{page_number}"
        if location_slug:
            return f"https://www.naukri.com/{query_slug}-jobs-in-{location_slug}{page_suffix}"
        return f"https://www.naukri.com/{query_slug}-jobs{page_suffix}"

    url = build_search_url()
        
    logger.info(f"Formed Naukri Search URL: {url}")
    
    jobs = []
    
    # Configure event loop policy for Windows if needed inside task context
    if sys.platform == 'win32':
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass # ignore if already set
            
    try:
        async with async_playwright() as p:
            logger.info("Playwright initialized. Launching Firefox in headless mode...")
            
            # Launch headless Firefox (bypasses Akamai firewall out of the box)
            browser = await p.firefox.launch(headless=True)
            logger.info("Firefox launched successfully.")
            
            # Setup context with rotated User-Agent
            ua = random.choice(USER_AGENTS)
            logger.info(f"Using rotated User-Agent for compatibility testing: {ua}")
            context = await browser.new_context(
                user_agent=ua,
                viewport={"width": 1280, "height": 800}
            )
            
            page = await context.new_page()
            
            max_pages = max(2, min(8, (max_results // 10) + 4))
            max_raw_results = max_results * 3
            seen_job_urls = set()

            for page_number in range(1, max_pages + 1):
                page_url = build_search_url(page_number)

                max_retries = 3
                backoff_factor = 2.0

                for attempt in range(max_retries):
                    try:
                        logger.info(f"Navigating to Naukri search page {page_number} (Attempt {attempt + 1}/{max_retries}): {page_url}")
                        await page.goto(page_url, wait_until="load", timeout=30000)
                        break
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logger.error(f"Failed to navigate to {page_url} after {max_retries} attempts: {e}")
                            await browser.close()
                            return jobs
                        sleep_time = backoff_factor ** attempt
                        logger.warning(f"Navigation failed: {e}. Retrying in {sleep_time} seconds...")
                        await asyncio.sleep(sleep_time)

                page_title = await page.title()
                page_content = await page.content()

                if "Access Denied" in page_title or "access denied" in page_content.lower():
                    logger.warning("Naukri returned Access Denied (Temporary block/Rate limit). Failing gracefully.")
                    await browser.close()
                    return jobs

                if "captcha" in page_title.lower() or "captcha" in page_content.lower() or "security check" in page_content.lower():
                    logger.warning("Naukri presented a CAPTCHA security check. Failing gracefully to remain compliant.")
                    await browser.close()
                    return jobs

                logger.info("Page loaded. Waiting for job list card container...")

                job_selectors = [
                    "div.srp-jobtuple-wrapper",
                    "div[class*='srp-jobtuple-wrapper']",
                    "article.jobTuple",
                    "a.title"
                ]

                found_selector = None
                for sel in job_selectors:
                    try:
                        await page.wait_for_selector(sel, timeout=10000)
                        found_selector = sel
                        logger.info(f"Found listings using selector: '{sel}'")
                        break
                    except Exception:
                        continue

                if not found_selector:
                    logger.info("No job cards found on this page. Stopping pagination.")
                    break

                if found_selector == "a.title":
                    titles = await page.query_selector_all("a.title")
                    cards = []
                    for t in titles[:30]:
                        parent_handle = await t.evaluate_handle("el => el.closest('.srp-jobtuple-wrapper') || el.closest('[class*=\"jobtuple\"]') || el.parentElement")
                        parent_el = parent_handle.as_element()
                        if parent_el and parent_el not in cards:
                            cards.append(parent_el)
                else:
                    cards = await page.query_selector_all(found_selector)

                logger.info(f"Found {len(cards)} job listing card(s) on page {page_number}.")

                for idx, card in enumerate(cards[:30]):
                    if len(jobs) >= max_raw_results:
                        break

                    try:
                        await asyncio.sleep(0.1)
                        title_el = await card.query_selector("a.title")
                        if not title_el:
                            title_el = await card.query_selector("a[class*='title']")

                        if not title_el:
                            continue

                        title = (await title_el.inner_text()).strip()
                        href = await title_el.get_attribute("href")

                        if href:
                            if href.startswith("//"):
                                apply_url = f"https:{href}"
                            elif href.startswith("/"):
                                apply_url = f"https://www.naukri.com{href}"
                            else:
                                apply_url = href
                        else:
                            apply_url = ""

                        if not apply_url or apply_url in seen_job_urls:
                            continue
                        seen_job_urls.add(apply_url)

                        comp_el = await card.query_selector("a.comp-name")
                        if not comp_el:
                            comp_el = await card.query_selector("[class*='comp-name']")
                        if not comp_el:
                            comp_el = await card.query_selector("a.company")

                        company = ""
                        if comp_el:
                            comp_text = (await comp_el.inner_text()).strip()
                            company = comp_text.split("\n")[0].strip()

                        loc_el = await card.query_selector("span.loc-wrap")
                        if not loc_el:
                            loc_el = await card.query_selector("span.locWdth")
                        if not loc_el:
                            loc_el = await card.query_selector("[class*='loc']")

                        job_location = ""
                        if loc_el:
                            job_location = (await loc_el.inner_text()).strip()
                        else:
                            job_location = location

                        desc_el = await card.query_selector(".job-desc")
                        if not desc_el:
                            desc_el = await card.query_selector("[class*='desc']")

                        description = ""
                        if desc_el:
                            description = (await desc_el.inner_text()).strip()

                        jobs.append({
                            "title": title,
                            "company": company or "N/A",
                            "location": job_location or "N/A",
                            "description": description,
                            "apply_url": apply_url,
                            "source": "Naukri"
                        })

                    except Exception as card_err:
                        logger.warning(f"Error parsing job card index {idx}: {card_err}")
                        continue

                if len(jobs) >= max_raw_results:
                    break

            logger.info("Loading full job descriptions for %s candidate jobs.", min(len(jobs), max_results))
            detail_page = await context.new_page()
            enriched_jobs = []
            description_selectors = [
                "section.styles_job-desc-container__txpYf",
                "div.styles_JDC__dang-inner-html__h0K4t",
                "div.dang-inner-html",
                "section.job-desc",
                "div.job-desc",
                "[class*='job-desc-container']",
                "[class*='job-desc']",
            ]
            for job in jobs:
                if len(enriched_jobs) >= max_results:
                    break
                full_description = ""
                try:
                    await detail_page.goto(
                        job["apply_url"],
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    for selector in description_selectors:
                        element = await detail_page.query_selector(selector)
                        if not element:
                            continue
                        candidate_text = (await element.inner_text()).strip()
                        if len(candidate_text) > len(full_description):
                            full_description = candidate_text
                    if full_description:
                        job["description"] = full_description
                    logger.info(
                        "Job detail loaded for '%s' at '%s': %s characters.",
                        job["title"],
                        job["company"],
                        len(job["description"]),
                    )
                except Exception as detail_error:
                    logger.warning(
                        "Could not load full description for '%s' at '%s': %s",
                        job["title"],
                        job["company"],
                        detail_error,
                    )
                enriched_jobs.append(job)

            await detail_page.close()
            await browser.close()
            logger.info(f"Naukri search finished. Extracted {len(enriched_jobs)} enriched jobs.")
            return enriched_jobs
            
    except Exception as e:
        logger.error(f"Failed to perform search: {e}")
        raise e
