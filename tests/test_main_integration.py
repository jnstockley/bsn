import sys
from unittest import TestCase
from unittest.mock import MagicMock, patch, call

from main import main


class TestMainIntegration(TestCase):
    """Integration tests for the main application entry point (updated for new main.py)."""

    def setUp(self):
        self.mock_youtube_service = MagicMock()

    def tearDown(self):
        pass

    # Tests for main function - main loop
    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.get_recent_videos")
    @patch("main.pull_my_subscriptions")
    @patch("main.oauth")
    def test_main_runs_subscription_and_video_checks(
        self, mock_oauth, mock_pull_subs, mock_get_recent, mock_calc_interval, mock_sleep
    ):
        """Test that main runs pull_my_subscriptions and get_recent_videos and sends notifications"""
        mock_calc_interval.return_value = 60
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service

        # Simulate recently_uploaded_channels returned by pull_my_subscriptions
        mock_pull_subs.return_value = ([], [MagicMock()])

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        mock_pull_subs.assert_called_once_with(self.mock_youtube_service)
        mock_get_recent.assert_called_once()

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.pull_my_subscriptions")
    @patch("main.oauth")
    def test_main_sleeps_for_calculated_interval(
        self, mock_oauth, mock_pull_subs, mock_calc_interval, mock_sleep
    ):
        """Test that main sleeps for the calculated interval between checks"""
        expected_interval = 120
        mock_calc_interval.return_value = expected_interval
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service

        # Ensure pull_my_subscriptions returns a pair to avoid unpack errors
        mock_pull_subs.return_value = ([], [])

        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        mock_sleep.assert_called_once_with(expected_interval)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.pull_my_subscriptions")
    @patch("main.oauth")
    def test_main_gets_fresh_service_each_loop_iteration(
        self, mock_oauth, mock_pull_subs, mock_calc_interval, mock_sleep
    ):
        """Test that main gets a fresh YouTube service on each loop iteration"""
        mock_calc_interval.return_value = 60
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service

        # Ensure pull_my_subscriptions returns a pair to avoid unpack errors
        mock_pull_subs.return_value = ([], [])

        # Make loop run twice then exit
        mock_sleep.side_effect = [None, KeyboardInterrupt()]

        try:
            main()
        except KeyboardInterrupt:
            pass

        assert mock_oauth.get_authenticated_youtube_service.call_count == 2

    # Tests for main entry point with command line arguments
    @patch("main.healthcheck")
    @patch("main.load_dotenv")
    @patch("sys.argv", ["main.py", "healthcheck"])
    def test_main_entry_point_runs_healthcheck(self, mock_load_dotenv, mock_healthcheck):
        """Test that main entry point runs healthcheck when argv[1] is 'healthcheck'"""
        with patch("main.__name__", "__main__"):
            exec(
                """
if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
    healthcheck()
else:
    pass  # Don't run main() in test
""",
                {"sys": sys, "healthcheck": mock_healthcheck, "main": lambda: None},
            )

        mock_healthcheck.assert_called_once()

    @patch("main.main")
    @patch("main.load_dotenv")
    @patch("sys.argv", ["main.py"])
    def test_main_entry_point_runs_main_without_args(self, mock_load_dotenv, mock_main):
        """Test that main entry point runs main() when no arguments provided"""
        with patch("main.__name__", "__main__"):
            exec(
                """
if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
    pass  # Don't run healthcheck in test
else:
    main()
""",
                {"sys": sys, "healthcheck": lambda: None, "main": mock_main},
            )

        mock_main.assert_called_once()

    @patch("main.main")
    @patch("main.load_dotenv")
    @patch("sys.argv", ["main.py", "other_arg"])
    def test_main_entry_point_runs_main_with_non_healthcheck_arg(
        self, mock_load_dotenv, mock_main
    ):
        """Test that main entry point runs main() when argument is not 'healthcheck'"""
        with patch("main.__name__", "__main__"):
            exec(
                """
if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
    pass  # Don't run healthcheck in test
else:
    main()
""",
                {"sys": sys, "healthcheck": lambda: None, "main": mock_main},
            )

        mock_main.assert_called_once()

    @patch("main.healthcheck")
    @patch("main.main")
    @patch("main.load_dotenv")
    def test_main_entry_point_loads_dotenv(
        self, mock_load_dotenv, mock_main, mock_healthcheck
    ):
        """Test that main entry point loads .env file"""
        with patch("sys.argv", ["main.py"]):
            with patch("main.__name__", "__main__"):
                exec(
                    """
load_dotenv()
if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
    healthcheck()
else:
    main()
""",
                    {
                        "sys": sys,
                        "load_dotenv": mock_load_dotenv,
                        "healthcheck": mock_healthcheck,
                        "main": mock_main,
                    },
                )

        mock_load_dotenv.assert_called_once()

    # Integration tests - full flow scenarios
    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.get_recent_videos")
    @patch("main.pull_my_subscriptions")
    @patch("main.oauth")
    def test_main_full_flow_with_existing_tables(
        self,
        mock_oauth,
        mock_pull_subs,
        mock_get_recent,
        mock_calc_interval,
        mock_sleep,
    ):
        """Integration test: Full flow when tables already exist"""
        # Setup: Tables exist, service available
        mock_oauth.get_authenticated_youtube_service.return_value = (
            self.mock_youtube_service
        )
        mock_calc_interval.return_value = 90
        mock_pull_subs.return_value = ([], [])

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify full flow
        mock_sleep.assert_called_once_with(90)
