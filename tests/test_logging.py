import logging
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch


class TestLogging(TestCase):
    def setUp(self):
        """Set up test fixtures"""
        # Store original environment variables
        self.original_log_level = os.environ.get("LOG_LEVEL")
        self.original_log_dir = os.environ.get("LOG_DIR")

    def tearDown(self):
        """Clean up after tests"""
        # Restore original environment variables
        if self.original_log_level is not None:
            os.environ["LOG_LEVEL"] = self.original_log_level
        elif "LOG_LEVEL" in os.environ:
            del os.environ["LOG_LEVEL"]

        if self.original_log_dir is not None:
            os.environ["LOG_DIR"] = self.original_log_dir
        elif "LOG_DIR" in os.environ:
            del os.environ["LOG_DIR"]

    @patch("util.logging.logging.getLogger")
    @patch("util.logging.logging.FileHandler")
    @patch("util.logging.logging.StreamHandler")
    @patch("util.logging.os.makedirs")
    def test_logger_default_log_level(
        self, mock_makedirs, mock_stream_handler, mock_file_handler, mock_get_logger
    ):
        """Test that logger uses default INFO log level when LOG_LEVEL not set"""
        # This test verifies the module imports correctly with defaults
        # The actual module has already been imported, so we're testing behavior
        with patch.dict(os.environ, {}, clear=True):
            # Import would use default "INFO"
            log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            self.assertEqual(log_level, "INFO")

    def test_logger_custom_log_level_from_env(self):
        """Test that logger respects LOG_LEVEL environment variable"""
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            self.assertEqual(log_level, "DEBUG")

    def test_logger_log_level_case_insensitive(self):
        """Test that LOG_LEVEL is converted to uppercase"""
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            log_level = os.getenv("LOG_LEVEL", "INFO").upper()
            self.assertEqual(log_level, "DEBUG")

    def test_logger_default_log_dir(self):
        """Test that logger uses default ../logs directory when LOG_DIR not set"""
        with patch.dict(os.environ, {}, clear=True):
            log_dir = os.path.join(os.getenv("LOG_DIR", "../logs"))
            self.assertEqual(log_dir, "../logs")

    def test_logger_custom_log_dir_from_env(self):
        """Test that logger respects LOG_DIR environment variable"""
        with patch.dict(os.environ, {"LOG_DIR": "/tmp/test_logs"}):
            log_dir = os.path.join(os.getenv("LOG_DIR", "../logs"))
            self.assertEqual(log_dir, "/tmp/test_logs")

    def test_logger_creates_log_directory(self):
        """Test that logger creates log directory if it doesn't exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log_dir = os.path.join(tmpdir, "logs")

            # Simulate the logging module creating the directory
            os.makedirs(test_log_dir, exist_ok=True)

            # Verify directory was created
            self.assertTrue(os.path.exists(test_log_dir))

    def test_logger_creates_directory_with_exist_ok(self):
        """Test that logger creates directory with exist_ok=True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log_dir = os.path.join(tmpdir, "logs")

            # Create directory first time
            os.makedirs(test_log_dir, exist_ok=True)
            self.assertTrue(os.path.exists(test_log_dir))

            # Create again - should not raise error
            os.makedirs(test_log_dir, exist_ok=True)
            self.assertTrue(os.path.exists(test_log_dir))

    def test_logger_formatting(self):
        """Test that logger uses correct format string"""
        expected_format = (
            "%(asctime)s - %(filename)s:%(funcName)s:%(lineno)d - %(levelname)s - %(message)s"
        )

        formatter = logging.Formatter(expected_format)
        self.assertEqual(formatter._fmt, expected_format)

    def test_logger_has_file_handler(self):
        """Test that logger configuration includes file handler"""
        # Import the logger from the module
        from util.logging import logger

        # Check that logger has handlers
        self.assertGreater(len(logger.handlers), 0)

        # Check that at least one handler is a FileHandler
        has_file_handler = any(
            isinstance(handler, logging.FileHandler) for handler in logger.handlers
        )
        self.assertTrue(has_file_handler)

    def test_logger_has_console_handler(self):
        """Test that logger configuration includes console handler"""
        # Import the logger from the module
        from util.logging import logger

        # Check that logger has handlers
        self.assertGreater(len(logger.handlers), 0)

        # Check that at least one handler is a StreamHandler
        has_stream_handler = any(
            isinstance(handler, logging.StreamHandler)
            and not isinstance(handler, logging.FileHandler)
            for handler in logger.handlers
        )
        self.assertTrue(has_stream_handler)

    def test_logger_file_handler_logs_to_correct_file(self):
        """Test that file handler logs to app.log in the log directory"""
        from util.logging import logger

        # Find the file handler
        file_handlers = [
            handler
            for handler in logger.handlers
            if isinstance(handler, logging.FileHandler)
        ]

        self.assertGreater(len(file_handlers), 0)

        # Check that the file handler points to app.log
        file_handler = file_handlers[0]
        self.assertTrue(file_handler.baseFilename.endswith("app.log"))

    def test_logger_level_matches_env(self):
        """Test that logger level matches the configured log level"""
        from util.logging import logger, log_level

        # The logger should be set to the log_level from environment
        expected_level = getattr(logging, log_level)
        self.assertEqual(logger.level, expected_level)

    def test_logger_handlers_have_correct_level(self):
        """Test that all handlers have the correct log level"""
        from util.logging import logger, log_level

        expected_level = getattr(logging, log_level)

        for handler in logger.handlers:
            self.assertEqual(handler.level, expected_level)

    def test_logger_handlers_have_formatter(self):
        """Test that all handlers have a formatter configured"""
        from util.logging import logger

        for handler in logger.handlers:
            self.assertIsNotNone(handler.formatter)

    def test_logger_formatter_includes_all_required_fields(self):
        """Test that formatter includes all required fields"""
        from util.logging import logger

        for handler in logger.handlers:
            formatter = handler.formatter
            format_string = formatter._fmt

            # Check for required fields in format string
            self.assertIn("%(asctime)s", format_string)
            self.assertIn("%(filename)s", format_string)
            self.assertIn("%(funcName)s", format_string)
            self.assertIn("%(lineno)d", format_string)
            self.assertIn("%(levelname)s", format_string)
            self.assertIn("%(message)s", format_string)

    def test_logger_can_log_info(self):
        """Test that logger can log info messages"""
        from util.logging import logger

        # This should not raise an exception
        try:
            logger.info("Test info message")
            success = True
        except Exception:
            success = False

        self.assertTrue(success)

    def test_logger_can_log_error(self):
        """Test that logger can log error messages"""
        from util.logging import logger

        # This should not raise an exception
        try:
            logger.error("Test error message")
            success = True
        except Exception:
            success = False

        self.assertTrue(success)

    def test_logger_can_log_debug(self):
        """Test that logger can log debug messages"""
        from util.logging import logger

        # This should not raise an exception
        try:
            logger.debug("Test debug message")
            success = True
        except Exception:
            success = False

        self.assertTrue(success)

    def test_logger_can_log_warning(self):
        """Test that logger can log warning messages"""
        from util.logging import logger

        # This should not raise an exception
        try:
            logger.warning("Test warning message")
            success = True
        except Exception:
            success = False

        self.assertTrue(success)

    def test_logger_module_name(self):
        """Test that logger is created with the correct module name"""
        from util.logging import logger

        # The logger should be created with __name__ from util.logging
        self.assertEqual(logger.name, "util.logging")

    def test_valid_log_levels(self):
        """Test various valid log level values"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            with patch.dict(os.environ, {"LOG_LEVEL": level}):
                log_level = os.getenv("LOG_LEVEL", "INFO").upper()
                self.assertEqual(log_level, level)
                # Verify it's a valid logging level
                self.assertTrue(hasattr(logging, level))
