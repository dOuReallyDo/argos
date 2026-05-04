"""OAuth2 social login — Google, GitHub — integrated with Argos source attribution.

When a user authenticates via Google:
1. They get a JWT tied to their email as source_id
2. First-time users: auto-create a source with their verified email
3. Returning users: all their uploads are attributed to the same source
4. Admin list: certain emails get admin scope
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from httpx_oauth.clients.google import GoogleOAuth2

from core.config import get_settings

from core.models import SourceType
from encryption.auth import create_access_token
from storage.database import AsyncSession, get_db
from storage.repository import SourceRepository

settings = get_settings()
router = APIRouter(tags=["Auth"])

# ── Google OAuth ──────────────────────────────────────────
GOOGLE_CLIENT_ID = settings.google_oauth_client_id
GOOGLE_CLIENT_SECRET = settings.google_oauth_client_secret
GOOGLE_REDIRECT_URI = settings.google_oauth_redirect_uri or (
    f"https://{settings.public_host}/api/auth/google/callback"
    if settings.public_host
    else "http://localhost:8000/api/auth/google/callback"
)

google_oauth = GoogleOAuth2(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)

# Admin list — these emails get full admin access
ADMIN_EMAILS = {"morphblue91@gmail.com", "blonde.trinity.red@gmail.com"}

# ── Login page ────────────────────────────────────────────

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Argos — Login</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        <div class="mb-6">
            <div class="w-16 h-16 bg-indigo-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <svg viewBox="0 0 32 32" class="w-8 h-8" fill="none">
                    <circle cx="16" cy="16" r="14" stroke="#4263eb" stroke-width="2"/>
                    <path d="M10 20l3-6 3 4 3-8 3 10" stroke="#4263eb" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                    <circle cx="16" cy="4" r="2" fill="#4263eb"/>
                </svg>
            </div>
            <h1 class="text-2xl font-bold text-gray-900">Argos RAG</h1>
            <p class="text-gray-500 mt-2">Accedi per caricare e cercare documenti</p>
        </div>
        <a href="/api/auth/google/login" class="flex items-center justify-center gap-3 w-full py-3 px-4 bg-white border-2 border-gray-200 rounded-xl hover:border-gray-300 hover:shadow-sm transition-all text-gray-700 font-medium">
            <svg viewBox="0 0 24 24" class="w-5 h-5">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
            </svg>
            Accedi con Google
        </button>
        <p class="text-xs text-gray-400 mt-6">
            I tuoi documenti sono sempre attribuiti al tuo account verificato.<br>
            Crittografia AES-256-GCM attiva.
        </p>
    </div>
</body>
</html>
"""


@router.get("/login", response_class=HTMLResponse)
async def login_page():
    """Render the login page."""
    return HTMLResponse(content=HTML_LOGIN)


@router.get("/google/login")
async def google_login(request: Request):
    """Redirect to Google for authentication."""
    redirect_uri = str(request.url_for("google_callback"))
    # Override with the actual public URL if behind tunnel
    if settings.public_host and "localhost" in redirect_uri:
        redirect_uri = redirect_uri.replace(
            "http://localhost:8000",
            f"https://{settings.public_host}",
        )
    authorization_url = await google_oauth.get_authorization_url(
        redirect_uri,
        scope=["email", "profile"],
        extras_params={"access_type": "offline"},
    )
    return RedirectResponse(authorization_url)


@router.get("/google/callback", name="google_callback")
async def google_callback(
    request: Request,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback — create source, issue JWT."""
    redirect_uri = str(request.url).split("?")[0]

    try:
        token = await google_oauth.get_access_token(code, redirect_uri)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth authentication failed",
        )

    user_id, user_email = await google_oauth.get_id_email(
        token["access_token"]
    )

    # Create or get source for this email
    source = await SourceRepository.get_or_create(
        db, SourceType.EMAIL, user_email
    )

    # Determine scope
    scope = "admin" if user_email in ADMIN_EMAILS else "read-write"

    # Issue JWT
    jwt_token = create_access_token(source.id, scope=scope)

    # Redirect to UI with token
    frontend_url = settings.frontend_url
    if settings.public_host and "localhost" in frontend_url:
        frontend_url = f"https://{settings.public_host}"

    return RedirectResponse(
        f"{frontend_url}/?token={jwt_token}&source_id={source.id}&email={user_email}&scope={scope}"
    )


@router.get("/me")
async def get_me(request: Request):
    """Return current user info (behind Cloudflare Access)."""
    email = request.headers.get("Cf-Access-Authenticated-User-Email", "")
    return {
        "email": email,
        "authenticated": bool(email),
    }
