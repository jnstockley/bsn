from unittest import TestCase
from unittest.mock import MagicMock, patch

from notifications.notifications import send_youtube_channels_notifications


class TestNotifications(TestCase):
    def setUp(self):
        """Set up test fixtures"""
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
        self.sample_video = {
            "snippet": {
                "title": "Amazing Test Video",
                "resourceId": {"videoId": "dQw4w9WgXcQ"},
            }
        }

    def tearDown(self):
        """Clean up after tests"""
        pass

    # Tests for send_youtube_channels_notifications
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_single_channel_with_video(self, mock_apprise_class):
        """Test sending notification for a single channel with video details"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], self.sample_video)

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify the apprise URL was added
        mock_apprise_instance.add.assert_called_once_with("test://localhost")

        # Verify notify was called with correct title and body
        expected_title = "Test Channel has uploaded a new video to YouTube!"
        expected_body = "Amazing Test Video\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_apprise_instance.notify.assert_called_once_with(
            title=expected_title, body=expected_body
        )

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_multiple_channels(self, mock_apprise_class):
        """Test sending notification for multiple channels"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        channels = [self.sample_channel, self.sample_channel_2]
        send_youtube_channels_notifications(channels, None)

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify the apprise URL was added
        mock_apprise_instance.add.assert_called_once_with("test://localhost")

        # Verify notify was called with correct title and body
        expected_title = "Test Channel,Another Channel have uploaded new videos to YouTube!"
        expected_body = "Check them out here: https://www.youtube.com/feed/subscriptions"
        mock_apprise_instance.notify.assert_called_once_with(
            title=expected_title, body=expected_body
        )

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_single_channel_without_video(self, mock_apprise_class):
        """Test sending notification for a single channel without video details (should not send)"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], None)

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify the apprise URL was added
        mock_apprise_instance.add.assert_called_once_with("test://localhost")

        # Verify notify was NOT called (returns early with warning)
        mock_apprise_instance.notify.assert_not_called()

    @patch("notifications.notifications.apprise.Apprise")
    @patch(
        "notifications.notifications.apprise_urls",
        ["test://localhost", "test://example.com"],
    )
    def test_send_notifications_multiple_apprise_urls(self, mock_apprise_class):
        """Test that multiple apprise URLs are added"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], self.sample_video)

        # Verify both apprise URLs were added
        assert mock_apprise_instance.add.call_count == 2
        mock_apprise_instance.add.assert_any_call("test://localhost")
        mock_apprise_instance.add.assert_any_call("test://example.com")

        # Verify notify was still called once
        mock_apprise_instance.notify.assert_called_once()

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_three_channels(self, mock_apprise_class):
        """Test sending notification for three channels"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        channel_3 = {
            "id": "UC1111111111",
            "snippet": {"title": "Third Channel"},
            "statistics": {"videoCount": "300"},
        }
        channels = [self.sample_channel, self.sample_channel_2, channel_3]
        send_youtube_channels_notifications(channels, None)

        # Verify notify was called with all three channel names
        expected_title = "Test Channel,Another Channel,Third Channel have uploaded new videos to YouTube!"
        expected_body = "Check them out here: https://www.youtube.com/feed/subscriptions"
        mock_apprise_instance.notify.assert_called_once_with(
            title=expected_title, body=expected_body
        )

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_video_with_special_characters(self, mock_apprise_class):
        """Test sending notification with video title containing special characters"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        special_video = {
            "snippet": {
                "title": "Test Video: Amazing & Cool! (2026)",
                "resourceId": {"videoId": "abc123"},
            }
        }

        send_youtube_channels_notifications([self.sample_channel], special_video)

        # Verify notify was called with the special characters preserved
        expected_body = "Test Video: Amazing & Cool! (2026)\nhttps://www.youtube.com/watch?v=abc123"
        mock_apprise_instance.notify.assert_called_once()
        call_args = mock_apprise_instance.notify.call_args
        assert call_args[1]["body"] == expected_body

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_channel_with_special_characters(
        self, mock_apprise_class
    ):
        """Test sending notification with channel name containing special characters"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        special_channel = {
            "id": "UC1234567890",
            "snippet": {"title": "Test & Demo Channel™"},
            "statistics": {"videoCount": "100"},
        }

        send_youtube_channels_notifications([special_channel], self.sample_video)

        # Verify notify was called with the special characters preserved in title
        expected_title = "Test & Demo Channel™ has uploaded a new video to YouTube!"
        mock_apprise_instance.notify.assert_called_once()
        call_args = mock_apprise_instance.notify.call_args
        assert call_args[1]["title"] == expected_title

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", [])
    def test_send_notifications_empty_apprise_urls(self, mock_apprise_class):
        """Test behavior when no apprise URLs are configured"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], self.sample_video)

        # Verify Apprise was instantiated
        mock_apprise_class.assert_called_once()

        # Verify add was never called (no URLs)
        mock_apprise_instance.add.assert_not_called()

        # Verify notify was still called (Apprise handles no destinations gracefully)
        mock_apprise_instance.notify.assert_called_once()

    @patch("notifications.notifications.logger")
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_logs_warning_for_no_video(
        self, mock_apprise_class, mock_logger
    ):
        """Test that a warning is logged when single channel has no video"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], None)

        # Verify warning was logged
        mock_logger.warning.assert_called_once_with("No video found")

    @patch("notifications.notifications.logger")
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_logs_info_for_multiple_channels(
        self, mock_apprise_class, mock_logger
    ):
        """Test that info is logged when sending notifications for multiple channels"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        channels = [self.sample_channel, self.sample_channel_2]
        send_youtube_channels_notifications(channels, None)

        # Verify info was logged
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Sending notifications for" in call_args
        assert "channels" in call_args

    @patch("notifications.notifications.logger")
    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_logs_info_for_single_channel_with_video(
        self, mock_apprise_class, mock_logger
    ):
        """Test that info is logged when sending notifications for single channel with video"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        send_youtube_channels_notifications([self.sample_channel], self.sample_video)

        # Verify info was logged
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "Sending notifications for" in call_args
        assert "channels" in call_args

    @patch("notifications.notifications.apprise.Apprise")
    @patch("notifications.notifications.apprise_urls", ["test://localhost"])
    def test_send_notifications_empty_channels_list(self, mock_apprise_class):
        """Test handling of empty channels list"""
        mock_apprise_instance = MagicMock()
        mock_apprise_class.return_value = mock_apprise_instance

        # This should raise an IndexError or be handled
        # Based on the code, it will try to access channels[0] when len != > 1
        # and video is provided, which will fail
        # Let's test the case where no video is provided with empty list
        with self.assertRaises(IndexError):
            send_youtube_channels_notifications([], self.sample_video)
