from urllib.parse import urlparse

from sqlalchemy.orm import Query

from app.models.job import Job

from typing import Optional

SUPPORTED_JOB_SOURCE = "Naukri"
SUPPORTED_JOB_SOURCES = ("Naukri", "LinkedIn", "Foundit", "Wellfound", "Hirist", "Cutshort", "Indeed")
SUPPORTED_JOB_DOMAINS = {
    "Naukri": "naukri.com",
    "LinkedIn": "linkedin.com",
    "Foundit": ("foundit.in", "foundit.com"),
    "Wellfound": "wellfound.com",
    "Hirist": ("hirist.tech", "hirist.com"),
    "Cutshort": "cutshort.io",
    "Indeed": ("indeed.com", "indeed.co.in"),
}
SUPPORTED_JOB_DOMAIN = SUPPORTED_JOB_DOMAINS[SUPPORTED_JOB_SOURCE]


def is_valid_naukri_url(url: Optional[str]) -> bool:
    return is_valid_job_url_for_source(url, "Naukri")


def is_valid_linkedin_url(url: Optional[str]) -> bool:
    return is_valid_job_url_for_source(url, "LinkedIn")


def is_supported_job_source(source: Optional[str]) -> bool:
    return bool(source) and source in SUPPORTED_JOB_SOURCES


def is_valid_job_url_for_source(url: Optional[str], source: Optional[str]) -> bool:
    if not url:
        return False
    if not is_supported_job_source(source):
        return False

    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    supported_domains = SUPPORTED_JOB_DOMAINS[source]
    if isinstance(supported_domains, str):
        supported_domains = (supported_domains,)
    return (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and any(host == domain or host.endswith(f".{domain}") for domain in supported_domains)
    )


def apply_supported_job_filter(query: Query) -> Query:
    return query.filter(
        Job.source.in_(SUPPORTED_JOB_SOURCES),
        Job.apply_url.isnot(None),
    )
