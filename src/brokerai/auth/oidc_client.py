from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from brokerai.auth.cookies import delete_session_cookie, set_session_cookie
from brokerai.auth.mode import is_oidc_mode
from brokerai.auth.session import SessionManager
from brokerai.auth.store import AuthStore, is_valid_username, normalize_optional_name
from brokerai.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

_OIDC_STATE_COOKIE = "brokerai_oidc_state"
_OIDC_STATE_MAX_AGE = 600


@dataclass(frozen=True)
class OidcClaims:
    sub: str
    username: str
    first_name: str | None
    last_name: str | None
    email: str | None


@dataclass(frozen=True)
class OidcMetadata:
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    end_session_endpoint: str | None


class OidcClient:
    """OIDC authorization-code + PKCE client for self-hosted identity providers."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._state_serializer = URLSafeTimedSerializer(
            self.settings.secret_key,
            salt="brokerai-oidc-state",
        )
        self._metadata: OidcMetadata | None = None

    def _httpx_verify(self) -> bool:
        """Whether outbound OIDC HTTP clients validate TLS certificates."""
        return self.settings.oidc_tls_verify

    async def metadata(self) -> OidcMetadata:
        if self._metadata is not None:
            return self._metadata
        discovery_url = f"{self.settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=15.0, verify=self._httpx_verify()) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            payload = response.json()
        self._metadata = OidcMetadata(
            authorization_endpoint=str(payload["authorization_endpoint"]),
            token_endpoint=str(payload["token_endpoint"]),
            jwks_uri=str(payload["jwks_uri"]),
            end_session_endpoint=str(payload["end_session_endpoint"])
            if payload.get("end_session_endpoint")
            else None,
        )
        return self._metadata

    def redirect_uri(self, request: Request) -> str:
        if self.settings.oidc_redirect_uri:
            return self.settings.oidc_redirect_uri
        forwarded_proto = request.headers.get("x-forwarded-proto")
        forwarded_host = request.headers.get("x-forwarded-host")
        if forwarded_proto and forwarded_host:
            return f"{forwarded_proto}://{forwarded_host}/api/auth/oidc/callback"
        base = str(request.base_url).rstrip("/")
        return f"{base}/api/auth/oidc/callback"

    async def build_login_redirect(self, request: Request, response: Response) -> str:
        if not is_oidc_mode(self.settings):
            raise HTTPException(status_code=404, detail="OIDC auth is not enabled")

        metadata = await self.metadata()
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = create_s256_code_challenge(code_verifier)
        redirect_uri = self.redirect_uri(request)

        signed_state = self._state_serializer.dumps(
            {
                "state": state,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            }
        )
        response.set_cookie(
            key=_OIDC_STATE_COOKIE,
            value=signed_state,
            httponly=True,
            samesite="lax",
            secure=request.headers.get("x-forwarded-proto", "").lower() == "https",
            max_age=_OIDC_STATE_MAX_AGE,
            path="/api/auth/oidc",
        )

        params = {
            "response_type": "code",
            "client_id": self.settings.oidc_client_id,
            "redirect_uri": redirect_uri,
            "scope": self.settings.oidc_scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{metadata.authorization_endpoint}?{urlencode(params)}"

    async def handle_callback(
        self,
        request: Request,
        response: Response,
        *,
        code: str | None,
        state: str | None,
        error: str | None,
        error_description: str | None,
    ) -> str:
        if error:
            detail = error_description or error
            raise HTTPException(status_code=401, detail=f"OIDC login failed: {detail}")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing OIDC callback parameters")

        signed_state = request.cookies.get(_OIDC_STATE_COOKIE)
        if not signed_state:
            raise HTTPException(status_code=400, detail="OIDC state cookie missing")
        try:
            saved = self._state_serializer.loads(signed_state, max_age=_OIDC_STATE_MAX_AGE)
        except (BadSignature, SignatureExpired) as exc:
            raise HTTPException(status_code=400, detail="OIDC state expired or invalid") from exc

        if saved.get("state") != state:
            raise HTTPException(status_code=400, detail="OIDC state mismatch")

        redirect_uri = str(saved["redirect_uri"])
        code_verifier = str(saved["code_verifier"])
        metadata = await self.metadata()

        client = AsyncOAuth2Client(
            client_id=self.settings.oidc_client_id,
            client_secret=self.settings.oidc_client_secret,
            scope=self.settings.oidc_scopes,
            verify=self._httpx_verify(),
        )
        try:
            token = await client.fetch_token(
                metadata.token_endpoint,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        finally:
            await client.aclose()

        claims = await self._verify_id_token(token, metadata)
        parsed = parse_oidc_claims(claims)
        self._enforce_allowed_sub(parsed.sub)

        store = AuthStore(self.settings)
        try:
            record = store.create_or_link_oidc_user(
                oidc_sub=parsed.sub,
                username=parsed.username,
                first_name=parsed.first_name,
                last_name=parsed.last_name,
                email=parsed.email,
            )
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

        session_token = SessionManager(self.settings).create_token(
            record.username,
            oidc_sub=record.oidc_sub,
        )
        set_session_cookie(response, session_token, request)
        response.delete_cookie(_OIDC_STATE_COOKIE, path="/api/auth/oidc")
        return record.username

    async def logout_url(self, request: Request) -> str | None:
        if self.settings.oidc_logout_url:
            return self.settings.oidc_logout_url
        metadata = await self.metadata()
        if not metadata.end_session_endpoint:
            return None
        post_logout = self.settings.oidc_post_logout_redirect_uri or str(request.base_url).rstrip("/")
        params = urlencode({"post_logout_redirect_uri": post_logout})
        return f"{metadata.end_session_endpoint}?{params}"

    async def logout(self, request: Request, response: Response) -> str | None:
        delete_session_cookie(response)
        return await self.logout_url(request)

    async def _verify_id_token(self, token: dict[str, Any], metadata: OidcMetadata) -> dict[str, Any]:
        id_token = token.get("id_token")
        if not id_token:
            raise HTTPException(status_code=401, detail="OIDC provider did not return an ID token")

        async with httpx.AsyncClient(timeout=15.0, verify=self._httpx_verify()) as http_client:
            jwks_response = await http_client.get(metadata.jwks_uri)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()

        from authlib.jose import jwt

        issuer = self.settings.oidc_issuer.rstrip("/")
        try:
            claims = jwt.decode(
                id_token,
                jwks,
                claims_options={
                    "iss": {"essential": True, "values": [issuer, f"{issuer}/"]},
                    "aud": {"essential": True, "values": [self.settings.oidc_client_id]},
                    "exp": {"essential": True},
                },
            )
            claims.validate()
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid OIDC ID token") from exc

        return dict(claims)

    def _enforce_allowed_sub(self, oidc_sub: str) -> None:
        allowed = self.settings.oidc_allowed_sub.strip()
        if allowed and oidc_sub != allowed:
            raise HTTPException(status_code=403, detail="OIDC subject is not allowed for this BrokerAI instance")


def parse_oidc_claims(claims: dict[str, Any]) -> OidcClaims:
    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status_code=401, detail="OIDC token missing subject")

    username = username_from_oidc_claims(claims)
    given_name = claims.get("given_name")
    family_name = claims.get("family_name")
    name = str(claims.get("name") or "").strip()
    first_name = normalize_optional_name(str(given_name).strip() if given_name else None)
    last_name = normalize_optional_name(str(family_name).strip() if family_name else None)
    if not first_name and not last_name and name:
        parts = name.split(None, 1)
        first_name = normalize_optional_name(parts[0])
        last_name = normalize_optional_name(parts[1]) if len(parts) > 1 else None

    email = str(claims.get("email") or "").strip() or None
    return OidcClaims(
        sub=sub,
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )


def username_from_oidc_claims(claims: dict[str, Any]) -> str:
    """Derive a BrokerAI username from OIDC claims."""
    preferred = claims.get("preferred_username") or claims.get("email") or claims.get("sub") or "user"
    candidate = re.sub(r"[^a-z0-9_-]", "", str(preferred).lower())
    if candidate and not candidate[0].isalpha():
        candidate = f"u{candidate}"
    candidate = candidate[:32]
    if is_valid_username(candidate):
        return candidate

    sub = str(claims.get("sub") or "user")
    digest = hashlib.sha256(sub.encode()).hexdigest()[:8]
    fallback = f"user{digest}"
    if is_valid_username(fallback):
        return fallback
    raise HTTPException(status_code=401, detail="Unable to derive a valid username from OIDC claims")
