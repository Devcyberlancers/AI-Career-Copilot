import logging

import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.models.user import User
from app.models.auth_tokens import EmailVerificationToken, PasswordResetToken
from app.schemas.user import UserSignup, UserLogin
from app.schemas.notifications import ForgotPasswordRequest, ResetPasswordRequest, VerifyEmailRequest
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.services.email_notification_service import (
    BASE_FRONTEND_URL,
    EMAIL_OUTBOX_DIR,
    EMAIL_PROVIDER,
    PASSWORD_RESET_TOKEN_EXPIRY_MINUTES,
    EMAIL_TOKEN_EXPIRY_MINUTES,
    generate_secure_token,
    hash_token,
    send_template,
    send_welcome_email,
)

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

FRONTEND_VERIFY_EMAIL_PATH = os.getenv("FRONTEND_VERIFY_EMAIL_PATH", "/verify-email")
FRONTEND_RESET_PASSWORD_PATH = os.getenv("FRONTEND_RESET_PASSWORD_PATH", "/reset-password")


def _verification_url(token: str) -> str:
    return f"{BASE_FRONTEND_URL}{FRONTEND_VERIFY_EMAIL_PATH}?token={token}"


def _reset_url(token: str) -> str:
    return f"{BASE_FRONTEND_URL}{FRONTEND_RESET_PASSWORD_PATH}?token={token}"


def _create_email_verification_token(db: Session, user: User) -> str:
    token = generate_secure_token()
    db.add(EmailVerificationToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=EMAIL_TOKEN_EXPIRY_MINUTES),
    ))
    db.commit()
    return token


def _create_password_reset_token(db: Session, user: User) -> str:
    token = generate_secure_token()
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=datetime.datetime.utcnow() + datetime.timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRY_MINUTES),
    ))
    db.commit()
    return token



class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(user_data: UserSignup, db: Session = Depends(get_db)):
    # Check if user already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password and save user
    hashed_pwd = hash_password(user_data.password)
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed_pwd,
        is_admin=False,
        desired_role=user_data.desired_role,
        location=user_data.location,
        skills=user_data.skills
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    try:
        verification_token = _create_email_verification_token(db, new_user)
        send_welcome_email(new_user.email, new_user.name, db=db, user_id=new_user.id)
        send_template(
            to_email=new_user.email,
            template_key="verify_email",
            context={
                "name": new_user.name,
                "verify_url": _verification_url(verification_token),
                "expires_at": (datetime.datetime.utcnow() + datetime.timedelta(minutes=EMAIL_TOKEN_EXPIRY_MINUTES)).isoformat(),
            },
            db=db,
            user_id=new_user.id,
        )
    except Exception as exc:
        logger.warning("Welcome or verification email failed for user id=%s: %s", new_user.id, exc)

    return {"message": "Account created successfully"}

@router.post("/login")
def login(login_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == login_data.email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    access_token = create_access_token(data={"sub": user.email, "type": "access"})
    refresh_token = create_refresh_token(data={"sub": user.email})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "is_admin": user.is_admin,
        },
    }


@router.post("/refresh")
def refresh_access_token(
    token_data: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not refresh credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(
        token_data.refresh_token,
        expected_type="refresh",
    )
    if payload is None:
        logger.warning("Refresh failed: refresh token validation failed")
        raise credentials_exception

    email = payload.get("sub")
    if not email:
        logger.warning("Refresh failed: refresh token is missing sub")
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        logger.warning("Refresh failed: user not found for subject=%s", email)
        raise credentials_exception

    access_token = create_access_token(
        data={"sub": user.email, "type": "access"}
    )
    refresh_token = create_refresh_token(data={"sub": user.email})
    logger.info("Refresh succeeded for user id=%s", user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "is_admin": user.is_admin,
        },
    }

@router.post("/auth/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    generic_message = "If an account exists for this email, a reset link has been sent."
    is_production = os.getenv("ENVIRONMENT", "development").strip().lower() in {"production", "prod"}
    user = db.query(User).filter(User.email == request.email).first()
    email_sent = False
    reset_url = None
    if user:
        token = _create_password_reset_token(db, user)
        reset_url = _reset_url(token)
        try:
            email_sent = send_template(
                to_email=user.email,
                template_key="forgot_password",
                context={"name": user.name, "reset_url": reset_url},
                db=db,
                user_id=user.id,
            )
        except Exception as exc:
            logger.warning("Forgot password email failed for user id=%s: %s", user.id, exc)

    if is_production:
        return {"message": generic_message}

    if not user:
        return {
            "message": "No account exists for that email in this local database.",
            "user_found": False,
            "email_sent": False,
            "email_provider": EMAIL_PROVIDER,
            "outbox_dir": str(EMAIL_OUTBOX_DIR),
        }

    local_hint = " Check backend/email_outbox for the reset email file." if EMAIL_PROVIDER == "file" else ""
    return {
        "message": generic_message + local_hint,
        "user_found": True,
        "email_sent": email_sent,
        "email_provider": EMAIL_PROVIDER,
        "outbox_dir": str(EMAIL_OUTBOX_DIR) if EMAIL_PROVIDER == "file" else None,
        "reset_url": reset_url if EMAIL_PROVIDER == "file" else None,
    }


@router.post("/auth/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(request.token)
    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used == False,  # noqa: E712
    ).first()
    if not token_row or token_row.expires_at <= datetime.datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token is invalid or expired.")

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reset token is invalid or expired.")

    user.password_hash = hash_password(request.new_password)
    token_row.used = True
    token_row.used_at = datetime.datetime.utcnow()
    db.commit()

    try:
        send_template(
            to_email=user.email,
            template_key="password_changed",
            context={"name": user.name},
            db=db,
            user_id=user.id,
        )
    except Exception as exc:
        logger.warning("Password changed email failed for user id=%s: %s", user.id, exc)

    return {"message": "Password reset successfully."}


@router.post("/auth/verify-email")
def verify_email(request: VerifyEmailRequest, db: Session = Depends(get_db)):
    token_hash = hash_token(request.token)
    token_row = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token_hash == token_hash,
        EmailVerificationToken.used == False,  # noqa: E712
    ).first()
    if not token_row or token_row.expires_at <= datetime.datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token is invalid or expired.")

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token is invalid or expired.")

    user.email_verified = True
    user.email_verified_at = datetime.datetime.utcnow()
    token_row.used = True
    token_row.used_at = datetime.datetime.utcnow()
    db.commit()
    return {"message": "Email verified successfully."}

