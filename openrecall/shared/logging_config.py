"""Shared logging configuration for OpenRecall."""

import logging
from openrecall.shared.config import settings


def configure_logging(component: str = "openrecall") -> logging.Logger:
    """Configure logging based on debug setting.
    
    Args:
        component: Name of the component for the logger (e.g., 'server', 'client')
        
    Returns:
        Configured logger instance.
    """
    log_level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Suppress noisy third-party loggers (even in debug mode)
    noisy_loggers = [
        "PIL",
        "h5py",
        "urllib3",
        "matplotlib",
        "fontTools",
    ]
    for name in noisy_loggers:
        logging.getLogger(name).setLevel(logging.WARNING)

    # In non-debug mode, also suppress these
    if not settings.debug:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)

    return logging.getLogger(component)
