import logging

# Цвета для терминала
COLORS = {
    "DEBUG": "\033[38;5;245m",
    "INFO": "\033[38;5;39m",
    "WARNING": "\033[38;5;220m",
    "ERROR": "\033[38;5;203m",
    "CRITICAL": "\033[41m",
    "TIME": "\033[38;5;240m",
    "SOURCE": "\033[38;5;141m",
    "RESET": "\033[0m"
}

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


# ✅ ИМЕННОЙ логгер, НЕ root
logger = logging.getLogger("minecraft_bot")
logger.setLevel(logging.INFO)

# ❗ КЛЮЧЕВОЕ — запрещаем проброс в root
logger.propagate = False

# Настраиваем handler ТОЛЬКО один раз
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = ColorFormatter(
        "%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d — %(message)s",
        "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Глушим шумные логгеры
logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("aiosqlite.core").setLevel(logging.WARNING)

__all__ = ["logger", "ColorFormatter", "COLORS"]
