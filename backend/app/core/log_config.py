import logging

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """Sends the application's "dxscan.*" loggers to the console.

    Uvicorn only configures its own loggers, so without this our INFO messages are dropped and the
    warnings reach stderr unformatted. Idempotent: the dev server's reload imports main.py again.
    """
    logger = logging.getLogger("dxscan")
    logger.setLevel(level.upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
