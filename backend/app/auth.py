"""OIDC bearer token validation + server-side RBAC (no trust in UI claims)."""
import os
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str]

@lru_cache(maxsize=1)
def oidc_jwks_url() -> str:
    override = os.getenv("OIDC_JWKS_URL", "")
    if override:
        return override
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    response = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=5)
    response.raise_for_status()
    return response.json()["jwks_uri"]

@lru_cache(maxsize=1)
def jwks_client():
    return jwt.PyJWKClient(oidc_jwks_url(), cache_jwk_set=True, lifespan=300)

def decode_access_token(token: str) -> Principal:
    try:
        signing_key = jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=os.environ["OIDC_ISSUER"].rstrip("/"),
            audience=os.environ["OIDC_AUDIENCE"],
            options={"require": ["exp", "iss", "sub", "aud"]},
            leeway=30,
        )
        raw_roles = claims.get("launchpilot_roles", [])
        if not isinstance(raw_roles, list):
            raw_roles = []
        realm_access = claims.get("realm_access", {})
        realm_roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
        raw_roles = raw_roles + (realm_roles if isinstance(realm_roles, list) else [])
        roles = frozenset(r for r in raw_roles if r in {"launchpilot_admin", "launchpilot_viewer"})
        return Principal(subject=str(claims["sub"]), roles=roles)
    except (jwt.PyJWTError, httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token", headers={"WWW-Authenticate": "Bearer"}) from exc

def principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if os.getenv("AUTH_MODE", "demo") == "demo":
        # Explicitly *only* valid for local demo; lifespan blocks APP_ENV=production.
        return Principal(subject="local-demo-admin", roles=frozenset({"launchpilot_admin", "launchpilot_viewer"}))
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    return decode_access_token(credentials.credentials)

def require_role(role: str):
    def check(user: Principal = Depends(principal)) -> Principal:
        if role not in user.roles and "launchpilot_admin" not in user.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user
    return check

viewer = require_role("launchpilot_viewer")
admin = require_role("launchpilot_admin")
