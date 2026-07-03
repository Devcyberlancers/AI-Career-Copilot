import os
import subprocess
import sys
import time
import requests
import logging
from pathlib import Path

logger = logging.getLogger("app.utils.job_search")

JOB_SEARCH_SERVICE_URL = os.getenv("JOB_SEARCH_SERVICE_URL", "http://localhost:8002")
AUTO_START_JOB_SEARCH_SERVICE = os.getenv("AUTO_START_JOB_SEARCH_SERVICE", "true").lower() == "true"
SERVICE_START_TIMEOUT_SECONDS = int(os.getenv("JOB_SEARCH_SERVICE_START_TIMEOUT", "20"))

def get_project_root() -> Path:
    return Path(__file__).resolve().parents[3]

def is_job_search_service_running() -> bool:
    try:
        response = requests.get(f"{JOB_SEARCH_SERVICE_URL}/", timeout=2)
        return response.status_code == 200
    except requests.RequestException:
        return False

def get_service_python(service_dir: Path) -> str:
    configured_python = os.getenv("JOB_SEARCH_SERVICE_PYTHON")
    if configured_python:
        return configured_python

    venv_python = service_dir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)

    return sys.executable

def start_job_search_service() -> bool:
    if not AUTO_START_JOB_SEARCH_SERVICE:
        return False

    service_dir = get_project_root() / "job-search-service"
    if not service_dir.exists():
        logger.error("Job search service directory not found at %s", service_dir)
        return False

    python_executable = get_service_python(service_dir)
    log_path = service_dir / "job-search-service.log"
    log_file = open(log_path, "a", encoding="utf-8")

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    try:
        subprocess.Popen(
            [
                python_executable,
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8002",
            ],
            cwd=str(service_dir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=False,
            creationflags=creationflags,
        )
    except Exception as exc:
        log_file.close()
        logger.error("Failed to start job search service automatically: %s", exc)
        return False

    deadline = time.time() + SERVICE_START_TIMEOUT_SECONDS
    while time.time() < deadline:
        if is_job_search_service_running():
            logger.info("Job search service started automatically.")
            return True
        time.sleep(0.5)

    logger.error("Job search service did not become ready within %s seconds.", SERVICE_START_TIMEOUT_SECONDS)
    return False

def ensure_job_search_service() -> bool:
    if is_job_search_service_running():
        return True
    logger.info("Job search service is not running. Attempting automatic startup.")
    return start_job_search_service()

def search_jobs_for_user(user_id: int, query: str, location: str = "", max_results: int = 20, source: str = "Naukri") -> dict:
    """
    Search jobs via the job-search-service.
    This will fetch jobs from Naukri and automatically store them in the database.
    """
    payload = {
        "user_id": user_id,
        "query": query,
        "location": location,
        "max_results": max(1, min(max_results or 20, 100)),
        "source": source,
    }

    logger.info(f"Triggering {source} job search for user {user_id} with query: '{query}', location: '{location}'")

    if not ensure_job_search_service():
        raise RuntimeError(
            "Job search service could not be started automatically. "
            "Check job-search-service/job-search-service.log."
        )

    response = requests.post(
        f"{JOB_SEARCH_SERVICE_URL}/search-jobs",
        json=payload,
        timeout=300
    )
    response.raise_for_status()
    data = response.json()

    if isinstance(data, dict) and data.get("success") is False:
        raise RuntimeError(data.get("error") or "Job search failed")

    if isinstance(data, list):
        return {
            "success": True,
            "query": query,
            "location": location,
            "max_results": payload["max_results"],
            "source": source,
            "jobs_found": len(data),
            "jobs_stored": 0,
            "jobs_skipped": 0,
            "jobs": data
        }

    return data

def trigger_job_search(user_id: int, query: str, location: str = "") -> bool:
    """
    Fire-and-forget-compatible wrapper used by auth/profile flows.
    """
    try:
        search_jobs_for_user(user_id, query, location)
        logger.info(f"Job search triggered successfully for user {user_id}")
        return True
    except requests.exceptions.Timeout:
        logger.error(f"Job search timed out for user {user_id}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Could not connect to job search service at {JOB_SEARCH_SERVICE_URL}")
        return False
    except Exception as e:
        logger.error(f"Error triggering job search for user {user_id}: {str(e)}")
        return False
