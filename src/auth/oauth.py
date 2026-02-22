"""
Production-level OAuth 2.0 flow for Google / YouTube.

Responsibilities
----------------
1. First-time authentication via the Device Authorization Grant (no browser
   redirect needed – ideal for headless / server environments).
2. Automatic token refresh when a stored credential is expired or within the
   configurable refresh-ahead window.
3. Persisting and loading credentials from the database using the
   ``OauthCredential`` SQLAlchemy model.
4. Building an authenticated ``googleapiclient`` YouTube service with
   transparent auto-refresh on every call.

Environment variables required
-------------------------------
``GOOGLE_CLIENT_ID``      – OAuth 2.0 client ID (TV/Device application type).
``GOOGLE_CLIENT_SECRET``  – OAuth 2.0 client secret.

Optional
--------
``OAUTH_SCOPES``          – Space-separated scopes (default: YouTube read-only).
``TOKEN_REFRESH_MARGIN_SECONDS`` – How many seconds before expiry to proactively
                                    refresh (default: 300).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from sqlalchemy.orm import Session

from db import engine
from models import OauthCredential
from util.logging import logger

# ---------------------------------------------------------------------------
# Constants / configuration
# ---------------------------------------------------------------------------

_DEVICE_AUTH_URL = "https://oauth2.googleapis.com/device/code"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

_DEFAULT_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]
)
_YOUTUBE_API_SERVICE = "youtube"
_YOUTUBE_API_VERSION = "v3"

# Number of seconds before actual expiry to trigger a proactive refresh.
_REFRESH_MARGIN_SECONDS = int(os.getenv("TOKEN_REFRESH_MARGIN_SECONDS", "300"))


# ---------------------------------------------------------------------------
# Internal helpers – database I/O
# ---------------------------------------------------------------------------


def _load_credential() -> Optional[OauthCredential]:
    """Return the first stored OauthCredential row, or *None* if none exist."""
    with Session(engine) as session:
        return session.query(OauthCredential).first()


def _save_credential(
    creds: Credentials,
    db_row: Optional[OauthCredential] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
) -> OauthCredential:
    """Persist a ``google.oauth2.credentials.Credentials`` object to the DB.

    If *db_row* is provided the existing row is updated in-place; otherwise a
    new row is inserted.
    """
    with Session(engine) as session:
        if db_row is not None:
            # Re-attach the detached instance to this session.
            row = session.merge(db_row)
        else:
            row = OauthCredential()
            session.add(row)

        row.access_token = creds.token
        row.refresh_token = creds.refresh_token
        row.token_uri = creds.token_uri
        row.scopes = " ".join(creds.scopes) if creds.scopes else None
        row.token_type = "Bearer"
        row.expiry = creds.expiry  # already a UTC-aware or naive-UTC datetime

        # Only overwrite identity fields when explicitly supplied.
        if client_id is not None:
            row.client_id = client_id
        if client_secret is not None:
            row.client_secret = client_secret
        if user_id is not None:
            row.user_id = user_id
        if user_email is not None:
            row.user_email = user_email

        session.commit()
        session.refresh(row)
        # Detach from session so it can be used outside.
        session.expunge(row)
        return row


def _delete_credential(db_row: OauthCredential) -> None:
    """Hard-delete a credential row from the database."""
    with Session(engine) as session:
        row = session.merge(db_row)
        session.delete(row)
        session.commit()


# ---------------------------------------------------------------------------
# Internal helpers – Google credential objects
# ---------------------------------------------------------------------------


def _row_to_credentials(row: OauthCredential) -> Credentials:
    """Reconstruct a ``google.oauth2.credentials.Credentials`` from a DB row."""
    scopes = row.scopes.split(" ") if row.scopes else None
    return Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri=row.token_uri or _TOKEN_URL,
        client_id=row.client_id,
        client_secret=row.client_secret,
        scopes=scopes,
        expiry=row.expiry,
    )


def _is_expired(
    creds: Credentials, margin_seconds: int = _REFRESH_MARGIN_SECONDS
) -> bool:
    """Return *True* if the credential is expired or will expire within *margin_seconds*."""
    if creds.expiry is None:
        # No expiry information – treat as valid (server will reject if not).
        return False

    expiry = creds.expiry
    # Normalise to UTC-aware datetime for comparison.
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)
    seconds_remaining = (expiry - now).total_seconds()
    return seconds_remaining <= margin_seconds


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


def refresh_credential(
    row: OauthCredential,
) -> Optional[OauthCredential]:
    """Refresh an access token using the stored refresh token.

    Returns the updated ``OauthCredential`` row on success, or *None* if the
    refresh token is missing / the refresh request fails (in which case the
    stale row is deleted so that the next startup triggers a fresh device auth).
    """
    if not row.refresh_token:
        logger.error(
            "No refresh token stored – cannot refresh credential id=%s.", row.id
        )
        _delete_credential(row)
        return None

    creds = _row_to_credentials(row)

    try:
        creds.refresh(Request())
        logger.info("Successfully refreshed access token for credential id=%s.", row.id)
    except Exception as exc:
        logger.error(
            "Failed to refresh access token for credential id=%s: %s. Removing stale credential.",
            row.id,
            exc,
        )
        _delete_credential(row)
        return None

    updated_row = _save_credential(creds, db_row=row)
    return updated_row


# ---------------------------------------------------------------------------
# Device code (first-time) authentication
# ---------------------------------------------------------------------------


def _fetch_device_code(client_id: str, scopes: str) -> dict:
    """Request a device code from Google's device authorization endpoint."""
    response = requests.post(
        _DEVICE_AUTH_URL,
        data={"client_id": client_id, "scope": scopes},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def _poll_for_tokens(
    client_id: str,
    client_secret: str,
    device_code: str,
    interval: int,
    expires_in: int,
) -> Optional[dict]:
    """Poll the token endpoint until the user authorises the device or the code expires."""
    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        time.sleep(interval)
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
            timeout=15,
        )
        payload = resp.json()

        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error:
            logger.error("Device code polling error: %s", error)
            return None

        return payload  # success – contains access_token, refresh_token, etc.

    logger.error("Device code expired before the user completed authorisation.")
    return None


def _fetch_user_info(access_token: str) -> dict:
    """Retrieve the authenticated user's profile from Google."""
    resp = requests.get(
        _USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def authenticate_with_device_code(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scopes: Optional[str] = None,
) -> Optional[OauthCredential]:
    """Run the full Device Authorization Grant flow interactively.

    Prints the verification URL + user code to *stdout* so the operator can
    complete the flow on any device with a browser.  Blocks until authorisation
    succeeds or the device code expires.

    Returns the newly created ``OauthCredential`` row, or *None* on failure.
    """
    client_id = client_id or os.getenv("GOOGLE_CLIENT_ID")
    client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET")
    scopes = scopes or os.getenv("OAUTH_SCOPES", _DEFAULT_SCOPES)

    if not client_id or not client_secret:
        logger.error(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set to run device auth."
        )
        return None

    logger.info("Starting device code OAuth flow…")

    try:
        device_data = _fetch_device_code(client_id, scopes)
    except Exception as exc:
        logger.error("Failed to obtain device code: %s", exc)
        return None

    device_code = device_data["device_code"]
    user_code = device_data["user_code"]
    verification_url = device_data.get("verification_url") or device_data.get(
        "verification_uri"
    )
    interval = int(device_data.get("interval", 5))
    expires_in = int(device_data.get("expires_in", 1800))

    print(
        f"\n{'=' * 60}\n"
        f"  To authorise this application, visit:\n"
        f"    {verification_url}\n"
        f"  and enter the code:  {user_code}\n"
        f"{'=' * 60}\n",
        flush=True,
    )
    logger.info(
        "Waiting for user to complete device authorisation (code: %s)…", user_code
    )

    token_data = _poll_for_tokens(
        client_id, client_secret, device_code, interval, expires_in
    )
    if not token_data:
        return None

    # Build a Credentials object so we can use the standard helper.
    expiry_dt: Optional[datetime] = None
    expires_in_secs = token_data.get("expires_in")
    if expires_in_secs is not None:
        expiry_dt = datetime.fromtimestamp(
            time.time() + int(expires_in_secs), tz=timezone.utc
        ).replace(tzinfo=None)  # store as naive UTC to match SQLAlchemy convention

    creds = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes.split(),
        expiry=expiry_dt,
    )

    # Fetch user identity.
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    try:
        info = _fetch_user_info(token_data["access_token"])
        user_id = info.get("id")
        user_email = info.get("email")
        logger.info("Authenticated as %s (%s).", user_email, user_id)
    except Exception as exc:
        logger.warning("Could not fetch user info: %s", exc)

    row = _save_credential(
        creds,
        user_id=user_id,
        user_email=user_email,
        client_id=client_id,
        client_secret=client_secret,
    )
    logger.info("Credential stored in database (id=%s).", row.id)
    return row


# ---------------------------------------------------------------------------
# Revoke expired / unusable tokens
# ---------------------------------------------------------------------------


def revoke_expired_tokens() -> None:
    """Scan all stored credentials and revoke/delete those that cannot be refreshed.

    A credential is considered unrecoverable when it has no refresh token AND
    its access token is already expired.  Valid or refreshable credentials are
    left untouched.
    """
    with Session(engine) as session:
        rows: list[OauthCredential] = session.query(OauthCredential).all()  # type: ignore[assignment]
        # Detach all rows before closing session.
        for row in rows:
            session.expunge(row)

    for row in rows:
        creds = _row_to_credentials(row)
        if not _is_expired(creds):
            continue  # still valid

        if row.refresh_token:
            # Attempt a refresh; refresh_credential handles DB updates/deletions.
            logger.info(
                "Credential id=%s is expired – attempting refresh before revoke check.",
                row.id,
            )
            refresh_credential(row)
        else:
            logger.warning(
                "Credential id=%s is expired with no refresh token – revoking and deleting.",
                row.id,
            )
            if row.access_token:
                try:
                    requests.post(
                        _REVOKE_URL,
                        params={"token": row.access_token},
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=10,
                    )
                except Exception as exc:
                    logger.warning(
                        "Revoke request failed for credential id=%s: %s", row.id, exc
                    )
            _delete_credential(row)


# ---------------------------------------------------------------------------
# Public API – get an authenticated YouTube service
# ---------------------------------------------------------------------------


def get_authenticated_youtube_service(
    force_auth: bool = False,
) -> Optional[Resource]:
    """Return an authenticated ``googleapiclient`` YouTube v3 ``Resource``.

    Behaviour
    ---------
    1. Load the stored credential from the database.
    2. If none exists (or *force_auth* is ``True`` and no credential exists),
       run the device-code flow to obtain one.
    3. If the credential is expired (or within the refresh-ahead margin),
       refresh it transparently.
    4. Build and return the YouTube service resource.

    Returns ``None`` if authentication cannot be established.
    """
    row = _load_credential()

    if row is None:
        logger.info("No stored credential found – starting device auth flow.")
        row = authenticate_with_device_code()
        if row is None:
            logger.error("Device auth failed – cannot build YouTube service.")
            return None

    creds = _row_to_credentials(row)

    if _is_expired(creds):
        logger.info(
            "Credential id=%s is expired or expiring soon – refreshing before building service.",
            row.id,
        )
        row = refresh_credential(row)
        if row is None:
            # refresh_credential already deleted the stale row; try device auth.
            logger.info("Refresh failed – starting device auth flow.")
            row = authenticate_with_device_code()
            if row is None:
                logger.error("Device auth failed after refresh failure.")
                return None
        creds = _row_to_credentials(row)

    try:
        youtube = build(
            _YOUTUBE_API_SERVICE,
            _YOUTUBE_API_VERSION,
            credentials=creds,
        )
        logger.info("Built authenticated YouTube service for credential id=%s.", row.id)
        return youtube
    except Exception as exc:
        logger.error("Failed to build YouTube service: %s", exc)
        return None
