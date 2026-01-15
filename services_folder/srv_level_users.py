from discord import Interaction as Type_Interaction
from services_folder.hlpr_logging import logger
import services_folder.hlpr_perms_manager as hlpr_perms_manager
from configs_folder.advanced_settings import MAX_LEVEL, USER_LEVEL_COOLDOWN

import random
import asyncio
import time
import threading


user_level_last_calls = {}
user_level_lock = threading.Lock()

def xp_to_level(bot, guild_id: int, user_id: int) -> int:
    """Конвертация опыта в уровень по формуле"""

    xp = bot.db.level_users.get_xp(guild_id, user_id)
    level = 0

    while True:
        next_level_xp = 25 * (level + 1) * (level + 2)
        if xp < next_level_xp or level >= MAX_LEVEL:
            break
        level += 1

    return level


def xp_left_to_next_level(bot, guild_id: int, user_id: int) -> int:
    """
    Возвращает количество опыта, которое осталось до следующего уровня.
    Если достигнут MAX_LEVEL — возвращает 0.
    """

    xp = bot.db.level_users.get_xp(guild_id, user_id)
    level = xp_to_level(bot, guild_id, user_id)

    if level >= MAX_LEVEL:
        return 0

    # XP, необходимый для достижения следующего уровня
    next_level_xp = 25 * (level + 1) * (level + 2)

    return max(0, next_level_xp - xp)


async def on_xp_added(bot, guild_id: int, user_id: int):
    try:
        new_level = xp_to_level(bot, guild_id, user_id)
        old_level = bot.db.level_users.get_user_level(guild_id, user_id)

        # если уровень изменился — сохраняем
        if new_level != old_level:
            bot.db.level_users.set_user_level(guild_id, user_id, new_level)

        guild = bot.get_guild(guild_id)
        if not guild:
            return

        member = guild.get_member(user_id)
        if not member:
            return

        rewards = bot.db.level_rewards.get_rewards(guild_id)  # список кортежей (уровень, role_id)
        # Сортируем по уровню, чтобы найти максимальный подходящий
        rewards_sorted = sorted(rewards, key=lambda x: x[0])

        # Определяем роль за максимальный уровень, которую должен иметь пользователь
        max_role_to_give = None
        for required_level, role_id in rewards_sorted:
            if new_level >= required_level:
                max_role_to_give = guild.get_role(role_id)

        # Убираем все роли за уровни, кроме максимальной
        for required_level, role_id in rewards:
            role = guild.get_role(role_id)
            if not role:
                continue
            if role in member.roles:
                if role != max_role_to_give:
                    try:
                        await member.remove_roles(role, reason="Removed old level role")
                    except Exception as e:
                        logger.warning(
                            f"Не удалось забрать роль {role_id} у пользователя {user_id}: {e}"
                        )
        gived_role = None
        # Выдаём роль за максимальный уровень, если её ещё нет
        if max_role_to_give and max_role_to_give not in member.roles:
            try:
                gived_role = max_role_to_give
                await member.add_roles(max_role_to_give, reason="Level reward")
            except Exception as e:
                logger.warning(
                    f"Не удалось выдать роль {max_role_to_give.id} пользователю {user_id}: {e}"
                )

        # уведомление о повышении уровня
        if new_level > old_level:
            ch_id = bot.db.level_alerts.get_level_alerts_channel(guild_id)
            if not ch_id:
                return

            try:
                ch = bot.get_channel(ch_id) or await bot.fetch_channel(ch_id)
                if gived_role:
                    await ch.send(
                        f"🎉 <@{user_id}> достиг уровня **{new_level}**! И получил роль {gived_role.name}!"
                    )
                else:
                    await ch.send(
                        f"🎉 <@{user_id}> достиг уровня **{new_level}**! Поздравляем!"
                    )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление: {e}")

    except Exception as e:
        logger.exception(f"Ошибка в on_xp_added: {e}")


def can_call(guild_id: int, user_id: int) -> bool:
    key = (guild_id, user_id)
    now = time.time()

    with user_level_lock:
        last_time = user_level_last_calls.get(key)
        if last_time and now - last_time < USER_LEVEL_COOLDOWN:
            return False

        user_level_last_calls[key] = now
        return True

def try_give_xp(bot,
    guild_id: int,
    user_id: int
    ):
    if not can_call(guild_id, user_id):
        return

    bot.db.level_users.add_xp(guild_id, user_id, random.randint(5, 10))
    # Проверяем асинхронно, повысился ли уровень и отправляем уведомление если нужно
    try:
        asyncio.create_task(on_xp_added(bot, guild_id, user_id))
    except Exception:
        pass