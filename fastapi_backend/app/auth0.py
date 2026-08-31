"""
Helper for verifying an Auth0 access token and fetching the social profile.

Flow used by this project (Authorization Code / SPA flow handled entirely
on the FRONTEND via Auth0's hosted login page + Google/Facebook connections):

1. Frontend redirects the user to Auth0's Universal Login (Google/Facebook
   button shown there because those social connections are enabled on the
   Auth0 tenant).
2. Auth0 redirects back to the frontend with an access_token (via Auth0 SPA
   SDK / auth0.js).
3. Frontend sends that access_token to our backend: POST /auth/social-login
4. Backend calls Auth0's /userinfo endpoint with the token to verify it and
   fetch the user's profile (id, email, name, provider).
5. Backend creates the user if new, then issues OUR OWN JWT access/refresh
   tokens (so the rest of the API only ever has to deal with one token
   format).

This keeps token verification simple (no JWKS/RS256 validation code needed)
while still being secure, because /userinfo is called server-to-server and
Auth0 rejects invalid/expired tokens itself.
"""

import httpx
from fastapi import HTTPException, status

from app.config import settings


async def get_auth0_profile(auth0_access_token: str) -> dict:
    if not settings.auth0_domain:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth0 is not configured on the server (.env AUTH0_DOMAIN missing).",
        )

    url = f"https://{settings.auth0_domain}/userinfo"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {auth0_access_token}"})

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Auth0 access token",
        )

    data = resp.json()
    # Example Auth0 /userinfo payload:
    # {
    #   "sub": "google-oauth2|1234567890",
    #   "name": "Jane Doe",
    #   "email": "jane@example.com",
    #   "picture": "...",
    #   ...
    # }
    provider = "google" if "google" in data.get("sub", "") else (
        "facebook" if "facebook" in data.get("sub", "") else "auth0"
    )

    return {
        "sub": data.get("sub"),
        "email": data.get("email"),
        "name": data.get("name") or data.get("nickname") or "Social User",
        "provider": provider,
    }
