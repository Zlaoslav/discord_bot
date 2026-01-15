from discord import Interaction as Type_Interaction
from services_folder.hlpr_logging import logger
import services_folder.hlpr_perms_manager as hlpr_perms_manager
from configs_folder.advanced_settings import MAX_LEVEL

def try_set_level_reward(
    bot,
    interaction : Type_Interaction,
    level : int
) -> str:
    if interaction.guild is None:
        return "Команда доступна только на сервере."
    if not hlpr_perms_manager.has_perm(interaction.user.id, hlpr_perms_manager.PermRole.OWNER):
        return "У вас недостаточно прав для этой команды." 
    if level <= 0 or level > MAX_LEVEL:
        return f"Уровень должен быть больше нуля и меньше {MAX_LEVEL}!"
    try:
        reward = reward.id or 0
        bot.db.level_rewards.set_reward(interaction.guild_id, level, reward)
        return f"Роль: <@&{reward}> назначенна наградой за уровень {level} успешно!"
    except Exception as e:
        logger.exception(f"Ошибка при сохранении награды за уровень: {e}")
        return f"Ошибка установки награды!"