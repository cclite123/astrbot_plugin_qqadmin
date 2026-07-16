from __future__ import annotations

from enum import IntEnum

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .config import PluginConfig
from .data import QQAdminDB
from .utils import get_ats


class PermLevel(IntEnum):
    """
    定义用户的权限等级。数字越小，权限越高。
    保留 OWNER/ADMIN/MEMBER 用于 Bot 群内角色检查。
    """

    SUPERUSER = 0
    OWNER = 1
    ADMIN = 2
    HIGH = 3
    MEMBER = 4
    UNKNOWN = 5

    def __str__(self):
        return {
            PermLevel.SUPERUSER: "超管",
            PermLevel.OWNER: "群主",
            PermLevel.ADMIN: "管理员",
            PermLevel.HIGH: "高等级成员",
            PermLevel.MEMBER: "成员",
            PermLevel.UNKNOWN: "未知/无权限",
        }.get(self, "未知/无权限")

    @classmethod
    def from_str(cls, perm_str: str):
        mapping = {
            "超管": cls.SUPERUSER,
            "群主": cls.OWNER,
            "管理员": cls.ADMIN,
            "高等级成员": cls.HIGH,
            "成员": cls.MEMBER,
            "未知": cls.UNKNOWN,
            "无权限": cls.UNKNOWN,
        }
        return mapping.get(perm_str, cls.UNKNOWN)


class PermissionManager:
    _initialized = False

    def __init__(self):
        self.cfg: PluginConfig | None = None
        self.db: QQAdminDB | None = None

    def lazy_init(self, config: PluginConfig, db: QQAdminDB):
        if self._initialized:
            raise RuntimeError("PermissionManager already initialized")
        self.cfg = config
        self.db = db
        self._initialized = True

    def refresh(self, config: PluginConfig, db: QQAdminDB | None = None):
        self.cfg = config
        if db is not None:
            self.db = db
        self._initialized = True

    async def get_perm_level(
        self, event: AiocqhttpMessageEvent, user_id: str | int
    ) -> PermLevel:
        group_id = event.get_group_id()
        if int(group_id) == 0 or int(user_id) == 0:
            return PermLevel.UNKNOWN
        if self.cfg and str(user_id) in self.cfg.super_admins:
            return PermLevel.SUPERUSER
        try:
            info = await event.bot.get_group_member_info(
                group_id=int(group_id), user_id=int(user_id), no_cache=True
            )
        except Exception:
            return PermLevel.UNKNOWN
        role = info.get("role", "unknown")
        level = int(info.get("level", 0))
        group_config = (
            self.db.get_group_snapshot(group_id)
            if self.db is not None
            else {"level_threshold": self.cfg.level_threshold if self.cfg else 50}
        )
        level_threshold = int(group_config.get("level_threshold", 50))
        match role:
            case "owner":
                return PermLevel.OWNER
            case "admin":
                return PermLevel.ADMIN
            case "member":
                return PermLevel.HIGH if level >= level_threshold else PermLevel.MEMBER
            case _:
                return PermLevel.UNKNOWN

    async def perm_block(
        self,
        event: AiocqhttpMessageEvent,
        bot_perm: PermLevel,
        check_at: bool = True,
    ) -> str | None:
        """检查 Bot 权限和 @目标权限（用户超管权限由命令分发器单独检查）"""
        bot_level = await self.get_perm_level(event, user_id=event.get_self_id())
        if bot_level > bot_perm:
            return f"我没{bot_perm}权限"

        if check_at:
            for at_id in get_ats(event):
                at_level = await self.get_perm_level(event, user_id=at_id)
                if bot_level >= at_level:
                    return f"我动不了{at_level}"

        return None


perm_manager = PermissionManager()
