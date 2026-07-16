import asyncio
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from astrbot import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.event_message_type import EventMessageType

from .config import PluginConfig
from .core import (
    BanproHandle,
    CurfewHandle,
    FileHandle,
    JoinHandle,
    LLMHandle,
    MemberHandle,
    NormalHandle,
    NoticeHandle,
)
from .data import QQAdminDB
from .group_info_cache import QQGroupInfoCache
from .permission import (
    PermLevel,
    perm_manager,
)
from .utils import print_logo
from .web import QQAdminWebController


@dataclass
class CommandEntry:
    """命令注册表条目"""

    name: str
    handler: Callable
    aliases: set[str] = field(default_factory=set)
    bot_perm: PermLevel = PermLevel.ADMIN
    check_at: bool = True
    args_spec: tuple = ()


class QQAdminPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.cfg = PluginConfig(config, context)
        self.db = QQAdminDB(self.cfg)
        self.db.default_cfg = self.cfg.build_group_default_config()
        self.group_cache = QQGroupInfoCache(context, self.db)
        self.normal = NormalHandle(self.cfg, self.db)
        self.notice = NoticeHandle(self, self.cfg)
        self.banpro = BanproHandle(self.cfg, self.db)
        self.join = JoinHandle(self.cfg, self.db)
        self.member = MemberHandle(self)
        self.file = FileHandle(self.cfg)
        self.curfew = CurfewHandle(self.context, self.cfg)
        self.llm = LLMHandle(self.context, self.cfg, self.db)
        self.web = QQAdminWebController(context, self.cfg, self.db, self.group_cache)
        self.web.register_routes()

        self._commands: dict[str, CommandEntry] = {}
        self._build_command_table()

    async def initialize(self):
        await self.db.init()
        task = asyncio.create_task(self.curfew.initialize())
        task.add_done_callback(self._log_task_exception)
        perm_manager.lazy_init(self.cfg, self.db)
        if not self.cfg.super_admins:
            logger.warning(
                "[QQAdmin] 超级管理员列表为空，所有命令将无法执行！"
                "请在配置中添加 super_admins"
            )
        if random.random() < 0.01:
            print_logo()

    @filter.on_platform_loaded()
    async def on_platform_loaded(self):
        """平台加载完成时"""
        if not self.curfew.curfew_managers:
            task = asyncio.create_task(self.curfew.initialize())
            task.add_done_callback(self._log_task_exception)

    # ========== 命令注册表 ==========

    @staticmethod
    def _log_task_exception(task: asyncio.Task):
        """后台任务异常回调"""
        if task.cancelled():
            return
        if exc := task.exception():
            logger.error(f"[QQAdmin] 后台任务异常: {exc}", exc_info=exc)

    def _build_command_table(self):
        """构建命令名 -> CommandEntry 的查找表"""
        entries = [
            # === NormalHandle 群管理 ===
            CommandEntry("禁言", self.normal.set_group_ban,
                         args_spec=("int", "ban_time")),
            CommandEntry("禁我", self.normal.set_group_ban_me,
                         args_spec=("int", "ban_time")),
            CommandEntry("解禁", self.normal.cancel_group_ban),
            CommandEntry("开启全禁", self.normal.set_group_whole_ban,
                         aliases={"全员禁言", "开启全员禁言"}),
            CommandEntry("关闭全禁", self.normal.cancel_group_whole_ban,
                         aliases={"关闭全员禁言"}),
            CommandEntry("改名", self.normal.set_group_card,
                         args_spec=("str", "target_card")),
            CommandEntry("改我", self.normal.set_group_card_me,
                         args_spec=("str", "target_card")),
            CommandEntry("头衔", self.normal.set_group_special_title,
                         bot_perm=PermLevel.OWNER,
                         args_spec=("str", "new_title")),
            CommandEntry("申请头衔", self.normal.set_group_special_title_me,
                         aliases={"我要头衔"},
                         bot_perm=PermLevel.OWNER,
                         args_spec=("str", "new_title")),
            CommandEntry("踢了", self.normal.set_group_kick),
            CommandEntry("拉黑", self.normal.set_group_block),
            CommandEntry("上管", self.normal.set_group_admin,
                         aliases={"设置管理员"},
                         bot_perm=PermLevel.OWNER, check_at=False),
            CommandEntry("下管", self.normal.cancel_group_admin,
                         aliases={"取消管理员"},
                         bot_perm=PermLevel.OWNER, check_at=False),
            CommandEntry("设精", self.normal.set_essence_msg,
                         aliases={"设为精华"}),
            CommandEntry("移精", self.normal.delete_essence_msg,
                         aliases={"移除精华"}),
            CommandEntry("查看群精华", self.normal.get_essence_msg_list,
                         aliases={"群精华"}),
            CommandEntry("设置群头像", self.normal.set_group_portrait),
            CommandEntry("设置群名", self.normal.set_group_name,
                         args_spec=("str", "group_name")),
            CommandEntry("撤回", self.normal.delete_msg,
                         bot_perm=PermLevel.MEMBER),

            # === NoticeHandle 公告 ===
            CommandEntry("发布群公告", self.notice.send_group_notice),
            CommandEntry("查看群公告", self.notice.get_group_notice,
                         bot_perm=PermLevel.MEMBER),

            # === BanproHandle 增强管控 ===
            CommandEntry("禁词禁言", self.banpro.handle_word_ban_time,
                         args_spec=("int", "time")),
            CommandEntry("设置禁词", self.banpro.handle_ban_words,
                         aliases={"禁词", "违禁词"}),
            CommandEntry("内置禁词", self.banpro.handle_builtin_ban_words,
                         args_spec=("mode", "mode_str")),
            CommandEntry("刷屏禁言", self.banpro.handle_spamming_ban_time,
                         args_spec=("int", "time")),
            CommandEntry("投票禁言", self.banpro.start_vote_mute,
                         args_spec=("int", "ban_time")),
            CommandEntry("赞同禁言",
                         lambda e: self.banpro.vote_mute(e, agree=True),
                         bot_perm=PermLevel.MEMBER),
            CommandEntry("反对禁言",
                         lambda e: self.banpro.vote_mute(e, agree=False),
                         bot_perm=PermLevel.MEMBER),

            # === CurfewHandle 宵禁 ===
            CommandEntry("开启宵禁", self.curfew.start_curfew,
                         args_spec=("two_str", "input_start_time", "input_end_time")),
            CommandEntry("关闭宵禁", self.curfew.stop_curfew),

            # === JoinHandle 进群管理 ===
            CommandEntry("进群审核", self.join.handle_join_review,
                         args_spec=("mode", "mode_str")),
            CommandEntry("进群白词", self.join.handle_accept_words),
            CommandEntry("进群黑词", self.join.handle_reject_words),
            CommandEntry("未命中驳回", self.join.handle_no_match_reject,
                         args_spec=("mode", "mode_str")),
            CommandEntry("进群等级", self.join.handle_join_min_level,
                         args_spec=("int", "level")),
            CommandEntry("进群次数", self.join.handle_join_max_time,
                         args_spec=("int", "time")),
            CommandEntry("进群黑名单", self.join.handle_block_ids),
            CommandEntry("批准", self._agree_add_group,
                         aliases={"同意进群"},
                         args_spec=("str", "extra")),
            CommandEntry("驳回", self._refuse_add_group,
                         aliases={"拒绝进群", "不批准"},
                         args_spec=("str", "extra")),
            CommandEntry("进群禁言", self.join.handle_join_ban,
                         args_spec=("int", "time")),
            CommandEntry("进群欢迎", self.join.handle_join_welcome,
                         bot_perm=PermLevel.MEMBER),
            CommandEntry("退群通知", self.join.handle_leave_notify,
                         bot_perm=PermLevel.MEMBER,
                         args_spec=("mode", "mode_str")),
            CommandEntry("退群拉黑", self.join.handle_leave_block,
                         args_spec=("mode", "mode_str")),

            # === MemberHandle 群成员工具 ===
            CommandEntry("群友信息", self.member.get_group_member_list,
                         bot_perm=PermLevel.MEMBER),
            CommandEntry("清理群友", self.member.clear_group_member,
                         args_spec=("two_int", "inactive_days", "under_level", 30, 10)),

            # === FileHandle 群文件 ===
            CommandEntry("上传群文件", self._upload_group_file,
                         bot_perm=PermLevel.MEMBER,
                         args_spec=("str", "path")),
            CommandEntry("删除群文件", self._delete_group_file,
                         args_spec=("str", "path")),
            CommandEntry("查看群文件", self.file.view_group_file,
                         bot_perm=PermLevel.MEMBER,
                         args_spec=("str", "path")),

            # === LLMHandle ===
            CommandEntry("取名", self.llm.ai_set_card,
                         bot_perm=PermLevel.MEMBER, check_at=False),
            CommandEntry("取头衔", self.llm.ai_set_title,
                         bot_perm=PermLevel.MEMBER, check_at=False),

            # === 配置管理（插件自身方法，使用 yield） ===
            CommandEntry("群管配置", self._cmd_set_config,
                         aliases={"群管设置"},
                         bot_perm=PermLevel.MEMBER, check_at=False),
            CommandEntry("群管重置", self._cmd_reset_config,
                         bot_perm=PermLevel.MEMBER, check_at=False,
                         args_spec=("str", "group_id")),
        ]

        for entry in entries:
            self._commands[entry.name] = entry
            for alias in entry.aliases:
                self._commands[alias] = entry

    # ========== 命令分发器 ==========

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_command(self, event: AiocqhttpMessageEvent):
        """中央命令分发器：解析命令名 -> 超管检查 -> Bot权限检查 -> 执行"""
        text = event.message_str.strip()
        if not text:
            return

        parts = text.split(maxsplit=1)
        cmd_name = parts[0]
        args_str = parts[1].strip() if len(parts) > 1 else ""

        entry = self._commands.get(cmd_name)
        if entry is None:
            return  # 非命令消息，忽略

        # 超管检查（静默拒绝）
        if str(event.get_sender_id()) not in self.cfg.super_admins:
            return

        # Bot 权限检查
        result = await perm_manager.perm_block(
            event, bot_perm=entry.bot_perm, check_at=entry.check_at
        )
        if result:
            await event.send(event.plain_result(result))
            event.stop_event()
            return

        # 解析参数
        kwargs = self._parse_args(entry.args_spec, args_str)

        # 执行处理器（兼容普通 async 和 async generator）
        handler = entry.handler
        coro = handler(event, **kwargs) if kwargs else handler(event)
        try:
            if hasattr(coro, "__aiter__"):
                async for item in coro:
                    if item is not None:
                        await event.send(item)
            else:
                await coro
        except Exception as e:
            logger.error(
                f"[QQAdmin] 命令 '{cmd_name}' 执行失败: {e}", exc_info=True
            )
            await event.send(event.plain_result(f"命令执行出错：{e}"))
        finally:
            event.stop_event()

    @staticmethod
    def _parse_args(args_spec: tuple, args_str: str) -> dict:
        """根据 args_spec 解析参数字符串"""
        if not args_spec:
            return {}

        kind = args_spec[0]
        tokens = args_str.split()

        if kind == "int":
            name = args_spec[1]
            if not tokens:
                return {name: None}
            try:
                return {name: int(tokens[0])}
            except ValueError:
                return {name: None}

        if kind == "str":
            name = args_spec[1]
            return {name: args_str.strip() or None}

        if kind == "mode":
            name = args_spec[1]
            return {name: tokens[0] if tokens else None}

        if kind == "two_str":
            name1, name2 = args_spec[1], args_spec[2]
            parts = args_str.split(maxsplit=1)
            return {
                name1: parts[0] if len(parts) > 0 else None,
                name2: parts[1] if len(parts) > 1 else None,
            }

        if kind == "two_int":
            name1, name2 = args_spec[1], args_spec[2]
            default1, default2 = args_spec[3], args_spec[4]

            def parse_token(tok, default):
                try:
                    return int(tok)
                except (ValueError, TypeError):
                    return default

            return {
                name1: parse_token(tokens[0], default1) if len(tokens) > 0 else default1,
                name2: parse_token(tokens[1], default2) if len(tokens) > 1 else default2,
            }

        return {}

    # ========== 包装方法（处理 None → 默认值转换） ==========

    async def _upload_group_file(self, event, path=None):
        """上传群文件 — path 转 str 保持与原逻辑一致"""
        await self.file.upload_group_file(event, str(path))

    async def _delete_group_file(self, event, path=None):
        """删除群文件 — path 转 str 保持与原逻辑一致"""
        await self.file.delete_group_file(event, str(path))

    async def _agree_add_group(self, event, extra=None):
        """批准进群 — extra 默认空串"""
        await self.join.agree_add_group(event, extra or "")

    async def _refuse_add_group(self, event, extra=None):
        """驳回进群 — extra 默认空串"""
        await self.join.refuse_add_group(event, extra or "")

    # ========== 配置管理命令 ==========

    async def _cmd_set_config(self, event: AiocqhttpMessageEvent):
        """群管配置 <群号 | 留空> <配置串>"""
        raw: str = event.message_str.partition(" ")[2].strip()
        if not raw:  # 空串，仅查询
            gid = event.get_group_id()
            config_str = await self.db.export_cn_lines(gid)
            yield event.plain_result(f"【群管配置】\n{config_str}")
            return

        # 正则：^(\d+)\s+(.+)  捕获"数字 + 空格 + 剩余串"
        m = re.match(r"(\d+)\s+(.+)", raw)
        if m:
            gid = str(m.group(1))
            arg = m.group(2)
        else:
            gid = event.get_group_id()
            arg = raw

        # 更新配置
        await self.db.import_cn_lines(gid, arg)
        config_str = await self.db.export_cn_lines(gid)
        yield event.plain_result(f"【群管配置】更新:\n{config_str}")

    async def _cmd_reset_config(self, event: AiocqhttpMessageEvent, group_id=None):
        """群管重置 <群号 | all>"""
        gid = group_id or event.get_group_id()
        if gid == "all":
            await self.db.reset_to_default()
            yield event.plain_result("已重置所有群的群管配置")
        else:
            await self.db.reset_to_default(str(gid))
            yield event.plain_result("已重置本群的群管配置")

    # ========== 自动监听器 ==========

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_ban_words(self, event: AiocqhttpMessageEvent):
        """自动检测违禁词，撤回并禁言"""
        if (
            not event.is_admin()
            and str(event.get_sender_id()) not in self.cfg.super_admins
        ):
            await self.banpro.on_ban_words(event)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def spamming_ban(self, event: AiocqhttpMessageEvent):
        """刷屏检测与禁言"""
        await self.banpro.spamming_ban(event)

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    @filter.event_message_type(EventMessageType.GROUP_MESSAGE)
    async def event_monitoring(self, event: AiocqhttpMessageEvent):
        """监听进群/退群事件"""
        await self.join.event_monitoring(event)

    @filter.llm_tool()  # type: ignore
    async def llm_set_group_ban(
        self, event: AiocqhttpMessageEvent, user_id: str, duration: int
    ):
        """
        在群聊中禁言某用户。被禁言的用户在禁言期间将无法发送消息。
        Args:
            user_id(string): 要禁言的用户的QQ账号，必定为一串数字，如(12345678)
            duration(number): 禁言持续时间（秒），范围为0~86400, 0表示取消禁言
        """
        try:
            await event.bot.set_group_ban(
                group_id=int(event.get_group_id()),
                user_id=int(user_id),
                duration=duration,
            )
            logger.info(
                f"用户：{user_id}在群聊中被：{event.get_sender_name()}执行禁言{duration}秒"
            )
            event.stop_event()
            yield
        except Exception as e:
            logger.error(f"禁言用户 {user_id} 失败: {e}")
            yield

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await self.curfew.stop_all_tasks()
        await self.db.close()
        logger.info("插件 astrbot_plugin_QQAdmin 已优雅关闭")
