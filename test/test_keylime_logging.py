import unittest
from configparser import RawConfigParser

from keylime.keylime_logging import apply_child_logger


class TestApplyChildLogger(unittest.TestCase):
    def setUp(self):
        # Set up the base logging configuration
        self.original_config = RawConfigParser()
        self.original_config.read_dict(
            {
                "loggers": {"keys": "root,keylime"},
                "handlers": {"keys": "consoleHandler"},
                "formatters": {"keys": "formatter"},
                "logger_root": {"level": "INFO", "handlers": "consoleHandler"},
                "handler_console": {
                    "class": "StreamHandler",
                    "level": "NOTSET",
                    "formatter": "formatter",
                },
                "formatter_formatter": {
                    "format": "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S",
                },
            }
        )

        # Set up the new raw configuration to add a child logger
        self.raw_config = RawConfigParser()
        self.raw_config.read_dict(
            {
                "loggers": {"keys": "child_logger"},
                "logger_child_logger": {"level": "DEBUG", "handlers": "file"},
                "handlers": {"keys": "file"},
                "handler_file": {
                    "class": "FileHandler",
                    "level": "DEBUG",
                    "formatter": "detailed",
                    "args": "('logfile.log', 'w')",
                },
                "formatters": {"keys": "detailed"},
                "formatter_detailed": {"format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(message)s"},
            }
        )

    def test_apply_child_logger(self):
        # Apply the child logger
        updated_config = apply_child_logger(self.original_config, self.raw_config, "child_logger")

        # Check that the child logger was added to the 'loggers' section
        loggers = updated_config.get("loggers", "keys").split(",")
        self.assertIn("child_logger", loggers)

        # Check that the handler for the child logger was added
        handlers = updated_config.get("handlers", "keys").split(",")
        self.assertIn("file", handlers)

        # Check that the formatter for the child logger was added
        formatters = updated_config.get("formatters", "keys").split(",")
        self.assertIn("detailed", formatters)

        # Check the specific child logger configuration
        self.assertTrue(updated_config.has_section("logger_child_logger"))
        self.assertEqual(updated_config.get("logger_child_logger", "level"), "DEBUG")
        self.assertEqual(updated_config.get("logger_child_logger", "handlers"), "file")

        # Check the handler and formatter sections
        self.assertTrue(updated_config.has_section("handler_file"))
        self.assertEqual(updated_config.get("handler_file", "class"), "FileHandler")
        self.assertEqual(updated_config.get("handler_file", "level"), "DEBUG")
        self.assertEqual(updated_config.get("handler_file", "formatter"), "detailed")

        self.assertTrue(updated_config.has_section("formatter_detailed"))
        self.assertEqual(
            updated_config.get("formatter_detailed", "format"),
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s - %(message)s",
        )

        # Ensure original configuration is still intact
        for section, options in self.original_config.items():
            with self.subTest(section=section):
                self.assertIn(section, updated_config)
                for option, value in options.items():
                    if section in ("loggers", "handlers", "formatters") and option == "keys":
                        # Allow merged keys but check existing ones remain
                        existing_keys = value.split(",")
                        updated_keys = updated_config[section]["keys"].split(",")
                        for key in existing_keys:
                            self.assertIn(key, updated_keys)
                    else:
                        # Validate unchanged options
                        self.assertEqual(updated_config[section][option], value)


if __name__ == "__main__":
    unittest.main()
