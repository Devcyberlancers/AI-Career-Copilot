import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Optional

from .cutshort import search_cutshort
from .foundit import search_foundit
from .hirist import search_hirist
from .indeed import search_indeed
from .linkedin import search_linkedin
from .naukri import search_naukri
from .wellfound import search_wellfound

logger = logging.getLogger("job-search-service.manager")

SearchProvider = Callable[[str, str, int], Awaitable[List[dict]]]


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    search: SearchProvider


class JobSearchManager:
    def __init__(self) -> None:
        self.providers: Dict[str, ProviderConfig] = {
            "Naukri": ProviderConfig("Naukri", search_naukri),
            "LinkedIn": ProviderConfig("LinkedIn", search_linkedin),
            "Foundit": ProviderConfig("Foundit", search_foundit),
            "Wellfound": ProviderConfig("Wellfound", search_wellfound),
            "Hirist": ProviderConfig("Hirist", search_hirist),
            "Cutshort": ProviderConfig("Cutshort", search_cutshort),
            "Indeed": ProviderConfig("Indeed", search_indeed),
        }

    @property
    def supported_sources(self) -> tuple[str, ...]:
        return tuple(self.providers.keys())

    def normalize_source(self, source: Optional[str]) -> str:
        if not source:
            return "Naukri"
        for supported in self.supported_sources:
            if supported.lower() == source.strip().lower():
                return supported
        if source.strip().lower() == "all":
            return "All"
        return "Naukri"

    def normalize_job(self, job: dict, source: str) -> dict:
        return {
            "title": str(job.get("title") or "").strip() or "Untitled Job",
            "company": str(job.get("company") or "").strip() or "N/A",
            "location": str(job.get("location") or "").strip() or "N/A",
            "description": str(job.get("description") or "").strip(),
            "apply_url": str(job.get("apply_url") or "").strip(),
            "source": source,
        }

    def fingerprint(self, job: dict) -> tuple[str, str, str, str]:
        def clean(value: str) -> str:
            return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())

        return (
            clean(job.get("source", "")),
            clean(job.get("title", "")),
            clean(job.get("company", "")),
            clean(job.get("location", "")),
        )

    def dedupe(self, jobs: List[dict]) -> List[dict]:
        seen_urls = set()
        seen_fingerprints = set()
        unique: List[dict] = []
        for job in jobs:
            url = (job.get("apply_url") or "").strip().lower()
            fingerprint = self.fingerprint(job)
            if url and url in seen_urls:
                continue
            if fingerprint in seen_fingerprints:
                continue
            if url:
                seen_urls.add(url)
            seen_fingerprints.add(fingerprint)
            unique.append(job)
        return unique

    async def search_source(self, source: str, query: str, location: str, max_results: int) -> List[dict]:
        normalized_source = self.normalize_source(source)
        provider = self.providers.get(normalized_source)
        if not provider:
            raise ValueError(f"Unsupported job source: {source}")
        raw_jobs = await provider.search(query, location, max_results)
        return [
            self.normalize_job(job, provider.name)
            for job in raw_jobs
            if job.get("apply_url")
        ][:max_results]

    async def search_all(self, query: str, location: str, max_results: int) -> List[dict]:
        per_source_limit = max(1, max_results)
        tasks = [
            self.search_source(source, query, location, per_source_limit)
            for source in self.supported_sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        merged: List[dict] = []
        for source, result in zip(self.supported_sources, results):
            if isinstance(result, Exception):
                logger.warning("Provider %s failed: %s", source, result)
                continue
            merged.extend(result)
        return self.dedupe(merged)[:max_results]


job_search_manager = JobSearchManager()
