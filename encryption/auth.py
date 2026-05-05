"""Authentication & Authorization — JWT + OAuth2 with FastAPI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordBearer,
)
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from core.config import get_settings

settings = get_settings()

# ── Password hashing (for admin users) ────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 scheme (for interactive API docs) ──────────────────
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# ── API Key scheme (for programmatic access) ──────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# ── Bearer token (for JWT) ────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)


# ── Token Models ──────────────────────────────────────────────

class TokenData(BaseModel):
    """Decoded JWT payload."""
    sub: str  # source_id or user_id
    exp: datetime
    scope: str = "read"


class TokenResponse(BaseModel):
    """OAuth2 token response."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ── JWT Functions ─────────────────────────────────────────────

def create_access_token(
    source_id: str,
    expires_minutes: Optional[int] = None,
    scope: str = "read",
) -> str:
    """Create a JWT access token.

    The token's subject is the source_id — this ties every
    API request to a specific attributed source.
    """
    if expires_minutes is None:
        expires_minutes = settings.jwt_expire_minutes

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )
    payload = {
        "sub": source_id,
        "exp": expire,
        "scope": scope,
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        source_id: str = payload.get("sub", "")
        scope: str = payload.get("scope", "read")
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

        if not source_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: no subject",
            )

        return TokenData(sub=source_id, exp=exp, scope=scope)

    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
        )


# ── Dependency: Get current source from token ─────────────────

async def get_current_source(
    authorization: Optional[HTTPAuthorizationCredentials] = Security(
        bearer_scheme
    ),
    token: Optional[str] = Depends(oauth2_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> TokenData:
    """FastAPI dependency: authenticate and return source identity.
    
    In development mode, auth is optional — returns a guest identity.
    """
    from core.config import get_settings
    settings = get_settings()
    
    token_str = None

    if authorization:
        token_str = authorization.credentials
    elif token:
        token_str = token
    elif api_key:
        return TokenData(
            sub=api_key,
            exp=datetime.now(timezone.utc) + timedelta(days=365),
            scope="read-write",
        )

    if not token_str:
        if settings.env == "development":
            return TokenData(
                sub="dev-guest",
                exp=datetime.now(timezone.utc) + timedelta(days=365),
                scope="read-write",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required (Bearer token, OAuth2, or X-API-Key)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verify_token(token_str)


async def get_current_source_write(
    token_data: TokenData = Depends(get_current_source),
) -> TokenData:
    """Require write scope for uploads."""
    if "write" not in token_data.scope and token_data.scope != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Write access required",
        )
    return token_data


# ── Password utilities (for admin panel) ──────────────────────

def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain, hashed)
