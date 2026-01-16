from bot import Bot
from services_folder.hlpr_logging import logger

async def sync_local_slash(bot: Bot, guild):
    try:
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logger.debug(f"✅ Все локальные слэш-команды синхронизованы для {guild}")
        return synced
    except Exception as e:
        logger.error(f"Ошибка при sync_local_slash: {e}")
        return None

async def clear_local_slash(bot: Bot, guild):
    try:
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
        logger.debug("✅ Все локальные слэш-команды удалены")
        return True
    except Exception as e:
        logger.error(f"Ошибка при clear_local_slash: {e}")
        return False
