from unittest import TestCase
from unittest.mock import MagicMock, patch

from util.healthcheck import healthcheck


class TestHealthcheck(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.example_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        self.mock_youtube = MagicMock()

    def tearDown(self):
        """Clean up after tests"""
        pass

    # Tests for healthcheck
    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_success(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test successful healthcheck"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response
        mock_response = {
            "items": [{"id": self.example_channel_id}],
            "pageInfo": {"totalResults": 1},
        }
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck and expect exit(0)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 0)
        mock_logger.info.assert_called_once_with("Healthcheck passed.")

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.logger")
    def test_healthcheck_youtube_channel_table_missing(
        self, mock_logger, mock_database, mock_oauth
    ):
        """Test healthcheck fails when YouTubeChannel table doesn't exist"""
        # Mock database table existence - YouTubeChannel missing
        mock_database.table_exists.side_effect = lambda table: False

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("YouTubeChannel table does not exist", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.logger")
    def test_healthcheck_oauth_credentials_table_missing(
        self, mock_logger, mock_database, mock_oauth
    ):
        """Test healthcheck fails when oauth_credentials table doesn't exist"""
        # Mock database table existence - oauth_credentials missing
        def table_exists_side_effect(table):
            if table == "youtubechannel":
                return True
            return False

        mock_database.table_exists.side_effect = table_exists_side_effect

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("OAuthCredentials table does not exist", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_no_oauth_credentials(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test healthcheck fails when no OAuth credentials exist"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials - empty
        mock_oauth_creds.select.return_value = []

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("No OAuth credentials found in database", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_no_youtube_service(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test healthcheck fails when YouTube service is not available"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service - None
        mock_oauth.get_authenticated_youtube_service.return_value = None

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("No valid YouTube service available", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_channel_not_found_no_items(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test healthcheck fails when channel is not found (no items in response)"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response - no items
        mock_response = {}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("Healthcheck channel not found", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_channel_not_found_empty_items(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test healthcheck fails when channel is not found (empty items list)"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response - empty items
        mock_response = {"items": [], "pageInfo": {"totalResults": 0}}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("Healthcheck channel not found", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_channel_not_found_zero_results(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test healthcheck fails when channel is not found (zero total results)"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response - zero total results
        mock_response = {
            "items": [{"id": self.example_channel_id}],
            "pageInfo": {"totalResults": 0},
        }
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck and expect exit(1)
        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        self.assertIn("Healthcheck channel not found", error_msg)

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_verifies_correct_channel_id(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test that healthcheck calls YouTube API with correct channel ID"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response
        mock_response = {
            "items": [{"id": self.example_channel_id}],
            "pageInfo": {"totalResults": 1},
        }
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck
        with self.assertRaises(SystemExit):
            healthcheck()

        # Verify YouTube API was called with correct parameters
        mock_youtube.channels().list.assert_called_once_with(
            part="id", id=self.example_channel_id
        )

    @patch("util.healthcheck.oauth")
    @patch("util.healthcheck.database")
    @patch("util.healthcheck.OAuthCredentials")
    @patch("util.healthcheck.logger")
    def test_healthcheck_calls_oauth_with_force_auth(
        self, mock_logger, mock_oauth_creds, mock_database, mock_oauth
    ):
        """Test that healthcheck calls OAuth with force_auth=True"""
        # Mock database table existence
        mock_database.table_exists.side_effect = lambda table: True

        # Mock OAuth credentials
        mock_creds = MagicMock()
        mock_oauth_creds.select.return_value = [mock_creds]

        # Mock YouTube service
        mock_youtube = MagicMock()
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        # Mock YouTube API response
        mock_response = {
            "items": [{"id": self.example_channel_id}],
            "pageInfo": {"totalResults": 1},
        }
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_youtube.channels().list.return_value = mock_request

        # Test healthcheck
        with self.assertRaises(SystemExit):
            healthcheck()

        # Verify OAuth was called with force_auth=True
        mock_oauth.get_authenticated_youtube_service.assert_called_once_with(
            force_auth=True
        )
