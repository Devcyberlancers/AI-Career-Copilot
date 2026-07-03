import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.user import User
from app.auth.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login", auto_error=False)
logger = logging.getLogger("uvicorn.error")

def get_current_user(
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    logger.info(
        "Authentication dependency: bearer token received=%s length=%s",
        bool(token),
        len(token) if token else 0,
    )
    if not token:
        logger.warning("Authentication failed: bearer token is missing")
        raise credentials_exception
        
    payload = decode_access_token(token, expected_type="access")
    if payload is None:
        logger.warning("Authentication failed: JWT validation rejected the token")
        raise credentials_exception
        
    email: str = payload.get("sub")
    if not email:
        logger.warning("Authentication failed: JWT is missing the sub claim")
        raise credentials_exception
        
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger.warning(
            "Authentication failed: no user exists for JWT subject=%s",
            email,
        )
        raise credentials_exception

    logger.info("Authenticated user id=%s email=%s", user.id, user.email)
    return user
