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
from unittest.mock import MagicMock, AsyncMock, patch


from youtube.youtube import (
    pull_my_subscriptions,
    get_recent_videos,
    calculate_interval_between_cycles,
    _chunk_list,
    check_rss_for_new_videos,
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
            patch("youtube.youtube.check_rss_for_new_videos", return_value=[]),
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
            patch("youtube.youtube.check_rss_for_new_videos", return_value=[]),
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
                        "channelId": mock_channel.id,
                        "channelTitle": "Test Channel",
                    },
                    "status": {"privacyStatus": "public"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid123",
                    },
                }
            ],
            "pageInfo": {"totalResults": 1},
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.playlistItems().list.return_value = mock_request

        # Session/DB call order per channel:
        #   1. __check_available_quota  → policy + usage (scalar_one_or_none x2)
        #   2. __increment_quota_usage  → policy + usage (scalar_one_or_none x2)
        #   3. channel name update      → channel lookup  (scalar_one_or_none x1)
        #   4. __is_short increment     → policy + usage  (scalar_one_or_none x2)
        #   5. __is_live  increment     → policy + usage  (scalar_one_or_none x2)
        #   6. existing-video check     → scalar_one_or_none → None
        #      then delete + add (no scalar_one_or_none)
        #   7. calculate_interval_between_cycles → scalars().all() (no scalar_one_or_none)

        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999

        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999

        mock_session = MagicMock()
        scalar_side_effects = [
            quota_check_policy,  # 1: check quota – policy
            quota_check_usage,  # 2: check quota – usage
            quota_inc_policy,  # 3: increment (main request) – policy
            quota_inc_usage,  # 4: increment (main request) – usage
            None,  # 5: channel name update – channel not found
            quota_inc_policy,  # 6: increment (__is_short) – policy
            quota_inc_usage,  # 7: increment (__is_short) – usage
            quota_inc_policy,  # 8: increment (__is_live)  – policy
            quota_inc_usage,  # 9: increment (__is_live)  – usage
            None,  # 10: existing video check → not in DB
        ]
        mock_session.execute.return_value.scalar_one_or_none.side_effect = (
            scalar_side_effects
        )

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
                    "snippet": {"title": "Test Video", "channelTitle": "Test Channel"},
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

        # Private video: __check_available_quota (policy+usage), __increment_quota_usage
        # (policy+usage), channel name update lookup (1), then privacy check → continue.
        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999
        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = [
            quota_check_policy,
            quota_check_usage,
            quota_inc_policy,
            quota_inc_usage,
            None,  # channel name update → channel not found
        ]
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None

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
                        "channelId": mock_channel.id,
                        "channelTitle": "Test Channel",
                    },
                    "status": {"privacyStatus": "public"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid123",
                    },
                }
            ],
            "pageInfo": {"totalResults": 1},
        }

        mock_request = MagicMock()
        mock_request.execute.return_value = mock_response
        self.mock_youtube.playlistItems().list.return_value = mock_request

        # quota check + quota increment (2 reads each), channel name update (1),
        # is_short/is_live increments (2 reads each), then existing video check → existing
        quota_check_policy = MagicMock()
        quota_check_usage = MagicMock()
        quota_check_usage.quota_remaining = 9999
        quota_inc_policy = MagicMock()
        quota_inc_usage = MagicMock()
        quota_inc_usage.quota_remaining = 9999
        existing_video = MagicMock()  # non-None → video already in DB

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = [
            quota_check_policy,  # 1: check quota – policy
            quota_check_usage,  # 2: check quota – usage
            quota_inc_policy,  # 3: increment (main request) – policy
            quota_inc_usage,  # 4: increment (main request) – usage
            None,  # 5: channel name update – channel not found
            quota_inc_policy,  # 6: increment (__is_short) – policy
            quota_inc_usage,  # 7: increment (__is_short) – usage
            quota_inc_policy,  # 8: increment (__is_live)  – policy
            quota_inc_usage,  # 9: increment (__is_live)  – usage
            existing_video,  # 10: existing video found → skip
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
                        "channelId": mock_channel.id,
                        "channelTitle": "Test Channel",
                    },
                    "status": {"privacyStatus": "public"},
                    "contentDetails": {
                        "videoPublishedAt": published_at,
                        "videoId": "vid_old",
                    },
                }
            ],
            "pageInfo": {"totalResults": 1},
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

        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.side_effect = [
            quota_check_policy,  # 1: check quota – policy
            quota_check_usage,  # 2: check quota – usage
            quota_inc_policy,  # 3: increment (main request) – policy
            quota_inc_usage,  # 4: increment (main request) – usage
            None,  # 5: channel name update – channel not found
            quota_inc_policy,  # 6: increment (__is_short) – policy
            quota_inc_usage,  # 7: increment (__is_short) – usage
            quota_inc_policy,  # 8: increment (__is_live)  – policy
            quota_inc_usage,  # 9: increment (__is_live)  – usage
            None,  # 10: existing video check → not in DB, so it gets saved
        ]

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


class TestCheckRssForNewVideos(TestCase):
    def setUp(self):
        self.channel_a = MagicMock()
        self.channel_a.id = "UCaaaaaaaaaaaaaaaaaaaaaaaa"
        self.channel_a.name = "Channel A"

        self.channel_b = MagicMock()
        self.channel_b.id = "UCbbbbbbbbbbbbbbbbbbbbbbbb"
        self.channel_b.name = "Channel B"

    # ------------------------------------------------------------------ helpers

    def _make_atom_feed(self, video_id: str, published: str) -> bytes:
        """Build a minimal YouTube Atom feed with one entry."""
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<feed xmlns="http://www.w3.org/2005/Atom"'
            f'      xmlns:yt="http://www.youtube.com/xml/schemas/2015">'
            f"  <entry>"
            f"    <yt:videoId>{video_id}</yt:videoId>"
            f"    <published>{published}</published>"
            f"  </entry>"
            f"</feed>"
        ).encode()

    def _make_session_cm(self, existing_video=None):
        """Return a mock Session context manager for DB look-ups."""
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar_one_or_none.return_value = (
            existing_video
        )
        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_session
        mock_session_cm.__exit__.return_value = None
        return mock_session_cm

    # ------------------------------------------------------------------ tests

    def test_returns_empty_when_no_channels(self):
        """Empty channel list returns [] without making any requests."""
        result = check_rss_for_new_videos([])
        assert result == []

    def test_returns_channel_with_new_video(self):
        """Channel with a brand-new video (not in DB, published recently) is returned."""
        now = datetime.now(timezone.utc)
        published = (now - timedelta(seconds=5)).isoformat()
        feed_bytes = self._make_atom_feed("vid_new", published)

        mock_session_cm = self._make_session_cm(existing_video=None)

        with (
            patch(
                "youtube.youtube._fetch_all_rss_feeds",
                new_callable=AsyncMock,
                return_value=[(self.channel_a, feed_bytes)],
            ),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.calculate_interval_between_cycles", return_value=9),
        ):
            result = check_rss_for_new_videos([self.channel_a])

        assert result == [self.channel_a]

    def test_skips_channel_when_video_already_in_db(self):
        """Channel whose most recent RSS video is already in DB is NOT returned."""
        now = datetime.now(timezone.utc)
        published = (now - timedelta(seconds=5)).isoformat()
        feed_bytes = self._make_atom_feed("vid_existing", published)

        existing_video = MagicMock()
        mock_session_cm = self._make_session_cm(existing_video=existing_video)

        with (
            patch(
                "youtube.youtube._fetch_all_rss_feeds",
                new_callable=AsyncMock,
                return_value=[(self.channel_a, feed_bytes)],
            ),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.calculate_interval_between_cycles", return_value=9),
        ):
            result = check_rss_for_new_videos([self.channel_a])

        assert result == []

    def test_skips_channel_when_video_too_old(self):
        """Channel whose most recent RSS video is older than 3 cycles is NOT returned."""
        now = datetime.now(timezone.utc)
        # 10 minutes ago is well beyond 3 × 9s = 27s
        published = (now - timedelta(minutes=10)).isoformat()
        feed_bytes = self._make_atom_feed("vid_old", published)

        with (
            patch(
                "youtube.youtube._fetch_all_rss_feeds",
                new_callable=AsyncMock,
                return_value=[(self.channel_a, feed_bytes)],
            ),
            patch("youtube.youtube.calculate_interval_between_cycles", return_value=9),
        ):
            result = check_rss_for_new_videos([self.channel_a])

        assert result == []

    def test_skips_channel_on_rss_fetch_error(self):
        """A None payload (fetch error) for a channel is handled gracefully."""
        with (
            patch(
                "youtube.youtube._fetch_all_rss_feeds",
                new_callable=AsyncMock,
                return_value=[(self.channel_a, None)],
            ),
            patch("youtube.youtube.calculate_interval_between_cycles", return_value=9),
        ):
            result = check_rss_for_new_videos([self.channel_a])

        assert result == []

    def test_all_channels_passed_to_fetch(self):
        """All channels are forwarded to _fetch_all_rss_feeds in a single call."""
        now = datetime.now(timezone.utc)
        published = (now - timedelta(seconds=5)).isoformat()
        feed_a = self._make_atom_feed("vid_a", published)
        feed_b = self._make_atom_feed("vid_b", published)

        mock_session_cm = self._make_session_cm(existing_video=None)

        fetch_mock = AsyncMock(
            return_value=[
                (self.channel_a, feed_a),
                (self.channel_b, feed_b),
            ]
        )

        with (
            patch("youtube.youtube._fetch_all_rss_feeds", fetch_mock),
            patch("youtube.youtube.Session", return_value=mock_session_cm),
            patch("youtube.youtube.select"),
            patch("youtube.youtube.calculate_interval_between_cycles", return_value=9),
        ):
            result = check_rss_for_new_videos([self.channel_a, self.channel_b])

        # Both channels were passed in a single call
        fetch_mock.assert_called_once_with([self.channel_a, self.channel_b])
        assert result == [self.channel_a, self.channel_b]
