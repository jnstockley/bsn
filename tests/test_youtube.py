from datetime import datetime, timedelta
from unittest import TestCase
from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError

from models.models import YouTubeChannel, OAuthCredentials
from youtube.youtube import (
    pull_youtube_subscriptions,
    get_channels_by_id,
    get_channels_with_new_videos,
    update_channels,
    check_for_new_videos,
    get_most_recent_video,
    calculate_interval_between_cycles,
    _chunk_list,
)


class TestYouTube(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.mock_youtube = MagicMock()
        self.sample_channel_id = "UC1234567890"
        self.sample_channel_id_2 = "UC0987654321"

    def tearDown(self):
        """Clean up after tests"""
        pass

    # Tests for pull_youtube_subscriptions
    def test_pull_youtube_subscriptions_single_page(self):
        """Test pulling subscriptions when all results fit in one page"""
        mock_response = {
            "items": [
                {
                    "snippet": {"resourceId": {"channelId": self.sample_channel_id}},
                    "contentDetails": {"totalItemCount": "100"},
                }
            ],
            "pageInfo": {"totalResults": 1},
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.subscriptions().list.return_value = mock_request

        with patch.object(
            YouTubeChannel, "select"
        ) as mock_select, patch.object(
            YouTubeChannel, "create"
        ) as mock_create:
            # Mock the query chain: select().where().exists()
            mock_query = MagicMock()
            mock_query.where.return_value.exists.return_value = False
            mock_select.return_value = mock_query

            # Mock the iteration over select() for the deletion check
            mock_select.return_value.__iter__.return_value = []

            pull_youtube_subscriptions(self.mock_youtube)

            mock_create.assert_called_once_with(
                id=self.sample_channel_id, num_videos=100
            )

    def test_pull_youtube_subscriptions_multiple_pages(self):
        """Test pulling subscriptions with pagination"""
        mock_response_page1 = {
            "items": [
                {
                    "snippet": {"resourceId": {"channelId": self.sample_channel_id}},
                    "contentDetails": {"totalItemCount": "100"},
                }
            ],
            "pageInfo": {"totalResults": 2},
            "nextPageToken": "token123",
        }

        mock_response_page2 = {
            "items": [
                {
                    "snippet": {"resourceId": {"channelId": self.sample_channel_id_2}},
                    "contentDetails": {"totalItemCount": "200"},
                }
            ],
            "pageInfo": {"totalResults": 2},
        }

        mock_request = MagicMock()
        mock_request.execute.side_effect = [mock_response_page1, mock_response_page2]
        self.mock_youtube.subscriptions().list.return_value = mock_request

        with patch.object(
            YouTubeChannel, "select"
        ) as mock_select, patch.object(
            YouTubeChannel, "create"
        ) as mock_create:
            # Mock the query chain: select().where().exists()
            mock_query = MagicMock()
            mock_query.where.return_value.exists.return_value = False
            mock_select.return_value = mock_query

            # Mock the iteration over select() for the deletion check
            mock_select.return_value.__iter__.return_value = []

            pull_youtube_subscriptions(self.mock_youtube)

            assert mock_create.call_count == 2

    def test_pull_youtube_subscriptions_deletes_unsubscribed_channels(self):
        """Test that channels no longer subscribed are deleted"""
        mock_response = {
            "items": [
                {
                    "snippet": {"resourceId": {"channelId": self.sample_channel_id}},
                    "contentDetails": {"totalItemCount": "100"},
                }
            ],
            "pageInfo": {"totalResults": 1},
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.subscriptions().list.return_value = mock_request

        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id_2

        with patch.object(
            YouTubeChannel, "select"
        ) as mock_select, patch.object(
            YouTubeChannel, "delete_by_id"
        ) as mock_delete, patch.object(
            YouTubeChannel, "create"
        ) as mock_create:
            # Mock the query chain: select().where().exists()
            mock_query = MagicMock()
            mock_query.where.return_value.exists.return_value = False
            mock_select.return_value = mock_query

            # Mock the iteration over select() for the deletion check
            mock_select.return_value.__iter__.return_value = [mock_channel]

            pull_youtube_subscriptions(self.mock_youtube)

            mock_delete.assert_called_once_with(self.sample_channel_id_2)

    def test_pull_youtube_subscriptions_skips_existing_channels(self):
        """Test that existing channels are not recreated"""
        mock_response = {
            "items": [
                {
                    "snippet": {"resourceId": {"channelId": self.sample_channel_id}},
                    "contentDetails": {"totalItemCount": "100"},
                }
            ],
            "pageInfo": {"totalResults": 1},
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.subscriptions().list.return_value = mock_request

        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        with patch.object(
            YouTubeChannel, "select"
        ) as mock_select, patch.object(
            YouTubeChannel, "create"
        ) as mock_create:
            # Mock the query chain: select().where().exists()
            mock_query = MagicMock()
            mock_query.where.return_value.exists.return_value = True
            mock_select.return_value = mock_query

            # Mock the iteration over select() for the deletion check
            mock_select.return_value.__iter__.return_value = [mock_channel]

            pull_youtube_subscriptions(self.mock_youtube)

            mock_create.assert_not_called()

    # Tests for get_channels_by_id
    def test_get_channels_by_id_success(self):
        """Test successfully getting channels by ID"""
        mock_response = {
            "items": [
                {
                    "id": self.sample_channel_id,
                    "statistics": {"videoCount": "100"},
                    "snippet": {"title": "Test Channel"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.channels().list.return_value = mock_request

        result = get_channels_by_id(self.mock_youtube, [self.sample_channel_id])

        assert result == mock_response["items"]
        self.mock_youtube.channels().list.assert_called_once_with(
            part="statistics,snippet", id=self.sample_channel_id
        )

    def test_get_channels_by_id_chunks_large_lists(self):
        """Test that channel IDs are chunked when there are more than 50"""
        channel_ids = [f"UC{i:08d}" for i in range(75)]

        mock_response = {"items": [{"id": "test"}]}
        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.channels().list.return_value = mock_request

        result = get_channels_by_id(self.mock_youtube, channel_ids)

        # Should be called twice (50 + 25)
        assert self.mock_youtube.channels().list.call_count == 2
        assert len(result) == 2

    def test_get_channels_by_id_no_items_found(self):
        """Test handling when no items are found"""
        mock_response = {}

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.channels().list.return_value = mock_request

        result = get_channels_by_id(self.mock_youtube, [self.sample_channel_id])

        assert result is None

    def test_get_channels_by_id_http_error(self):
        """Test handling of HTTP errors"""
        mock_request = MagicMock()
        mock_request.uri = "https://youtube.com/test"

        http_error = HttpError(
            resp=MagicMock(status=403),
            content=b"Quota exceeded"
        )
        mock_request.execute.side_effect = http_error
        self.mock_youtube.channels().list.return_value = mock_request

        result = get_channels_by_id(self.mock_youtube, [self.sample_channel_id])

        assert result is None

    # Tests for get_channels_with_new_videos
    def test_get_channels_with_new_videos_new_video_found(self):
        """Test detecting channels with new videos"""
        mock_prev_channel = MagicMock()
        mock_prev_channel.id = self.sample_channel_id
        mock_prev_channel.num_videos = 100

        current_channels = [
            {
                "id": self.sample_channel_id,
                "statistics": {"videoCount": "101"},
            }
        ]

        result = get_channels_with_new_videos([mock_prev_channel], current_channels)

        assert len(result) == 1
        assert result[0]["id"] == self.sample_channel_id

    def test_get_channels_with_new_videos_no_new_videos(self):
        """Test when no new videos are found"""
        mock_prev_channel = MagicMock()
        mock_prev_channel.id = self.sample_channel_id
        mock_prev_channel.num_videos = 100

        current_channels = [
            {
                "id": self.sample_channel_id,
                "statistics": {"videoCount": "100"},
            }
        ]

        result = get_channels_with_new_videos([mock_prev_channel], current_channels)

        assert len(result) == 0

    def test_get_channels_with_new_videos_video_removed(self):
        """Test handling when videos are removed from a channel"""
        mock_prev_channel = MagicMock()
        mock_prev_channel.id = self.sample_channel_id
        mock_prev_channel.num_videos = 100

        current_channels = [
            {
                "id": self.sample_channel_id,
                "statistics": {"videoCount": "99"},
            }
        ]

        with patch.object(YouTubeChannel, "update") as mock_update:
            mock_update.return_value.where.return_value.execute.return_value = None

            result = get_channels_with_new_videos([mock_prev_channel], current_channels)

            assert len(result) == 0
            mock_update.assert_called_once_with(num_videos=99)

    # Tests for update_channels
    def test_update_channels(self):
        """Test updating channel video counts"""
        channels = [
            {
                "id": self.sample_channel_id,
                "statistics": {"videoCount": "101"},
            }
        ]

        with patch.object(YouTubeChannel, "update") as mock_update:
            mock_update.return_value.where.return_value.execute.return_value = None

            update_channels(channels)

            mock_update.assert_called_once_with(num_videos=101)

    def test_update_channels_multiple(self):
        """Test updating multiple channels"""
        channels = [
            {
                "id": self.sample_channel_id,
                "statistics": {"videoCount": "101"},
            },
            {
                "id": self.sample_channel_id_2,
                "statistics": {"videoCount": "202"},
            },
        ]

        with patch.object(YouTubeChannel, "update") as mock_update:
            mock_update.return_value.where.return_value.execute.return_value = None

            update_channels(channels)

            assert mock_update.call_count == 2

    # Tests for check_for_new_videos
    @patch("youtube.youtube.send_youtube_channels_notifications")
    @patch("youtube.youtube.get_most_recent_video")
    @patch("youtube.youtube.update_channels")
    @patch("youtube.youtube.get_channels_with_new_videos")
    @patch("youtube.youtube.get_channels_by_id")
    def test_check_for_new_videos_single_channel(
        self,
        mock_get_by_id,
        mock_get_new,
        mock_update,
        mock_get_video,
        mock_send_notif,
    ):
        """Test checking for new videos with a single channel"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        current_channels = [{"id": self.sample_channel_id}]
        new_video_channels = [{"id": self.sample_channel_id}]
        mock_video = {"snippet": {"title": "Test Video"}}

        with patch.object(YouTubeChannel, "select") as mock_select:
            mock_select.return_value = [mock_channel]
            mock_get_by_id.return_value = current_channels
            mock_get_new.return_value = new_video_channels
            mock_get_video.return_value = mock_video

            check_for_new_videos(self.mock_youtube)

            mock_get_video.assert_called_once_with(
                self.mock_youtube, self.sample_channel_id
            )
            mock_send_notif.assert_called_once_with(new_video_channels, mock_video)

    @patch("youtube.youtube.send_youtube_channels_notifications")
    @patch("youtube.youtube.get_most_recent_video")
    @patch("youtube.youtube.update_channels")
    @patch("youtube.youtube.get_channels_with_new_videos")
    @patch("youtube.youtube.get_channels_by_id")
    def test_check_for_new_videos_multiple_channels(
        self,
        mock_get_by_id,
        mock_get_new,
        mock_update,
        mock_get_video,
        mock_send_notif,
    ):
        """Test checking for new videos with multiple channels"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        current_channels = [
            {"id": self.sample_channel_id},
            {"id": self.sample_channel_id_2},
        ]
        new_video_channels = [
            {"id": self.sample_channel_id},
            {"id": self.sample_channel_id_2},
        ]

        with patch.object(YouTubeChannel, "select") as mock_select:
            mock_select.return_value = [mock_channel]
            mock_get_by_id.return_value = current_channels
            mock_get_new.return_value = new_video_channels

            check_for_new_videos(self.mock_youtube)

            mock_get_video.assert_not_called()
            mock_send_notif.assert_called_once_with(new_video_channels, None)

    @patch("youtube.youtube.send_youtube_channels_notifications")
    @patch("youtube.youtube.update_channels")
    @patch("youtube.youtube.get_channels_with_new_videos")
    @patch("youtube.youtube.get_channels_by_id")
    def test_check_for_new_videos_no_new_videos(
        self, mock_get_by_id, mock_get_new, mock_update, mock_send_notif
    ):
        """Test checking for new videos when there are none"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        current_channels = [{"id": self.sample_channel_id}]
        new_video_channels = []

        with patch.object(YouTubeChannel, "select") as mock_select:
            mock_select.return_value = [mock_channel]
            mock_get_by_id.return_value = current_channels
            mock_get_new.return_value = new_video_channels

            check_for_new_videos(self.mock_youtube)

            mock_send_notif.assert_not_called()

    # Tests for get_most_recent_video
    def test_get_most_recent_video_success(self):
        """Test successfully getting the most recent video"""
        now = datetime.now()
        published_at = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "publishedAt": published_at,
                        "position": 0,
                    },
                    "status": {"privacyStatus": "public"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result == mock_response["items"][0]

    def test_get_most_recent_video_not_public(self):
        """Test when the most recent video is not public"""
        now = datetime.now()
        published_at = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "publishedAt": published_at,
                        "position": 0,
                    },
                    "status": {"privacyStatus": "private"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result is None

    def test_get_most_recent_video_too_old(self):
        """Test when the most recent video is too old"""
        now = datetime.now()
        published_at = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "publishedAt": published_at,
                        "position": 0,
                    },
                    "status": {"privacyStatus": "public"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result is None

    def test_get_most_recent_video_wrong_position(self):
        """Test when the video is not in position 0"""
        now = datetime.now()
        published_at = (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "publishedAt": published_at,
                        "position": 1,
                    },
                    "status": {"privacyStatus": "public"},
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result is None

    def test_get_most_recent_video_no_items(self):
        """Test when no items are returned"""
        mock_response = {}

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        mock_request.uri = "https://youtube.com/test"
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result is None

    def test_get_most_recent_video_http_error(self):
        """Test handling of HTTP errors"""
        mock_request = MagicMock()
        mock_request.uri = "https://youtube.com/test"

        http_error = HttpError(
            resp=MagicMock(status=404),
            content=b"Playlist not found"
        )
        mock_request.execute.side_effect = http_error
        self.mock_youtube.playlistItems().list.return_value = mock_request

        result = get_most_recent_video(self.mock_youtube, self.sample_channel_id)

        assert result is None

    # Tests for calculate_interval_between_cycles
    def test_calculate_interval_between_cycles_single_key(self):
        """Test interval calculation with a single API key"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id
        mock_cred = MagicMock()

        with patch.object(YouTubeChannel, "select") as mock_channel_select, patch.object(
            OAuthCredentials, "select"
        ) as mock_cred_select:
            mock_channel_select.return_value = [mock_channel]
            mock_cred_select.return_value = [mock_cred]

            interval = calculate_interval_between_cycles()

            # With 1 channel and 1 API key:
            # requests_per_cycle = 1 (rounded up from (1+1)/50)
            # num_cycles_per_day = 10000 / 1 = 10000
            # interval = 86400 / 10000 = 8.64 seconds
            assert interval == 9  # Rounded up

    def test_calculate_interval_between_cycles_multiple_keys(self):
        """Test interval calculation with multiple API keys"""
        mock_channels = [MagicMock() for _ in range(100)]
        mock_creds = [MagicMock() for _ in range(2)]

        with patch.object(YouTubeChannel, "select") as mock_channel_select, patch.object(
            OAuthCredentials, "select"
        ) as mock_cred_select:
            mock_channel_select.return_value = mock_channels
            mock_cred_select.return_value = mock_creds

            interval = calculate_interval_between_cycles()

            # With 100 channels and 2 API keys:
            # requests_per_cycle = 3 (rounded up from (100+1)/50)
            # total_requests = 2 * 10000 = 20000
            # num_cycles_per_day = 20000 / 3 = 6666
            # interval = 86400 / 6666 = 12.96 seconds
            assert interval == 13  # Rounded up

    def test_calculate_interval_between_cycles_many_channels(self):
        """Test interval calculation with many channels"""
        mock_channels = [MagicMock() for _ in range(500)]
        mock_creds = [MagicMock()]

        with patch.object(YouTubeChannel, "select") as mock_channel_select, patch.object(
            OAuthCredentials, "select"
        ) as mock_cred_select:
            mock_channel_select.return_value = mock_channels
            mock_cred_select.return_value = mock_creds

            interval = calculate_interval_between_cycles()

            # With 500 channels and 1 API key:
            # requests_per_cycle = 11 (rounded up from (500+1)/50)
            # num_cycles_per_day = 10000 / 11 = 909
            # interval = 86400 / 909 = 95.05 seconds
            assert interval == 96  # Rounded up

    # Tests for _chunk_list
    def test_chunk_list_less_than_chunk_size(self):
        """Test chunking a list smaller than chunk size"""
        test_list = ["id1", "id2", "id3"]
        result = list(_chunk_list(test_list))

        assert len(result) == 1
        assert result[0] == "id1,id2,id3"

    def test_chunk_list_exactly_chunk_size(self):
        """Test chunking a list exactly equal to chunk size"""
        test_list = [f"id{i}" for i in range(50)]
        result = list(_chunk_list(test_list))

        assert len(result) == 1
        assert len(result[0].split(",")) == 50

    def test_chunk_list_multiple_chunks(self):
        """Test chunking a list into multiple chunks"""
        test_list = [f"id{i}" for i in range(125)]
        result = list(_chunk_list(test_list))

        assert len(result) == 3
        assert len(result[0].split(",")) == 50
        assert len(result[1].split(",")) == 50
        assert len(result[2].split(",")) == 25

    def test_chunk_list_custom_chunk_size(self):
        """Test chunking with a custom chunk size"""
        test_list = [f"id{i}" for i in range(30)]
        result = list(_chunk_list(test_list, chunk_size=10))

        assert len(result) == 3
        assert len(result[0].split(",")) == 10
        assert len(result[1].split(",")) == 10
        assert len(result[2].split(",")) == 10

    def test_chunk_list_empty_list(self):
        """Test chunking an empty list"""
        test_list = []
        result = list(_chunk_list(test_list))

        assert len(result) == 0
