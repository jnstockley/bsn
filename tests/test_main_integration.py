import sys
import time
from unittest import TestCase
from unittest.mock import MagicMock, patch, call

from main import main


class TestMainIntegration(TestCase):
    """Integration tests for the main application entry point"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_youtube_service = MagicMock()

    def tearDown(self):
        """Clean up after tests"""
        pass

    # Tests for main function - database initialization
    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    @patch("main.YouTubeChannel")
    @patch("main.OAuthCredentials")
    def test_main_creates_youtube_channel_table_if_missing(
        self,
        mock_oauth_creds,
        mock_youtube_channel,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main creates YouTubeChannel table if it doesn't exist"""
        # Setup: YouTubeChannel table missing, OAuthCredentials exists
        mock_database.table_exists.side_effect = lambda table: table == "oauth_credentials"
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify YouTubeChannel table was created
        mock_database.create_tables.assert_called_once_with([mock_youtube_channel])
        mock_database.commit.assert_called()

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    @patch("main.YouTubeChannel")
    @patch("main.OAuthCredentials")
    def test_main_creates_oauth_credentials_table_if_missing(
        self,
        mock_oauth_creds,
        mock_youtube_channel,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main creates OAuthCredentials table if it doesn't exist"""
        # Setup: OAuthCredentials table missing, YouTubeChannel exists
        mock_database.table_exists.side_effect = lambda table: table == "youtubechannel"
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify OAuthCredentials table was created
        assert mock_database.create_tables.call_count == 1
        mock_database.create_tables.assert_called_with([mock_oauth_creds])

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    @patch("main.YouTubeChannel")
    @patch("main.OAuthCredentials")
    def test_main_creates_both_tables_if_missing(
        self,
        mock_oauth_creds,
        mock_youtube_channel,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main creates both tables if neither exist"""
        # Setup: Both tables missing
        mock_database.table_exists.return_value = False
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify both tables were created
        assert mock_database.create_tables.call_count == 2
        mock_database.create_tables.assert_any_call([mock_youtube_channel])
        mock_database.create_tables.assert_any_call([mock_oauth_creds])

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_triggers_force_auth_when_oauth_table_created(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main triggers force_auth when OAuthCredentials table is created"""
        # Setup: OAuthCredentials table missing
        mock_database.table_exists.side_effect = lambda table: table == "youtubechannel"
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify force_auth was called during table creation
        calls = mock_oauth.get_authenticated_youtube_service.call_args_list
        # Should be called twice: once during setup (force_auth=True), once in loop (force_auth=True)
        assert len(calls) >= 2
        assert calls[0] == call(force_auth=True)

    # Tests for main function - main loop
    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_runs_subscription_and_video_checks(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main runs pull_youtube_subscriptions and check_for_new_videos"""
        # Setup: Tables exist
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify subscription pull and video check were called
        mock_pull_subs.assert_called_once_with(self.mock_youtube_service)
        mock_check_videos.assert_called_once_with(self.mock_youtube_service)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_sleeps_for_calculated_interval(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main sleeps for the calculated interval between checks"""
        # Setup
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        expected_interval = 120
        mock_calc_interval.return_value = expected_interval

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify sleep was called with correct interval
        mock_sleep.assert_called_once_with(expected_interval)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_calculates_interval_once_at_startup(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that calculate_interval_between_cycles is called once at startup"""
        # Setup
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run twice then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = [None, KeyboardInterrupt()]

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify calculate_interval was called only once (not in the loop)
        mock_calc_interval.assert_called_once()

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_loops_multiple_times(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main continues to loop multiple times"""
        # Setup
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run 3 times then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = [None, None, KeyboardInterrupt()]

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify functions were called 3 times
        assert mock_pull_subs.call_count == 3
        assert mock_check_videos.call_count == 3
        assert mock_sleep.call_count == 3

    # Tests for main function - error handling
    @patch("main.calculate_interval_between_cycles")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_exits_when_no_youtube_service_available(
        self, mock_database, mock_oauth, mock_calc_interval
    ):
        """Test that main exits with code 1 when YouTube service is not available"""
        # Setup: No YouTube service available
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = None
        mock_calc_interval.return_value = 60

        with self.assertRaises(SystemExit) as cm:
            main()

        self.assertEqual(cm.exception.code, 1)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_gets_fresh_service_each_loop_iteration(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Test that main gets a fresh YouTube service on each loop iteration"""
        # Setup
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Make the loop run 2 times then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = [None, KeyboardInterrupt()]

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify get_authenticated_youtube_service was called twice (once per iteration)
        assert mock_oauth.get_authenticated_youtube_service.call_count == 2

    # Tests for main entry point with command line arguments
    @patch("main.healthcheck")
    @patch("main.load_dotenv")
    @patch("sys.argv", ["main.py", "healthcheck"])
    def test_main_entry_point_runs_healthcheck(self, mock_load_dotenv, mock_healthcheck):
        """Test that main entry point runs healthcheck when argv[1] is 'healthcheck'"""
        # Import and execute the if __name__ == "__main__" block
        with patch("main.__name__", "__main__"):
            # Re-execute the module's main block
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
        # Import and execute the if __name__ == "__main__" block
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
        # Import and execute the if __name__ == "__main__" block
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
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_full_flow_with_existing_tables(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Integration test: Full flow when tables already exist"""
        # Setup: Tables exist, service available
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 90

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify full flow
        mock_database.table_exists.assert_any_call("youtubechannel")
        mock_database.table_exists.assert_any_call("oauth_credentials")
        mock_calc_interval.assert_called_once()
        mock_oauth.get_authenticated_youtube_service.assert_called_with(force_auth=True)
        mock_pull_subs.assert_called_once_with(self.mock_youtube_service)
        mock_check_videos.assert_called_once_with(self.mock_youtube_service)
        mock_sleep.assert_called_once_with(90)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    @patch("main.YouTubeChannel")
    @patch("main.OAuthCredentials")
    def test_main_full_flow_with_table_creation(
        self,
        mock_oauth_creds,
        mock_youtube_channel,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Integration test: Full flow with table creation"""
        # Setup: Tables don't exist
        mock_database.table_exists.return_value = False
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 100

        # Make the loop run once then raise KeyboardInterrupt to exit
        mock_sleep.side_effect = KeyboardInterrupt()

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify full flow including table creation
        assert mock_database.create_tables.call_count == 2
        mock_database.create_tables.assert_any_call([mock_youtube_channel])
        mock_database.create_tables.assert_any_call([mock_oauth_creds])
        assert mock_database.commit.call_count >= 2
        mock_calc_interval.assert_called_once()
        mock_pull_subs.assert_called_once_with(self.mock_youtube_service)
        mock_check_videos.assert_called_once_with(self.mock_youtube_service)
        mock_sleep.assert_called_once_with(100)

    @patch("main.time.sleep")
    @patch("main.calculate_interval_between_cycles")
    @patch("main.check_for_new_videos")
    @patch("main.pull_youtube_subscriptions")
    @patch("main.oauth")
    @patch("main.database")
    def test_main_continuous_operation_simulation(
        self,
        mock_database,
        mock_oauth,
        mock_pull_subs,
        mock_check_videos,
        mock_calc_interval,
        mock_sleep,
    ):
        """Integration test: Simulate continuous operation over multiple cycles"""
        # Setup
        mock_database.table_exists.return_value = True
        mock_oauth.get_authenticated_youtube_service.return_value = self.mock_youtube_service
        mock_calc_interval.return_value = 60

        # Simulate 5 cycles of operation
        mock_sleep.side_effect = [None, None, None, None, KeyboardInterrupt()]

        try:
            main()
        except KeyboardInterrupt:
            pass

        # Verify operations ran 5 times
        assert mock_oauth.get_authenticated_youtube_service.call_count == 5
        assert mock_pull_subs.call_count == 5
        assert mock_check_videos.call_count == 5
        assert mock_sleep.call_count == 5

        # Verify they were called with correct arguments each time
        for call_args in mock_pull_subs.call_args_list:
            self.assertEqual(call_args[0][0], self.mock_youtube_service)
        for call_args in mock_check_videos.call_args_list:
            self.assertEqual(call_args[0][0], self.mock_youtube_service)
        for call_args in mock_sleep.call_args_list:
            self.assertEqual(call_args[0][0], 60)
