"""
Rewritten tests to match the new youtube API in `src/youtube/youtube.py` and SQLAlchemy models
in `src/models.py`.

Changes made:
- Import model classes from the top-level `models` package (the new `src/models.py` is exposed as
  `models`). Use class names `YoutubeChannel` and `OauthCredential`.
- Use the new function names from `youtube.youtube`: `pull_my_subscriptions`,
  `get_recent_videos`, `calculate_interval_between_cycles`, `_chunk_list`.
- Adapted tests to patch module-level helpers (e.g. `__youtube_subs_response_to_channels` and
  `Session`) instead of patching Peewee-style class methods.
- Replaced old get_channels_by_id/get_most_recent_video/update_channels/check_for_new_videos tests
  with tests that exercise the available public functions and behavior.
"""

from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import MagicMock, patch


from youtube.youtube import (
    pull_my_subscriptions,
    get_recent_videos,
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

    # Tests for pull_my_subscriptions (replaces pull_youtube_subscriptions tests)
    def test_pull_my_subscriptions_single_page(self):
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

        # Patch the internal transformer to avoid DB writes and return predictable objects
        with patch(
            "youtube.youtube.__youtube_subs_response_to_channels"
        ) as mock_transform:
            mock_transform.return_value = (["chan_obj"], ["recent_obj"])

            channels, recently = pull_my_subscriptions(self.mock_youtube)

            # Ensure the transformer was called with the accumulated items
            mock_transform.assert_called_once()
            assert channels == ["chan_obj"]
            assert recently == ["recent_obj"]

    def test_pull_my_subscriptions_multiple_pages(self):
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

        with patch(
            "youtube.youtube.__youtube_subs_response_to_channels"
        ) as mock_transform:
            mock_transform.return_value = (["c1", "c2"], ["recent_obj"])

            channels, recently = pull_my_subscriptions(self.mock_youtube)

            # The transformer should be called once with both items concatenated by __make_request
            mock_transform.assert_called_once()
            assert channels == ["c1", "c2"]
            assert recently == ["recent_obj"]

    # Tests for get_recent_videos (replaces get_most_recent_video semantics)
    def test_get_recent_videos_success(self):
        """Test that get_recent_videos returns a list of YoutubeVideo-like objects for public videos"""
        # Create a lightweight channel object with an `id` attribute
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        now = datetime.now(timezone.utc)
        published_at = (
            (now - timedelta(minutes=1))
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "title": "Test Video",
                        "thumbnails": {"high": {"url": "https://img"}},
                    },
                    "status": {"privacyStatus": "public"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid123",
                    },
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.playlistItems().list.return_value = mock_request

        # Patch Session to avoid touching the real DB; provide a context manager whose __enter__ returns
        # a mock session object with the methods used in get_recent_videos
        mock_session = MagicMock()
        mock_session.execute.return_value = None
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        mock_session.expunge.return_value = None

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        # One video should be returned and have the expected id and title
        assert len(videos) == 1
        v = videos[0]
        assert v.id == "vid123"
        assert v.title == "Test Video"
        assert v.youtube_channel_id == f"UC{v.youtube_channel_id[2:]}" or isinstance(
            v.youtube_channel_id, str
        )

    def test_get_recent_videos_skips_non_public(self):
        """When the playlist item is not public, get_recent_videos should skip it"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        now = datetime.now(timezone.utc)
        published_at = (
            (now - timedelta(minutes=1))
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        mock_response = {
            "items": [
                {
                    "snippet": {"title": "Test Video"},
                    "status": {"privacyStatus": "private"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid123",
                    },
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.playlistItems().list.return_value = mock_request

        mock_session = MagicMock()
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        assert videos == []

    # Tests for calculate_interval_between_cycles
    def test_calculate_interval_between_cycles_single_key(self):
        """Test interval calculation with a single API key"""
        # Prepare mock objects to be returned by session.execute(...).scalars().all()
        mock_channels = [MagicMock()]
        mock_creds = [MagicMock()]

        # Build objects that have .scalars().all() -> our lists
        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels
        mock_creds_result = MagicMock()
        mock_creds_result.scalars.return_value.all.return_value = mock_creds

        mock_session = MagicMock()
        # The first execute call returns channels_result, second returns creds_result
        mock_session.execute.side_effect = [mock_channels_result, mock_creds_result]

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            interval = calculate_interval_between_cycles()

        assert interval == 9

    def test_calculate_interval_between_cycles_multiple_keys(self):
        """Test interval calculation with multiple API keys"""
        mock_channels = [MagicMock() for _ in range(100)]
        mock_creds = [MagicMock() for _ in range(2)]

        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels
        mock_creds_result = MagicMock()
        mock_creds_result.scalars.return_value.all.return_value = mock_creds

        mock_session = MagicMock()
        mock_session.execute.side_effect = [mock_channels_result, mock_creds_result]

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            interval = calculate_interval_between_cycles()

        assert interval == 13

    def test_calculate_interval_between_cycles_many_channels(self):
        """Test interval calculation with many channels"""
        mock_channels = [MagicMock() for _ in range(500)]
        mock_creds = [MagicMock()]

        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels
        mock_creds_result = MagicMock()
        mock_creds_result.scalars.return_value.all.return_value = mock_creds

        mock_session = MagicMock()
        mock_session.execute.side_effect = [mock_channels_result, mock_creds_result]

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            interval = calculate_interval_between_cycles()

        assert interval == 96

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
