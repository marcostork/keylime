import contextvars
import logging, ast
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

def parse_field(key, value):
    """Handle special cases for specific logging fields."""
    if key == 'args':
        return ast.literal_eval(value)  # Safely parse tuple or list
    elif key in ['handlers', 'filters']:
        return [item.strip() for item in value.split(',')]  # Convert to list
    elif key in ['propagate', 'disable_existing_loggers']:
        return value.lower() in ['true', '1']  # Convert to boolean
    elif key == 'level':
        return getattr(logging, value.upper(), value)  # Map to logging level constant
    else:
        return value  # Default case for other fields


def extract_update(raw_config: RawConfigParser):
    """Reads the component configuration and extracts any logging configuration available.
    Returns a dictionary that can be used to update logging configuration"""
    logging_conf_update = {}

    for section in raw_config.sections():
        if section.startswith('logging'):
            logging_conf_update = {key: value for key, value in raw_config[section].items()}
        elif section.startswith('formatter_'):
            formatter_name = section.split('_', 1)[1]
            logging_conf_update.setdefault('formatters', {})[formatter_name] = {
                key: parse_field(value) for key, value in raw_config.items(section)
            }
        elif section.startswith('logger_'):
            logger_name = section.split('_', 1)[1]
            logging_conf_update.setdefault('loggers', {})[logger_name] = {
                key: parse_field(value) for key, value in raw_config.items(section)
            }
        elif section.startswith('handlers_'):
            handler_name = section.split('_', 1)[1]
            logging_conf_update.setdefault('handlers', {})[handler_name] = {
                key: parse_field(value) for key, value in raw_config.items(section)
            }
    
    # Check if mandatory 'version' is present, otherwise retrieve it from the original configuration
    if 'version' not in logging_conf_update.keys():
        logging_conf_update['version'] = ast.literal_eval(
            {key: value for key, value in config.get_config("logging")['logging'].items()}['version']
        )


def init_logging(loggername: str) -> Logger:
    logger = logging.getLogger(f"keylime.{loggername}")
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
