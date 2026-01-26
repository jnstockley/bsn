from datetime import datetime, timezone, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch, call

import requests
from google.auth.credentials import TokenState
from google.oauth2.credentials import Credentials

from auth.oauth import (
    get_authenticated_youtube_service,
    run_auth_flow,
    save_credentials_to_db,
    load_credentials_from_db,
    get_credentials,
    revoke_credentials,
    _now_utc,
    DEVICE_CODE_URL,
    TOKEN_URL,
    REVOKE_URL,
    DEFAULT_SCOPES,
)


class TestOAuth(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.client_id = "test_client_id.apps.googleusercontent.com"
        self.client_secret = "test_client_secret"
        self.user_id = "test_user_id"
        self.user_email = "test@example.com"
        self.access_token = "test_access_token"
        self.refresh_token = "test_refresh_token"
        self.scopes = ["https://www.googleapis.com/auth/youtube.readonly"]

        # Create a mock credentials object
        self.mock_creds = MagicMock(spec=Credentials)
        self.mock_creds.token = self.access_token
        self.mock_creds.refresh_token = self.refresh_token
        self.mock_creds.token_uri = TOKEN_URL
        self.mock_creds.client_id = self.client_id
        self.mock_creds.client_secret = self.client_secret
        self.mock_creds.scopes = self.scopes
        self.mock_creds.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        self.mock_creds.token_state = TokenState.FRESH

    def tearDown(self):
        """Clean up after tests"""
        pass

    # Tests for _now_utc
    def test_now_utc_returns_aware_datetime(self):
        """Test that _now_utc returns a timezone-aware datetime"""
        now = _now_utc()
        self.assertIsInstance(now, datetime)
        self.assertIsNotNone(now.tzinfo)
        self.assertEqual(now.tzinfo, timezone.utc)

    def test_now_utc_returns_current_time(self):
        """Test that _now_utc returns approximately the current time"""
        before = datetime.now(timezone.utc)
        result = _now_utc()
        after = datetime.now(timezone.utc)

        self.assertGreaterEqual(result, before)
        self.assertLessEqual(result, after)

    # Tests for get_authenticated_youtube_service
    @patch("auth.oauth.get_credentials")
    @patch("auth.oauth.build")
    def test_get_authenticated_youtube_service_with_credentials(
        self, mock_build, mock_get_creds
    ):
        """Test getting YouTube service with existing credentials"""
        mock_get_creds.return_value = self.mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = get_authenticated_youtube_service()

        self.assertEqual(result, mock_service)
        mock_get_creds.assert_called_once()
        mock_build.assert_called_once_with("youtube", "v3", credentials=self.mock_creds)

    @patch("auth.oauth.get_credentials")
    def test_get_authenticated_youtube_service_no_credentials_no_force(
        self, mock_get_creds
    ):
        """Test getting YouTube service without credentials and force_auth=False"""
        mock_get_creds.return_value = None

        result = get_authenticated_youtube_service(force_auth=False)

        self.assertIsNone(result)
        mock_get_creds.assert_called_once()

    @patch("auth.oauth.run_auth_flow")
    @patch("auth.oauth.get_credentials")
    @patch("auth.oauth.build")
    def test_get_authenticated_youtube_service_force_auth(
        self, mock_build, mock_get_creds, mock_run_auth
    ):
        """Test getting YouTube service with force_auth=True"""
        mock_get_creds.return_value = None
        mock_run_auth.return_value = self.mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        result = get_authenticated_youtube_service(
            force_auth=True,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

        self.assertEqual(result, mock_service)
        mock_run_auth.assert_called_once_with(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=list(DEFAULT_SCOPES),
        )

    @patch("auth.oauth.get_credentials")
    @patch("auth.oauth.build")
    def test_get_authenticated_youtube_service_build_fails(
        self, mock_build, mock_get_creds
    ):
        """Test when building YouTube service fails"""
        mock_get_creds.return_value = self.mock_creds
        mock_build.side_effect = Exception("Build failed")

        result = get_authenticated_youtube_service()

        self.assertIsNone(result)

    @patch("auth.oauth.get_credentials")
    @patch.dict("os.environ", {"OAUTH_CLIENT_ID": "env_client_id", "OAUTH_CLIENT_SECRET": "env_secret"})
    def test_get_authenticated_youtube_service_uses_env_vars(self, mock_get_creds):
        """Test that service uses environment variables when params not provided"""
        mock_get_creds.return_value = None

        result = get_authenticated_youtube_service(force_auth=False)

        # Should log about checking environment variables
        self.assertIsNone(result)

    @patch("auth.oauth.run_auth_flow")
    @patch("auth.oauth.get_credentials")
    def test_get_authenticated_youtube_service_custom_scopes(
        self, mock_get_creds, mock_run_auth
    ):
        """Test getting YouTube service with custom scopes"""
        mock_get_creds.return_value = None
        custom_scopes = ["https://www.googleapis.com/auth/youtube"]
        mock_run_auth.return_value = self.mock_creds

        get_authenticated_youtube_service(
            force_auth=True,
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=custom_scopes,
        )

        mock_run_auth.assert_called_once_with(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=custom_scopes,
        )

    # Tests for run_auth_flow
    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.save_credentials_to_db")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.time.sleep")
    def test_run_auth_flow_success(
        self, mock_sleep, mock_load_creds, mock_save_creds, mock_post
    ):
        """Test successful OAuth device flow"""
        # Mock device code response
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        # Mock token response (success on first try)
        token_response = MagicMock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": 3600,
        }

        mock_post.side_effect = [device_response, token_response]
        mock_load_creds.return_value = self.mock_creds

        result = run_auth_flow(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=self.scopes,
        )

        self.assertEqual(result, self.mock_creds)
        self.assertEqual(mock_post.call_count, 2)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.OAuthCredentials")
    def test_run_auth_flow_no_client_id(self, mock_oauth_creds, mock_post):
        """Test run_auth_flow raises error when no client_id available"""
        mock_oauth_creds.select().first.return_value = None

        with self.assertRaises(ValueError) as context:
            run_auth_flow(client_id=None)

        self.assertIn("client_id must be provided", str(context.exception))

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.OAuthCredentials")
    def test_run_auth_flow_uses_db_client_id(self, mock_oauth_creds, mock_post):
        """Test run_auth_flow uses client_id from database when not provided"""
        mock_row = MagicMock()
        mock_row.client_id = self.client_id
        mock_oauth_creds.select().first.return_value = mock_row

        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()
        mock_post.return_value = device_response

        with patch("auth.oauth.time.sleep"):
            with patch("auth.oauth.time.time", side_effect=[0, 1000]):
                # Will timeout
                result = run_auth_flow(client_id=None)

        # Should have attempted with DB client_id
        mock_post.assert_called()

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_timeout(self, mock_time, mock_sleep, mock_post):
        """Test run_auth_flow times out waiting for authorization"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        token_response = MagicMock()
        token_response.status_code = 400
        token_response.json.return_value = {"error": "authorization_pending"}

        mock_post.side_effect = [device_response] + [token_response] * 10
        mock_time.side_effect = [0, 0] + [1000] * 20  # Simulate timeout

        result = run_auth_flow(
            client_id=self.client_id, client_secret=self.client_secret, timeout=10
        )

        self.assertIsNone(result)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.save_credentials_to_db")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_authorization_pending(
        self, mock_time, mock_sleep, mock_load_creds, mock_save_creds, mock_post
    ):
        """Test run_auth_flow handles authorization_pending correctly"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        pending_response = MagicMock()
        pending_response.status_code = 400
        pending_response.json.return_value = {"error": "authorization_pending"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": 3600,
        }

        mock_post.side_effect = [device_response, pending_response, success_response]
        mock_load_creds.return_value = self.mock_creds
        mock_time.side_effect = [0, 1, 2, 3, 4, 5]

        result = run_auth_flow(client_id=self.client_id)

        self.assertEqual(result, self.mock_creds)
        mock_sleep.assert_called()

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_slow_down(self, mock_time, mock_sleep, mock_post):
        """Test run_auth_flow handles slow_down error"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        slow_down_response = MagicMock()
        slow_down_response.status_code = 400
        slow_down_response.json.return_value = {"error": "slow_down"}

        mock_post.side_effect = [device_response, slow_down_response] + [
            slow_down_response
        ] * 10
        mock_time.side_effect = [0, 1] + [1000] * 20

        result = run_auth_flow(client_id=self.client_id, timeout=10)

        self.assertIsNone(result)
        # Should have increased interval
        mock_sleep.assert_called()

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_access_denied(self, mock_time, mock_post):
        """Test run_auth_flow handles access_denied error"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        denied_response = MagicMock()
        denied_response.status_code = 400
        denied_response.json.return_value = {"error": "access_denied"}

        mock_post.side_effect = [device_response, denied_response]
        mock_time.side_effect = [0, 1, 2]

        result = run_auth_flow(client_id=self.client_id)

        self.assertIsNone(result)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_expired_token(self, mock_time, mock_post):
        """Test run_auth_flow handles expired_token error"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        expired_response = MagicMock()
        expired_response.status_code = 400
        expired_response.json.return_value = {"error": "expired_token"}

        mock_post.side_effect = [device_response, expired_response]
        mock_time.side_effect = [0, 1, 2]

        result = run_auth_flow(client_id=self.client_id)

        self.assertIsNone(result)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_unknown_error(self, mock_time, mock_post):
        """Test run_auth_flow handles unknown errors"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"error": "unknown_error"}

        mock_post.side_effect = [device_response, error_response]
        mock_time.side_effect = [0, 1, 2]

        result = run_auth_flow(client_id=self.client_id)

        self.assertIsNone(result)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.sleep")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_network_error_during_polling(
        self, mock_time, mock_sleep, mock_post
    ):
        """Test run_auth_flow handles network errors during polling"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        mock_post.side_effect = [
            device_response,
            requests.RequestException("Network error"),
        ] + [device_response] * 10
        mock_time.side_effect = [0, 1] + [1000] * 20

        result = run_auth_flow(client_id=self.client_id, timeout=10)

        self.assertIsNone(result)
        mock_sleep.assert_called()

    # Tests for save_credentials_to_db
    @patch("auth.oauth.OAuthCredentials")
    def test_save_credentials_to_db_creates_new(self, mock_oauth_creds):
        """Test saving new credentials to database"""
        mock_row = MagicMock()
        mock_row.id = 1
        mock_oauth_creds.get_or_create.return_value = (mock_row, True)

        result = save_credentials_to_db(
            self.mock_creds,
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_email=self.user_email,
            user_id=self.user_id,
        )

        self.assertEqual(result, 1)
        mock_oauth_creds.get_or_create.assert_called_once()

    @patch("auth.oauth.OAuthCredentials")
    def test_save_credentials_to_db_updates_existing(self, mock_oauth_creds):
        """Test updating existing credentials in database"""
        mock_row = MagicMock()
        mock_row.id = 1
        mock_oauth_creds.get_or_create.return_value = (mock_row, False)

        result = save_credentials_to_db(
            self.mock_creds,
            client_id=self.client_id,
            client_secret=self.client_secret,
        )

        self.assertEqual(result, 1)
        mock_row.save.assert_called_once()

    @patch("auth.oauth.OAuthCredentials")
    def test_save_credentials_to_db_handles_no_scopes(self, mock_oauth_creds):
        """Test saving credentials without scopes"""
        mock_row = MagicMock()
        mock_row.id = 1
        self.mock_creds.scopes = None
        mock_oauth_creds.get_or_create.return_value = (mock_row, True)

        result = save_credentials_to_db(self.mock_creds)

        self.assertEqual(result, 1)

    @patch("auth.oauth.OAuthCredentials")
    def test_save_credentials_to_db_handles_scopes_join_exception(self, mock_oauth_creds):
        """Test saving credentials when joining scopes fails"""
        mock_row = MagicMock()
        mock_row.id = 1
        # Create a mock that raises when iterated
        mock_scopes = MagicMock()
        mock_scopes.__iter__ = MagicMock(side_effect=Exception("Iterator error"))
        self.mock_creds.scopes = mock_scopes
        mock_oauth_creds.get_or_create.return_value = (mock_row, True)

        result = save_credentials_to_db(self.mock_creds)

        self.assertEqual(result, 1)

    # Tests for load_credentials_from_db
    @patch("auth.oauth.OAuthCredentials")
    def test_load_credentials_from_db_success(self, mock_oauth_creds):
        """Test successfully loading credentials from database"""
        mock_row = MagicMock()
        mock_row.access_token = self.access_token
        mock_row.refresh_token = self.refresh_token
        mock_row.token_uri = TOKEN_URL
        mock_row.client_id = self.client_id
        mock_row.client_secret = self.client_secret
        mock_row.scopes = " ".join(self.scopes)
        mock_row.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_oauth_creds.select().first.return_value = mock_row

        result = load_credentials_from_db()

        self.assertIsNotNone(result)
        self.assertIsInstance(result, Credentials)
        self.assertEqual(result.token, self.access_token)
        self.assertEqual(result.refresh_token, self.refresh_token)

    @patch("auth.oauth.OAuthCredentials")
    def test_load_credentials_from_db_no_credentials(self, mock_oauth_creds):
        """Test loading credentials when none exist"""
        mock_oauth_creds.select().first.return_value = None

        result = load_credentials_from_db()

        self.assertIsNone(result)

    @patch("auth.oauth.OAuthCredentials")
    def test_load_credentials_from_db_with_user_id(self, mock_oauth_creds):
        """Test loading credentials for specific user"""
        mock_row = MagicMock()
        mock_row.access_token = self.access_token
        mock_row.refresh_token = self.refresh_token
        mock_row.token_uri = TOKEN_URL
        mock_row.client_id = self.client_id
        mock_row.client_secret = self.client_secret
        mock_row.scopes = " ".join(self.scopes)
        mock_row.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_oauth_creds.get_or_none.return_value = mock_row

        result = load_credentials_from_db(user_id=self.user_id)

        self.assertIsNotNone(result)
        mock_oauth_creds.get_or_none.assert_called_once()

    @patch("auth.oauth.OAuthCredentials")
    def test_load_credentials_from_db_handles_exception(self, mock_oauth_creds):
        """Test loading credentials handles exceptions"""
        mock_oauth_creds.select().first.side_effect = Exception("DB error")

        result = load_credentials_from_db()

        self.assertIsNone(result)

    # Tests for get_credentials
    @patch("auth.oauth.load_credentials_from_db")
    def test_get_credentials_fresh_token(self, mock_load_creds):
        """Test getting fresh credentials that don't need refresh"""
        self.mock_creds.token_state = TokenState.FRESH
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials()

        self.assertEqual(result, self.mock_creds)
        mock_load_creds.assert_called_once()

    @patch("auth.oauth.save_credentials_to_db")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.Request")
    def test_get_credentials_refreshes_stale_token(
        self, mock_request_class, mock_load_creds, mock_save_creds
    ):
        """Test getting credentials refreshes stale token"""
        self.mock_creds.token_state = TokenState.STALE
        self.mock_creds.refresh_token = self.refresh_token
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials()

        self.assertEqual(result, self.mock_creds)
        self.mock_creds.refresh.assert_called_once()
        mock_save_creds.assert_called_once()

    @patch("auth.oauth.save_credentials_to_db")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.Request")
    def test_get_credentials_refreshes_invalid_token(
        self, mock_request_class, mock_load_creds, mock_save_creds
    ):
        """Test getting credentials refreshes invalid token"""
        self.mock_creds.token_state = TokenState.INVALID
        self.mock_creds.refresh_token = self.refresh_token
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials()

        self.assertEqual(result, self.mock_creds)
        self.mock_creds.refresh.assert_called_once()

    @patch("auth.oauth.load_credentials_from_db")
    def test_get_credentials_no_credentials(self, mock_load_creds):
        """Test getting credentials when none exist"""
        mock_load_creds.return_value = None

        result = get_credentials()

        self.assertIsNone(result)

    @patch("auth.oauth.OAuthCredentials")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.Request")
    def test_get_credentials_refresh_fails(
        self, mock_request_class, mock_load_creds, mock_oauth_creds
    ):
        """Test getting credentials when refresh fails"""
        self.mock_creds.token_state = TokenState.STALE
        self.mock_creds.refresh_token = self.refresh_token
        self.mock_creds.refresh.side_effect = Exception("Refresh failed")
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials()

        self.assertIsNone(result)
        mock_oauth_creds.delete().execute.assert_called_once()

    @patch("auth.oauth.OAuthCredentials")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.Request")
    def test_get_credentials_refresh_fails_with_user_id(
        self, mock_request_class, mock_load_creds, mock_oauth_creds
    ):
        """Test getting credentials when refresh fails for specific user"""
        self.mock_creds.token_state = TokenState.STALE
        self.mock_creds.refresh_token = self.refresh_token
        self.mock_creds.refresh.side_effect = Exception("Refresh failed")
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials(user_id=self.user_id)

        self.assertIsNone(result)
        mock_oauth_creds.delete().where().execute.assert_called_once()

    @patch("auth.oauth.load_credentials_from_db")
    def test_get_credentials_no_refresh_token(self, mock_load_creds):
        """Test getting credentials when token is stale but no refresh token"""
        self.mock_creds.token_state = TokenState.STALE
        self.mock_creds.refresh_token = None
        mock_load_creds.return_value = self.mock_creds

        result = get_credentials()

        # Should return credentials without attempting refresh
        self.assertEqual(result, self.mock_creds)

    # Tests for revoke_credentials
    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.OAuthCredentials")
    def test_revoke_credentials_success_with_refresh_token(
        self, mock_oauth_creds, mock_post
    ):
        """Test successfully revoking credentials using refresh token"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = revoke_credentials(self.mock_creds)

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            REVOKE_URL, params={"token": self.refresh_token}, timeout=10
        )
        mock_oauth_creds.delete().where().execute.assert_called_once()

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.OAuthCredentials")
    def test_revoke_credentials_success_with_access_token(
        self, mock_oauth_creds, mock_post
    ):
        """Test successfully revoking credentials using access token"""
        self.mock_creds.refresh_token = None
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_post.return_value = mock_response

        result = revoke_credentials(self.mock_creds)

        self.assertTrue(result)
        mock_post.assert_called_once_with(
            REVOKE_URL, params={"token": self.access_token}, timeout=10
        )

    def test_revoke_credentials_no_token(self):
        """Test revoking credentials when no token available"""
        self.mock_creds.refresh_token = None
        self.mock_creds.token = None

        result = revoke_credentials(self.mock_creds)

        self.assertFalse(result)

    @patch("auth.oauth.requests.post")
    def test_revoke_credentials_fails_with_error_status(self, mock_post):
        """Test revoking credentials fails with error status code"""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        mock_post.return_value = mock_response

        result = revoke_credentials(self.mock_creds)

        self.assertFalse(result)

    @patch("auth.oauth.requests.post")
    def test_revoke_credentials_network_error(self, mock_post):
        """Test revoking credentials handles network errors"""
        mock_post.side_effect = requests.RequestException("Network error")

        result = revoke_credentials(self.mock_creds)

        self.assertFalse(result)

    @patch("auth.oauth.requests.post")
    @patch("auth.oauth.time.time")
    def test_run_auth_flow_invalid_json_response(self, mock_time, mock_post):
        """Test run_auth_flow handles invalid JSON in error response"""
        device_response = MagicMock()
        device_response.json.return_value = {
            "device_code": "test_device_code",
            "user_code": "TEST-CODE",
            "verification_url": "https://google.com/device",
            "expires_in": 600,
            "interval": 5,
        }
        device_response.raise_for_status = MagicMock()

        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.side_effect = ValueError("Invalid JSON")

        mock_post.side_effect = [device_response, error_response]
        mock_time.side_effect = [0, 1, 2]

        result = run_auth_flow(client_id=self.client_id)

        self.assertIsNone(result)

    @patch("auth.oauth.OAuthCredentials")
    @patch("auth.oauth.load_credentials_from_db")
    @patch("auth.oauth.Request")
    def test_get_credentials_refresh_fails_delete_exception(
        self, mock_request_class, mock_load_creds, mock_oauth_creds
    ):
        """Test getting credentials when refresh and delete both fail"""
        self.mock_creds.token_state = TokenState.STALE
        self.mock_creds.refresh_token = self.refresh_token
        self.mock_creds.refresh.side_effect = Exception("Refresh failed")
        mock_load_creds.return_value = self.mock_creds

        # Make the delete operation also fail
        mock_oauth_creds.delete().execute.side_effect = Exception("Delete failed")

        result = get_credentials()

        self.assertIsNone(result)

    # Tests for constants
    def test_constants_defined(self):
        """Test that OAuth constants are properly defined"""
        self.assertEqual(DEVICE_CODE_URL, "https://oauth2.googleapis.com/device/code")
        self.assertEqual(TOKEN_URL, "https://oauth2.googleapis.com/token")
        self.assertEqual(REVOKE_URL, "https://oauth2.googleapis.com/revoke")
        self.assertEqual(
            DEFAULT_SCOPES, ["https://www.googleapis.com/auth/youtube.readonly"]
        )
