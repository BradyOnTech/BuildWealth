from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient, PyJWTError


class HostedIdentityConfigError(ValueError):
    pass


class HostedIdentityExchangeError(ValueError):
    pass


@dataclass(frozen=True)
class HostedIdentityProfile:
    provider: str
    subject: str
    email: str
    display_name: str
    email_verified: bool
    mfa_enabled: bool


def generate_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


def code_challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class OIDCAuthProvider:
    """Generic OIDC authorization-code adapter.

    BuildWealth does not trust unverified browser-provided identity. This
    adapter exchanges the authorization code server-side, validates the ID
    token when required, and verifies the UserInfo subject against it.
    """

    def __init__(self, settings: Any):
        self.settings = settings

    @property
    def provider_name(self) -> str:
        return str(self.settings.auth_oidc_provider_name or "Hosted Identity").strip()

    def is_configured(self) -> bool:
        return all(
            [
                self.provider_name,
                str(self.settings.auth_oidc_client_id or "").strip(),
                str(self.settings.auth_oidc_client_secret or "").strip(),
                str(self.settings.auth_oidc_redirect_uri or "").strip(),
                self._has_discovery() or self._has_explicit_endpoints(),
            ]
        )

    async def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
    ) -> str:
        metadata = await self._metadata()
        authorization_endpoint = str(metadata.get("authorization_endpoint") or "").strip()
        if not authorization_endpoint:
            raise HostedIdentityConfigError("OIDC authorization endpoint is not configured")
        params = {
            "client_id": str(self.settings.auth_oidc_client_id),
            "redirect_uri": str(self.settings.auth_oidc_redirect_uri),
            "response_type": "code",
            "scope": self._scopes(),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{authorization_endpoint}?{urlencode(params)}"

    async def exchange_code_for_profile(
        self,
        *,
        code: str,
        code_verifier: str,
        expected_nonce: str,
    ) -> HostedIdentityProfile:
        metadata = await self._metadata()
        token_endpoint = str(metadata.get("token_endpoint") or "").strip()
        userinfo_endpoint = str(metadata.get("userinfo_endpoint") or "").strip()
        if not token_endpoint or not userinfo_endpoint:
            raise HostedIdentityConfigError("OIDC token and userinfo endpoints are required")

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_auth_method = str(
                getattr(self.settings, "auth_oidc_token_auth_method", "client_secret_basic") or ""
            ).strip().lower()
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": str(self.settings.auth_oidc_redirect_uri),
                "client_id": str(self.settings.auth_oidc_client_id),
                "code_verifier": code_verifier,
            }
            token_auth = None
            if token_auth_method == "client_secret_post":
                token_data["client_secret"] = str(self.settings.auth_oidc_client_secret)
            else:
                token_auth = (
                    str(self.settings.auth_oidc_client_id),
                    str(self.settings.auth_oidc_client_secret),
                )
            token_response = await client.post(
                token_endpoint,
                data=token_data,
                headers={"accept": "application/json"},
                auth=token_auth,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            access_token = str(token_payload.get("access_token") or "").strip()
            if not access_token:
                raise HostedIdentityExchangeError("OIDC token response did not include an access token")
            id_token = str(token_payload.get("id_token") or "").strip()
            id_token_claims = self._validate_id_token(
                id_token,
                access_token=access_token,
                metadata=metadata,
                expected_nonce=expected_nonce,
            )

            userinfo_response = await client.get(
                userinfo_endpoint,
                headers={
                    "accept": "application/json",
                    "authorization": f"Bearer {access_token}",
                },
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()

        return self._profile_from_claims(
            userinfo if isinstance(userinfo, dict) else {},
            id_token_claims=id_token_claims,
            expected_nonce=expected_nonce,
        )

    async def _metadata(self) -> dict[str, Any]:
        explicit = self._explicit_metadata()
        if explicit:
            return explicit
        issuer = str(self.settings.auth_oidc_issuer_url or "").strip().rstrip("/")
        if not issuer:
            raise HostedIdentityConfigError("OIDC issuer URL is not configured")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{issuer}/.well-known/openid-configuration")
            response.raise_for_status()
            metadata = response.json()
        if not isinstance(metadata, dict):
            return {}
        discovered_issuer = str(metadata.get("issuer") or "").strip().rstrip("/")
        if discovered_issuer and discovered_issuer != issuer:
            raise HostedIdentityConfigError("OIDC discovery issuer did not match the configured issuer")
        return metadata

    def _explicit_metadata(self) -> dict[str, str]:
        authorization_endpoint = str(self.settings.auth_oidc_authorization_endpoint or "").strip()
        token_endpoint = str(self.settings.auth_oidc_token_endpoint or "").strip()
        userinfo_endpoint = str(self.settings.auth_oidc_userinfo_endpoint or "").strip()
        issuer = str(self.settings.auth_oidc_issuer_url or "").strip().rstrip("/")
        jwks_uri = str(getattr(self.settings, "auth_oidc_jwks_uri", "") or "").strip()
        if not all([authorization_endpoint, token_endpoint, userinfo_endpoint]):
            return {}
        metadata = {
            "authorization_endpoint": authorization_endpoint,
            "token_endpoint": token_endpoint,
            "userinfo_endpoint": userinfo_endpoint,
        }
        if issuer:
            metadata["issuer"] = issuer
        if jwks_uri:
            metadata["jwks_uri"] = jwks_uri
        return metadata

    def _has_discovery(self) -> bool:
        return bool(str(self.settings.auth_oidc_issuer_url or "").strip())

    def _has_explicit_endpoints(self) -> bool:
        return bool(self._explicit_metadata())

    def _scopes(self) -> str:
        scopes = str(self.settings.auth_oidc_scopes or "").strip()
        return scopes or "openid email profile"

    def _validate_id_token(
        self,
        id_token: str,
        *,
        access_token: str,
        metadata: dict[str, Any],
        expected_nonce: str,
    ) -> dict[str, Any]:
        require_id_token = bool(getattr(self.settings, "auth_oidc_require_id_token", True))
        if not id_token:
            if require_id_token:
                raise HostedIdentityExchangeError("OIDC token response did not include an ID token")
            return {}
        issuer = str(metadata.get("issuer") or self.settings.auth_oidc_issuer_url or "").strip().rstrip("/")
        if not issuer:
            raise HostedIdentityConfigError("OIDC issuer is required to validate ID tokens")
        allowed_algs = self._allowed_id_token_algs()
        try:
            header = jwt.get_unverified_header(id_token)
        except PyJWTError as exc:
            raise HostedIdentityExchangeError("OIDC ID token header could not be read") from exc
        algorithm = str(header.get("alg") or "").strip()
        if not algorithm or algorithm == "none" or algorithm not in allowed_algs:
            raise HostedIdentityExchangeError("OIDC ID token signing algorithm is not allowed")
        try:
            key = self._id_token_key(id_token, algorithm, metadata)
            claims = jwt.decode(
                id_token,
                key=key,
                algorithms=allowed_algs,
                audience=str(self.settings.auth_oidc_client_id),
                issuer=issuer,
                options={"require": ["iss", "sub", "aud", "exp", "iat"]},
            )
        except PyJWTError as exc:
            raise HostedIdentityExchangeError("OIDC ID token validation failed") from exc
        self._validate_oidc_claims(
            claims,
            expected_nonce=expected_nonce,
            access_token=access_token,
            algorithm=algorithm,
        )
        return claims if isinstance(claims, dict) else {}

    def _id_token_key(self, id_token: str, algorithm: str, metadata: dict[str, Any]) -> Any:
        if algorithm.startswith("HS"):
            return str(self.settings.auth_oidc_client_secret)
        jwks_uri = str(metadata.get("jwks_uri") or getattr(self.settings, "auth_oidc_jwks_uri", "") or "").strip()
        if not jwks_uri:
            raise HostedIdentityConfigError("OIDC JWKS URI is required to validate ID tokens")
        signing_key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
        return signing_key.key

    def _validate_oidc_claims(
        self,
        claims: dict[str, Any],
        *,
        expected_nonce: str,
        access_token: str,
        algorithm: str,
    ) -> None:
        nonce = str(claims.get("nonce") or "").strip()
        if not nonce or nonce != expected_nonce:
            raise HostedIdentityExchangeError("OIDC nonce did not match the login request")
        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1:
            authorized_party = str(claims.get("azp") or "").strip()
            if authorized_party != str(self.settings.auth_oidc_client_id):
                raise HostedIdentityExchangeError("OIDC ID token authorized party did not match")
        at_hash = str(claims.get("at_hash") or "").strip()
        if at_hash and not _constant_time_at_hash_matches(access_token, at_hash, algorithm):
            raise HostedIdentityExchangeError("OIDC access token hash did not match the ID token")

    def _allowed_id_token_algs(self) -> list[str]:
        raw = str(getattr(self.settings, "auth_oidc_allowed_id_token_algs", "") or "").strip()
        allowed = [item.strip() for item in raw.replace(",", " ").split() if item.strip()]
        return allowed or ["RS256", "ES256"]

    def _profile_from_claims(
        self,
        userinfo: dict[str, Any],
        *,
        id_token_claims: dict[str, Any],
        expected_nonce: str,
    ) -> HostedIdentityProfile:
        subject = str(userinfo.get("sub") or id_token_claims.get("sub") or "").strip()
        id_subject = str(id_token_claims.get("sub") or "").strip()
        if id_subject and subject != id_subject:
            raise HostedIdentityExchangeError("OIDC userinfo subject did not match the ID token")
        email = str(userinfo.get("email") or id_token_claims.get("email") or "").strip().lower()
        if not subject:
            raise HostedIdentityExchangeError("OIDC userinfo response did not include a subject")
        if not email:
            raise HostedIdentityExchangeError("OIDC userinfo response did not include an email")
        nonce = str(userinfo.get("nonce") or "").strip()
        if nonce and nonce != expected_nonce:
            raise HostedIdentityExchangeError("OIDC nonce did not match the login request")
        display_name = (
            str(userinfo.get("name") or "").strip()
            or str(id_token_claims.get("name") or "").strip()
            or str(userinfo.get("preferred_username") or "").strip()
            or str(id_token_claims.get("preferred_username") or "").strip()
            or email
        )
        email_verified = _truthy_claim(
            userinfo.get("email_verified", id_token_claims.get("email_verified"))
        )
        amr = userinfo.get("amr", id_token_claims.get("amr"))
        acr = str(userinfo.get("acr") or id_token_claims.get("acr") or "").lower()
        methods = {str(item).lower() for item in amr} if isinstance(amr, list) else set()
        mfa_enabled = bool(
            methods.intersection({"mfa", "otp", "webauthn", "fido", "fido2", "passkey"})
            or "mfa" in acr
            or _truthy_claim(userinfo.get("mfa_enabled"))
            or _truthy_claim(id_token_claims.get("mfa_enabled"))
        )
        if bool(getattr(self.settings, "auth_oidc_require_mfa", False)) and not mfa_enabled:
            raise HostedIdentityExchangeError("Hosted sign-in requires MFA for this environment")
        return HostedIdentityProfile(
            provider=self.provider_name,
            subject=subject,
            email=email,
            display_name=display_name,
            email_verified=email_verified,
            mfa_enabled=mfa_enabled,
        )


def _truthy_claim(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "verified"}


def _constant_time_at_hash_matches(access_token: str, claim: str, algorithm: str) -> bool:
    digest_name = "sha256"
    if algorithm.endswith("384"):
        digest_name = "sha384"
    elif algorithm.endswith("512"):
        digest_name = "sha512"
    digest = hashlib.new(digest_name, access_token.encode("utf-8")).digest()
    expected = base64.urlsafe_b64encode(digest[: len(digest) // 2]).decode("ascii").rstrip("=")
    return hmac.compare_digest(expected, claim)
