"""
discord_embed_builder.py

Утилиты для простого создания discord.Embed объектов (discord.py).
- Полностью кастомизируемый EmbedBuilder (chainable API).
- Быстрые пресеты: info_embed, warn_embed, error_embed, alert_embed.
- По умолчанию добавляется последний маленький (inline) field с текущей датой/временем
  в часовом поясе Europe/Riga. Это поведение можно отключить.

"""

from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple, Iterable, Union
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import re

import discord



def _get_riga_now() -> datetime:
    """
    Возвращает текущую дату/время в часовом поясе Europe/Riga (aware datetime).
    """
    try:
        tz = ZoneInfo("Europe/Riga")
    except Exception:
        tz = timezone.utc
    return datetime.now(tz)


def _format_timestamp(dt: datetime) -> str:
    """
    Форматирует дату/время в читаемую строку, например: '2026-02-08 14:23:12 EET'
    """
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return dt.isoformat()


def hex_to_int(color: Union[str, int, None]) -> Optional[int]:
    """
    Преобразует цвет в формат int (0xRRGGBB) для discord. Допускается:
    - строка '#AABBCC' или 'AABBCC' или короткий 'ABC'
    - None -> None
    """
    if color is None:
        return None
    if isinstance(color, int):
        return color
    s = str(color).strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) == 3:
        s = "".join([c*2 for c in s])
    if not re.fullmatch(r"[0-9a-fA-F]{6}", s):
        raise ValueError(f"Цвет должен быть в hex-формате RRGGBB, получили: {color!r}")
    return int(s, 16)


# --- EmbedBuilder -----------------------------------------------------------

class EmbedBuilder:
    """
    Embed builder, возвращающий discord.Embed.

    Примеры:
        eb = (EmbedBuilder()
              .set_title("Заголовок")
              .set_description("Описание")
              .set_color("#00ff00")
              .add_field("Ключ", "Значение", inline=True)
              )
        embed = eb.build()  # discord.Embed
    """

    def __init__(
                self,
                title: Optional[str] = None,
                description: Optional[str] = None,
                url: Optional[str] = None,
                color: Optional[Union[str, int]] = None,
                include_timestamp_field: bool = True,
                timestamp_label: str = "Время"
            ):
        
        self._title = title
        self._description = description
        self._url = url
        self._color = hex_to_int(color) if color is not None else None
        self._author: Optional[Dict[str, Any]] = None
        self._footer: Optional[Dict[str, Any]] = None
        self._image_url: Optional[str] = None
        self._thumbnail_url: Optional[str] = None
        self._fields: List[Dict[str, Any]] = []
        self._include_timestamp_field = include_timestamp_field
        self._timestamp_label = timestamp_label


    def set_title(self, title: str) -> "EmbedBuilder":
        self._title = title
        return self

    def set_description(self, description: str) -> "EmbedBuilder":
        self._description = description
        return self

    def set_url(self, url: str) -> "EmbedBuilder":
        self._url = url
        return self

    def set_color(self, color: Union[str, int]) -> "EmbedBuilder":
        self._color = hex_to_int(color)
        return self

    def set_author(self, name: str, url: Optional[str] = None, icon_url: Optional[str] = None) -> "EmbedBuilder":
        self._author = {"name": name}
        if url:
            self._author["url"] = url
        if icon_url:
            self._author["icon_url"] = icon_url
        return self

    def set_footer(self, text: str, icon_url: Optional[str] = None) -> "EmbedBuilder":
        self._footer = {"text": text}
        if icon_url:
            self._footer["icon_url"] = icon_url
        return self

    def set_image(self, url: str) -> "EmbedBuilder":
        self._image_url = url
        return self

    def set_thumbnail(self, url: str) -> "EmbedBuilder":
        self._thumbnail_url = url
        return self

    def add_field(self, name: str, value: str, inline: bool = False) -> "EmbedBuilder":
        """
        Добавляет поле. Поле остаётся в порядке добавления.
        """
        self._fields.append({"name": name, "value": value, "inline": inline})
        return self

    def add_fields(self, fields: Iterable[Tuple[str, str, bool]]) -> "EmbedBuilder":
        """
        Добавляет несколько полей из итерации кортежей (name, value, inline).
        """
        for n, v, i in fields:
            self.add_field(n, v, i)
        return self

    def clear_fields(self) -> "EmbedBuilder":
        self._fields = []
        return self

    def include_timestamp_field(self, enable: bool = True, label: Optional[str] = None) -> "EmbedBuilder":
        """
        Включает/отключает автоматическое добавление последнего маленького поля с временем.
        """
        self._include_timestamp_field = enable
        if label is not None:
            self._timestamp_label = label
        return self


    def set_raw_author(self, author: Dict[str, Any]) -> "EmbedBuilder":
        self._author = author
        return self

    def set_raw_footer(self, footer: Dict[str, Any]) -> "EmbedBuilder":
        self._footer = footer
        return self

    def build(self) -> discord.Embed:
        """
        Собирает и возвращает discord.Embed.
        Поле timestamp (Embed.timestamp) не используется здесь — вместо этого
        если включено, в конец добавляется маленькое inline поле с текущим временем.
        """
        # Создаём embed
        kwargs: Dict[str, Any] = {}
        if self._title is not None:
            kwargs["title"] = self._title
        if self._description is not None:
            kwargs["description"] = self._description
        if self._url is not None:
            kwargs["url"] = self._url
        if self._color is not None:
            kwargs["colour"] = discord.Colour(self._color) if isinstance(self._color, int) else self._color

        embed = discord.Embed(**kwargs)

        if self._author:
            # discord.Embed.set_author принимает name/url/icon_url
            embed.set_author(name=self._author.get("name", ""),
                             url=self._author.get("url"),
                             icon_url=self._author.get("icon_url"))

        if self._footer:
            embed.set_footer(text=self._footer.get("text", ""),
                             icon_url=self._footer.get("icon_url"))

        if self._image_url:
            embed.set_image(url=self._image_url)

        if self._thumbnail_url:
            embed.set_thumbnail(url=self._thumbnail_url)

        # add fields
        for f in self._fields:
            embed.add_field(name=f.get("name", ""), value=f.get("value", ""), inline=bool(f.get("inline", False)))

        # add timestamp field as last small field if enabled
        if self._include_timestamp_field:
            now = _get_riga_now()
            embed.add_field(name=self._timestamp_label, value=_format_timestamp(now), inline=True)

        return embed



_PRESET_COLORS = {
    "info": "#2f80ed",     # синий
    "warn": "#f2c94c",     # жёлтый
    "error": "#eb5757",    # красный
    "alert": "#ff8a00",    # оранжевый
}

def quick_embed_text(
            text: str,
            title: Optional[str] = None,
            color: Union[str, int] = "#5865F2",
            extra_fields: Optional[Iterable[Tuple[str, str, bool]]] = None,
            timestamp_field: bool = True,
            timestamp_label: str = "Время"
        ) -> discord.Embed:
    """
    Быстрая функция — возвращает discord.Embed с description=text.
    - title: опциональный заголовок
    - color: hex или int
    - extra_fields: iterable кортежей (name, value, inline) — будут добавлены перед timestamp
    - timestamp_field: включить/выключить последний маленький field с текущим временем
    - timestamp_label: подпись для timestamp field
    """
    eb = EmbedBuilder(
            title=title,
            description=text,
            color=color,
            include_timestamp_field=timestamp_field,
            timestamp_label=timestamp_label
        )
    if extra_fields:
        eb.add_fields(extra_fields)
    return eb.build()


def _preset_factory(preset_name: str):
    """
    Возвращает функцию-предсет для заданного имени ('info','warn','error','alert').
    Функция имеет сигнатуру (text, title=None, extra_fields=None, timestamp_field=True, timestamp_label='Время', color=None)
    color можно переопределить.
    """
    default_color = _PRESET_COLORS.get(preset_name)

    def _fn(
            text: str,
            title: Optional[str] = preset_name.capitalize(),
            extra_fields: Optional[Iterable[Tuple[str, str, bool]]] = None,
            timestamp_field: bool = True,
            timestamp_label: str = "Время",
            color: Optional[Union[str, int]] = None
        ) -> discord.Embed:
        
        col = color if color is not None else default_color

        return quick_embed_text(
                text=text,
                title=title,
                color=col,
                extra_fields=extra_fields, timestamp_field=timestamp_field,
                timestamp_label=timestamp_label
            )
    
    _fn.__name__ = f"{preset_name}_embed"
    _fn.__doc__ = f"Создаёт '{preset_name}' embed. См. quick_embed_text."
    return _fn

# пресеты
info_embed = _preset_factory("info")
warn_embed = _preset_factory("warn")
error_embed = _preset_factory("error")
alert_embed = _preset_factory("alert")

__all__ = ["EmbedBuilder", "quick_embed_text", "info_embed", "warn_embed", "error_embed", "alert_embed"]
