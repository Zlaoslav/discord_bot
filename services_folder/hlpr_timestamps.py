"""
Создание времянных меток дискорда,
стили:

t   14:32\n
T	14:32:10\n
d	06.02.2026\n
D	6 февраля 2026\n
f	6 февраля 2026 14:32\n
F	четверг, 6 февраля 2026 14:32\n
R	через 5 минут\n
"""
import time
from datetime import datetime, timezone

def from_unix(unix: int, style: str = "f") -> str:
    """Метка времени из UNIX-секунд"""
    return f"<t:{int(unix)}:{style}>"


def from_datetime(dt: datetime, style: str = "f") -> str:
    """Метка времени из datetime"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"


def from_parts(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    style: str = "f",
    tz=timezone.utc
) -> str:
    """Метка времени из отдельных значений даты и времени"""
    dt = datetime(year, month, day, hour, minute, second, tzinfo=tz)
    return f"<t:{int(dt.timestamp())}:{style}>"


def in_seconds(seconds: int, style: str = "R") -> str:
    """Метка времени через N секунд от текущего момента"""
    return f"<t:{int(time.time()) + int(seconds)}:{style}>"


def now(style: str = "f") -> str:
    """Метка времени для текущего момента"""
    return f"<t:{int(time.time())}:{style}>"


def today(style: str = "D") -> str:
    """Метка времени для текущей даты"""
    dt = datetime.now(timezone.utc)
    return f"<t:{int(dt.timestamp())}:{style}>"
