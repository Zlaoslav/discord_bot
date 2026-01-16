from bot import Bot
import discord
from typing import Optional

async def add_temp_mapping(bot: Bot, trigger_channel_id: int, user_id: int, voice_channel_id: int, text_channel_id: Optional[int] = None) -> None:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    # keep per-user settings here as optional field 'settings'
    m[str(user_id)] = {"voice": int(voice_channel_id), "text": int(text_channel_id) if text_channel_id else None, "settings": {}}
    await bot.db.tempvoice.update_tempvoice_map(trigger_channel_id, m)

async def remove_temp_mapping_by_voice(bot: Bot, trigger_channel_id: int, voice_channel_id: int) -> None:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    keys = [k for k, v in m.items() if v.get("voice") == int(voice_channel_id)]
    for k in keys:
        del m[k]
    await bot.db.tempvoice.update_tempvoice_map(trigger_channel_id, m)

async def remove_temp_mapping_by_user(bot: Bot, trigger_channel_id: int, user_id: int) -> None:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    if str(user_id) in m:
        del m[str(user_id)]
    await bot.db.tempvoice.update_tempvoice_map(trigger_channel_id, m)

async def update_user_settings(bot: Bot, trigger_channel_id: int, user_id: int, user_settings: dict) -> None:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return
    m = rec.get("current_map") or {}
    entry = m.get(str(user_id)) or {}
    entry_settings = entry.get("settings") or {}
    entry_settings.update(user_settings)
    entry["settings"] = entry_settings
    m[str(user_id)] = entry
    await bot.db.tempvoice.update_tempvoice_map(trigger_channel_id, m)

async def get_user_settings(bot: Bot, trigger_channel_id: int, user_id: int) -> dict:
    """Return merged settings: global settings overridden by per-user settings."""
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return {}
    global_settings = rec.get("settings") or {}
    m = rec.get("current_map") or {}
    entry = m.get(str(user_id)) or {}
    user_settings = entry.get("settings") or {}
    # merge
    merged = dict(global_settings)
    merged.update(user_settings)
    return merged


def _serialize_overwrites(overwrites: dict) -> dict:
    """Serialize channel.overwrites mapping to simple dict."""
    out = {}
    perms_keys = ("connect", "view_channel", "send_messages", "manage_channels", "mute_members", "deafen_members", "move_members", "priority_speaker")
    for target, ow in (overwrites or {}).items():
        try:
            if isinstance(target, discord.Role):
                key = f"role:{target.id}"
            elif isinstance(target, discord.Member):
                key = f"member:{target.id}"
            else:
                continue
        except Exception:
            continue
        vals = {}
        for p in perms_keys:
            try:
                v = getattr(ow, p, None)
            except Exception:
                v = None
            if v is None:
                vals[p] = None
            else:
                vals[p] = bool(v)
        out[key] = vals
    return out


def _deserialize_overwrites(serialized: dict, guild: discord.Guild) -> dict:
    """Deserialize mapping into {target: PermissionOverwrite} where target is Role or Member if found."""
    out = {}
    perms_keys = ("connect", "view_channel", "send_messages", "manage_channels", "mute_members", "deafen_members", "move_members", "priority_speaker")
    for key, perms in (serialized or {}).items():
        try:
            typ, id_str = key.split(":", 1)
            idn = int(id_str)
        except Exception:
            continue
        target = None
        if typ == "role":
            target = guild.get_role(idn)
        elif typ == "member":
            target = guild.get_member(idn)
            # if not in cache, skip (can't fetch here safely)
        if not target:
            continue
        ow = discord.PermissionOverwrite()
        for p in perms_keys:
            v = perms.get(p)
            try:
                setattr(ow, p, None if v is None else bool(v))
            except Exception:
                pass
        out[target] = ow
    return out

async def get_temp_channel_for_user(bot: Bot, trigger_channel_id: int, user_id: int) -> Optional[int]:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return None
    m = rec.get("current_map") or {}
    v = m.get(str(user_id))
    if not v:
        return None
    return v.get("voice")

async def get_all_temp_channels_for_trigger(bot: Bot, trigger_channel_id: int) -> list[int]:
    rec = await bot.db.tempvoice.get_tempvoice_by_trigger(trigger_channel_id)
    if not rec:
        return []
    m = rec.get("current_map") or {}
    return [v.get("voice") for v in m.values() if v.get("voice")]

