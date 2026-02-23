from datetime import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

from notifications.notifications import send_upload_notification


class TestNotifications(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        # sample channel dicts are no longer directly used by send_upload_notification;
        # tests will create mock video objects with a youtube_channel attribute instead.
        self.sample_channel = {
            "id": "UC1234567890",
            "snippet": {"title": "Test Channel"},
            "statistics": {"videoCount": "100"},
        }
        self.sample_channel_2 = {
            "id": "UC0987654321",
            "snippet": {"title": "Another Channel"},
            "statistics": {"videoCount": "200"},
        }

        # sample_video is a dict in previous tests; here we'll build MagicMock video objects
        self.sample_video_dict = {
            "snippet": {
                "title": "Amazing Test Video",
                "resourceId": {"videoId": "dQw4w9WgXcQ"},
            }
        }

    def tearDown(self):
        """Clean up after tests"""
        pass

    def _make_mock_video(
        self,
        channel_name="Test Channel",
        video_id="dQw4w9WgXcQ",
        title="Amazing Test Video",
    ):
        """Helper to create a mock video object with attributes used by send_upload_notification"""
        mock_video = MagicMock()
        mock_video.id = video_id
        mock_video.title = title
        mock_video.url = f"https://www.youtube.com/watch?v={video_id}"
        mock_video.thumbnail_url = "https://img"
        mock_video.uploaded_at = datetime(2026, 2, 20, 12, 0, 0)
        mock_video.youtube_channel_id = "UC1234567890"

        mock_channel = MagicMock()
        mock_channel.name = channel_name

        mock_video.youtube_channel = mock_channel

        return mock_video

    # Tests for send_upload_notification (new behavior)
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_single_video(self, mock_apprise_class):
        """Test sending notification for a single video"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        mock_video = self._make_mock_video()

        send_upload_notification([mock_video])

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify the apprise URL was added
        mock_apprise_instance.add.assert_called_once_with("test://localhost")

        # Verify notify was called with correct title and body
        expected_title = "Test Channel has uploaded a new video to YouTube!"
        expected_body = "Amazing Test Video\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ\nUploaded at: February 20, 2026 12:00 PM"
        mock_apprise_instance.notify.assert_called_once_with(
            title=expected_title, body=expected_body, attach=mock_video.thumbnail_url
        )

    @patch("notifications.notifications.apprise.Apprise")
    @patch(
        "notifications.notifications.apprise_urls",
        ["test://localhost", "test://example.com"],
    )
    def test_send_notifications_multiple_videos(self, mock_apprise_class):
        """Test sending notifications for multiple videos"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        v1 = self._make_mock_video(
            channel_name="Test Channel", video_id="aaa111", title="Video One"
        )
        v2 = self._make_mock_video(
            channel_name="Another Channel", video_id="bbb222", title="Video Two"
        )

        send_upload_notification([v1, v2])

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify both apprise URLs were added
        assert mock_apprise_instance.add.call_count == 2
        mock_apprise_instance.add.assert_any_call("test://localhost")
        mock_apprise_instance.add.assert_any_call("test://example.com")

        # Verify notify was called twice (once per video)
        assert mock_apprise_instance.notify.call_count == 2

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", [])
    def test_send_notifications_empty_apprise_urls(self, mock_apprise_class):
        """Test behavior when no apprise URLs are configured"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        v = self._make_mock_video()

        send_upload_notification([v])

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify add was never called (no URLs)
        mock_apprise_instance.add.assert_not_called()

        # Verify notify was still called once
        mock_apprise_instance.notify.assert_called_once()

    @patch("notifications.notifications.logger")
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_logs_info_for_each_video(
        self, mock_apprise_class, mock_logger
    ):
        """Test that info is logged when sending notifications for videos"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        v = self._make_mock_video()

        send_upload_notification([v])

        # Verify info was logged at least once
        mock_logger.info.assert_called()

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_video_with_special_characters(self, mock_apprise_class):
        """Test sending notification with video title containing special characters"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        special_video = self._make_mock_video(
            title="Test Video: Amazing & Cool! (2026)", video_id="abc123"
        )

        send_upload_notification([special_video])

        # Verify notify was called with the special characters preserved
        mock_apprise_instance.notify.assert_called_once()
        call_args = mock_apprise_instance.notify.call_args
        assert "Test Video: Amazing & Cool! (2026)" in call_args[1]["body"]

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_channel_with_special_characters(
        self, mock_apprise_class
    ):
        """Test sending notification with channel name containing special characters"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        special_video = self._make_mock_video(channel_name="Test & Demo Channel™")

        send_upload_notification([special_video])

        # Verify notify was called with the special characters preserved in title
        mock_apprise_instance.notify.assert_called_once()
        call_args = mock_apprise_instance.notify.call_args
        assert (
            "Test & Demo Channel™ has uploaded a new video to YouTube!"
            in call_args[1]["title"]
        )

    def test_send_notifications_empty_videos_list(self):
        """Test handling of empty videos list (no notifications should be sent)"""
        with patch("notifications.notifications.apprise.Apprise") as mock_apprise_class:
            mock_apprise_instance = MagicMock()
            mock_apprise_class.return_value = mock_apprise_instance

            send_upload_notification([])

            # Apprise instantiated but notify not called
            mock_apprise_class.assert_called_once()
            mock_apprise_instance.notify.assert_not_called()
