import contextvars
import logging, ast, io
from configparser import RawConfigParser
from logging import Logger
from logging import config as logging_config
from typing import TYPE_CHECKING, Any, Callable, Dict

from keylime import config

if TYPE_CHECKING:
    from logging import LogRecord

try:
    logging_config.fileConfig(config.get_config("logging"))
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

def apply_child_logger(raw_config: RawConfigParser, child_logger_name: str) -> RawConfigParser:
    """
    Applies logging configuration to add or modify a component logger using fileConfig.
    Ensures that all required sections ([loggers], [handlers], and [formatters]) are properly merged
    with the existing configuration to prevent disruption of other components' logging.

    Args:
        raw_config (RawConfigParser): The source configuration containing the new logger settings.
        child_logger_name (str): The name of the child logger to configure.
    """
    # Retrieve the current project-wide logging configuration as the base.
    logging_config = config.get_config("logging")

    # Merge the 'loggers' section, ensuring 'root' and 'keylime' are not altered.
    if 'loggers' in raw_config:
        existing_loggers = logging_config['loggers']['keys'].split(',')
        new_loggers = raw_config['loggers']['keys'].split(',')
        for new_logger in new_loggers:
            if new_logger not in existing_loggers:
                existing_loggers.append(new_logger)
        logging_config.set('loggers', 'keys', ','.join(existing_loggers))

    # Collect new handlers and formatters from the raw configuration.
    new_handler_keys = []
    new_formatter_keys = []
    for section in raw_config.sections():
        if section.startswith('handler_'):
            handler_name = section.split('_', 1)[1]
            new_handler_keys.append(handler_name)
            logging_config[section] = raw_config[section]
        elif section.startswith('formatter_'):
            formatter_name = section.split('_', 1)[1]
            new_formatter_keys.append(formatter_name)
            logging_config[section] = raw_config[section]

    # Add or update the child logger's configuration.
    child_logger_section = f'logger_{child_logger_name}'
    if raw_config.has_section(child_logger_section):
        logging_config[child_logger_section] = raw_config[child_logger_section]

    # Merge the 'handlers' section.
    if new_handler_keys:
        existing_handlers = logging_config['handlers']['keys'].split(',')
        for new_handler in new_handler_keys:
            if new_handler not in existing_handlers:
                existing_handlers.append(new_handler)
        logging_config.set('handlers', 'keys', ','.join(existing_handlers))

    # Merge the 'formatters' section.
    if new_formatter_keys:
        existing_formatters = logging_config['formatters']['keys'].split(',')
        for new_formatter in new_formatter_keys:
            if new_formatter not in existing_formatters:
                existing_formatters.append(new_formatter)
        logging_config.set('formatters', 'keys', ','.join(existing_formatters))

    return logging_config

def safe_get_config(loggername: str) -> RawConfigParser:
    try:
        return config.get_config(loggername)
    except Exception:  # Replace with the actual exception
        return None


def init_logging(loggername: str) -> Logger:

    logger = logging.getLogger(f"keylime.{loggername}")

    component_config = safe_get_config(loggername)
    
    # Apply logger component configuration
    if component_config:
        logging_config = apply_child_logger(component_config, f"keylime.{loggername}")
        # Apply the updated logging configuration using fileConfig.
        try:
            # Convert the updated configuration to a string for fileConfig compatibility.
            temp_config_string = io.StringIO()
            logging_config.write(temp_config_string)
            temp_config_string.seek(0)

            # Apply the configuration
            logging.config.fileConfig(logging_config, disable_existing_loggers=False)
        except KeyError as e:
            logger.error(f"Configuration Error: Missing key {e} in the configuration file.")
        except ValueError as e:
            logger.error(f"Configuration Error: Invalid value encountered - {e}.")
        except Exception as e:
            logger.error(f"Unexpected Error: {e}.")
    
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
