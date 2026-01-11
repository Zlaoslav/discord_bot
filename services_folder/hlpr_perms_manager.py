"""
Система управления правами Discord бота.
Права хранятся в JSON файле perms_data.json и могут изменяться командами.

Иерархия ролей (от высшей к низшей):
1. HOST - абсолютная власть, даёт все права включая рестарт/выключение бота
2. OWNER - владелец сервера, может всё кроме управления HOST и PERMSMANAGER
3. PERMSMANAGER (админ) - может менять права других (кроме HOST, OWNER, PERMSMANAGER)

Независимые роли (не наследуются от иерархии):
- SOUNDPAD - доступ к soundpad
- JOIN - право присоединиться к голосовому каналу
- LEAVE - право отключиться от голосового канала

Доступ к независимым ролям можно получить от HOST или OWNER.
"""

import json
from pathlib import Path
from typing import Set, List, Dict, Optional
from enum import Enum

__all__ = [
    "PermRole",
    "has_perm",
    "get_user_roles",
    "add_perm",
    "remove_perm",
    "init_perms",
    "can_manage_role",
    "get_hierarchy_level",
    "get_role_description",
    "INDEPENDENT_ROLES"
]
# Путь к файлу с правами
PERMS_FILE = Path(__file__).parent.parent / "configs_folder" / "perms_data.json"


class PermRole(Enum):
    """Роли прав."""
    # Иерархические роли
    HOST = "host"
    OWNER = "owner"
    PERMSMANAGER = "permsmanager"
    MODERATOR = "moderator"
    # Независимые роли
    CUSTOMPLAY = "customplay"
    SOUNDPAD = "soundpad"
    JOIN = "join"
    LEAVE = "leave"


# Иерархические роли (от высшей к низшей)
HIERARCHY_ROLES = [
    PermRole.HOST,
    PermRole.OWNER,
    PermRole.PERMSMANAGER,
    PermRole.MODERATOR
]

# Независимые роли
INDEPENDENT_ROLES = {
    PermRole.CUSTOMPLAY,
    PermRole.SOUNDPAD,
    PermRole.JOIN,
    PermRole.LEAVE,
}

# Все роли
ALL_ROLES = set(PermRole)

# Роли, которые нельзя менять ни при каких условиях
PROTECTED_ROLES = {PermRole.HOST, PermRole.OWNER, PermRole.PERMSMANAGER}


def _load_perms() -> Dict[int, Set[PermRole]]:
    """Загружает права из JSON файла."""
    if not PERMS_FILE.exists():
        return {}
    
    try:
        with open(PERMS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Конвертируем строки обратно в enum
        result = {}
        for user_id_str, roles in data.items():
            user_id = int(user_id_str)
            result[user_id] = {PermRole(role) for role in roles if role in [r.value for r in PermRole]}
        
        return result
    except (json.JSONDecodeError, IOError, ValueError):
        return {}


def _save_perms(perms: Dict[int, Set[PermRole]]) -> None:
    """Сохраняет права в JSON файл."""
    data = {
        str(user_id): sorted([role.value for role in roles])
        for user_id, roles in perms.items()
        if roles  # Не сохраняем пустые записи
    }
    
    with open(PERMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_hierarchy_level(roles: Set[PermRole]) -> int:
    """
    Возвращает уровень иерархии набора ролей.
    0 = HOST (высший), 1 = OWNER, 2 = PERMSMANAGER
    Возвращает 999 если нет иерархических ролей.
    """
    hierarchy_roles_user = [r for r in roles if r in HIERARCHY_ROLES]
    if not hierarchy_roles_user:
        return 999
    
    return min(HIERARCHY_ROLES.index(r) for r in hierarchy_roles_user)


def has_perm(user_id: int, required_role: PermRole) -> bool:
    """
    Проверяет, есть ли у пользователя требуемое право.
    
    Логика:
    - Если требуемая роль иерархическая: проверяем, есть ли роль на том же уровне или выше
    - Если требуемая роль независимая: проверяем наличие роли ИЛИ роли HOST/OWNER
    """
    perms = _load_perms()
    user_roles = perms.get(user_id, set())
    
    if not user_roles:
        return False
    
    # Если требуемая роль иерархическая
    if required_role in HIERARCHY_ROLES:
        required_idx = HIERARCHY_ROLES.index(required_role)
        # Проверяем, есть ли у пользователя роль с равным или более высоким уровнем
        for role in user_roles:
            if role in HIERARCHY_ROLES:
                role_idx = HIERARCHY_ROLES.index(role)
                if role_idx <= required_idx:
                    return True
        return False
    
    # Если требуемая роль независимая
    if required_role in INDEPENDENT_ROLES:
        # У пользователя есть сама роль
        if required_role in user_roles:
            return True
        # ИЛИ у пользователя есть HOST или OWNER
        if PermRole.HOST in user_roles or PermRole.OWNER in user_roles:
            return True
        return False
    
    return False


def get_user_roles(user_id: int) -> Set[PermRole]:
    """Возвращает все роли пользователя."""
    perms = _load_perms()
    return perms.get(user_id, set())


def add_perm(user_id: int, role: PermRole) -> bool:
    """
    Добавляет роль пользователю.
    Возвращает True если успешно, False если уже есть.
    """
    perms = _load_perms()
    if user_id not in perms:
        perms[user_id] = set()
    
    if role in perms[user_id]:
        return False
    
    perms[user_id].add(role)
    _save_perms(perms)
    return True


def remove_perm(user_id: int, role: PermRole) -> bool:
    """
    Удаляет роль пользователя.
    Возвращает True если успешно, False если нет такой роли или она защищена.
    """
    if role in PROTECTED_ROLES:
        return False
    
    perms = _load_perms()
    if user_id not in perms or role not in perms[user_id]:
        return False
    
    perms[user_id].remove(role)
    if not perms[user_id]:
        del perms[user_id]
    
    _save_perms(perms)
    return True


def set_user_perms(user_id: int, roles: Set[PermRole]) -> None:
    """Устанавливает все роли для пользователя."""
    perms = _load_perms()
    if roles:
        perms[user_id] = roles
    elif user_id in perms:
        del perms[user_id]
    
    _save_perms(perms)


def get_all_users_with_role(role: PermRole) -> List[int]:
    """Возвращает список ID всех пользователей с данной ролью."""
    perms = _load_perms()
    result = []
    
    for user_id, roles in perms.items():
        if role in roles:
            result.append(user_id)
    
    return result


def get_hierarchy_level(user_id: int) -> int:
    """
    Возвращает уровень иерархии пользователя.
    0 = HOST (высший), 1 = OWNER, 2 = PERMSMANAGER.
    Если нет иерархических ролей, возвращает 999.
    """
    roles = get_user_roles(user_id)
    return _get_hierarchy_level(roles)


def can_manage_role(manager_id: int, target_id: int, role: PermRole) -> tuple[bool, str]:
    """
    Проверяет, может ли manager_id менять роль target_id для role.
    Возвращает (может_ли, сообщение_об_ошибке).
    
    Правила:
    - Защищённые роли (HOST, OWNER, PERMSMANAGER) нельзя менять вообще
    - Manager должен иметь PERMSMANAGER или выше
    - Manager не может менять себе роли
    - Manager может менять только независимые роли (SOUNDPAD, JOIN, LEAVE)
    """
    # Защищённые роли нельзя менять вообще
    if role in PROTECTED_ROLES:
        return False, f"Роль `{role.value}` защищена и не может быть изменена."
    
    # Manager должен иметь PERMSMANAGER или выше
    if not has_perm(manager_id, PermRole.PERMSMANAGER):
        return False, "У вас нет прав на управление правами. Нужна роль `permsmanager` или выше."
    
    # Manager не может менять себе права
    if manager_id == target_id:
        return False, "Вы не можете менять свои собственные права."
    
    # Manager может менять только независимые роли
    if role not in INDEPENDENT_ROLES:
        return False, f"Можно менять только роли: {', '.join(r.value for r in INDEPENDENT_ROLES)}."
    
    # Manager не может давать роли выше своего уровня
    manager_level = get_hierarchy_level(manager_id)
    # Для независимых ролей проверяем, что manager хотя бы HOST или OWNER
    if manager_level > HIERARCHY_ROLES.index(PermRole.OWNER):
        return False, "Только владельцы и выше могут управлять этими правами."
    
    return True, ""


def get_role_description(role: PermRole) -> str:
    """Возвращает описание роли."""
    descriptions = {
        PermRole.HOST: "🔴 Роль хоста, если её вам выдали значит Slavik вам ОЧЕНЬ доверяет, позволяет использовать любые команды, включая eval()",
        PermRole.OWNER: "🟠 Владелец, все права которые не могут повлиять на работу бота, так же если вам её выдали значит вам доверяют",
        PermRole.PERMSMANAGER: "🟡 Админ, может менять права других",
        PermRole.MODERATOR: "🔵 Типо модератор да он крутой да да да ",
        PermRole.CUSTOMPLAY: "🎵 Доступ к /play /stop /skip",
        PermRole.SOUNDPAD: "🎵 Доступ к /soundpad",
        PermRole.JOIN: "➡️ Право присоединиться к войсу",
        PermRole.LEAVE: "⬅️ Право отключиться от войса",
    }
    return descriptions.get(role, role.value)


# Инициализация: убедимся что OWNER есть
def init_perms(owner_id: int) -> None:
    """Инициализирует систему, добавляя owner если его нет."""
    perms = _load_perms()
    if owner_id not in perms or PermRole.OWNER not in perms.get(owner_id, set()):
        if owner_id not in perms:
            perms[owner_id] = set()
        perms[owner_id].add(PermRole.OWNER)
        _save_perms(perms)
