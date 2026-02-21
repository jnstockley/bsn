from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Sequence

import requests
from google.auth.credentials import TokenState
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from db import engine
from models import OauthCredential
from util.logging import logger


DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
DEFAULT_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def get_authenticated_youtube_service(
    force_auth: bool = False,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scopes: Optional[Sequence[str]] = None,
) -> Resource | None:
    """Return a googleapiclient.discovery.Resource for the YouTube Data API v3.

    - Attempts to load credentials from the DB (and refreshes if needed).
    - If no credentials are present and force_auth is True, runs device auth flow.
    - Returns None when credentials are not available.
    """
    scopes = list(scopes) if scopes else list(DEFAULT_SCOPES)

    if not client_id:
        logger.info("No client_id provided; checking environment variables.")
        client_id = os.environ.get("OAUTH_CLIENT_ID", None)
    if not client_secret:
        logger.info("No client_secret provided; checking environment variables.")
        client_secret = os.environ.get("OAUTH_CLIENT_SECRET", None)

    creds = get_credentials()
    if creds is None and force_auth:
        logger.info("No credentials found; starting device auth flow (console).")
        creds = run_auth_flow(
            client_id=client_id, client_secret=client_secret, scopes=scopes
        )

    if creds is None:
        logger.warning("No valid credentials available for YouTube API.")
        return None

    try:
        service = build("youtube", "v3", credentials=creds)
        return service
    except Exception as exc:
        logger.exception("Failed to build YouTube service: %s", exc)
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def run_auth_flow(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    scopes: Optional[list[str]] = None,
    timeout: int = 600,
) -> Optional[Credentials]:
    """Run the OAuth2 Device Authorization Flow and persist credentials.

    This logs the verification URL + user code to stdout so an external user
    can complete consent using a browser.
    Returns google.oauth2.credentials.Credentials on success, or None on failure.
    """
    scopes = scopes or DEFAULT_SCOPES

    if client_id is None:
        # Try environment-style client from first DB row or raise
        stmt = select(OauthCredential).limit(1)
        with Session(engine) as s:
            credential: OauthCredential = s.execute(stmt).scalar_one_or_none()

        client_id = credential.client_id

    if client_id is None:
        raise ValueError(
            "client_id must be provided via argument or stored credentials"
        )

    data = {"client_id": client_id, "scope": " ".join(scopes)}

    resp = requests.post(DEVICE_CODE_URL, data=data, timeout=10)
    resp.raise_for_status()
    device = resp.json()

    device_code = device["device_code"]
    user_code = device["user_code"]
    verification_url = device.get("verification_url") or device.get("verification_uri")
    expires_in = int(device.get("expires_in", 600))
    interval = int(device.get("interval", 5))

    logger.info("To authorize, visit:")
    logger.info(verification_url)
    logger.info("and enter the code: %s", user_code)
    logger.info("This code will expire in {} seconds".format(expires_in))

    # Poll token endpoint
    start = time.time()
    while True:
        if time.time() - start > timeout:
            logger.warning("Timeout waiting for user to authorize device code")
            return None

        token_data = {
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        }
        if client_secret:
            token_data["client_secret"] = client_secret

        try:
            t_resp = requests.post(TOKEN_URL, data=token_data, timeout=10)
        except requests.RequestException as exc:
            logger.error("Network error while polling token endpoint: %s", exc)
            time.sleep(interval)
            continue

        if t_resp.status_code == 200:
            tok = t_resp.json()
            creds = Credentials(
                token=tok.get("access_token"),
                refresh_token=tok.get("refresh_token"),
                token_uri=TOKEN_URL,
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes,
            )
            # expiry may be present
            if "expires_in" in tok:
                creds.expiry = _now_utc() + timedelta(seconds=int(tok["expires_in"]))

            save_credentials_to_db(
                creds, client_id=client_id, client_secret=client_secret
            )
            creds = load_credentials_from_db()
            logger.info("Authorization successful; credentials saved.")
            return creds

        # handle errors
        try:
            err = t_resp.json()
        except ValueError:
            err = {"error": "unknown"}

        error = err.get("error")
        if error == "authorization_pending":
            # user hasn't completed step yet
            time.sleep(interval)
            continue
        if error == "slow_down":
            interval = min(interval + 5, 60)
            time.sleep(interval)
            continue
        if error in ("access_denied", "expired_token"):
            logger.error("Authorization failed: %s", error)
            return None

        # unknown error -> raise
        logger.error("Unexpected token endpoint response: %s", err)
        return None


def save_credentials_to_db(
    creds: Credentials,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    user_email: Optional[str] = None,
    user_id: Optional[str] = None,
) -> int:
    """Persist google.oauth2.credentials.Credentials to the DB using OAuthCredentials model."""
    # join scopes
    scopes = None
    try:
        scopes = " ".join(creds.scopes) if creds.scopes else None
    except Exception:
        scopes = None

    cred = OauthCredential(
        user_id=user_id,
        client_id=client_id or getattr(creds, "client_id", None),
        client_secret=client_secret or getattr(creds, "client_secret", None),
        user_email=user_email,
        access_token=creds.token,
        refresh_token=getattr(creds, "refresh_token", None),
        token_uri=getattr(creds, "token_uri", TOKEN_URL),
        scopes=scopes,
        token_type=None,
        expiry=creds.expiry.astimezone(timezone.utc).replace(tzinfo=None),
        extra=json.dumps({}),
    )

    with Session(engine) as s:
        s.add(cred)
        s.commit()
        s.refresh(cred)

    return cred.id


def load_credentials_from_db(user_id: Optional[str] = None) -> Optional[Credentials]:
    try:
        if user_id:
            stmt = select(OauthCredential).where(OauthCredential.user_id == user_id)
        else:
            stmt = select(OauthCredential).limit(1)
        with Session(engine) as s:
            cred = s.execute(stmt).scalar_one_or_none()
        if not cred:
            return None

        oauth_cred = Credentials(
            token=cred.access_token,
            refresh_token=cred.refresh_token,
            token_uri=cred.token_uri,
            client_id=cred.client_id,
            client_secret=cred.client_secret,
            scopes=(cred.scopes or "").split(),
        )
        oauth_cred.expiry = cred.expiry.astimezone(timezone.utc).replace(tzinfo=None)
        return oauth_cred
    except Exception as exc:
        logger.error("Error loading credentials from DB: %s", exc)
        return None


def get_credentials(user_id: Optional[str] = None) -> Optional[Credentials]:
    """Return valid credentials, refreshing automatically if needed.

    Returns None if no credentials available or if refresh fails.
    """
    creds = load_credentials_from_db(user_id=user_id)
    if creds is None:
        return None

    # if expired and refresh token present, refresh
    if (
        creds.token_state in (TokenState.STALE, TokenState.INVALID)
        and creds.refresh_token
    ):
        try:
            request = Request()
            creds.refresh(request)
            # persist new tokens
            save_credentials_to_db(
                creds, client_id=creds.client_id, client_secret=creds.client_secret
            )
        except Exception as exc:
            # likely invalid_grant or revoked token
            logger.error("Failed to refresh credentials: %s", exc)
            try:
                with Session(engine) as s:
                    # delete the row
                    if user_id:
                        stmt = delete(OauthCredential).where(
                            OauthCredential.user_id == user_id
                        )
                    else:
                        stmt = delete(OauthCredential)
                    s.execute(stmt)
                    s.commit()
            except Exception:
                pass
            return None

    return creds


def revoke_credentials(creds: Credentials) -> bool:
    token = creds.refresh_token or creds.token
    if not token:
        return False
    try:
        resp = requests.post(REVOKE_URL, params={"token": token}, timeout=10)
        if resp.status_code in (200, 204):
            # remove from DB
            stmt = delete(OauthCredential).where(
                OauthCredential.client_id == creds.client_id
            )
            with Session(engine) as s:
                s.execute(stmt)
                s.commit()
            return True
        logger.error("Failed to revoke token: %s %s", resp.status_code, resp.text)
        return False
    except requests.RequestException as exc:
        logger.error("Network error revoking token: %s", exc)
        return False
