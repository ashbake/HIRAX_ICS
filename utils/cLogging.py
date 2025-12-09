import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(
    log_dir="logs",
    log_name="hirax_control",
    log_level=logging.INFO,
    console_level=logging.INFO,
    log_to_file=True,
    log_to_console=True,
    max_bytes=10485760,  # 10MB
    backup_count=5
):
    """
    Configure logging for the application.
    
    Args:
        log_dir: Directory to store log files
        log_level: Logging level for file output
        console_level: Logging level for console output
        log_to_file: Whether to log to file
        log_to_console: Whether to log to console
        max_bytes: Maximum size of each log file before rotation
        backup_count: Number of backup log files to keep
    
    Returns:
        logging.Logger: Configured root logger
    """
    
    # Create logs directory if it doesn't exist
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Capture all levels, handlers will filter
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Define formats
    detailed_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # File handler with rotation
    if log_to_file:
        log_filename = f"{log_name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = RotatingFileHandler(
            log_path / log_filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(detailed_format)
        logger.addHandler(file_handler)
    
    # Console handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(console_level)
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)
    
    # Log the initialization
    logger.info("=" * 80)
    logger.info("Astronomy Instrumentation Control System - Logging Initialized")
    logger.info(f"Log level: {logging.getLevelName(log_level)}")
    if log_to_file:
        logger.info(f"Log file: {log_path / log_filename}")
    logger.info("=" * 80)
    
    return logger


def get_logger(name):
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Name of the logger (typically __name__)
    
    Returns:
        logging.Logger: Logger instance
    """
    return logging.getLogger(name)


# Optional: Create separate loggers for different subsystems
def setup_device_logger(device_name, log_dir="logs/devices"):
    """
    Create a separate logger for a specific device.
    Useful for debugging individual hardware components.
    
    Args:
        device_name: Name of the device (e.g., 'guide_camera', 'science_detector')
        log_dir: Directory for device-specific logs
    
    Returns:
        logging.Logger: Device-specific logger
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    logger = logging.getLogger(f"devices.{device_name}")
    logger.setLevel(logging.DEBUG)
    
    # Don't propagate to root logger to avoid duplicate logs
    logger.propagate = False
    
    # Device-specific file handler
    log_filename = f"{device_name}_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = RotatingFileHandler(
        log_path / log_filename,
        maxBytes=5242880,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    
    device_format = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(device_format)
    
    logger.addHandler(file_handler)
    
    return logger


# Example usage function
def log_camera_event(logger, event_type, **kwargs):
    """
    Helper function to log camera events with consistent formatting.
    
    Args:
        logger: Logger instance
        event_type: Type of event (e.g., 'exposure_start', 'temperature_update')
        **kwargs: Additional event parameters
    """
    params_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"[{event_type.upper()}] {params_str}")


if __name__ == "__main__":
    # Example usage
    setup_logging(log_level=logging.DEBUG)
    
    logger = get_logger(__name__)
    logger.debug("This is a debug message")
    logger.info("Starting observation sequence")
    logger.warning("Temperature outside optimal range")
    logger.error("Failed to connect to camera")
    
    # Device-specific logger example
    camera_logger = setup_device_logger("guide_camera")
    log_camera_event(camera_logger, "exposure_start", duration=5.0, binning="2x2")
    log_camera_event(camera_logger, "temperature_update", temp=-10.5, target=-15.0)