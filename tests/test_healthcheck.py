from unittest import TestCase
from unittest.mock import MagicMock, patch

from util.healthcheck import healthcheck


class TestHealthcheck(TestCase):
    def setUp(self):
        self.example_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"

    # Successful healthcheck: youtube service returns a response with items and totalResults >=1
    @patch("util.healthcheck.logger")
    @patch("util.healthcheck.oauth")
    def test_healthcheck_success(self, mock_oauth, mock_logger):
        mock_youtube = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {
            "items": [{"id": "UC_x5XG1OV2P6uZZ5FSM9Ttw"}],
            "pageInfo": {"totalResults": 1},
        }
        mock_youtube.channels().list.return_value = mock_request
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 0)
        mock_logger.info.assert_called_once_with("Healthcheck passed.")

    # No youtube service available -> exit(1)
    @patch("util.healthcheck.logger")
    @patch("util.healthcheck.oauth")
    def test_healthcheck_no_youtube_service(self, mock_oauth, mock_logger):
        mock_oauth.get_authenticated_youtube_service.return_value = None

        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called()

    # Channel not found scenarios
    @patch("util.healthcheck.logger")
    @patch("util.healthcheck.oauth")
    def test_healthcheck_channel_not_found_no_items(self, mock_oauth, mock_logger):
        mock_youtube = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {}
        mock_youtube.channels().list.return_value = mock_request
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called()

    @patch("util.healthcheck.logger")
    @patch("util.healthcheck.oauth")
    def test_healthcheck_channel_not_found_empty_items(self, mock_oauth, mock_logger):
        mock_youtube = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"items": [], "pageInfo": {"totalResults": 0}}
        mock_youtube.channels().list.return_value = mock_request
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        with self.assertRaises(SystemExit) as cm:
            healthcheck()

        self.assertEqual(cm.exception.code, 1)
        mock_logger.error.assert_called()

    @patch("util.healthcheck.oauth")
    def test_healthcheck_calls_oauth_get_authenticated_service(self, mock_oauth):
        mock_youtube = MagicMock()
        mock_request = MagicMock()
        mock_request.execute.return_value = {"items": [{"id": self.example_channel_id}], "pageInfo": {"totalResults": 1}}
        mock_youtube.channels().list.return_value = mock_request
        mock_oauth.get_authenticated_youtube_service.return_value = mock_youtube

        with self.assertRaises(SystemExit):
            healthcheck()

        mock_oauth.get_authenticated_youtube_service.assert_called_once_with()
