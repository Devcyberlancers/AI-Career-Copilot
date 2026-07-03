from urllib.parse import quote_plus

from .public_job_board import search_public_job_board


def _urls(query: str, location: str) -> list[str]:
    q = quote_plus(query)
    loc = quote_plus(location) if location else ""
    urls = [f"https://in.indeed.com/jobs?q={q}"]
    if loc:
        urls.insert(0, f"https://in.indeed.com/jobs?q={q}&l={loc}")
    return urls


async def search_indeed(query: str, location: str = "", max_results: int = 20) -> list[dict]:
    return await search_public_job_board(
        source="Indeed",
        query=query,
        location=location,
        max_results=max_results,
        search_urls=_urls(query, location),
        base_url="https://in.indeed.com",
        blocked_markers=["captcha", "verify you are human", "additional verification"],
    )


async def search_jobs(candidate_profile: dict) -> list[dict]:
    return await search_indeed(
        candidate_profile.get("query") or candidate_profile.get("desired_role") or "",
        candidate_profile.get("location") or "",
        candidate_profile.get("max_results") or 20,
    )
