import logging

# Цвета для терминала
COLORS = {
    "DEBUG": "\033[38;5;245m",    # серый
    "INFO": "\033[38;5;39m",      # синий
    "WARNING": "\033[38;5;220m",  # жёлтый
    "ERROR": "\033[38;5;203m",    # красный
    "CRITICAL": "\033[41m",       # белый на красном фоне
    "TIME": "\033[38;5;240m",     # тёмно-серый
    "SOURCE": "\033[38;5;141m",   # фиолетовый
    "RESET": "\033[0m"
}

# Форматтер с цветами
class ColorFormatter(logging.Formatter):
    def format(self, record):
        level_color = COLORS.get(record.levelname, COLORS["RESET"])
        time_color = COLORS["TIME"]
        source_color = COLORS["SOURCE"]

        msg = super().format(record)

        msg = msg.replace(
            record.asctime, f"{time_color}{record.asctime}{COLORS['RESET']}"
        ).replace(
            record.levelname, f"{level_color}{record.levelname}{COLORS['RESET']}"
        ).replace(
            f"{record.filename}:{record.lineno}",
            f"{source_color}{record.filename}:{record.lineno}{COLORS['RESET']}"
        )

        return msg


logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = ColorFormatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

__all__ = ["logger", "ColorFormatter", "COLORS"]
