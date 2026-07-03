from urllib.parse import quote_plus

from .public_job_board import search_public_job_board


def _urls(query: str, location: str) -> list[str]:
    q = quote_plus(query)
    loc = quote_plus(location) if location else ""
    urls = [f"https://www.foundit.in/search/{q}-jobs"]
    if loc:
        urls.insert(0, f"https://www.foundit.in/search/{q}-jobs-in-{loc}")
    return urls


async def search_foundit(query: str, location: str = "", max_results: int = 20) -> list[dict]:
    return await search_public_job_board(
        source="Foundit",
        query=query,
        location=location,
        max_results=max_results,
        search_urls=_urls(query, location),
        base_url="https://www.foundit.in",
        blocked_markers=["captcha", "access denied"],
    )


async def search_jobs(candidate_profile: dict) -> list[dict]:
    return await search_foundit(
        candidate_profile.get("query") or candidate_profile.get("desired_role") or "",
        candidate_profile.get("location") or "",
        candidate_profile.get("max_results") or 20,
    )
