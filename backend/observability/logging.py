"""Logger factory and file-handler helper.

The single logger factory is :func:`get_logger`; every module in the backend
starts with ``logger = get_logger(__name__)``. Hydra manages console logging
for the CLI; the API configures basic stdlib logging at startup. The only
custom handler this module ships is :func:`attach_file_handler` for capturing
errors beside Hydra's artifacts.

# ADR: Logging and Telemetry Contract
# See: adr/0012-logging-and-telemetry-contract.md
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger whose name equals *name*.

    The returned logger inherits the handlers attached to the root logger (or
    to a parent logger configured by Hydra / the API startup). Module-level
    loggers have NO handlers attached directly; they propagate up.

    :param name: typically ``__name__`` of the calling module.

    :return: a configured :class:`logging.Logger`.
    """
    return logging.getLogger(name)


def attach_file_handler(target: Path, level: int = logging.ERROR) -> logging.Handler:
    """
    Attach a file handler to the root logger at ``target``.

    Ensures exceptions reach an ``error.log`` next to Hydra's other artifacts.
    The caller is responsible for removing the handler if the process is
    long-lived.

    :param target:  Filesystem path to the log file (created if absent).
    :param level:   Minimum level captured by the handler.
    :returns:       The handler instance for caller-side cleanup.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(target)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    logging.getLogger().addHandler(handler)
    logger.info(
        "attach_file_handler: writing %s logs to %s",
        logging.getLevelName(level),
        target,
    )
    return handler
