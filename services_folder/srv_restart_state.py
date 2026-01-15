import discord
import asyncio
import sys
import os
from services_folder.hlpr_logging import logger
from configs_folder.advanced_settings import OWNER_ID

async def notify_after_restart(bot):
    # вызывается из on_ready после того как бот залогинился
    channel_id = await bot.db.restart_state.pop_restart_channel()
    if not channel_id:
        return  # ничего не нужно делать

    # пытаемся найти канал и отправить сообщение
    try:

        ch = await bot.fetch_channel(channel_id)
    except Exception as e:
        logger.warning(f"Не удалось получить канал для уведомления о рестарте: {e}")
        return

    try:
        # проверяем права бота в канале
        perms = ch.permissions_for(guild.me if (guild := getattr(ch, "guild", None)) else bot.user)
        if not perms.send_messages:
            # если нельзя писать в канале — попытка DM владельцу
            owner = bot.get_user(OWNER_ID) or await bot.fetch_user(OWNER_ID)
            try:
                await owner.send(f"⚠ Не удалось отправить уведомление о рестарте в канал {channel_id} — нет прав.")
            except Exception:
                pass
            return

        await ch.send("✅ Бот успешно перезапущен.")
    except Exception as e:
        logger.warning(f"Ошибка при отправке уведомления о рестарте: {e}")

async def restart_process(bot, interaction_or_ctx=None):
    """
    Сохраняет канал (если interaction_or_ctx передан), отвечает пользователю и перезапускает процесс.
    Если передан interaction (slash) — отправляет response, если ctx (prefix) — использует ctx.send.
    """
    channel_id = None
    try:
        if hasattr(interaction_or_ctx, "channel") and hasattr(interaction_or_ctx, "response"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            try:
                await interaction_or_ctx.response.send_message("♻️ Перезапускаюсь...", ephemeral=True)
            except Exception as e:
                logger.debug(f"Не удалось отправить interaction.response: {e}")
        elif hasattr(interaction_or_ctx, "send") and hasattr(interaction_or_ctx, "author"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            try:
                await interaction_or_ctx.send("♻️ Перезапускаюсь...")
            except Exception as e:
                logger.debug(f"Не удалось отправить ctx.send: {e}")
    except Exception as e:
        logger.exception(f"Ошибка при подготовке ответа перед рестартом: {e}")

    try:
        await bot.db.restart_state.save_restart_channel(int(channel_id) if channel_id is not None else None)
    except Exception as e:
        logger.exception(f"Ошибка при сохранении channel_id в БД: {e}")

    await asyncio.sleep(1)

    try:
        # Закрываем бота
        await bot.close()
    except Exception as e:
        logger.debug(f"Ошибка при закрытии бота: {e}")

    # Небольшая пауза перед завершением
    await asyncio.sleep(0.5)

    # Завершаем процесс бота (start.py автоматически перезапустит его с обновлением файлов)
    logger.info("Завершение процесса для перезапуска...")
    sys.exit(0)
    await asyncio.sleep(10)
    logger.fatal("ЗАВЕРШЕНИЕ РАБОТЫ НЕ УСПЕШНО")
    os._exit(0)


async def quickrestart_process(bot, interaction_or_ctx=None):
    """
    Быстрый перезапуск без обновления файлов.
    Сохраняет канал (если interaction_or_ctx передан), отвечает пользователю и перезапускает процесс.
    Если передан interaction (slash) — отправляет response, если ctx (prefix) — использует ctx.send.
    """
    # определяем канал для уведомления:
    channel_id = None
    try:
        # interaction (app command)
        if hasattr(interaction_or_ctx, "channel") and hasattr(interaction_or_ctx, "response"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            await interaction_or_ctx.response.send_message("⚡ Быстрый перезапуск...", ephemeral=True)
        # ctx (prefix)
        elif hasattr(interaction_or_ctx, "send") and hasattr(interaction_or_ctx, "author"):
            channel_id = getattr(interaction_or_ctx, "restart_target", None) or interaction_or_ctx.channel.id
            await interaction_or_ctx.send("⚡ Быстрый перезапуск...")
    except Exception:
        pass

    # сохраняем в БД канал (может быть None)
    await bot.db.restart_state.save_restart_channel(int(channel_id) if channel_id is not None else None)

    # создаём флаг быстрого перезапуска
    quick_restart_flag = os.path.join(os.path.dirname(__file__), ".quick_restart")
    try:
        with open(quick_restart_flag, "w") as f:
            f.write("")
    except Exception as e:
        logger.debug(f"Не удалось создать флаг быстрого перезапуска: {e}")

    # небольшая пауза чтобы response/сообщение успели отправиться в сеть
    await asyncio.sleep(0.5)

    try:
        # Закрываем бота
        await bot.close()
    except Exception as e:
        logger.debug(f"Ошибка при закрытии бота: {e}")

    # Небольшая пауза перед завершением
    await asyncio.sleep(0.5)

    # Завершаем процесс бота (start.py перезапустит его БЕЗ обновления файлов)
    logger.info("Завершение процесса для быстрого перезапуска...")
    sys.exit(0)
    await asyncio.sleep(10)
    logger.fatal("ЗАВЕРШЕНИЕ РАБОТЫ НЕ УСПЕШНО")
    os._exit(0)
