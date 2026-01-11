import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from services_folder.srv_tempvoice import get_tempvoice_by_trigger, get_temp_channel_for_user, get_user_settings, add_temp_mapping, remove_temp_mapping_by_voice, get_tempvoice_by_guild


class tempvoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Игнорировать ботов (включая самого бота)
        if member.bot:
            return
        # Пользователь зашёл в канал (или переместился)
        try:
            # если вошёл в канал
            if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
                trig = get_tempvoice_by_trigger(after.channel.id)
                # try global trigger (0) if specific trigger not found
                if not trig:
                    trig = get_tempvoice_by_trigger(0)
                if trig:
                    guild = after.channel.guild
                    # если у пользователя уже есть temp-канал — переместить
                    existing = get_temp_channel_for_user(after.channel.id, member.id)
                    if existing:
                        ch = guild.get_channel(int(existing))
                        if ch:
                            try:
                                await member.move_to(ch)
                            except Exception:
                                pass
                        return

                    trig_key = trig.get('trigger_channel_id') or 0
                    settings = trig.get('settings') or {}
                    # merge per-user settings
                    user_merged = get_user_settings(trig_key, member.id) or {}
                    final_settings = dict(settings)
                    final_settings.update(user_merged)
                    prefix = final_settings.get('prefix', 'TempVoice ')
                    # формируем название (макс 50 символов)
                    base_name = f"{prefix}{member.display_name}"[:50]
                    category = after.channel.category

                    # собираем overwrites
                    # собираем overwrites с приоритетом: allowed -> blocked -> trusted
                    overwrites: dict = {}
                    # по умолчанию разрешаем подключаться всем (будут блокировки ниже при необходимости)
                    overwrites[guild.default_role] = discord.PermissionOverwrite(connect=True, view_channel=True)

                    # сначала allowed (могут быть позже переопределены blocked)
                    for rid in (settings.get('allowed_roles') or []):
                        try:
                            r = guild.get_role(int(rid))
                            if r:
                                overwrites[r] = discord.PermissionOverwrite(connect=True)
                        except Exception:
                            continue

                    for uid in (settings.get('allowed_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=True)
                        except Exception:
                            continue

                    # затем blocked (переопределяют allowed)
                    for rid in (settings.get('blocked_roles') or []):
                        try:
                            r = guild.get_role(int(rid))
                            if r:
                                overwrites[r] = discord.PermissionOverwrite(connect=False)
                        except Exception:
                            continue

                    for uid in (settings.get('blocked_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=False)
                        except Exception:
                            continue

                    # trusted — всегда имеют доступ, перебивают блокировки
                    for uid in (settings.get('trusted_users') or []):
                        try:
                            m = guild.get_member(int(uid))
                            if m:
                                overwrites[m] = discord.PermissionOverwrite(connect=True, manage_channels=True)
                        except Exception:
                            continue

                    # создаём канал
                    user_limit = int(final_settings.get('user_limit') or 0) or 0
                    br = final_settings.get('bitrate')
                    kwargs = {"overwrites": overwrites, "category": category, "user_limit": user_limit}
                    if br:
                        try:
                            kwargs['bitrate'] = int(br)
                        except Exception:
                            pass

                    try:
                        # use per-user settings overrides if exist
                        # kwargs currently contains overwrites/category/user_limit/bitrate
                        ch = await guild.create_voice_channel(name=base_name, **kwargs)
                    except TypeError:
                        # старые версии discord.py могут не принимать bitrate
                        kwargs.pop('bitrate', None)
                        ch = await guild.create_voice_channel(name=base_name, **kwargs)

                    # Не создаём отдельный текстовый канал — используем встроенный связанный чат голосового канала.
                    # Сохраняем mapping (текстовый канал не применяется)
                    trig_key = trig.get('trigger_channel_id') or 0
                    add_temp_mapping(int(trig_key), member.id, ch.id, None)

                    # пытаемся переместить пользователя
                    try:
                        await member.move_to(ch)
                    except Exception:
                        pass

            # выход из канала — если ушёл из временного канала, проверить на удаление
            if before.channel is not None and (after.channel is None or (after.channel is not None and before.channel.id != after.channel.id)):
                # проверяем все триггеры сервера
                for rec in get_tempvoice_by_guild(member.guild.id):
                    mapping = rec.get('current_map') or {}
                    # если before.channel.id — один из temp каналов
                    for k, v in list(mapping.items()):
                        if v.get('voice') == (before.channel.id if before.channel else None):
                            # если канал пуст — удалить и очистить запись
                            vc = member.guild.get_channel(int(v.get('voice')))
                            if vc:
                                if len(vc.members) == 0:
                                    try:
                                        await vc.delete()
                                    except Exception:
                                        pass
                                    # удалить маппинг
                                    remove_temp_mapping_by_voice(rec.get('trigger_channel_id'), int(v.get('voice')))
                            else:
                                # канал не найден — удаляем запись
                                remove_temp_mapping_by_voice(rec.get('trigger_channel_id'), int(v.get('voice')))
        except Exception as e:
            logger.exception(f"Ошибка в on_voice_state_update (tempvoice): {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(tempvoice(bot))
