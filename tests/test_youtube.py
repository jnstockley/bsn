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

    # ------------------------------------------------------------------
    # Helper
    # ------------------------------------------------------------------

    def _make_quota_session_cm(self, increment_calls=1):
        """Return (mock_session, mock_session_cm) pre-loaded with enough
        scalar_one_or_none values to satisfy:
          - 1 × __check_available_quota  (2 DB reads: policy + usage)
          - ``increment_calls`` × __increment_quota_usage (2 DB reads each)

        quota_remaining is set to a real int so the `<= 0` guard doesn't raise.
        """

        def _make_pair():
            policy = MagicMock()
            usage = MagicMock()
            usage.quota_remaining = 9999
            return policy, usage

        side_effects = []
        # quota check
        p, u = _make_pair()
        side_effects += [p, u]
        # each increment call
        for _ in range(increment_calls):
            p, u = _make_pair()
            side_effects += [p, u]

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = side_effects

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None
        return mock_session, mock_session_cm

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

        # 1 page → 1 __increment_quota_usage call inside __make_request
        _, mock_session_cm = self._make_quota_session_cm(increment_calls=1)

        with (
            patch("youtube.youtube.Session", return_value=mock_session_cm),
            patch(
                "youtube.youtube.__youtube_subs_response_to_channels"
            ) as mock_transform,
        ):
            mock_transform.return_value = (["chan_obj"], ["recent_obj"])
            channels, recently = pull_my_subscriptions(self.mock_youtube)

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

        # 2 pages → 2 __increment_quota_usage calls inside __make_request
        _, mock_session_cm = self._make_quota_session_cm(increment_calls=2)

        with (
            patch("youtube.youtube.Session", return_value=mock_session_cm),
            patch(
                "youtube.youtube.__youtube_subs_response_to_channels"
            ) as mock_transform,
        ):
            mock_transform.return_value = (["c1", "c2"], ["recent_obj"])
            channels, recently = pull_my_subscriptions(self.mock_youtube)

        mock_transform.assert_called_once()
        assert channels == ["c1", "c2"]
        assert recently == ["recent_obj"]

    # Tests for get_recent_videos (replaces get_most_recent_video semantics)
    def test_get_recent_videos_success(self):
        """Test that get_recent_videos returns a list of YoutubeVideo-like objects for public videos"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        now = datetime.now(timezone.utc)
        # Use a very recent timestamp (5s ago) so the video passes the age
        # check: interval = ceil(86400 / (10000 // ceil(2/50))) = 9s × 3 = 27s
        published_at = (
            (now - timedelta(seconds=5))
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

        # The new logic makes these Session/DB calls per channel:
        #   1. __check_available_quota  → policy + usage (scalar_one_or_none x2)
        #   2. __increment_quota_usage  → policy + usage (scalar_one_or_none x2)
        #   3. DB session for existing-video check → scalar_one_or_none → None
        #      then delete + add (no scalar_one_or_none)
        #   4. calculate_interval_between_cycles → scalars().all()
        #
        # We use a single shared session whose scalar_one_or_none side-effects
        # cover calls 1-3, and override execute() for call 4.

        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999

        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999

        # calculate_interval_between_cycles: returns a channel list
        calc_channels_result = MagicMock()
        calc_channels_result.scalars.return_value.all.return_value = [MagicMock()]

        mock_session = MagicMock()
        scalar_side_effects = [
            quota_check_policy,
            quota_check_usage,
            quota_inc_policy,
            quota_inc_usage,
            None,  # existing video check → not in DB
        ]
        mock_session.execute.return_value.scalar_one_or_none.side_effect = (
            scalar_side_effects
        )

        # Override execute for the 6th call (calculate_interval_between_cycles)
        original_execute = mock_session.execute
        call_count = [0]

        def smart_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 6:
                return calc_channels_result
            return original_execute(stmt)

        mock_session.execute = smart_execute

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        mock_video = MagicMock()
        mock_video.id = "vid123"
        mock_video.title = "Test Video"
        mock_video.youtube_channel_id = self.sample_channel_id

        # Patch select + delete so SQLAlchemy never receives the mock class,
        # avoiding ORM coercion errors.
        with (
            patch("youtube.youtube.YoutubeVideo", return_value=mock_video),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.delete"),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
        ):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        assert len(videos) == 1
        v = videos[0]
        assert v.id == "vid123"
        assert v.title == "Test Video"
        assert isinstance(v.youtube_channel_id, str)

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

        # Private video still triggers 1 __increment_quota_usage (request was made).
        _, mock_session_cm = self._make_quota_session_cm(increment_calls=1)

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        assert videos == []

    def test_get_recent_videos_skips_existing_video(self):
        """When a video already exists in the DB, get_recent_videos should skip it"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        now = datetime.now(timezone.utc)
        published_at = (
            (now - timedelta(seconds=5))
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

        # quota check + quota increment (2 reads each), then existing video check → existing
        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999
        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999
        existing_video = MagicMock()  # non-None → video already in DB

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = [
            quota_check_policy,
            quota_check_usage,
            quota_inc_policy,
            quota_inc_usage,
            existing_video,  # existing video found → skip
        ]

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        mock_video = MagicMock()
        mock_video.id = "vid123"
        mock_video.title = "Test Video"
        mock_video.youtube_channel_id = self.sample_channel_id

        with (
            patch("youtube.youtube.YoutubeVideo", return_value=mock_video),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.delete"),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
        ):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        assert videos == []

    def test_get_recent_videos_skips_too_old(self):
        """When a video was uploaded longer ago than the cycle interval, it should be skipped"""
        mock_channel = MagicMock()
        mock_channel.id = self.sample_channel_id

        now = datetime.now(timezone.utc)
        # Publish timestamp well outside the interval window (10 minutes ago)
        published_at = (
            (now - timedelta(minutes=10))
            .astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ")
        )

        mock_response = {
            "items": [
                {
                    "snippet": {
                        "title": "Old Video",
                        "thumbnails": {"high": {"url": "https://img"}},
                    },
                    "status": {"privacyStatus": "public"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid_old",
                    },
                }
            ]
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.playlistItems().list.return_value = mock_request

        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999
        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999

        calc_channels_result = MagicMock()
        calc_channels_result.scalars.return_value.all.return_value = [MagicMock()]

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = [
            quota_check_policy,
            quota_check_usage,
            quota_inc_policy,
            quota_inc_usage,
            None,  # existing video check → not in DB, so it gets saved
        ]

        original_execute = mock_session.execute
        call_count = [0]

        def smart_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 6:
                return calc_channels_result
            return original_execute(stmt)

        mock_session.execute = smart_execute

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        mock_video = MagicMock()
        mock_video.id = "vid_old"
        mock_video.title = "Old Video"
        mock_video.youtube_channel_id = self.sample_channel_id

        with (
            patch("youtube.youtube.YoutubeVideo", return_value=mock_video),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.delete"),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
        ):
            videos = get_recent_videos([mock_channel], self.mock_youtube)

        # Video is saved to DB but NOT returned because it's too old
        assert videos == []

    # Tests for calculate_interval_between_cycles
    def test_calculate_interval_between_cycles_single_key(self):
        """Test interval calculation with a single channel"""
        mock_channels = [MagicMock()]

        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_channels_result

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            interval = calculate_interval_between_cycles()

        assert interval == 9

    def test_calculate_interval_between_cycles_multiple_keys(self):
        """Test interval calculation with multiple channels"""
        mock_channels = [MagicMock() for _ in range(100)]

        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_channels_result

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

        with patch("youtube.youtube.Session", return_value=mock_session_cm):
            interval = calculate_interval_between_cycles()

        # 100 channels: ceil(101/50)=3 requests/cycle, 10000//3=3333 cycles/day,
        # ceil(86400/3333)=26 seconds between cycles
        assert interval == 26

    def test_calculate_interval_between_cycles_many_channels(self):
        """Test interval calculation with many channels"""
        mock_channels = [MagicMock() for _ in range(500)]

        mock_channels_result = MagicMock()
        mock_channels_result.scalars.return_value.all.return_value = mock_channels

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_channels_result

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
