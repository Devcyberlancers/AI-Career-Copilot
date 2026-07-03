import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from datetime import timedelta
from typing import Optional

import bcrypt
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger("uvicorn.error")

SECRET_KEY = os.getenv("JWT_SECRET", "copilot_jwt_secret_dev_key_2026_xYz987")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    if ALGORITHM != "HS256":
        raise ValueError("Only HS256 is supported.")

    to_encode = data.copy()
    expires_in = expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.setdefault("type", "access")
    to_encode.update({
        "iat": int(time.time()),
        "exp": int(time.time() + expires_in.total_seconds()),
    })

    header = {"alg": ALGORITHM, "typ": "JWT"}
    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(to_encode, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"


def create_refresh_token(data: dict) -> str:
    refresh_data = data.copy()
    refresh_data["type"] = "refresh"
    return create_access_token(
        refresh_data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_access_token(
    token: str,
    expected_type: str = "access",
) -> Optional[dict]:
    token_length = len(token) if isinstance(token, str) else 0
    token_fingerprint = (
        hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
        if isinstance(token, str) and token
        else "missing"
    )
    logger.info(
        "JWT diagnostic: token received=%s length=%s fingerprint=%s expected_type=%s",
        bool(token),
        token_length,
        token_fingerprint,
        expected_type,
    )

    try:
        if ALGORITHM != "HS256":
            logger.error(
                "JWT diagnostic: wrong configured algorithm=%s; only HS256 is supported",
                ALGORITHM,
            )
            return None

        if not isinstance(token, str) or token.count(".") != 2:
            logger.warning("JWT diagnostic: malformed token structure")
            return None

        encoded_header, encoded_payload, encoded_signature = token.split(".")
        header = json.loads(_base64url_decode(encoded_header))
        token_algorithm = header.get("alg")
        if token_algorithm != ALGORITHM:
            logger.warning(
                "JWT diagnostic: wrong algorithm token_alg=%s expected_alg=%s",
                token_algorithm,
                ALGORITHM,
            )
            return None

        signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
        expected_signature = hmac.new(
            SECRET_KEY.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        supplied_signature = _base64url_decode(encoded_signature)
        if not hmac.compare_digest(expected_signature, supplied_signature):
            logger.warning(
                "JWT diagnostic: invalid signature fingerprint=%s",
                token_fingerprint,
            )
            return None

        payload = json.loads(_base64url_decode(encoded_payload))
        expiration = payload.get("exp")
        if expiration is None:
            logger.warning("JWT diagnostic: malformed token missing exp claim")
            return None
        if float(expiration) <= time.time():
            logger.warning(
                "JWT diagnostic: expired token expired_at=%s current_time=%s",
                expiration,
                int(time.time()),
            )
            return None

        subject = payload.get("sub")
        if not subject:
            logger.warning("JWT diagnostic: missing sub claim")
            return None

        token_type = payload.get("type", "access")
        if token_type != expected_type:
            logger.warning(
                "JWT diagnostic: wrong token type token_type=%s expected_type=%s",
                token_type,
                expected_type,
            )
            return None

        logger.info(
            "JWT diagnostic: token valid subject=%s type=%s",
            subject,
            token_type,
        )
        return payload
    except (
        binascii.Error,
        OverflowError,
        TypeError,
        UnicodeDecodeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "JWT diagnostic: malformed token error=%s",
            exc.__class__.__name__,
        )
        return None
