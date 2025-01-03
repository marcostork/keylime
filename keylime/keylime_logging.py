import contextvars
import logging
from configparser import RawConfigParser
from logging import Logger
from logging import config as logging_config
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from keylime import config

if TYPE_CHECKING:
    from logging import LogRecord


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


def _safe_get_config(loggername: str) -> Optional[RawConfigParser]:
    try:
        return config.get_config(loggername)
    except Exception:  # Replace with the actual exception
        return None


def init_logging(loggername: str) -> Logger:
    logger = logging.getLogger(f"keylime.{loggername}")

    component_config = _safe_get_config(loggername)

    # Apply logger component configuration if any, otherwise follow the current configuration
    if component_config:
        try:
            logging_config.fileConfig(component_config)
        except KeyError:
            logging.basicConfig(format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s", level=logging.DEBUG)

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
