"""Production authentication — bcrypt passwords and signed JWT tokens."""

import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from shared.configs.settings import get_settings

settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_users_db: dict[str, dict] = {}
_refresh_tokens: dict[str, str] = {}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    _refresh_tokens[token] = subject
    return token


def decode_token(token: str, expected_type: str = "access") -> dict:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc
    if payload.get("type") != expected_type:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token type")
    return payload


def register_user(name: str, email: str, password: str) -> dict:
    if email in _users_db:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")
    _users_db[email] = {
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
        "plan": "free",
    }
    return _users_db[email]


def authenticate_user(email: str, password: str) -> dict:
    user = _users_db.get(email)
    if not user or not verify_password(password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return user


def refresh_access_token(refresh_token: str) -> str:
    payload = decode_token(refresh_token, expected_type="refresh")
    subject = payload.get("sub")
    if not subject or _refresh_tokens.get(refresh_token) != subject:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return create_access_token(subject)


async def get_current_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> dict:
    if not token:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token, expected_type="access")
    email = payload.get("sub")
    user = _users_db.get(email)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


async def get_optional_user(token: Annotated[str | None, Depends(oauth2_scheme)]) -> dict | None:
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


CurrentUserDep = Annotated[dict, Depends(get_current_user)]
