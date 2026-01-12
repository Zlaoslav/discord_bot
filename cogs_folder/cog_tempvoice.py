import discord
from discord.ext import commands
from discord import app_commands
import services_folder.hlpr_perms_manager as perms_manager
from services_folder.hlpr_logging import logger
from services_folder.srv_tempvoice import get_temp_channel_for_user, get_user_settings, add_temp_mapping, remove_temp_mapping_by_voice, remove_temp_mapping_by_user, _serialize_overwrites, _deserialize_overwrites
from db_folder import DB
import time
class tempvoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_join_time = {}  # key = (guild_id, user_id), value = timestamp
        
    @app_commands.command(
        name="send_tempvoicepanel",
        description="Отправить панель TempVoice (owner only)"
    )
    async def send_tempvoicepanel(self, interaction: discord.Interaction, trigger: discord.VoiceChannel | None, channel: discord.TextChannel | None = None):
        if interaction.guild is None:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not perms_manager.has_perm(interaction.user.id, perms_manager.PermRole.OWNER):
            await interaction.response.send_message("У вас недостаточно прав.", ephemeral=True)
            return
        # support passing trigger or using global trigger (0)
        rec = None
        if trigger is not None:
            rec = DB.tempvoice.get_tempvoice_by_trigger(int(trigger.id))
        if not rec:
            # try global
            rec = DB.tempvoice.get_tempvoice_by_trigger(0)
        if not rec:
            await interaction.response.send_message("⚠️ Триггер не настроен. Сначала используйте /set_tempvoice.", ephemeral=True)
            return
        target = channel or interaction.channel
        # удаляем старую панель, если есть
        old_msg_id = rec.get('panel_message_id')
        if old_msg_id:
            try:
                ch = target
                old = await ch.fetch_message(old_msg_id)
                try:
                    await old.delete()
                except Exception:
                    pass
            except Exception:
                pass
        # отправим новую (с эмодзи и более дружелюбным текстом)
        trig_key = int(trigger.id) if trigger is not None else (rec.get('trigger_channel_id') or 0)
        view = TempVoicePanelView(int(trig_key))
        sent = await target.send("🎛️ Панель TempVoice — нажмите кнопки для управления вашим временным каналом.", view=view)
        DB.tempvoice.set_panel_message_id(int(trig_key), int(sent.id))
        await interaction.response.send_message("✅ Панель TempVoice отправлена.", ephemeral=True)
    
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        await self.on_tempvoice(member, before, after)
        await self.on_voice_join_time(member, before, after)
    
    async def on_voice_join_time(self, member, before, after):
        if member.bot:
            return
        
        key = (member.guild.id, member.id)
        now = time.time()

        # Пользователь вошёл в голосовой канал
        if before.channel is None and after.channel is not None:
            self.voice_join_time[key] = now

        # Пользователь вышел из голосового канала
        elif before.channel is not None and after.channel is None:
            join_time = self.voice_join_time.pop(key, None)
            if join_time:
                duration = int(now - join_time)
                DB.level_users.add_voice_time(member.guild.id, member.id, duration)

        # Пользователь переключился между каналами
        elif before.channel != after.channel:
            join_time = self.voice_join_time.get(key)
            if join_time:
                duration = int(now - join_time)
                DB.level_users.add_voice_time(member.guild.id, member.id, duration)
                self.voice_join_time[key] = now
    
    async def on_tempvoice(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Игнорировать ботов (включая самого бота)
        if member.bot:
            return
        # Пользователь зашёл в канал (или переместился)
        try:
            # если вошёл в канал
            if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
                trig = DB.tempvoice.get_tempvoice_by_trigger(after.channel.id)
                # try global trigger (0) if specific trigger not found
                if not trig:
                    trig = DB.tempvoice.get_tempvoice_by_trigger(0)
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
                for rec in DB.tempvoice.get_tempvoice_by_guild(member.guild.id):
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



class TempVoicePanelView(discord.ui.View):
    def __init__(self, trigger_channel_id: int):
        super().__init__(timeout=None)
        self.trigger_channel_id = trigger_channel_id
        
    @discord.ui.button(label="⚙️ Настройки", style=discord.ButtonStyle.secondary, custom_id="tv_settings")
    async def settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # отправим приватное (ephemeral) сообщение с опциями
        await interaction.response.send_message("Выберите действие настройки (будут применяться к вашему временно созданному каналу):", view=SettingsOptionsView(self.trigger_channel_id), ephemeral=True)

    @discord.ui.button(label="🔐 Права входа", style=discord.ButtonStyle.secondary, custom_id="tv_perms")
    async def perms_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Управление правами входа для TempVoice (ваш канал):", view=PermsOptionsView(self.trigger_channel_id), ephemeral=True)

class SettingsOptionsView(discord.ui.View):
    def __init__(self, trigger_channel_id: int):
        super().__init__(timeout=120)
        self.trigger_channel_id = trigger_channel_id

    @discord.ui.button(label="✏️ Изменить название", style=discord.ButtonStyle.primary)
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Modal для ввода нового имени
        class RenameModal(discord.ui.Modal, title="✏️ Изменить название канала"):
            new_name = discord.ui.TextInput(label="Новое имя (max 50)", max_length=50, placeholder="Например: TempVoice Алекс")

            async def on_submit(self_inner, modal_inter: discord.Interaction):
                new_name_val = self_inner.new_name.value.strip()
                # пытаемся найти temp канал пользователя
                rec = DB.tempvoice.get_tempvoice_by_trigger(self.trigger_channel_id)
                if not rec:
                    await modal_inter.response.send_message("Триггер не найден.", ephemeral=True)
                    return
                voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                if not voice_id:
                    await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                    return
                guild = modal_inter.guild
                try:
                    ch = guild.get_channel(int(voice_id))
                    if ch:
                        await ch.edit(name=new_name_val[:50])
                        await modal_inter.response.send_message(f"Название канала изменено на: {new_name_val}", ephemeral=True)
                    else:
                        await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                except Exception as e:
                    logger.warning(f"Ошибка при переименовании: {e}")
                    await modal_inter.response.send_message("Ошибка при переименовании (см лог).", ephemeral=True)

        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="👥 Изменить лимит", style=discord.ButtonStyle.primary)
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        class LimitModal(discord.ui.Modal, title="Установить лимит пользователей"):
            limit = discord.ui.TextInput(label="Лимит (0 — без лимита)", placeholder="0", max_length=4)

            async def on_submit(self_inner, modal_inter: discord.Interaction):
                try:
                    val = int(self_inner.limit.value.strip())
                except Exception:
                    await modal_inter.response.send_message("Неправильное число.", ephemeral=True)
                    return
                voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                if not voice_id:
                    await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                    return
                ch = modal_inter.guild.get_channel(int(voice_id))
                if not ch:
                    await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                    return
                try:
                    await ch.edit(user_limit=val)
                    await modal_inter.response.send_message(f"Лимит установлен: {val}", ephemeral=True)
                except Exception as e:
                    logger.warning(e)
                    await modal_inter.response.send_message("Ошибка при установке лимита.", ephemeral=True)

        await interaction.response.send_modal(LimitModal())

    @discord.ui.button(label="🎚️ Изменить битрейт", style=discord.ButtonStyle.primary)
    async def set_bitrate(self, interaction: discord.Interaction, button: discord.ui.Button):
        class BitrateModal(discord.ui.Modal, title="Установить битрейт (kbps)"):
            br = discord.ui.TextInput(label="Битрейт в kbps (например 64)", placeholder="64", max_length=6)

            async def on_submit(self_inner, modal_inter: discord.Interaction):
                try:
                    kb = int(self_inner.br.value.strip())
                except Exception:
                    await modal_inter.response.send_message("Неправильное число.", ephemeral=True)
                    return
                voice_id = get_temp_channel_for_user(self.trigger_channel_id, modal_inter.user.id)
                if not voice_id:
                    await modal_inter.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
                    return
                ch = modal_inter.guild.get_channel(int(voice_id))
                if not ch:
                    await modal_inter.response.send_message("Канал не найден.", ephemeral=True)
                    return
                try:
                    await ch.edit(bitrate=kb * 1000)
                    await modal_inter.response.send_message(f"Битрейт установлен: {kb} kbps", ephemeral=True)
                except Exception as e:
                    logger.warning(e)
                    await modal_inter.response.send_message("Ошибка при установке битрейта.", ephemeral=True)

        await interaction.response.send_modal(BitrateModal())

    @discord.ui.button(label="💬 Вкл/Выкл чат", style=discord.ButtonStyle.secondary)
    async def toggle_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        # переключим chat_enabled в настройках триггера и создадим/удалим текстовый канал
        voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
        if not voice_id:
            await interaction.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(int(voice_id))
        if not channel:
            await interaction.response.send_message("Канал не найден.", ephemeral=True)
            return
        rec = DB.tempvoice.get_tempvoice_by_trigger(self.trigger_channel_id)
        if not rec:
            await interaction.response.send_message("Триггер не найден.", ephemeral=True)
            return
        settings = rec.get("settings") or {}
        settings["chat_enabled"] = not bool(settings.get("chat_enabled"))
        DB.tempvoice.update_tempvoice_settings(self.trigger_channel_id, settings)

        role = interaction.guild.default_role
        await channel.set_permissions(role, send_messages=settings["chat_enabled"])
        await channel.set_permissions(role, send_messages_in_threads=settings["chat_enabled"])

        await interaction.response.send_message(
            f"💬 Встроенный чат: {settings['chat_enabled']}.",
            ephemeral=True,
        )

    @discord.ui.button(label="🔒 Заблокировать/Разблокировать", style=discord.ButtonStyle.danger)
    async def lock_unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        rec = DB.tempvoice.get_tempvoice_by_trigger(self.trigger_channel_id)
        if not rec:
            await interaction.response.send_message("Триггер не найден.", ephemeral=True)
            return
        settings = rec.get("settings") or {}
        locked_now = not bool(settings.get('locked'))
        settings['locked'] = locked_now

        # применим к текущему каналу пользователя
        voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
        if voice_id:
            ch = interaction.guild.get_channel(int(voice_id))
            if ch:
                try:
                    # получаем map saved_overwrites
                    saved = settings.get('saved_overwrites') or {}
                    if locked_now:
                        # сохраняем текущие overwrites
                        try:
                            so = _serialize_overwrites(ch.overwrites)
                            saved[str(ch.id)] = so
                            settings['saved_overwrites'] = saved
                        except Exception:
                            pass
                         # строим новые overwrites: блокируем @everyone и разрешаем trusted
                        new_overwrites = {}
                        # Запретим подключение для @everyone (voice-specific)
                        new_overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(connect=False, view_channel=False)
                        # Разрешим доступ для доверенных пользователей (voice perms)
                        for uid in (settings.get('trusted_users') or []):
                            try:
                                m = interaction.guild.get_member(int(uid))
                                if m:
                                    new_overwrites[m] = discord.PermissionOverwrite(connect=True, speak=True, manage_channels=True)
                            except Exception:
                                continue
                        try:
                            await ch.edit(overwrites=new_overwrites)
                        except Exception as e:
                            logger.warning(f"Ошибка при установке locked overwrites: {e}")
                    else:
                        # разблокировать: восстановим сохранённые overwrites если есть
                        try:
                            saved = settings.get('saved_overwrites') or {}
                            ser = saved.get(str(ch.id))
                            if ser:
                                des = _deserialize_overwrites(ser, interaction.guild)
                                await ch.edit(overwrites=des)
                                # удалить запись
                                try:
                                    del saved[str(ch.id)]
                                except KeyError:
                                    pass
                                settings['saved_overwrites'] = saved
                            else:
                                # нет сохранённых — просто разрешаем подключение
                                await ch.set_permissions(interaction.guild.default_role, connect=True)
                        except Exception as e:
                            logger.warning(f"Ошибка при восстановлении overwrites: {e}")
                    DB.tempvoice.update_tempvoice_settings(self.trigger_channel_id, settings)
                    await interaction.response.send_message(f"locked = {settings['locked']}", ephemeral=True)
                    return
                except Exception as e:
                    logger.warning(e)
        else:
            # нет временного канала у пользователя — просто переключаем флаг
            DB.tempvoice.update_tempvoice_settings(self.trigger_channel_id, settings)
            await interaction.response.send_message(f"locked установлено: {settings['locked']}", ephemeral=True)

    @discord.ui.button(label="🚪 Отключить участника", style=discord.ButtonStyle.danger)
    async def disconnect_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Предоставляем список участников только из вашего временного канала
        voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
        if not voice_id:
            await interaction.response.send_message("У вас нет временного канала.", ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(voice_id))
        if not ch:
            await interaction.response.send_message("Канал не найден.", ephemeral=True)
            remove_temp_mapping_by_user(self.trigger_channel_id, interaction.user.id)
            return

        members = [m for m in ch.members if not m.bot and m.id != interaction.user.id]
        if not members:
            await interaction.response.send_message("В вашем канале нет других участников для отключения.", ephemeral=True)
            return

        # Ограничение опций селекта до 25 (максимум Discord)
        options = [discord.SelectOption(label=m.display_name[:100], value=str(m.id), description=f"{m.id}") for m in members[:25]]

        class MemberSelect(discord.ui.Select):
            def __init__(self, opts, channel_id):
                super().__init__(placeholder="Выберите участника(ов) для отключения...", min_values=1, max_values=min(len(opts), 25), options=opts)
                self.channel_id = channel_id

            async def callback(self, select_inter: discord.Interaction):
                guild = select_inter.guild
                results = {"kicked": [], "failed": []}
                for val in self.values:
                    try:
                        uid = int(val)
                        member_obj = guild.get_member(uid) or await guild.fetch_member(uid)
                        if member_obj and member_obj.voice and member_obj.voice.channel and member_obj.voice.channel.id == int(self.channel_id):
                            try:
                                await member_obj.move_to(None)
                                results["kicked"].append(member_obj.mention)
                            except Exception:
                                results["failed"].append(member_obj.mention if member_obj else str(uid))
                        else:
                            results["failed"].append(str(uid))
                    except Exception:
                        results["failed"].append(val)

                parts = []
                if results['kicked']:
                    parts.append(f"Отключены: {', '.join(results['kicked'])}")
                if results['failed']:
                    parts.append(f"Не удалось: {', '.join(results['failed'])}")
                await select_inter.response.edit_message(content="\n".join(parts) or "Готово.", view=None)

        view = discord.ui.View(timeout=60)
        view.add_item(MemberSelect(options, voice_id))
        await interaction.response.send_message("Выберите участников для отключения:", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Удалить мой канал", style=discord.ButtonStyle.danger)
    async def delete_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        voice_id = get_temp_channel_for_user(self.trigger_channel_id, interaction.user.id)
        if not voice_id:
            await interaction.response.send_message("У вас нет созданного временного канала.", ephemeral=True)
            return
        ch = interaction.guild.get_channel(int(voice_id))
        if not ch:
            remove_temp_mapping_by_user(self.trigger_channel_id, interaction.user.id)
            await interaction.response.send_message("Канал не найден, запись удалена.", ephemeral=True)
            return
        # Показываем подтверждение (ephemeral) с кнопками
        class ConfirmDeleteView(discord.ui.View):
            def __init__(self, voice_channel, trig_id, user_id):
                super().__init__(timeout=60)
                self.voice_channel = voice_channel
                self.trig_id = trig_id
                self.user_id = user_id

            @discord.ui.button(label="Да, удалить 🗑️", style=discord.ButtonStyle.danger)
            async def confirm(self, i: discord.Interaction, b: discord.ui.Button):
                # Только владелец кнопки может подтвердить
                if i.user.id != interaction.user.id:
                    await i.response.send_message("Это подтверждение не для вас.", ephemeral=True)
                    return
                try:
                    if self.voice_channel:
                        await self.voice_channel.delete()
                    remove_temp_mapping_by_user(self.trig_id, self.user_id)
                    await i.response.edit_message(content="Ваш временный канал удалён.", view=None)
                except Exception as e:
                    logger.warning(e)
                    await i.response.edit_message(content="Ошибка при удалении канала.", view=None)

            @discord.ui.button(label="Отмена", style=discord.ButtonStyle.secondary)
            async def cancel(self, i: discord.Interaction, b: discord.ui.Button):
                if i.user.id != interaction.user.id:
                    await i.response.send_message("Это действие не для вас.", ephemeral=True)
                    return
                await i.response.edit_message(content="Удаление отменено.", view=None)

        view = ConfirmDeleteView(ch, self.trigger_channel_id, interaction.user.id)
        await interaction.response.send_message("Подтвердите удаление вашего временного канала:", view=view, ephemeral=True)

class PermsOptionsView(discord.ui.View):
    def __init__(self, trigger_channel_id: int):
        super().__init__(timeout=120)
        self.trigger_channel_id = trigger_channel_id

    async def ask_list_and_update(self, interaction: discord.Interaction, field: str, add: bool = True):
        # Показываем ephemeral сообщение с UserSelect для выбора пользователей
        class UsersSelect(discord.ui.UserSelect):
            def __init__(self, trig_id, field_name, add_flag):
                super().__init__(placeholder="Выберите пользователей...", min_values=1, max_values=25)
                self.trig_id = trig_id
                self.field_name = field_name
                self.add_flag = add_flag

            async def callback(self, select_inter: discord.Interaction):
                ids = [u.id for u in self.values]
                rec = DB.tempvoice.get_tempvoice_by_trigger(self.trig_id)
                if not rec:
                    await select_inter.response.send_message("⚠️ Триггер не найден.", ephemeral=True)
                    return
                settings = rec.get('settings') or {}
                lst = settings.get(self.field_name) or []
                if self.add_flag:
                    for i in ids:
                        if i not in lst:
                            lst.append(i)
                else:
                    for i in ids:
                        if i in lst:
                            lst.remove(i)
                settings[self.field_name] = lst
                DB.tempvoice.update_tempvoice_settings(self.trig_id, settings)
                await select_inter.response.edit_message(content=f"✅ Обновлено поле {self.field_name} (count={len(lst)})", view=None)

        view = discord.ui.View(timeout=60)
        view.add_item(UsersSelect(self.trigger_channel_id, field, add))
        await interaction.response.send_message(f"Выберите пользователей для `{field}`:", view=view, ephemeral=True)

    @discord.ui.button(label="✅ Разрешить пользователей", style=discord.ButtonStyle.primary)
    async def add_allowed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update(interaction, 'allowed_users', add=True)

    @discord.ui.button(label="❌ Убрать разрешения", style=discord.ButtonStyle.secondary)
    async def remove_allowed(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update(interaction, 'allowed_users', add=False)

    @discord.ui.button(label="⛔ Заблокировать пользователей", style=discord.ButtonStyle.danger)
    async def add_blocked(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update(interaction, 'blocked_users', add=True)

    @discord.ui.button(label="⭐ Добавить доверенных", style=discord.ButtonStyle.success)
    async def add_trusted(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update(interaction, 'trusted_users', add=True)

    @discord.ui.button(label="✅ Разрешить роли", style=discord.ButtonStyle.primary)
    async def add_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update_roles(interaction, 'allowed_roles', add=True)

    @discord.ui.button(label="❌ Убрать разрешённые роли", style=discord.ButtonStyle.secondary)
    async def remove_allowed_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update_roles(interaction, 'allowed_roles', add=False)

    @discord.ui.button(label="⛔ Заблокировать роли", style=discord.ButtonStyle.danger)
    async def add_blocked_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update_roles(interaction, 'blocked_roles', add=True)

    @discord.ui.button(label="❌ Убрать блокированные роли", style=discord.ButtonStyle.secondary)
    async def remove_blocked_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_list_and_update_roles(interaction, 'blocked_roles', add=False)

    async def ask_list_and_update_roles(self, interaction: discord.Interaction, field: str, add: bool = True):
        # Показываем эпхемерный RoleSelect для выбора ролей
        class RolesSelect(discord.ui.RoleSelect):
            def __init__(self, trig_id, field_name, add_flag):
                super().__init__(placeholder="Выберите роли...", min_values=1, max_values=25)
                self.trig_id = trig_id
                self.field_name = field_name
                self.add_flag = add_flag

            async def callback(self, select_inter: discord.Interaction):
                ids = [r.id for r in self.values]
                rec = DB.tempvoice.get_tempvoice_by_trigger(self.trig_id)
                if not rec:
                    await select_inter.response.send_message("⚠️ Триггер не найден.", ephemeral=True)
                    return
                settings = rec.get('settings') or {}
                lst = settings.get(self.field_name) or []
                if self.add_flag:
                    for i in ids:
                        if i not in lst:
                            lst.append(i)
                else:
                    for i in ids:
                        if i in lst:
                            lst.remove(i)
                settings[self.field_name] = lst
                DB.tempvoice.update_tempvoice_settings(self.trig_id, settings)
                await select_inter.response.edit_message(content=f"✅ Обновлено поле {self.field_name} (count={len(lst)})", view=None)

        view = discord.ui.View(timeout=60)
        view.add_item(RolesSelect(self.trigger_channel_id, field, add))
        await interaction.response.send_message(f"Выберите роли для `{field}`:", view=view, ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(tempvoice(bot))
