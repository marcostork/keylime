import contextvars
import logging
import sys
from configparser import RawConfigParser
from contextlib import contextmanager
from logging import Logger
from logging import config as logging_config
from typing import TYPE_CHECKING, Any, Callable, Dict

from keylime import config

if TYPE_CHECKING:
    from logging import LogRecord

DEFAULT_LOGGING_CONFIG = {
    "version": 1,
    "root": {"level": "NOTSET", "handlers": ["console"]},
    "loggers": {
        "keylime": {  # Keylime logger
            "level": "INFO",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "NOTSET",
            "formatter": "simple",
            "stream": "ext://sys.stdout",  # Outputs to console
        }
    },
    "formatters": {
        "simple": {
            "format": "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
}

try:
    logging_config.dictConfig(DEFAULT_LOGGING_CONFIG)
except KeyError:
    logging.basicConfig(format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s", level=logging.DEBUG)


request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id")


def set_log_func(loglevel: int, logger: Logger) -> Callable[..., None]:
    log_func = logger.info

    if loglevel == logging.CRITICAL:
        log_func = logger.critical
    elif loglevel == logging.ERROR:
        log_func = logger.error
    elif loglevel == logging.WARNING:
        log_func = logger.warning
    elif loglevel == logging.INFO:
        log_func = logger.info
    elif loglevel == logging.DEBUG:
        log_func = logger.debug

    return log_func


def log_http_response(logger: Logger, loglevel: int, response_body: Dict[str, Any]) -> bool:
    """Takes JSON response payload and logs error info"""
    if None in [response_body, logger]:
        return False

    log_func = set_log_func(loglevel, logger)

    matches = ["results", "code", "status"]
    if all(x in response_body for x in matches):
        log_func(f"Response code {response_body['code']}: {response_body['status']}")
    else:
        logger.error("Error: unexpected or malformed http response payload")
        return False

    return True


def annotate_logger(logger: Logger) -> None:
    request_id_filter = RequestIDFilter()

    for handler in logger.handlers:
        handler.addFilter(request_id_filter)


def _configure_logging_from_raw(raw_config: RawConfigParser) -> None:
    """
    Configures logging programmatically based on the provided RawConfigParser object.

    Args:
        raw_config (RawConfigParser): The source configuration containing logging sections.
    """
    # Dictionaries to store formatters and handlers
    formatters = {}
    handlers = {}

    # Step 1: Process formatters first
    for section in raw_config.sections():
        if section.startswith("formatter_"):
            formatter_name = section.split("_", 1)[1]
            formatter_options = dict(raw_config.items(section))
            format_str = formatter_options.get("format", "%(message)s")
            datefmt = formatter_options.get("datefmt", None)
            formatters[formatter_name] = logging.Formatter(format_str, datefmt)

    # Step 2: Process handlers after formatters
    for section in raw_config.sections():
        if section.startswith("handler_"):
            handler_name = section.split("_", 1)[1]
            handler_options = dict(raw_config.items(section))
            handler_class = handler_options.get("class", "logging.StreamHandler")
            level = handler_options.get("level", "NOTSET").upper()
            formatter_name = handler_options.get("formatter", None)
            args = eval(handler_options.get("args", "()"))  # Handle args safely

            try:
                if "StreamHandler" in handler_class:
                    handler = logging.StreamHandler(stream=sys.stdout if not args else args[0])
                elif "FileHandler" in handler_class:
                    handler = logging.FileHandler(filename=args[0])
                else:
                    raise ValueError(f"Unsupported handler class: {handler_class}")

                handler.setLevel(getattr(logging, level, logging.NOTSET))
                if formatter_name in formatters:
                    handler.setFormatter(formatters[formatter_name])

                handlers[handler_name] = handler
            except Exception as e:
                print(f"Error configuring handler {handler_name}: {e}", file=sys.stderr)

    # Step 3: Process loggers after handlers
    for section in raw_config.sections():
        if section.startswith("logger_"):
            logger_name = section.split("_", 1)[1]
            logger_options = dict(raw_config.items(section))
            level = logger_options.get("level", "NOTSET").upper()
            propagate = logger_options.get("propagate", "1") == "1"
            handler_names = logger_options.get("handlers", "").split(",")

            logger = logging.getLogger(logger_name)
            logger.setLevel(getattr(logging, level, logging.NOTSET))
            logger.propagate = propagate

            for handler_name in handler_names:
                handler_name = handler_name.strip()
                if handler_name in handlers:
                    logger.addHandler(handlers[handler_name])


@contextmanager
def safe_logging_configuration():
    """
    Context manager to safely apply logging configuration. If an error occurs,
    all loggers (root and named) are restored to their original state, including handlers and formatters.
    """
    # Backup all existing loggers and their handlers
    existing_loggers = {
        name: {
            "handlers": list(logger.handlers),
            "level": logger.level,
            "propagate": logger.propagate,
        }
        for name, logger in logging.Logger.manager.loggerDict.items()
        if isinstance(logger, logging.Logger)  # Ensure it's a valid logger
    }
    # Backup root logger
    root_logger = logging.getLogger()
    root_backup = {
        "handlers": list(root_logger.handlers),
        "level": root_logger.level,
    }

    try:
        yield  # Run the logging configuration
    except Exception as e:
        # Restore potentially affected loggers
        for name, logger in logging.Logger.manager.loggerDict.items():
            if name in existing_loggers and isinstance(logger, logging.Logger):
                logger.handlers = existing_loggers[name]["handlers"]
                logger.level = existing_loggers[name]["level"]
                logger.propagate = existing_loggers[name]["propagate"]
        # Restore root logger
        root_logger.handlers = root_backup["handlers"]
        root_logger.setLevel(root_backup["level"])
        raise


def _safe_get_config(loggername: str) -> RawConfigParser:
    try:
        return config.get_config(loggername)
    except Exception:  # Replace with the actual exception
        return None


def init_logging(loggername: str) -> Logger:
    logger = logging.getLogger(f"keylime.{loggername}")

    component_config = _safe_get_config(loggername)

    # Apply logger component configuration
    if component_config:
        # Update the logging configuration with the component logging configuration (if any)
        try:
            with safe_logging_configuration():
                _configure_logging_from_raw(component_config)
        except Exception as e:
            logger.error("Logging configuration error:", e)

    logging.getLogger("requests").setLevel(logging.WARNING)

    # Disable default Tornado logs, as we are outputting more detail to the 'keylime.web' logger
    logging.getLogger("tornado.general").disabled = True
    logging.getLogger("tornado.access").disabled = True
    logging.getLogger("tornado.application").disabled = True

    # Add metadata to root logger, so that it is inherited by all
    annotate_logger(logging.getLogger())

    return logger


class RequestIDFilter(logging.Filter):
    def filter(self, record: "LogRecord") -> bool:
        reqid = request_id_var.get("")

        record.reqid = reqid
        record.reqidf = f"(reqid={reqid})" if reqid else ""

        return True
