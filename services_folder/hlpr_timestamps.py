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


def parse_duration(duration: str) -> int:
    """Парсинг строки продолжительности в секунды (например, '1d', '2h30m', '45m')"""
    total_seconds = 0
    num = ""
    for char in duration:
        if char.isdigit():
            num += char
        else:
            if num == "":
                raise ValueError("Неверный формат продолжительности")
            value = int(num)
            if char == 'y':
                total_seconds += value * 365 * 86400
            elif char == 'w':
                total_seconds += value * 7 * 86400
            elif char == 'd':
                total_seconds += value * 86400
            elif char == 'h':
                total_seconds += value * 3600
            elif char == 'm':
                total_seconds += value * 60
            elif char == 's':
                total_seconds += value
            else:
                raise ValueError("Неверный формат продолжительности")
            num = ""
    if num != "":
        raise ValueError("Неверный формат продолжительности")
    return total_seconds


def format_relative(dt: datetime) -> str:
    """Форматирование datetime в строку вида '5 минут назад' или 'через 2 часа'"""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = dt - now
    seconds = int(delta.total_seconds())
    if seconds < 0:
        suffix = "назад"
        seconds = -seconds
    else:
        suffix = "через"
    
    if seconds < 60:
        return f"{suffix} {seconds} секунд"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{suffix} {minutes} минут"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{suffix} {hours} часов"
    else:
        days = seconds // 86400
        return f"{suffix} {days} дней"