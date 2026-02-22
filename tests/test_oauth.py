"""
Comprehensive tests for src/auth/oauth.py.

Covers:
- Database helpers: _load_credential, _save_credential, _delete_credential
- Google credential helpers: _row_to_credentials, _is_expired
- Token refresh: refresh_credential
- Device code flow internals: _fetch_device_code, _poll_for_tokens, _fetch_user_info,
  authenticate_with_device_code
- Revoke expired tokens: revoke_expired_tokens
- Public API: get_authenticated_youtube_service
"""

from __future__ import annotations

import time  # noqa: F401 – used indirectly via patch("auth.oauth.time.*")
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch

from models import OauthCredential
from auth.oauth import (
    _load_credential,
    _save_credential,
    _delete_credential,
    _row_to_credentials,
    _is_expired,
    _fetch_device_code,
    _poll_for_tokens,
    _fetch_user_info,
    authenticate_with_device_code,
    refresh_credential,
    revoke_expired_tokens,
    get_authenticated_youtube_service,
    _TOKEN_URL,
    _DEFAULT_SCOPES,
)


def _make_row(
    *,
    id: int = 1,
    access_token: str = "access-tok",
    refresh_token: str | None = "refresh-tok",
    token_uri: str = _TOKEN_URL,
    client_id: str = "client-id",
    client_secret: str = "client-secret",
    scopes: str = _DEFAULT_SCOPES,
    expiry: datetime | None = None,
    user_id: str = "uid-123",
    user_email: str = "user@example.com",
) -> OauthCredential:
    """Create a minimal OauthCredential instance without DB interaction."""
    row = OauthCredential()
    row.id = id
    row.access_token = access_token
    row.refresh_token = refresh_token
    row.token_uri = token_uri
    row.client_id = client_id
    row.client_secret = client_secret
    row.scopes = scopes
    row.token_type = "Bearer"
    row.expiry = expiry
    row.user_id = user_id
    row.user_email = user_email
    return row


def _future_expiry(seconds: int = 3600) -> datetime:
    """Return a naive-UTC datetime that is *seconds* in the future."""
    return (datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)).replace(
        tzinfo=None
    )


def _past_expiry(seconds: int = 3600) -> datetime:
    """Return a naive-UTC datetime that is *seconds* in the past."""
    return (datetime.now(tz=timezone.utc) - timedelta(seconds=seconds)).replace(
        tzinfo=None
    )


# ---------------------------------------------------------------------------
# _load_credential
# ---------------------------------------------------------------------------


class TestLoadCredential(TestCase):
    @patch("auth.oauth.Session")
    def test_returns_first_row(self, mock_session_cls):
        row = _make_row()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.first.return_value = row

        result = _load_credential()

        mock_session.query.assert_called_once_with(OauthCredential)
        self.assertIs(result, row)

    @patch("auth.oauth.Session")
    def test_returns_none_when_empty(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.first.return_value = None

        result = _load_credential()

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _save_credential
# ---------------------------------------------------------------------------


class TestSaveCredential(TestCase):
    def _make_google_creds(self, expiry=None):
        creds = MagicMock()
        creds.token = "new-access-tok"
        creds.refresh_token = "new-refresh-tok"
        creds.token_uri = _TOKEN_URL
        creds.scopes = [_DEFAULT_SCOPES]
        creds.expiry = expiry
        return creds

    @patch("auth.oauth.Session")
    def test_inserts_new_row_when_no_db_row(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session

        new_row = _make_row(id=99)
        mock_session.query.return_value.first.return_value = new_row

        # After commit + refresh the mock session just hands back the same OauthCredential
        def _refresh(obj):
            obj.id = 99

        mock_session.refresh.side_effect = _refresh
        mock_session.expunge.return_value = None

        creds = self._make_google_creds()
        _ = _save_credential(
            creds,
            user_id="u1",
            user_email="u@e.com",
            client_id="cid",
            client_secret="csec",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("auth.oauth.Session")
    def test_updates_existing_row_when_db_row_supplied(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session

        existing_row = _make_row()
        mock_session.merge.return_value = existing_row
        mock_session.expunge.return_value = None

        creds = self._make_google_creds(expiry=_future_expiry())
        _save_credential(creds, db_row=existing_row)

        mock_session.merge.assert_called_once_with(existing_row)
        # add should NOT be called for an update
        mock_session.add.assert_not_called()
        mock_session.commit.assert_called_once()

    @patch("auth.oauth.Session")
    def test_scopes_joined_as_space_separated_string(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session

        mock_session.add.side_effect = lambda r: None
        mock_session.expunge.return_value = None

        creds = MagicMock()
        creds.token = "tok"
        creds.refresh_token = "rtok"
        creds.token_uri = _TOKEN_URL
        creds.scopes = ["scope1", "scope2"]
        creds.expiry = None

        # Capture the row that would be set
        rows_seen = []

        def capture_add(row):
            rows_seen.append(row)

        mock_session.add.side_effect = capture_add
        mock_session.refresh.return_value = None

        _save_credential(creds)

        # The row's scopes field should be space-joined
        if rows_seen:
            self.assertEqual(rows_seen[0].scopes, "scope1 scope2")

    @patch("auth.oauth.Session")
    def test_scopes_none_when_creds_scopes_falsy(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session

        rows_seen = []

        def capture_add(row):
            rows_seen.append(row)

        mock_session.add.side_effect = capture_add
        mock_session.refresh.return_value = None
        mock_session.expunge.return_value = None

        creds = MagicMock()
        creds.token = "tok"
        creds.refresh_token = None
        creds.token_uri = _TOKEN_URL
        creds.scopes = None
        creds.expiry = None

        _save_credential(creds)

        if rows_seen:
            self.assertIsNone(rows_seen[0].scopes)


# ---------------------------------------------------------------------------
# _delete_credential
# ---------------------------------------------------------------------------


class TestDeleteCredential(TestCase):
    @patch("auth.oauth.Session")
    def test_deletes_merged_row(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session

        row = _make_row()
        merged = _make_row(id=1)
        mock_session.merge.return_value = merged

        _delete_credential(row)

        mock_session.merge.assert_called_once_with(row)
        mock_session.delete.assert_called_once_with(merged)
        mock_session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _row_to_credentials
# ---------------------------------------------------------------------------


class TestRowToCredentials(TestCase):
    def test_basic_mapping(self):
        row = _make_row(scopes="scope1 scope2")
        creds = _row_to_credentials(row)

        self.assertEqual(creds.token, row.access_token)
        self.assertEqual(creds.refresh_token, row.refresh_token)
        self.assertEqual(creds.token_uri, row.token_uri)
        self.assertEqual(creds.client_id, row.client_id)
        self.assertEqual(creds.client_secret, row.client_secret)
        self.assertEqual(creds.scopes, ["scope1", "scope2"])

    def test_none_scopes_yields_none(self):
        row = _make_row()
        row.scopes = None  # type: ignore[assignment]
        creds = _row_to_credentials(row)
        self.assertIsNone(creds.scopes)

    def test_falls_back_to_default_token_uri_when_row_has_none(self):
        row = _make_row()
        row.token_uri = None
        creds = _row_to_credentials(row)
        self.assertEqual(creds.token_uri, _TOKEN_URL)


# ---------------------------------------------------------------------------
# _is_expired
# ---------------------------------------------------------------------------


class TestIsExpired(TestCase):
    def test_no_expiry_returns_false(self):
        creds = MagicMock()
        creds.expiry = None
        self.assertFalse(_is_expired(creds, margin_seconds=0))

    def test_far_future_expiry_returns_false(self):
        creds = MagicMock()
        creds.expiry = _future_expiry(7200)
        self.assertFalse(_is_expired(creds, margin_seconds=300))

    def test_past_expiry_returns_true(self):
        creds = MagicMock()
        creds.expiry = _past_expiry(60)
        self.assertTrue(_is_expired(creds, margin_seconds=0))

    def test_expiry_within_margin_returns_true(self):
        # Token expires in 100 s, margin is 300 s → should be considered expired
        creds = MagicMock()
        creds.expiry = _future_expiry(100)
        self.assertTrue(_is_expired(creds, margin_seconds=300))

    def test_expiry_just_outside_margin_returns_false(self):
        # Token expires in 600 s, margin is 300 s → still valid
        creds = MagicMock()
        creds.expiry = _future_expiry(600)
        self.assertFalse(_is_expired(creds, margin_seconds=300))

    def test_tz_aware_expiry_is_handled(self):
        """Timezone-aware datetimes should be normalised correctly."""
        creds = MagicMock()
        creds.expiry = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
        self.assertTrue(_is_expired(creds, margin_seconds=0))


# ---------------------------------------------------------------------------
# refresh_credential
# ---------------------------------------------------------------------------


class TestRefreshCredential(TestCase):
    @patch("auth.oauth._save_credential")
    @patch("auth.oauth._row_to_credentials")
    def test_successful_refresh(self, mock_row_to_creds, mock_save):
        row = _make_row()
        mock_creds = MagicMock()
        mock_creds.expiry = _future_expiry()
        mock_row_to_creds.return_value = mock_creds
        updated_row = _make_row(access_token="new-tok")
        mock_save.return_value = updated_row

        result = refresh_credential(row)

        mock_creds.refresh.assert_called_once()
        mock_save.assert_called_once_with(mock_creds, db_row=row)
        self.assertIs(result, updated_row)

    @patch("auth.oauth._delete_credential")
    def test_no_refresh_token_deletes_and_returns_none(self, mock_delete):
        row = _make_row(refresh_token=None)
        row.refresh_token = None

        result = refresh_credential(row)

        mock_delete.assert_called_once_with(row)
        self.assertIsNone(result)

    @patch("auth.oauth._delete_credential")
    @patch("auth.oauth._row_to_credentials")
    def test_refresh_exception_deletes_and_returns_none(
        self, mock_row_to_creds, mock_delete
    ):
        row = _make_row()
        mock_creds = MagicMock()
        mock_creds.refresh.side_effect = Exception("network error")
        mock_row_to_creds.return_value = mock_creds

        result = refresh_credential(row)

        mock_delete.assert_called_once_with(row)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _fetch_device_code
# ---------------------------------------------------------------------------


class TestFetchDeviceCode(TestCase):
    @patch("auth.oauth.requests.post")
    def test_returns_parsed_json(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "device_code": "dev-code",
            "user_code": "USR-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 1800,
            "interval": 5,
        }
        mock_post.return_value = mock_resp

        result = _fetch_device_code("client-id", "scope1")

        mock_post.assert_called_once()
        self.assertEqual(result["device_code"], "dev-code")

    @patch("auth.oauth.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 400")
        mock_post.return_value = mock_resp

        with self.assertRaises(Exception):
            _fetch_device_code("cid", "scope")


# ---------------------------------------------------------------------------
# _poll_for_tokens
# ---------------------------------------------------------------------------


class TestPollForTokens(TestCase):
    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.requests.post")
    def test_returns_token_on_success(self, mock_post, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "acc", "refresh_token": "ref"}
        mock_post.return_value = mock_resp

        result = _poll_for_tokens("cid", "csec", "dev-code", interval=5, expires_in=300)

        self.assertEqual(result["access_token"], "acc")

    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.requests.post")
    def test_retries_on_authorization_pending(self, mock_post, mock_sleep):
        pending = MagicMock()
        pending.json.return_value = {"error": "authorization_pending"}

        success = MagicMock()
        success.json.return_value = {"access_token": "tok"}

        mock_post.side_effect = [pending, success]

        with patch("auth.oauth.time.monotonic", side_effect=[0, 1, 2, 999]):
            result = _poll_for_tokens(
                "cid", "csec", "dev-code", interval=1, expires_in=300
            )

        self.assertEqual(result["access_token"], "tok")

    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.requests.post")
    def test_increases_interval_on_slow_down(self, mock_post, mock_sleep):
        slow = MagicMock()
        slow.json.return_value = {"error": "slow_down"}

        success = MagicMock()
        success.json.return_value = {"access_token": "tok"}

        mock_post.side_effect = [slow, success]

        with patch("auth.oauth.time.monotonic", side_effect=[0, 1, 2, 999]):
            _poll_for_tokens("cid", "csec", "dev-code", interval=5, expires_in=300)

        # Sleep should have been called with an increased interval (10 after slow_down)
        calls = mock_sleep.call_args_list
        self.assertTrue(any(c.args[0] >= 10 for c in calls))

    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.requests.post")
    def test_returns_none_on_unrecoverable_error(self, mock_post, mock_sleep):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": "access_denied"}
        mock_post.return_value = mock_resp

        with patch("auth.oauth.time.monotonic", side_effect=[0, 1, 999]):
            result = _poll_for_tokens(
                "cid", "csec", "dev-code", interval=1, expires_in=300
            )

        self.assertIsNone(result)

    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.time.monotonic")
    def test_returns_none_when_code_expires(self, mock_monotonic, mock_sleep):
        # monotonic always returns a value beyond deadline
        mock_monotonic.return_value = 9999

        result = _poll_for_tokens("cid", "csec", "dev-code", interval=5, expires_in=300)

        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# _fetch_user_info
# ---------------------------------------------------------------------------


class TestFetchUserInfo(TestCase):
    @patch("auth.oauth.requests.get")
    def test_returns_user_dict(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "123", "email": "u@e.com"}
        mock_get.return_value = mock_resp

        result = _fetch_user_info("access-tok")

        self.assertEqual(result["email"], "u@e.com")
        mock_get.assert_called_once()

    @patch("auth.oauth.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("401")
        mock_get.return_value = mock_resp

        with self.assertRaises(Exception):
            _fetch_user_info("bad-tok")


# ---------------------------------------------------------------------------
# authenticate_with_device_code
# ---------------------------------------------------------------------------


class TestAuthenticateWithDeviceCode(TestCase):
    @patch("auth.oauth._save_credential")
    @patch("auth.oauth._fetch_user_info")
    @patch("auth.oauth._poll_for_tokens")
    @patch("auth.oauth._fetch_device_code")
    def test_successful_flow(
        self, mock_fetch_code, mock_poll, mock_user_info, mock_save
    ):
        mock_fetch_code.return_value = {
            "device_code": "dcode",
            "user_code": "UCODE",
            "verification_url": "https://google.com/device",
            "interval": 5,
            "expires_in": 1800,
        }
        mock_poll.return_value = {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_in": 3600,
        }
        mock_user_info.return_value = {"id": "uid", "email": "u@e.com"}
        expected_row = _make_row()
        mock_save.return_value = expected_row

        result = authenticate_with_device_code(
            client_id="cid", client_secret="csec", scopes=_DEFAULT_SCOPES
        )

        self.assertIs(result, expected_row)
        mock_save.assert_called_once()

    def test_returns_none_when_no_client_id(self):
        with patch.dict("os.environ", {}, clear=True):
            result = authenticate_with_device_code(client_id=None, client_secret=None)
        self.assertIsNone(result)

    @patch("auth.oauth._fetch_device_code")
    def test_returns_none_when_fetch_device_code_fails(self, mock_fetch):
        mock_fetch.side_effect = Exception("network error")

        result = authenticate_with_device_code(client_id="cid", client_secret="csec")

        self.assertIsNone(result)

    @patch("auth.oauth._poll_for_tokens")
    @patch("auth.oauth._fetch_device_code")
    def test_returns_none_when_polling_fails(self, mock_fetch, mock_poll):
        mock_fetch.return_value = {
            "device_code": "dc",
            "user_code": "UC",
            "verification_url": "https://g.co/device",
            "interval": 5,
            "expires_in": 300,
        }
        mock_poll.return_value = None

        result = authenticate_with_device_code(client_id="cid", client_secret="csec")

        self.assertIsNone(result)

    @patch("auth.oauth._save_credential")
    @patch("auth.oauth._fetch_user_info")
    @patch("auth.oauth._poll_for_tokens")
    @patch("auth.oauth._fetch_device_code")
    def test_user_info_failure_does_not_abort(
        self, mock_fetch, mock_poll, mock_user_info, mock_save
    ):
        """User info fetch failure should log a warning but still save the credential."""
        mock_fetch.return_value = {
            "device_code": "dc",
            "user_code": "UC",
            "verification_url": "https://g.co/device",
            "interval": 5,
            "expires_in": 300,
        }
        mock_poll.return_value = {"access_token": "acc", "expires_in": 3600}
        mock_user_info.side_effect = Exception("403 Forbidden")
        mock_save.return_value = _make_row()

        result = authenticate_with_device_code(client_id="cid", client_secret="csec")

        self.assertIsNotNone(result)
        mock_save.assert_called_once()

    @patch("auth.oauth._save_credential")
    @patch("auth.oauth._fetch_user_info")
    @patch("auth.oauth._poll_for_tokens")
    @patch("auth.oauth._fetch_device_code")
    def test_reads_client_id_from_env(
        self, mock_fetch, mock_poll, mock_user_info, mock_save
    ):
        mock_fetch.return_value = {
            "device_code": "dc",
            "user_code": "UC",
            "verification_url": "https://g.co/device",
            "interval": 5,
            "expires_in": 300,
        }
        mock_poll.return_value = {"access_token": "acc", "expires_in": 3600}
        mock_user_info.return_value = {"id": "uid", "email": "e@e.com"}
        mock_save.return_value = _make_row()

        with patch.dict(
            "os.environ",
            {"GOOGLE_CLIENT_ID": "env-cid", "GOOGLE_CLIENT_SECRET": "env-csec"},
        ):
            authenticate_with_device_code()

        args, kwargs = mock_fetch.call_args
        self.assertEqual(args[0], "env-cid")


# ---------------------------------------------------------------------------
# revoke_expired_tokens
# ---------------------------------------------------------------------------


class TestRevokeExpiredTokens(TestCase):
    @patch("auth.oauth._delete_credential")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth.Session")
    def test_skips_valid_credentials(
        self, mock_session_cls, mock_is_expired, mock_delete
    ):
        row = _make_row()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.all.return_value = [row]
        mock_is_expired.return_value = False

        revoke_expired_tokens()

        mock_delete.assert_not_called()

    @patch("auth.oauth._delete_credential")
    @patch("auth.oauth.requests.post")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth.Session")
    def test_deletes_expired_credential_with_no_refresh_token(
        self, mock_session_cls, mock_is_expired, mock_post, mock_delete
    ):
        row = _make_row(refresh_token=None)
        row.refresh_token = None

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.all.return_value = [row]
        mock_is_expired.return_value = True

        revoke_expired_tokens()

        mock_post.assert_called_once()  # revoke request sent
        mock_delete.assert_called_once_with(row)

    @patch("auth.oauth.refresh_credential")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth.Session")
    def test_refreshes_expired_credential_with_refresh_token(
        self, mock_session_cls, mock_is_expired, mock_refresh
    ):
        row = _make_row()
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.all.return_value = [row]
        mock_is_expired.return_value = True
        mock_refresh.return_value = _make_row(access_token="new-tok")

        revoke_expired_tokens()

        mock_refresh.assert_called_once_with(row)

    @patch("auth.oauth._delete_credential")
    @patch("auth.oauth.requests.post")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth.Session")
    def test_revoke_request_failure_does_not_raise(
        self, mock_session_cls, mock_is_expired, mock_post, mock_delete
    ):
        """Revoke HTTP failure should be swallowed; credential still deleted."""
        row = _make_row(refresh_token=None)
        row.refresh_token = None

        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        mock_session.query.return_value.all.return_value = [row]
        mock_is_expired.return_value = True
        mock_post.side_effect = Exception("network error")

        # Should not raise
        revoke_expired_tokens()

        mock_delete.assert_called_once_with(row)


# ---------------------------------------------------------------------------
# get_authenticated_youtube_service
# ---------------------------------------------------------------------------


class TestGetAuthenticatedYoutubeService(TestCase):
    @patch("auth.oauth.build")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth._row_to_credentials")
    @patch("auth.oauth._load_credential")
    def test_returns_service_when_credential_is_valid(
        self, mock_load, mock_row_to_creds, mock_is_expired, mock_build
    ):
        row = _make_row()
        mock_load.return_value = row
        mock_creds = MagicMock()
        mock_row_to_creds.return_value = mock_creds
        mock_is_expired.return_value = False
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        result = get_authenticated_youtube_service()

        self.assertIs(result, mock_youtube)
        mock_build.assert_called_once()

    @patch("auth.oauth.authenticate_with_device_code")
    @patch("auth.oauth._load_credential")
    def test_triggers_device_auth_when_no_credential(self, mock_load, mock_auth):
        mock_load.return_value = None
        mock_auth.return_value = None  # auth also fails

        result = get_authenticated_youtube_service()

        mock_auth.assert_called_once()
        self.assertIsNone(result)

    @patch("auth.oauth.build")
    @patch("auth.oauth.authenticate_with_device_code")
    @patch("auth.oauth._load_credential")
    def test_device_auth_succeeds_after_no_stored_credential(
        self, mock_load, mock_auth, mock_build
    ):
        mock_load.return_value = None
        new_row = _make_row()
        mock_auth.return_value = new_row
        mock_youtube = MagicMock()
        mock_build.return_value = mock_youtube

        with (
            patch("auth.oauth._row_to_credentials") as mock_r2c,
            patch("auth.oauth._is_expired", return_value=False),
        ):
            mock_r2c.return_value = MagicMock()
            result = get_authenticated_youtube_service()

        self.assertIs(result, mock_youtube)

    @patch("auth.oauth.build")
    @patch("auth.oauth._save_credential")
    @patch("auth.oauth.refresh_credential")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth._row_to_credentials")
    @patch("auth.oauth._load_credential")
    def test_refreshes_expired_credential_and_returns_service(
        self,
        mock_load,
        mock_row_to_creds,
        mock_is_expired,
        mock_refresh,
        mock_save,
        mock_build,
    ):
        row = _make_row()
        mock_load.return_value = row
        mock_row_to_creds.return_value = MagicMock()
        mock_is_expired.return_value = True

        refreshed_row = _make_row(access_token="refreshed-tok")
        mock_refresh.return_value = refreshed_row
        mock_build.return_value = MagicMock()

        result = get_authenticated_youtube_service()

        mock_refresh.assert_called_once_with(row)
        self.assertIsNotNone(result)

    @patch("auth.oauth.authenticate_with_device_code")
    @patch("auth.oauth.refresh_credential")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth._row_to_credentials")
    @patch("auth.oauth._load_credential")
    def test_falls_back_to_device_auth_when_refresh_fails(
        self,
        mock_load,
        mock_row_to_creds,
        mock_is_expired,
        mock_refresh,
        mock_auth,
    ):
        row = _make_row()
        mock_load.return_value = row
        mock_row_to_creds.return_value = MagicMock()
        mock_is_expired.return_value = True
        mock_refresh.return_value = None  # refresh failed
        mock_auth.return_value = None  # device auth also fails

        result = get_authenticated_youtube_service()

        mock_auth.assert_called_once()
        self.assertIsNone(result)

    @patch("auth.oauth._is_expired")
    @patch("auth.oauth._row_to_credentials")
    @patch("auth.oauth._load_credential")
    def test_returns_none_when_build_raises(
        self, mock_load, mock_row_to_creds, mock_is_expired
    ):
        row = _make_row()
        mock_load.return_value = row
        mock_row_to_creds.return_value = MagicMock()
        mock_is_expired.return_value = False

        with patch("auth.oauth.build", side_effect=Exception("build failed")):
            result = get_authenticated_youtube_service()

        self.assertIsNone(result)

    @patch("auth.oauth.build")
    @patch("auth.oauth.authenticate_with_device_code")
    @patch("auth.oauth.refresh_credential")
    @patch("auth.oauth._is_expired")
    @patch("auth.oauth._row_to_credentials")
    @patch("auth.oauth._load_credential")
    def test_full_recovery_path_refresh_fails_then_device_auth_succeeds(
        self,
        mock_load,
        mock_row_to_creds,
        mock_is_expired,
        mock_refresh,
        mock_auth,
        mock_build,
    ):
        row = _make_row()
        mock_load.return_value = row
        mock_row_to_creds.return_value = MagicMock()
        mock_is_expired.return_value = True
        mock_refresh.return_value = None  # refresh failed → device auth

        new_row = _make_row(access_token="fresh-tok")
        mock_auth.return_value = new_row
        mock_build.return_value = MagicMock()

        result = get_authenticated_youtube_service()

        mock_auth.assert_called_once()
        self.assertIsNotNone(result)
