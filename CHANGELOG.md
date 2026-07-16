# 更新日志

## v3.4.0

破坏性变更:

- 重构权限系统：移除旧的5级权限层级（超级管理员 > 群主 > 管理员 > 成员），改为"超级管理员/非超级管理员"二元模型。
- 新增 `super_admins` 配置项，独立于 AstrBot 的 `admins_id`。只有 `super_admins` 中配置的QQ号才能使用群管插件的所有指令。
- 移除 `perms` 配置项（旧权限映射表），不再需要按指令配置权限等级。
- 非超级管理员发送的指令消息会被静默忽略（不回复、不执行）。
- 移除 `core/enhance_handel.py`（未使用的遗留代码）。

新功能:

- 引入中央命令分发器：所有52条指令通过统一的 `on_command` 监听器处理，替代了原来的 `@filter.command()` 装饰器模式。
- 命令注册表（`CommandEntry` 数据类）支持别名、参数规范、Bot权限等级声明。
- 超级管理员免受违禁词检测和刷屏检测的自动处罚。

Bug修复:

- 修复 `handle_spamming_ban_time` 方法写入错误的数据库字段（`word_ban_time` → `spamming_ban_time`），刷屏禁言功能现已正常工作。
- 修复 `curfew_handle.py` 中 `client` 为 None 时宵禁初始化崩溃的问题。
- 命令分发器添加异常处理，handler 异常不再导致事件传播失控。
- 修复 `llm_handle.py` 中 API 响应缺少 `messages` 字段或返回空列表时的崩溃。
- 修复 `join_handle.py` 中引用消息解析在昵称含全角冒号时截断的问题。
- 为 `join_handle.py` 中多处 `db.get()` 调用添加默认值，防止返回 None 时 TypeError。
- 修复 `page_service.py` 中 `vote_ban` 子字段直接访问可能 KeyError 的问题。
- 移除 `utils.py` 中 HTTPS 降级为 HTTP 的不安全代码。
- 修复 `curfew_handle.py` 中使用已弃用的 `asyncio.get_event_loop()`。
- 统一 `main.py` 中 `EventMessageType` 的引用方式。
- 为 `normal_handle.py` 中8个缺少异常处理的方法添加 try/except。
- 修复 `normal_handle.py` 中的裸 `except:` 语句。

增强:

- 为 fire-and-forget 异步任务添加异常回调，避免静默丢失错误。
- 补充多处缺失的类型注解（`start_vote_mute`、`handle_leave_notify`、`handle_leave_block`、`view_group_file`）。
- 移除 `config.py` 中的死代码分支（`refresh_runtime_settings` 中永远不会触发的 `except ValueError`）。
- 更新 README.md 文档，准确反映当前权限模型和配置要求。

## v3.3.0

新功能:

- 引入一个 Web 设置页面（HTML/CSS/JS），用于浏览 QQ 群并编辑各群的管理配置，支持跟随默认模板。
- 暴露用于设置页面的 HTTP API，用来加载 schema/初始化数据、刷新群列表，以及获取/更新/重置群配置。
- 新增群信息缓存服务，用于从各适配器聚合 QQ 群元数据，并向插件提供统一且带缓存的视图。

增强:

- 优化 QQAdminDB，区分“跟随默认模板”的群记录与“显式配置”的群记录，提供规范化的群快照，并支持替换或重置群配置。
- 允许按群覆盖关键行为（随机封禁时间范围、投票封禁参数、LLM 消息窗口、权限阈值与映射、`admin_audit`），同时在 `PluginConfig` 中保留默认模板。
- 更新权限检查逻辑，从群配置而非全局配置中读取所需等级和阈值，并移除对私聊中执行受权限保护命令的支持。
- 调整入群、普通、banpro 和 LLM 相关的处理器，通过共享的群配置快照遵从各群的配置值。
- 改进 `PluginConfig` 的运行时处理，提供更安全的随机封禁时间解析，并增加用于构建默认群配置结构的构建器。
- 新增一个 Web 控制器，将插件专用路由注册到 AstrBot 上下文中，并统一 JSON 响应格式与错误处理。

文档:

- 添加一个简单的 CHANGELOG，记录在 v3.3.0 版本中引入 Web 前端的变更，同时更新Readme文档。

杂项:

- 将插件元数据版本升级至 v3.3.0，声明最低 AstrBot 版本要求，并移除旧的文本版 `ADMIN_HELP` 及其命令入口。
