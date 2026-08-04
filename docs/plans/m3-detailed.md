# m3-detailed · M3.0–M3.12 L3 客服业务（步骤级详细计划）

> **写作基线**：M2.4 毕业时点（commit `014ec21`，301 测试全绿，2026-07-10）· 撰写 2026-07-10（Fable 5 交接工程）。
> **粒度**：接口级（plans/README §5）——模块边界、表结构、端点与帧形状给定；函数内细节由 M3.0 开工走查按 M2 实际落地细化。
> **权威序**（plans/README §2）：实际代码 > 00 §2.2 口径表 > 本计划 > 02/03/04 叙述。范围以 00 §7.1 各步骤行为权威，本计划不扩权。
> **本计划的特殊风险**：写作时 M2.5–M2.13 尚未交付，M3 依赖的三个 M2 挂点（locks/ContextBuilder/前置校验重跑）在本文只能引用**契约描述**，不能引用签名——一切标【开工核对】的条目在 M3.0 必须逐项 Read 真实源码后才许动手。
> **实际落地偏差（毕业回填 2026-07-28）**：M3.0–M3.12 全部落地、无步骤被砍；13 步 69 条偏差
> 逐步登记于头部实况块 #1–#14l（差异权威）；测试 553→**852**（+299，对 §5.2 预告 +134–204
> 上浮 95——各步名分逐条在案，主因=计划未列面：RLS 前置义务/语义锚双向 lint/受控缝契约钉/
> 帧词汇全表/校验回归钉子）；真实调用总账 <¥0.15（M3 口径内，各凭证可查）；
> L2"零修改"口径修正为"零行为修改+三处 additive 受控缝经拍板"（retrieval/precheck 生产接线/text_sink）。
>
> **M3.0 开工核对实况**（2026-07-24 执行 §0 全部 19 项；本块为差异权威登记，各步开工时按此修订对应章节，信任序=实际代码 > 本块 > 本计划正文）：
> 1. **基线**：HEAD `b0e438b`（复盘补丁五）、tag `m2-runtime` 在位、测试 **553**（=00 §6.3 时间线末笔）、工作区干净；alembic head 仍 `74da3bf5d6ab`（M2 后半程零新迁移——M3.1 新迁移 down_revision 指它）；retro-m2.md 存在已通读（0-3 ✅）。
> 2. **时点漂移（纯登记）**：EventType 现 **16 类**（M2.8 +guardrail_triggered、M2.10 +recovery_abandoned）；Settings 末字段现为 `recovery_limit`（M2.10 增恢复调度四字段），M3 新增字段接其后；AgentSpec 现 **9 字段**（M2.8 +`owned_values`+`entry_classifier`）——M3.8 装配须一并注入（owned_values 按**用户**、entry_classifier 按租户 config），§4.8 build_agent_spec 签名相应扩为含用户侧输入。
> 3. **0-4 锁实况**：`SessionLock` 协议 acquire/extend/release(session_id, owner_token, *, ttl_s=30.0)；`hold_session_lock(lock, sid, *, ttl_s=30.0, renew_interval_s=10.0)` **已是 async context manager**（§4.2"若未提供则包一层"分支不启用）；`SessionLockHeld` docstring 明写 M3.2 映射 409；生产组装唯一入口 `build_session_lock()`。**另**：`AgentRuntime` 内部租约被他副本持有同样抛 `SessionLockHeld`（runtime.py:330/387/501）——M3.2 统一 except 之即可，锁/租约两种占用同映射 409。
> 4. **0-5 槽位实况**：`MemoryProviderLike.fetch(*, tenant_id, user_id, query)` / `RetrievalProviderLike.search(*, tenant_id, query)`（**无 user_id**），返回 `Sequence[ScoredSnippet(text, score)]`；provider 返回已重排整条 snippet，**预算装填由 builder `_pack_snippets` 承担**——§4.5"适配成 callable 并裁进 retrieval_budget"收窄为纯形状适配（Retriever→ScoredSnippet 序列，不自行裁剪）；检索/记忆文本的不可信包裹在**适配器侧**做（`wrap_untrusted` source 约定已预留 "retrieval"/"memory"——guardrails.py:320-328；builder 冻结零改动）。**#42 实锚确认**（00 §10.1）：context.py:172/182 两处裸 await 无 C34 try——M3.5 接真 provider 前必修；修案二选一 M3.5 开工拍板：(a) L3 适配器内 try 包 provider 调用、异常返 `()` fail-open+留痕（L2 零改动，不破 M3 红线）；(b) 按 #42 原文改 context.py 加 try（动 L2 冻结面，需显式豁免）。
> 5. **0-6 前置校验挂点实况**：`PrecheckHook = Callable[[str, Mapping[str, Any]], Awaitable[str | None]]`（runtime.py:60，**(tool_name, args 快照)→None 通过/str 拒因**；注入位=`AgentRuntime(precheck=…)` 构造参）；否决**不终止**——veto 经 `_PRECHECK_VETO_TEMPLATE` 作为观察回填续跑（D19，runtime.py:517-519）。§4.9 设想的 `revalidate_refund(args, ctx)` 签名**不成立**（无 ToolContext）：身份重校验由 API 层构造 runtime 时闭包捕获会话身份，或 revalidator 按 approval.session_id 自查 sessions 行——M3.9 开工时按实况改 §4.9 设计。
> 6. **0-7 实况 / U8 定案**：`AgentRuntime.run(spec, session_id, user_input)` 未动；**user_message 由 loop 写**（loop.py:213-214，I5/D19）——§4.2 算法第 6 步走"绝不双写"分支：API 层只传原文进 run，**不开 EventWriter、不写任何事件**。T1 冲突实况：非 idle 起跑抛 RuntimeError（runtime.py:324-325 注释点名 M3.2 准入层先按 run_state 给业务提示）——M3.2 准入顺序=先读 run_state 分流（awaiting_approval 走准入规则），再调 run，残余竞态映射 409/提示。
> 7. **0-8 实况**：恢复单入口=`AgentRuntime.resume(spec, session_id, approval_id=None)`（非 None=审批分诊 `_resume_locked`；None=崩溃分诊 `_recover_locked`）；`approval_requested` 由 loop 挂起链路写（loop.py:534-564，含 ApprovalStore.create 生产调用方），`approval_decided/cancelled/expired` 由 `_resume_locked` 写；**审批单 expires_at = now + `LoopPolicy.approval_ttl_s`（默认 3600s，loop.py:538）**——§4.9"tenants.config 直读缺省 86400"不成立，正路=M3.8 装配时从租户 config 注入 `LoopPolicy(approval_ttl_s=…)`（spec.py:53-54 docstring 本就写明），种子值 M3.11 定；M3.9 reaper 到期扫描第 3 步的"终止路径"=对每单调 `resume(approval_id=该单)`——EXPIRED 分支（事件+CANCELLED 终止+T4 复位，runtime.py:544-559）现成，勿自造。**#44 实锚确认**：`_recover_locked` 全程不查审批单（approved 未 attach_event 的操作会被 `_DISCARDED_NOTE` 弃置）——修向=M3.8 ResumeHook 实现认领前先查"该会话 approved 且 event_id IS NULL"的单，有则改走 `resume(approval_id=X)`。
> 8. **0-9 workers 实况**：celery app=`aegis.workers.celery_app:celery_app`，任务模块**显式 include 点名**（M3.4 ingest / M3.9 审批扫描新模块必须加入 include 列表）；beat 现有唯一条目 `reap-expired-leases`→`aegis.workers.reaper.reap_expired_leases`（间隔 Settings.reaper_interval_s=30s）；worker 命令 `uv run celery -A aegis.workers.celery_app worker --pool=solo -l info`；`ResumeHook=(session_id, lease_owner, lease_generation)` 经 `register_resume_hook` 进程级注册（M3.8）；reaper 自建 NullPool **owner** 引擎（直读 settings.database_url）——M3.3 的 get_engine() 切 app 角色不影响 reaper，与 D3/D4 天然相容。
> 9. **0-10/0-11 实况**：Cassette.load/save（StopChunk 收尾防呆/四道白名单/原子落盘）、Recorder 当 gateway 传入自动分道、normalize_events（C31）——M3.11 照用，cassettes 现有 minimal_demo+long_dialog+adversarial×4+README（§6 登记表 L3 行待补）；`Guardrails.output_guard(*, system_prompt, tool_names, owned_values=()) → OutputGuard`，`feed(delta)->str / flush()->str / hit / final_check(full)`——"逐字符≡整段"不变量明写为 M3.10 逐帧前提（guardrails.py:403-411），句子级缓冲首字延迟代价在 M3.10 兑现（D14）。
> 10. **0-17/0-18**：PG/Redis 容器 healthy；pgvector 可用版本 **0.8.4**≥0.8.0 ✅ 但库内**未** CREATE EXTENSION（extversion 空）——M3.4 迁移首句负责（08 §8 #15 一致）；.env 存在且含 DASHSCOPE_API_KEY（值未读）；CI 步序 alembic 先于 pytest（ci.yml）——§4.3 CI 陷阱前提成立。
> 11. **分层契约实况**：pyproject 层列表现为 `[apps, workers, runtime, gateway, core]`（M2.10 已纳 workers 且 **apps 在 workers 之上**）——§1"现为 apps→runtime→gateway→core"过时；M3.1 目标层序成立且**必须**把 workers 升到 apps 之上（M3.4 workers.ingest 要 import apps.support.rag，现序下即违约），api 与 workers 同层独立的 import-linter 写法以实测语法为准（§4.1 表内 `"aegis.api : aegis.workers"` 的冒号写法待 M3.1 验证，正解疑为 `"aegis.api | aegis.workers"`）。依赖核实（B.1 成立）：fastapi/uvicorn/pyjwt/pgvector 均不在 pyproject；celery 已在（勿重复 add）。
> 12. **0-15**：#6/#7/#8/#13/#17–#22 归位不变；**00 §10.1 新增 #42（M3.5）/#43（M3.7）/#44（M3.8/M3.9）三条 M2 复盘候选挂 M3**（本计划写作时不存在）——#43 落点=§4.7 工具体内不变量追加契约条款：写工具"发出后传输型模糊错误"（连接重置等）不得以普通异常回 ERROR 引导重试，按超时语义处置（handler 内转 TimeoutError 交 X1 → RESULT_UNKNOWN，或 dict 话术引导查询确认），具体形状 M3.7 开工定。
> 13. **0-19**：P1–P7 已于 2026-07-24 会话呈报用户，拍板结果回填于本块之后与 00 §10.1。
> 14a. **M3.1 交付进度与偏差（进行中，逐份登记；收口时并入 00 §7.3 对账行）**：
>     **交付① ✅（2026-07-24，提交 `9e7e72d`，迁移 `6304edbb4760`，测试 553→561）**——tenancy 两表+TenantDirectory+种子起步版+env.py 注册。偏差两条：
>     ⑴ 测试文件落 `tests/test_tenancy.py`（根目录）非 §5.2 表写的 `tests/core/`——实况 core 模块测试均在 tests/ 根（test_config/test_tokens/test_locks 同例），沿用既有约定，§5.2 的 M3.1 行按此理解；
>     ⑵ AI 交付稿 mypy 缺陷一处：seed_demo 两常量省略注解，TENANTS 推断 `dict[str, object]`×USERS 推断 `dict[str, str]` 撞同名循环变量——dict 值类型不变性报 assignment 错；修=两常量显式 `list[dict[str, Any]]`（用户现场修复后提交）。
>     **交付② ✅（2026-07-24，提交 `3a41a50`，测试 561→577）**——api/auth.py（HS256 双密钥窗+require_roles 矩阵执行器）+api/main.py（create_app 工厂+/healthz）+config 四字段+mint_token.py（P7）+层契约五层化。偏差三条：
>     ⑶ §4.1 表内 import-linter 同层写法 `"aegis.api : aegis.workers"` **语义不对**——查证 import-linter 2.13 源码：`:`=同层可互 import（non-independent）、`|`=同层互不 import（independent）；我们要后者，实装用 `"aegis.api | aegis.workers"`；
>     ⑷ AI 交付稿测试密钥未按 RFC 7518 下限取值（19/12/20 字节），PyJWT 2.13 发 InsecureKeyLengthWarning 22 条——处置升级：auth.py 增 `_MIN_SECRET_BYTES=32` 硬检查（弱钥=配置错误 fail-loud，与空钥同路 ValueError），测试密钥全部加长并新增 `test_short_secret_is_config_error`；教训=涉密钥/长度类安全参数，交付稿按规范下限起步；
>     ⑸ 测试实增 16（预告区间 10–14 上浮 2：alg-none 与弱钥两条安全面加固），端点依赖用 Annotated 写法天然规避 ruff B008（无需 bugbear 豁免配置——§4.1 未预见 B 规则已启用的交互，落地方案更优）。
>     **交付③ ✅（2026-07-24，提交 `43db3a5`，测试 577→581）**——router.py `monthly_budget_resolver` 注入缝（`_resolve_monthly_budget` 三态：resolver 值/静态配置/None=读挂 fail-open）+ factory 注入 `TenantDirectory.monthly_budget`；#13/#22 就此闭合（00 §10.1 已翻转）。偏差一条：
>     ⑹ 测试并入 `tests/gateway/test_router.py` 既有预算闸门测试群（§5.2 原写独立文件 `test_budget_resolver.py`）——复用 make_gw/StubMeter/FakeProvider 替身不复制 harness；"resolver=None 落回静态"不变量由既有预算测试零改动全绿作证。
>     **交付④ ✅（2026-07-24，提交 `69b2e93`，测试 581→588）**——`GET /v1/usage`（U13：明细+模型/天/会话三聚合裸 SQL；operator 点名他租显式 403；create_app +session_factory 注入参）。偏差一条：
>     ⑺ 交付稿"Decimal→float 展示"认知错误：返回注解 `dict[str, Any]` 使 FastAPI 走 response_model→pydantic v2 序列化，Decimal 缺省编码为**精确小数字符串**（非 fastapi.encoders 直通路径的 float）——定案保留字符串契约（"钱不过 float"延伸到线上表示），测试改 Decimal 精确比较、usage.py docstring 同步修正。
> 14b. **M3.2 交付与偏差（✅ 2026-07-24，提交 `d2bd55d`，测试 588→600）**——ratelimit.py+chat.py+main 五注入参+config 两字段；四条偏差：
>     ⑻ **端点不自取锁**：§4.2 步骤④"端点持锁覆盖全程"不成立——M2.9 实况锁由 AgentRuntime._maybe_lock 内部持有，端点预取会自撞；定案=锁全权归 runtime，端点统一 except SessionLockHeld→409（同时覆盖锁占用与租约占用两信号）；except 阶梯顺序=SessionLockHeld→事实源三类（RuntimeError 子类）裸穿→裸 RuntimeError（T1 残余竞态）→409；
>     ⑼ 入站限流用 `try_take` 替代计划的 `wait_take(max_wait=0)`——语义等价且直接拿到 (verdict, wait) 二元组，Retry-After=Lua 桶真实提示非拍定常数；
>     ⑽ 矩阵 operator 列"—"落实为 403（`require_roles(USER, ADMIN)`）——02 §7.1 行义的机器执行，计划步骤未显式列；
>     ⑾ **交付稿缺陷（探针定位）**：ratelimit.py 沿用全仓 future-annotations 惯例 × 依赖工厂闭包引用=字符串注解反解失明，参数退化必填 query 全量 422（detail loc=["query","principal"]）；修=该文件弃 future import+头注说明；教训=**依赖工厂内层注解引用的名字必须模块全局可见，或该文件放弃 future annotations**；升 3.14 后全仓退役（00 §10.1 #45 已登记）；题 108 入库。#19 就此翻 ✅（首见建行+双匹配 404 已实装）。
> 14c. **M3.3 交付与偏差（进行中）**——**交付① ✅（2026-07-24，提交 `1c08806`，迁移 `c895f9007bf7`，测试 600→606）**：tenant_ctx.py（ContextVar+tenant_context+begin 钩子）+ db.py 双轨引擎（app=aegis_app+钩子 / owner=维护面 D4）+ config `database_url_app` + 手写迁移（角色幂等/GRANT 五连+DEFAULT PRIVILEGES/五表 ENABLE RLS+USING·WITH CHECK 双子句）+ tests/test_rls.py 六测（真提交独立引擎、前置自检、过滤式清理）。偏差三条：
>     ⑿ **D2 伪码 `exec_driver_sql+%s` 在 asyncpg 方言是语法错误**（探针实证 `syntax error at or near "%"`——exec_driver_sql 原样透传而 asyncpg 只认 $n）；定案=`text()` 具名绑定走编译层（方言无关），§4.3 钩子伪码以此为准；探针另证 set_config 第三参 true 事务级不残留（连接归池安全）；
>     ⒀ AI 测试稿裸 INSERT 缺列（lease_generation/recovery_count 的 default=0 在 ORM 层）——M3.1 陷阱清单原条自己踩（写侧变体），修=显式给全列；教训：**同一课两面：ORM default 既不帮裸 INSERT 也不帮裸 SELECT 断言**；
>     ⒁ 测试落 tests/ 根（core 惯例，同 ⑴）。**前置义务登记**：M3.4/M3.7 新表（documents/chunks/mock_orders/mock_write_ops）各自迁移必须 ENABLE RLS+策略（DEFAULT PRIVILEGES 只自动给 DML 授权，RLS 不隐式继承）；#18 Celery 侧 tenant_context 归 M3.4 ingest 任务体首行；**M2 演示/冒烟脚本 RLS 冲击**（smoke_agent_real/demo_hitl/kill9 等经 get_session_factory=app 角色、无上下文将被拦）——处置=随用随修（脚本首行 tenant_context 或换 owner 工厂），M5.4 排练统一过，本步不改（范围纪律）。
>     **交付② ✅ → M3.3 步收口（2026-07-24，提交 `d73e098`，测试 606→608）**：auth 验签即设 ContextVar（任务级生灭免 reset）+ usage `tenant_context(target)` 嵌套覆盖（RLS 下 admin 跨租户视图前提）+ seed/mint 切 owner（D4）。偏差一条：
>     ⒂ AI 测试稿断言粒度错——预设"四查询四次开会话"，实况 usage 端点**单会话单事务跑四查询**（factory 恰调一次、钩子恰开一枪）；红反向证实了会话粒度设计，修=断言 `["tenant-b"]`。**M3.3 账**：两交付 `1c08806`/`d73e098`，测试 600→608（+8=6/2，区间 6–10 内）；02 §7.2 两条点名集成测试绿；#18 请求路径+维护面 D4 已兑现（Celery 逐租户侧归 M3.4 ingest 任务体）；超时预案未启用（实际一天完成，RLS 未移 M4）。
>     **—— M3.1 步收口（2026-07-24）**：四交付全毕（`9e7e72d`/`3a41a50`/`43db3a5`/`69b2e93`），测试 553→588（+35，预告区间 22–32 上浮 3——安全面与聚合对账加固）；00 §7.3 对账行已登记；#13/#17/#21/#22 翻 ✅、#19 机制定案注记（实装随 M3.2）；08 §0.1 基线更 588/`69b2e93` + §0-bis M3.1 增量节 + §8 #14 翻转；深挖题 103–107 入库；02 §3 tenants 行补 config 治理句（#21 一段话）。下一步 M3.2（开工先执行本文件 §4.2 并按头部实况块 #3/#6 修正后的事实动手）。
> 14. **拍板结果（2026-07-24，用户裁决：七项全部按建议）**：**P1 长期记忆砍出 v1**（#20 ✅——M3.5 按"默认不含"形态执行、只做 RAG 检索接入；M3.8 装配 `ContextConfig(memory_budget=0)` 显式关层；01 §2/03 §3/02 §7.2/00 §7.1 M3.5 行叙事已同步修订；槽位列入 00 §10.3"接口已预留"档，升级路径=评审 C24 方案(a) `user_memories` 表+会话完成时 fast 档提炼写入）；**P2** HS256+`jwt_secret: SecretStr`+previous 双密钥窗轮换，TTL user 7200s / staff 28800s；**P3** `monthly_budget_resolver` 可选注入缝（None 落回现 int，既有测试零改动）+ TenantDirectory 60s 进程内 TTL 缓存（#22 同批裁决：短缓存、不上 Redis 计数器）；**P4** 不补 FK；**P5** RLS 覆盖=仅带 tenant_id 列的九表（events/messages/tool_invocations 取舍已登记 02 §7.2）；**P6** documents/chunks 按 §4.4 表设计（chunks 冗余 tenant_id、embedding 可空、UNIQUE(document_id, seq)）；**P7** `scripts/mint_token.py` 脚本签发、不做登录端点（取舍已登记 02 §7.1）。
> 14d. **M3.4 开工拍板与交付进度（进行中）**：切分四份（①数据层 / ②L1 受控缝 EmbeddingClient / ③切块+Celery 任务 / ④API 收口+全链路）；**计划外决策 A–E 全按建议拍板（2026-07-24 用户确认）**：
>     A=**API→Celery 入队不走 `.delay()`**——层契约 `aegis.api | aegis.workers` 互不 import（M3.1 五层化的直接后果，§4.4 伪码 `ingest_document.delay` 作废）；任务名常量落 `apps/support/rag/ingest.py`（api 与 workers 都在 apps 之上、两端同源 import），api 侧轻量 producer（`celery.Celery(broker=…)` 只发不收）`send_task`，经 create_app 注入 `enqueue`，另加测试钉两端任务名一致（wire 契约进 CI）；
>     B=**ingest 任务引擎走租户面**：每任务 NullPool 新引擎（reaper 3.2#8 跨 loop 教训）但连 `database_url_app` + `install_tenant_guard` + 任务体 `tenant_context(tenant_id)`——逐租户任务冒充租户过 RLS（D4 维护面的对偶；#18 在此闭合）；
>     C=worker 内 EmbeddingClient 两防炸：meter 绑任务局部 factory（`build_embedding_client(session_factory=None)` 参数化，缺省全局供 API 进程/M3.5）、limiter=None（批次串行天然限速；get_redis 单例跨 event loop 炸——M2.9 教训）；
>     D=`Settings.model_prices` 补 `"text-embedding-v4"` 演示值条目（防 compute_cost 记 0 刷 warning）；
>     E=重试两层：EmbeddingClient.embed 内有限退避（429 优先 Retry-After/timeout/5xx，读语义幂等；AuthError/BadRequest 裸抛不重试）+ Celery `max_retries=5` 指数退避兜长故障窗。
>     **交付① ✅（2026-07-24 验收完成，提交 `55ea421` 已推送，迁移 `7fe5de25a9ca`，测试 608→619 全绿实测；`\\d chunks` 实物核查：vector(1024)/hnsw 余弦/uq_chunks_document_seq/双 btree/tenant_isolation 双子句全在位）**——五件生产（两空 `__init__`+`rag/models.py`+手写迁移+env.py 注册）+ `tests/apps/test_rag_models.py` 5 测 + `tests/test_rls.py` M3.4 增量节 6 测；本交付起交付稿先过四路对抗校验（引用事实/ORM-迁移一致性/运行时真环境探针/范围协议，13 findings 消化后才发）。偏差三条：
>     ⒃ 测试落点与 §5.2 预告不同——§5.2 只列 split/embeddings/ingest_resume 三文件，实增 `test_rag_models.py` 与 `test_rls.py` 增量节（RLS 前置义务系 M3.3 之后新增、计划未预见）；交付①即 +11，M3.4 总数收口时以实数对账 §5.2 区间；
>     ⒄ **pgvector 0.5 实况修正**：`uv add pgvector` 装 0.5.x，读回纯 `list[float]`、零传递依赖（0.5 起去 numpy）——交付稿初版"ndarray"认知被真环境探针纠正，`embedding` 注解定为 `Mapped[list[float] | None]`（诚实形态）；
>     ⒅ 观察项（登记不改，范围纪律）：conftest `db_conn` 的 create_all 兜底自 M3.4 起无法自举全新裸库（vector 类型依赖扩展、扩展只在迁移里建），失败会被 except 吞成"PG 未启动"的误导 skip——本地纪律=先 `alembic upgrade head` 再 pytest（CI 步序天然满足）；候选处置=skip 文案补"或先跑迁移"，随后续步顺路。下一份=交付②（gateway/embeddings.py + record_embedding + build_embedding_client + 价目条目）。
>     **交付② ✅（2026-07-24 验收完成，提交 `f8fa77e` 已推送，测试 619→633 全绿实测）**——embeddings.py（162 行：EmbeddingClient 切批/index 归位/三重形状校验 fail-loud/重试壳复用 resilience 白名单与退避尺/计量 fail-open + EmbeddingMeterLike Protocol + EMBED_BATCH_SIZE=10）+ metering.record_embedding + factory（_price_table 提取 + build_embedding_client **双参数化 session_factory+client**）+ config 价目一行 + test_embeddings.py 14 测。**四路校验 17 findings 消化实录：major 一枚**——shared_client keep-alive 连接绑死创建时 event loop，Celery 每任务 asyncio.run 下隔次任务交替炸裸 RuntimeError（非 httpx 异常、绕过翻译阶梯；真实 HTTP 服务器探针实证）——修=工厂增 client 直通参，**交付③ worker 必须同时传任务局部 session_factory 与任务局部 AsyncClient（async 入口内建、finally aclose），且任务体在 tenant_context 内跑（否则计量 INSERT 被 usage_ledger WITH CHECK 拒、再被 fail-open 吞）——两条均为 ③ 开工核对项**。偏差登记（续 ⒅）：
>     ⒆ meter 参数 `MeteringRecorder`→`EmbeddingMeterLike` Protocol（router.MeterLike 同款先例，mypy 下测试替身不背真账本）；
>     ⒇ 计划签名外三处小改：payload 增 `encoding_format:"float"` 键（钉浮点数组形态）、限流速率用模块常量 _EMBED_RATE/BURST/MAX_WAIT（计划未给来源，M3.5 接线再议升 Settings）、`_price_table` 提取触 build_gateway 一行（同一表达式等价提取，防两份价目转换漂移——00 §2.1 第 5 条裁定为正当微改非顺手重构）；
>     (21) **拍板 F ✅（2026-07-24 用户同意）：embedding 用量计入租户月度预算**——month_spend 不分 tier、record_embedding 行 cached=False 天然入闸；口径=预算管真实花销（metering docstring 已载）；否决路径（tier 过滤）作废；
>     (22) 观察项（登记不改）：ruff 未配 `[tool.ruff.lint.isort] known-first-party=["aegis"]`，"新模块交付前测试文件 I001 假阳性"每次新建模块复发——候选一行配置随后续步顺路。
>     另两条 info 级加固已吸收进交付稿：`embed()` str 防呆（str 满足 Sequence[str]，按字符向量化是静默灾难）、`_record` 的 `or 0` 归一（上游 usage null 记零行不丢行）；"畸形 200 烧满重试预算"口径钉进 test_shape_mismatch（call_count==3）。测试 14 对预告 6–8 的上浮映射已在交付正文对账。下一份=交付③（rag/ingest.py split_text+任务名常量 + workers/ingest.py 断点续传 + celery include）。
>     **交付③ ✅（2026-07-24 验收完成，提交 `6e5f769` 已推送，迁移 `c28efda87e6a`，测试 633→648 全绿实测）**——rag/ingest.py（INGEST_TASK_NAME 两端同源 + split_text 三级降级：段落聚合/句界/硬切窗，overlap 种子"装不下即丢"不变量）+ workers/ingest.py（薄同步壳+ingest_once 四步：PROCESSING→切块幂等（count==0 才切+UNIQUE 兜底并发）→IS NULL 批量回填（每批独立事务）→DONE 清 error；壳=asyncio.run+指数退避 5 重试+FAILED 终局消毒落列）+ celery include + models.py text 列 + 手写迁移。**两路独立校验（Agent 形态，ultracode 已关）在 split_text 撞出同一条 blocker**：flush 后同轮 append 使"丢种子"elif 成死分支——种子+新段可产出 410 token 越界块（反例 30+380/400/50）；修=elif→独立 if，回归测试 test_overlap_seed_never_busts_budget 钉死；事实路代理在一次性影子库实证修复后 15/15+mypy+迁移链全绿。偏差登记（续 (22)）：
>     (23) **拍板 G ✅（2026-07-24 用户同意）：documents 补 `text` 列**（迁移 `c28efda87e6a`，NOT NULL server_default=''）——计划内在矛盾三坐标：§4.4 任务签名两次钉死只带 (document_id, tenant_id) × API 行为"落 documents(PENDING)、chunks 不动" × P6 表无原文列 → worker 拿不到原文；三替代全否决：meta JSONB 塞原文（违 P6"文档级事实归列"、不可审计）/ Celery 消息携带（违 wire 签名、原文进 Redis、消息丢=原文永久丢，续传在切块前断）/ API 侧切块（违 00 §7.1"切块归 worker"与 02 §6"慢活不进事件循环"）；P6 口径补句：原文归 documents（v1 行内 Text，对象存储属 v2）；
>     (24) split_text 越界块缺陷实录（面试素材：死分支让不变量注释说谎——`elif` 在"flush 必伴同轮 append"的结构下永不可达，注释"绝不产出超预算块"为假直到 elif→if）；已知余量内噪音两条入 docstring 认账（段间连接符 (k-1)/2 token 未入账、混排硬切窗 ±1）；
>     (25) 微偏差三条：壳返回 dict 非计划的 None（reaper 先例同款，task_ignore_result 下进日志）；embeddings.py:70"worker 装配显式传参"措辞实况=工厂缺省+跨层钉子测试（随 M3.5 触碰该文件时顺路改注释）；⒅ 新变体登记——本步起老库不跑新迁移是硬错（UndefinedColumn）非误导 skip，指令块已列 upgrade 先于 pytest 的硬约束。
>     **#18 就此闭合**（00 §10.1 已翻 ✅ 带注记：任务 async 内胆 tenant_context 包全程——比计划"任务体首行"更强，含计量路径；运行时证据（真实链路 usage_ledger embedding 行+DONE）随④验收补录）。下一份=交付④（api/kb.py POST /v1/kb/documents + create_app 注入 enqueue（producer send_task）+ 任务名两端一致已由③测试钉住 + **真实链路验收**：起 worker 传 1 篇文档→DONE→账本 embedding 行）。
>     **交付④ 代码面 ✅（2026-07-24 验收完成，提交 `993d1c4` 已推送，测试 648→655 全绿实测；用户敲入稿与影子排练稿逐字节一致）**——api/kb.py（KbDocumentIn 验证/先落库后投递/enqueue 失败 503 行留 PENDING/build_enqueue 轻量 producer send_task=决策 A 落地现场）+ main.py create_app 第六注入参 enqueue + test_kb.py 7 测（矩阵×3/三键一致/401/503 降级/422）。**轻量流程首录（(27)）**：影子副本全链排练（robocopy 副本+uv sync+四门+全量 pytest，≈3 分钟）替代多 agent 校验——当场抓两处 format 规范形（**ruff line-length 对 CJK 按宽度 2 计列**，前三份交付反复在 120 列翻车的根因，记档）；工作形态调整经用户 2026-07-24 口头确认（胶水类交付零代理、新算法/基建面至多一路对抗读码），00 §2.1 落档待用户另行确认。偏差：(26) `text` 上限 200_000 字符（计划未给，演示口径防误传巨文件）。
>     **挂起项：真实链路验收（M3.4 毕业实验）未跑**——起 worker 传 1 篇文档→DONE→usage_ledger embedding 行（=#18 运行时证据+拍板 F 账本落地+§4.4 验收栏后半）；用户指示最后再跑。**M3.4 步收口动作（00 §7.3 对账行/08 §0-bis 增量/§5.2 实数对账 +47/深挖题追加）随真实链路验收一并做**。
>     **—— M3.4 步收口 ✅（2026-07-24）**：**真实链路验收 PASS**（用户实跑，AI 库内核证：documents `returns-demo.md`=done/chunk_count=1/error 空、chunks 1/1 已回填、usage_ledger embedding 行 28 token/¥0.000014——#18 运行时证据补录 00 §10.1、拍板 F 账本落地、§4.4 验收栏后半闭合）。四交付账：`55ea421`/`f8fa77e`/`6e5f769`/`993d1c4`，测试 608→**655**（+47=11/14/15/7；§5.2 预告 +14–20 上浮 27——RLS 前置义务与工件对账 +8、②受控缝契约钉扎 +6、③校验回归钉子与 wire/include 双锚 +7、④矩阵参数化与降级面 +4、其余为各交付正文逐条点名的名分项）；§5.2 点名三文件（test_ingest_split/test_embeddings/test_ingest_resume）全部落地，另增四文件已在 ⒃(23)(26) 登记。00 §7.3 M3.4 行/08 §0.1 基线 655/`993d1c4`+§0-bis M3.4 增量节+§8 #15 翻 ✅/深挖题 117–123 均已回填。**下一步 M3.5 多租户检索**（开工核对必含：00 §10.1 **#42**——context.py:172/182 裸 await 无 C34 fail-open，建议修在 L3 适配器不动 L2；实况块 #4 检索槽位形状；§3.5 阈值留白 RETRIEVAL_SCORE_THRESHOLD=0.35 占位实测校准）。
> 14e. **M3.5 开工拍板与交付进度（进行中，逐份登记）**：切分四份（①rerank 纯函数 / ②retrieve.py Retriever / ③槽位适配器+#42 修复 / ④真实校准+步收口）；**开工拍板三项（2026-07-25 用户确认，全按建议）**：
>     Ⅰ=**#42 修案 (a)**——L3 适配器内 try 包 provider 调用、异常返 `()` fail-open+logger.warning 留痕，L2 context.py 零改动（C34：检索是增强层；(b) 动 L2 冻结面否决）；
>     Ⅱ=查询侧 embedding **不接 limiter、_EMBED_RATE 常量不升 Settings**（M3.4 偏差⒇"再议"收口：QPS 已被 M3.2 入站限流兜住、摄取侧批间串行天然限速；登记不改，需要时再升）；
>     Ⅲ=数值留白起步值确认：RETRIEVAL_SCORE_THRESHOLD=0.35 占位（④实测校准）、EXACT_SCAN_MAX_CHUNKS=10_000、top_k=5（00 唯一给定值）。
>     **交付① ✅（2026-07-25 验收完成，提交 `c615482`/`a7a3ba6`/`9ff6e52` 已推送，测试 655→667 全绿，CI 绿）**——rerank.py（RetrievedChunk/keyword_coverage CJK 二元组+字母数字段/rerank 0.7×sim+0.3×cov、sorted 稳定同分保输入序、meta 规则位注释挂点）+ tests/apps/test_rerank.py 12 测。偏差三条：
>     (28) **既有测试冲击**：M3.1④ test_usage 固定租户 id tenant-a×全局相等断言，被 M3.4 真实链路残留（28 token embedding 计量行）打红——本机红 CI 绿的环境依赖测试（M2.10"全局相等断言天生脆"+M2.11"残留×复用同 id"合体复发，M3.4 验收在真实链路**之前**跑故当时未现形）；修=`c615482` 种子租户随机重绑定（M2.11 cassette 重绑定同款），断言强度不降；④实测校准还会写真实行，此修是本步前置；
>     (29) RetrievedChunk 定义在 rerank.py 而非 §4.5 签名块视觉归属的 retrieve.py——调用方向 retrieve→rerank 单向，共享类型住依赖下游（与 core 不向上 import runtime 同名别名同款分层代价）；
>     (30) **AI 事故实录**：交付①预检时 rerank.py 尚未敲入，ruff 把 aegis 误判三方（I001 假阳性=偏差(22)预告面）、AI `--fix` 盲吞将其固化，推送后 CI 红而本机 `.ruff_cache` 掩盖持续绿；修=`9ff6e52` pyproject `[tool.ruff.lint.isort] known-first-party=["aegis"]`（分类不再依赖模块在盘与缓存），**偏差(22)就此闭合**；教训=lint 假阳性不许 --fix 盲吞、交付预检加 `--no-cache` 与 CI 同条件。下一份=交付②（retrieve.py 六步算法）。
>     **交付② ✅（2026-07-25 验收完成，提交 `0579055`+`43e3bfd` 已推送，测试 667→676 全绿，CI 绿）**——retrieve.py（Retriever 六步：embed 事务外/租户计数 60s 进程缓存 clock 注入/两开关 SET LOCAL 与查询同事务/裸 SQL `CAST(:qvec AS vector)` 具名绑定/3×top_k 候选池/全低于阈值返空）+ test_retrieval.py 9 测（SET 断言=连接级 before_cursor_execute 捕获，机制先经 scratchpad 探针实证再进交付）。偏差与实录四条：
>     (31) `__init__` 增两注入参 exact_scan_max_chunks/clock（超出 §4.5 签名；纯测试性缝——大租户分支免搬一万行、TTL 测试不睡真钟；默认值=计划语义）；
>     (32) **用户评审揪出设计缺陷（交付稿撤修）**：AI 稿 search 内 `with tenant_context(tenant_id)` 自包裹——叶子自冒充把 RLS"环境身份×参数租户"交叉核验短路成第一防线镜像（装配 bug 传错租户时：无自包=USING∩WHERE 空集安全失败；有自包=B 语料进 A 会话，恰是对抗①泄漏方向）；修=撤包裹，身份恒由边界建立（auth 裸 set 任务级生灭/任务内胆 with/脚本 main 自包/usage 特批冒充=全仓四处封闭名单），与 ingest_once 不自包、任务壳包全程先例对齐。衍生问答产 ContextVar 三形态探针（协程内 set 随 asyncio.run 生死/同步壳 set 粘线程上下文/--pool=solo 不 reset=跨任务静默串租且泄漏黏性），题库候选待收口追加；
>     (33) 提交纪律偏差：②落地为两笔同 message 提交（`0579055` 旧稿+`43e3bfd` 撤修稿，第二笔未注明"为什么改"——M2.11 `3679e7f` 同病）；已推送不改历史，照登；
>     (34) 实证注记：pgvector 存储 float32，similarity 读回 ~1e-8 噪音（0.6→0.6000000238，scratchpad 探针）——测试口径一律 pytest.approx 禁精确比较。下一份=交付③（槽位适配器 RetrievalProvider+#42 修案 (a)，落 retrieve.py 文件内——全景图已确认）。
>     **交付③ ✅（2026-07-25 验收完成，提交 `c4f0829` 已推送，测试 676→681 全绿，CI 绿）**——RetrievalProvider 落 retrieve.py（import 区+末尾类，L2 零改动）：形状适配（keyword-only 契约、不裁剪——装填归 builder `_pack_snippets`）、`wrap_untrusted(source="retrieval")` 注入面包裹（X4：事件与库存原文）、`except Exception`→`()` fail-open+warning 留痕（C34 样板镜像、不记 query 原文=打码纪律）——**#42 修案 (a) 落地**；测试 +5 含 ContextBuilder 两条集成（#7 接电证明 + #42 回归钉子"检索抖动 build 存活无检索层"；哨兵 sink 顺带钉死"检索路径不写事件"）。
>     **交付④ ✅（2026-07-25 收口，提交 `dac1f32`，零生产代码）**——真实校准 PASS：on-topic 三条 score 0.45–0.60 全命中、off-topic 两条 0.19/0.31 全拒答（**「优惠券」sim=0.4473 被 0.7 权重压回 0.3131=重排首笔真实战果**——纯相似度阈值会漏过它）、B 租户查 A 专有短语「七天无理由退货」空集（对抗①真实链路 PASS）；分离窗 [0.31,0.45] 含 0.35 → **维持占位值**（语料=M3.4 真实链路那 1 块 28 token，结论边界如实声明，M3.11 扩容后复核）；校准脚本经用户特许 AI 直写入库 `scripts/calibrate_retrieval_threshold.py` + README 索引行（calibrate_ 新前缀族=数值留白定值工种）；检索唯一入口 Grep ✓（全仓 `<=>` 作查询仅 `_SEARCH_SQL` 一处，余 4 处注释）。
>     **—— M3.5 步收口 ✅（2026-07-25）**：四交付七提交（`c615482`/`a7a3ba6`/`9ff6e52`/`0579055`+`43e3bfd`/`c4f0829`/`dac1f32`），测试 655→**681**（+26=12/9/5；§5.2 预告 +12–18 上浮 8——名分：②SET 捕获三条+列映射契约钉子 +4、③ContextBuilder 集成两条 +2、①覆盖率粒度加固 +2）；§5.2 点名两文件 test_rerank/test_retrieval 全落地。00 §7.3 M3.5 行 + **#7/#42 翻 ✅** + 08 §0.1 基线 681/`dac1f32` + §0-bis M3.5 增量节 + 题库 124–127 均已回填。拍板Ⅲ数值收口：0.35 实测维持；EXACT_SCAN_MAX_CHUNKS=10_000 与 top_k=5 本步未触界（M3.11 复核）。下一步 **M3.6 意图路由**（开工先执行 §4.6 并对照本头部实况块）。
> 14f. **M3.6 开工拍板与交付进度（进行中，逐份登记）**：切分二份（①intent.py+测试 / ②真实实测分类延迟+步收口，零生产代码）；**计划外微决策两项（2026-07-25 用户确认，全按建议）**：
>     Ⅰ=**fail-open 捕获面 `except Exception`**（宽于 §4.6 字面"任何网关异常（六类）"）——与 check_input/RetrievalProvider 两处 C34 样板一致：分诊是增强层，网关六类与解析 bug 同样不该杀请求；留痕记 session_id+异常类型、不记用户原文（打码纪律）。字面"六类"若实装即 `except GatewayError`，ProviderError 泄漏（继承同基类）一并被吞，与宽捕无实差、收窄收益为零；
>     Ⅱ=**answer_faq 的 deadline_s 同 classify 取 10.0**（§4.6 未给值；比网关缺省 25s 首块计时更紧；开发调试可调项、不进 Settings）。
>     **交付① ✅（2026-07-25，提交 `d2475f9` 已推送，测试 681→696；影子排练四门+全量 pytest 先行全绿、用户敲入稿与排练稿逐字节一致；②开工时 AI 核对 git log+collect=696、工作区干净，CI 状态待用户侧确认）**——intent.py（Intent 五值 StrEnum（AGENT 刻意不在 prompt 词表=失败落点非模型词汇）/INTENT_PROMPT 挂"定了不动"纪律（M3.11 cassette 录制语义）/_parse_intent 恰一词判据（宽容只救格式、绝不把歧义洗成裁决）/classify（与 build_classifier 同构，失败落点 AGENT 而非 ValueError）/answer_faq（system=faq_digest 原文=prompt 政策归租户配置；**刻意不兜异常**：直答是主路径非增强层，处置权归 M3.8/M3.10 调用方——设计取舍非偏差））+ tests/apps/test_intent.py 15 测。偏差两条：
>     (35) 两函数签名外微扩 `deadline_s: float = 10.0` keyword 参数——build_classifier 同款先例、偏差(31) 同类注入缝；
>     (36) 测试 +15 超 §5.2 预告上限 3——名分：加料救回三态化 +2、分片流拼接 +1、answer_faq 形状/流式/传播三条系 §4.6 测试蓝图未列的本步函数面。下一份=交付②（真实实测分类延迟（验收线 fast 档 <1s，记录供 M3.12）+重复问缓存命中路径观察+步收口四件）。
>     **交付② 实测 ✅（2026-07-25 用户实跑）**：新鲜四调 **2357/976/901/947 ms**（首条含 httpx 连接建立与 Redis 池预热，后三条 <1s 达标线内）、重复首条精确缓存命中 **8 ms**（cache._key 租户前缀+essence 剔除 session/request/deadline 的直接效果；<50ms 口径先导观察，正式验收归 M3.12）、分类 **4/4 全中**（INTENT_PROMPT 质量首证，供 M3.11 评测集参考）；
>     (37) **拍板：实测脚本入库**（2026-07-25 用户点单"加到 scripts 目录"，推翻交付②预设的"临时脚本不入库"收法——理由成立：M3.12 复测同口径、M5.2 口径②同族）——`scripts/measure_intent_latency.py`（AI 直写入库=M3.5④ calibrate 同款特许；**新前缀族 measure_=轻量延迟实测工种**）+ scripts/README.md 索引行；首测数字进脚本 docstring 作 provenance，简历级数字仍以 M3.12 正式实测为准。
>     **—— M3.6 步收口 ✅（2026-07-25）**：两交付两提交（`d2475f9`/`e79734f`），测试 681→**696**（+15；§5.2 预告 +8–12 上浮 3，名分见 (36)）；§5.2 点名文件 test_intent.py 落地。00 §7.3 M3.6 行 + 08 §0.1 基线 696/`e79734f` + §0-bis M3.6 增量节 + 题库 128–129 均已回填。实测收口：分类延迟新鲜 <1s 达标（缓存命中 8 ms 先导）；INTENT_PROMPT 自 `d2475f9` 起挂"定了不动"纪律（**起点修正见后置修订：纪律实际自 M3.11 录制时点生效，录制前修订窗口开放**）。
>     **M3.6 后置修订（2026-07-25，M3.7① 期间用户提问揪出「FAQ 直答上下文盲窗」）**：轮 1 tool（"订单 A123 退款申请了"）→ 轮 2「一般要多久？」单看酷似 faq → answer_faq 只见 faq_digest+单句，用通用条款自信答非所问。**定性**：四路唯 FAQ/HANDOFF 绕过主 Agent=仅有的上下文盲路径（RAG/TOOL/AGENT 误分无此问题——ContextBuilder 历史层在场）；质量缺陷非安全缺陷（无越权/无副作用/事件有痕），但"自信地答非所问"是客服最伤信任的失败形态；题 128"faq_digest 兜着"的说法对指代跟进问不成立、已修正。**处置三件（2026-07-25 用户拍板按建议，代码统一落 M3.8——"就地改"指令经用户撤回）**：⑴ **M3.8 接线守卫（承重）**——service.py 分支处 FAQ 直答仅当会话无历史（首条消息）生效，有历史判 faq 一律按 AGENT 进主 Agent（确定性清零，intent.py 零改动，§4.8 已挂）；⑵ M3.8 顺路交付 INTENT_PROMPT 修订（faq 行加自足限定+跟进问排除句——统计优化非承重；趁 M3.11 未录 cassette 的免费修订窗）；⑶ M3.11 语料清单显式含 FAQ 文档（守卫补集条件：主 Agent 路径必须也答得了 FAQ，§4.11 已挂）。缓存 <50ms 验收不受损：价值场景=不同用户新会话首问同一高频问题，守卫放行。下一步 **M3.7 模拟业务系统+工具五件**（开工先执行 §4.7 并对照本头部实况块；开工核对必含：**#43** 写传输模糊错契约条款、**#38** 五工具 risk_policy/risk_exempt 逐个声明核对、**#6** 幂等键下游去重闭环、M3.3 前置义务=mock 两表迁移自带 ENABLE RLS+策略、coupon_threshold 租户 config 新键（缺省 0=fail-closed，§4.7 注））。
> 14g. **M3.7 开工拍板与交付进度（进行中，逐份登记）**：切分四份（①数据层 / ②mock 子应用+故障注入 / ③工具五件 / ④真实链路验收+步收口）；**开工拍板三项（2026-07-25 用户确认，全按建议）**：
>     Ⅰ=**#43 条款形状=修案 (a) handler 内转译**——refunds/coupons 调 mock：`httpx.ConnectError`（连接未建立=请求未发出无副作用）保持普通异常→ERROR 可改道；其余传输/协议错误（发出后模糊）**转抛 TimeoutError** 交 executor 既有 X1 路径→RESULT_UNKNOWN+封死重试话术（源码核实 executor.py:184-199：`except TimeoutError` 包住 `await tool.handler(...)`，handler 自抛与 asyncio.timeout 到期同分支——executor 零改动）；monkeypatch 注入测试钉契约；
>     Ⅱ=**mock 不挂主 app**（§4.7"路径挂主 app /mock 前缀"作废）——mock 端点信任内部调用方（tenant_id/user_id 裸 query 参数），挂主 app=未认证水平越权入口，恰是对抗③要封的方向；工具经 ASGITransport 进程内直达，curl 演示需求走脚本；
>     Ⅲ=**④验收订单数据用验收脚本自带 upsert**（不动 seed_demo——种子订单脚本归 M3.11 正式化，范围纪律）。
>     **交付① ✅（2026-07-25，提交 `974b0be` 已推送，迁移 `f4b8d2a97c31`，测试 696→704 全绿；影子排练四门+全量 pytest 先行，且**含影子库环节**：aegis_shadow 空库七级迁移链全量重放干净=新迁移对裸库自举也成立——迁移类交付新工艺）**——mock_backend/{__init__,models}.py（MockOrderStatus 四态/MockOrderRecord 含 Numeric(12,2) 钱不过 float/MockWriteOpRecord **PK=idempotency_key**=去重物质基础）+ 手写迁移（两表+RLS 双子句=M3.3 前置义务第三次兑现）+ env.py 注册 + 测试 8（test_mock_models 4：状态快照/Decimal 精确往返/台账往返/主键冲突；test_rls M3.7 增量节 4：策略在位/隔离读/拒绝面/放行面）。偏差：(38) 测试文件 test_mock_models.py 与 test_rls 增量节系 §5.2 未点名（M3.4⒃ 同款名分，整步收口实数对账）。下一份=交付②（mock 子应用：四端点+去重算法+故障注入中间件+client.py+config 两字段）。
>     **交付② ✅（2026-07-25，提交 `3df3cc3` 已推送，测试 704→718 全绿；影子排练四门+全量先行）**——mock_backend/app.py（create_mock_api 工厂=create_app 同惯例/四端点+/tickets 内存台账/**去重单事务化**：claim（ON CONFLICT DO NOTHING+_rowcount 单点）→撞键回放台账 payload→首键校验+执行+回填同事务=崩溃零中间态+**失败不烧钥匙**、并发恰一由唯一索引仲裁/故障注入中间件=X1 剧本发生器）+ client.py（ASGITransport 懒单例、测试勿用单例=M2.9 跨 loop 教训传承）+ config mock_latency_ms/mock_error_rate 两字段+`_no_mock_injection_in_prod` 校验器 + 测试 14（test_mock_backend 13：读 3/物流 2/工单 1/去重 5（含二击回放不重执行+失败不烧钥匙）/coupon 同算法 1/注入 503 1；test_config +1 prod 禁令）。偏差与定案：(39) 去重四步伪码**单事务化**（语义增强非偏离——中间态与烧钥匙两缺口顺手闭合）；(40) 读端点 user_id 不作过滤参数（§4.7"query 参数 tenant_id/user_id"收窄——mock 交出行、归属判定权在工具，防线不从工具漂到 mock）；观察项：ticket_id 用 uuid4（M4.3 若需确定性再加注入缝）。下一份=交付③（工具五件+#43 条款+幂等键接线）。
>     **交付③ ✅（2026-07-25，提交 `95faef2` 已推送，测试 718→732 全绿；影子排练先行）**——tools/ 七文件（__init__ 空+_shared 底座+五工具）：**#38 声明清单 CI 化**（READ×2/WRITE+exempt×1（tickets 豁免理由留档：无资金面+handoff 直通防"转人工卡在待人批"死锁）/WRITE+policy×2）；对抗③三路拒绝（他人/跨租户/不存在）**逐字节同话术**（DENIED_TEXT 单点）；**#6 全链闭环**（写请求头 Idempotency-Key=ctx.tool_call_id——台账主键即 write-ahead 事件 id，测试钉死"M2.4 透传的钥匙首次开锁"）；**#43 落地**（post_write 单点：ConnectError/ConnectTimeout=发出前、原样上抛→ERROR 可改道；其余 HTTPError=发出后转 TimeoutError 交 X1（executor.py:188 同捕 handler 自抛）——executor 零改动，双分支测试钉契约）；coupon_threshold 缺省 0 fail-closed 与 200/200.01 边界钉死；409 业务拒绝回 dict=不进连败账（拒绝是"成功的观察"非工具故障）。偏差：(41) `_shared.py` 计划清单外第 6 文件——归属校验与 #43 是五工具共同不变量，复制五份=漂移面。下一份=交付④（真实链路验收三幕+步收口）。
>     **交付④ ✅（2026-07-25 用户实跑，三幕全 PASS；零测试增量）**——scripts/demo_tools_acceptance.py（demo_ 族，AI 直写=measure/calibrate 同款特许）+README 索引行：幕 A 真实 Agent（standard 档+四工具）**completed、工具序列恰 ['order_query','refund_apply']**（§4.7 验收"查单退款一次成功"）；幕 B 同键二击 **duplicate false→true**（#6 真库实录）；幕 C 越权读写**统一话术拒绝**（对抗③实录）。影子门抓 AI 稿两处引用错（AgentEvent.type 误写 event_type / 多余 aclosing——硬规则 8 的排练面证明，按真实源码修正）；(42) 演示订单 upsert 自带+自清理（拍板Ⅲ 落地；随机会话 id=M2.11 教训、finally 清 mock 行=M2.10 教训）；④=chore `6865ba8`（已于 M3.8 开工对账回填）。
> 14h. **M3.8 开工拍板与交付进度（进行中，逐份登记）**：切分三份（①prompts+agent 装配器+INTENT_PROMPT 修订 / ②handoff+service+L2 受控缝+chat 收敛 / ③真实链路验收+步收口）；**开工拍板四项（2026-07-25 用户确认，全按建议）**：
>     Ⅰ=**ResumeHook 注册挪 M3.9**——00 §7.1 M3.8 行（权威范围）无此项，reaper.py:42"M3.8 注册真实钩子"系 M2.10 写作时预估；M3.9 本就改 reaper（审批到期扫描），worker 跨 loop 受控缝工程（build_gateway/build_session_lock 的 loop 绑定单例参数化——shared_client/get_redis/get_engine 三处源码注释自证"跨 event loop 不可复用"）集中一步做，#44 修向同域；reaper 注释随 M3.9 修正；
>     Ⅱ=**L2 受控缝获准**——AgentRuntime.__init__ 增 `retrieval: RetrievalProviderLike | None = None`、_assemble 传给 ContextBuilder（additive 两行、默认 None=现行为、既有 732 零冲击）；§1"M3 对 L2 零修改"口径修正为"**零行为修改；additive 注入缝经拍板**"（L1 monthly_budget_resolver 同款先例）；#7 生产接线唯一不丑陋通路（context.py:138 缝在、runtime.py:293-300 没传）；
>     Ⅲ=**检索接线不做"仅 RAG 预热"特殊化**——槽位天然每轮注入（query=当轮 user_input，context.py:181-187；成本≈每轮一次 embedding；off-topic 被 0.35 阈值拒成空集自动无层）；RAG/TOOL 区分退化为分类语义保留（进 service 可观测面）；连带定案：FALLBACK_NO_RETRIEVAL 作为常任规则**静态进 SYSTEM_PROMPT_TEMPLATE**（不做动态空集检测——检索在 builder 内部 service 不可观测，新增观察缝收益低）；§4.6"RAG 分支先跑 Retriever 预热首轮"与 §4.8"检索空→注入 FALLBACK_NO_RETRIEVAL 指令"两处字面作废；
>     Ⅳ=**owned_values v1 恒空**——users 表无 PII 列、数据源属 v2；build_agent_spec 保留 keyword 参数缝（缺省 ()），C23 机制由 M2.8 测试作证；00 §10.3"接口已预留"档已追加。
>     **交付① ✅（2026-07-25，两提交 `988cf20`（装配器）/`539e160`（INTENT_PROMPT 修订=后置修订⑵兑现），测试 732→744 全绿；影子排练先行）**——prompts.py（SYSTEM_PROMPT_TEMPLATE 四规则：规则 3=拍板Ⅲ"宁可说不知道"静态化、规则 4=计划外新增"审批/拒绝如实转达不擅自重试"（X1 话术的 prompt 侧镜像）；FALLBACK_LOOP_LIMIT）+ agent.py（ALL_TOOLS 货架 dict/build_agent_spec：白名单点名未知名炸、dict.fromkeys 去重保序、预算与 approval_ttl_s 注入读 LoopPolicy() 默认不硬编码、memory_budget=0、owned_values 缝、entry_classifier 按 config）+ intent.py 修订两处（faq 自足限定+跟进问排除句，片段断言钉防误删）+ 测试 12（assembly 11+intent 1）。下一份=交付②（handoff+service+L2 受控缝+chat 收敛）。
>     **交付② ✅（2026-07-25，提交 `0793b48`，测试 744→754 全绿；admission 12 既有测试新接线零改动全绿=收敛无回归证明）**——runtime.py **L2 受控缝**（拍板Ⅱ 落地：+retrieval additive 参、_assemble 传 builder）+ prompts.py +HANDOFF_REPLY_TEMPLATE + handoff.py（create_handoff：摘要三档 sessions.summary→末三条 messages→占位；handoff 事件归调用方=单写者纪律）+ service.py（ChatFrame+ChatService：**FAQ 直答守卫**（无历史∧有摘要才直答，判据=messages 投影计数；**先答后写**=失败零残留回落主 Agent 不双写）/HANDOFF 直通三事件/主分支事件译帧/**兜底路径② FALLBACK 替换 loop 打断话术出帧**（排练揪出双 token 帧后定案——原话仍在事件流 X4 不丢事实）/租户缺行合成空配置留痕不拒服务）+ chat.py 收敛（PLACEHOLDER_SPEC 退役、取消路径 spec 经 service.build_spec 按租户装配、_collect 阶梯原样泛化）+ main.py（七注入参：+gateway/+chat_service、生产缺省链含检索接线=#7 生产注入收尾；注入 runtime 不给 gateway=聊天响亮拒绝、kb/usage 形态合法）。偏差三条：(43) 计划签名三处修正（Principal 层错→裸 str 参数（apps 不向上 import api）、ChatService 构造去 retriever 加 runtime/lock、create_handoff 去 summary 参数）；(44) 帧序定案=FALLBACK 替换非叠加；(45) create_app agent_spec 参数退役（callsites 核查零外部使用）。测试 +10=service 7+handoff 3；admission _make_app 补 gateway 接线。下一份=交付③（真实链路验收三幕+步收口）。
>     **交付③ ✅（2026-07-25 用户实跑，复跑后三幕全 PASS）**——scripts/demo_chat_acceptance.py（demo_ 族，生产装配原件 create_app() 驱动）+seed_demo config **tools/faq 两键前移**（(46)：M3.11 种子任务的配置部分因验收依赖前移，coupon_threshold/订单/语料仍留 M3.11——#21 治理路径不破）：幕 A 全链查单退款 80 直执（completed・序列 [order_query,refund_apply]・订单落库 refunded）；**幕 B FAQ 守卫实证**——首问「你们几点营业？」faq_direct、跟进问「一般要多久？」completed（M3.6 盲窗从用户提问到真实链路修复的完整闭环）；幕 C 工具面 A 四件/B 二件。**(47) 幕 C 首跑 FAIL 实录（AI 脚本缺陷，两课）**：_act_c 在 tenant_context 外读 tenant-b 配置→tenants 表在 RLS 名单内→无身份读=空集→合成空配置 tools=[]（**对抗①防线在配置面的真实开火**——WARNING 即 service 留痕按设计工作）；而 A 面"正常"纯属 TenantDirectory 60s TTL **缓存残影**（幕 A/B 已在上下文内载入缓存）——修=每租户各包 tenant_context（fix 单笔提交）；两课：⑴脚本身份声明是**每幕/每租户**义务非包一次 main 完事；⑵TTL 内缓存残影不能当正确性证据（缓存会暂时掩盖身份错误）。
>     **—— M3.8 步收口 ✅（2026-07-25）**：三交付五提交（`988cf20`/`539e160`/`0793b48`/`2b7f417`（③ demo_chat_acceptance.py 入库，含幕 C 身份自声明修）/`e189772`（seed config tools/faq 前移）——**两哈希已于 M3.9 开工核补（2026-07-26）**；`e189772` message 未写"为什么"=提交纪律偏差，已推送不改），测试 744→**754**（+22=12/10；§5.2 预告 +8–12 上浮 10——名分：service 编排层 7 测系计划蓝图未列的汇合面、守卫/兜底为后置修订与拍板新增行为、INTENT_PROMPT 片段钉 1）；§5.2 点名两文件 test_agent_assembly/test_handoff 落地。**#7 全闭环**（M3.5 接电+M3.8② 生产注入，00 §10.1 已尾注）。00 §7.3 M3.8 行 + 08 §0.1 基线 754 + §0-bis M3.8 增量节 + 题库 133–135 均已回填。下一步 **M3.9 HITL 业务闭环**（L；开工先执行 §4.9 并对照本头部实况块；开工核对必含：**#8** 前置校验重跑实装（实况块 #5：PrecheckHook=(tool_name,args) 无 ctx——身份靠闭包捕获或自查 sessions，§4.9 revalidate 签名按实况改）、**#44** 修向（ResumeHook/恢复分诊认领前查"approved 且未 attach_event"单）、**拍板Ⅰ承接**：ResumeHook 真钩子注册+worker 跨 loop 受控缝工程（build_gateway/build_session_lock 参数化——shared_client/get_redis/get_engine 三单例 loop 绑定）、审批 TTL 走 LoopPolicy.approval_ttl_s 已 M3.8 注入（§4.9"config 直读缺省 86400"不成立——实况块 #7）、reaper 到期扫描对每单调 resume(approval_id) 的 EXPIRED 分支现成勿自造、demo_hitl.ps1 用 curl.exe 非 PS 别名）。
> 14i. **M3.9 开工核对与拍板（2026-07-26；用户授权"拍板项全部按建议"，本块为差异权威）**：基线对账 ✅（HEAD `e189772`、tag 三枚、测试 754、工作区干净——M3.8 收口两哈希 `2b7f417`/`e189772` 已核补）；§4.9 逐项 Read 源码核对结论：⑴ PrecheckHook=(tool_name,args)→str|None 无 ctx（runtime.py:60）、注入位=构造参（runtime.py:214，create_app 现未传——本步接线）、veto 模板 runtime.py:73 经 :521-524 回填（L2 路径已有测试 test_suspend_resume.py:278）；⑵ §4.9"expires_at=config.get('approval_ttl_s',86400)"不成立——TTL 已由 M3.8 agent.py:48 从租户 config 注入 LoopPolicy（实况块 #7 兑现，本步零动作）；⑶ approval_pending 提示已由 M3.8 提前兑现（service.py:178-186 产帧 + chat.py _summary awaiting 摘要）——§4.9 该行本步零新代码，验收演示覆盖；⑷ §4.9"reaper 翻 EXPIRED 后逐单终止"升级为**对账 sweep**（见拍板Ⅵ——expire_due 翻转与 resume 消费之间的崩溃窗会造永久孤儿：expire_due 只返回本轮新翻单）。**拍板七项（全按建议）**：
>     Ⅰ=切分五份：①revalidate.py+#8 生产接线 / ②api/approvals.py 审批 API+owner 查读缝 / ③#44 修复=_recover_locked 审批认领分诊支（L2 受控修改） / ④worker 跨 loop 受控缝+workers/hitl.py（ResumeHook 真钩子+审批对账扫描） / ⑤demo_hitl.ps1 四段+步收口；
>     Ⅱ=revalidate 形状：`build_precheck(factory)->PrecheckHook` 无身份闭包；职责=快照对业务事实的新鲜度（订单在场/未退款/金额≤paid_amount），**归属重校验由批准执行走 executor 全程时 handler 内 fetch_owned_order 以真实 ctx 重跑兑现**（refunds.py:24 源码作证——§4.9 `revalidate_refund(args, ctx)` 签名废案）；DB 直读 mock_orders 不走 mock API（躲故障注入误伤批准后校验+mock_client 单例跨 loop 面）；未登记工具 fail-closed 拒绝（走到 precheck 必是挂过审批的工具）；
>     Ⅲ=审批 API：授权查读走 **owner 工厂**（get_owner_session_factory 现成）经 create_app 第八注入参——RLS 下 operator 上下文读不到他租单、403/404 无法分辨（对抗④要求 403 的结构性前提）；判定后 decide+resume 在 `tenant_context(approval.tenant_id)` 内执行（usage admin 特批同款=冒充封闭名单第五处，02 §7.2 随③落档）；approve/reject 均**同步消费 resume**（chat.py:141 取消路径同形先例；崩溃窗恰由本步 #44/sweep 兜底=设计自洽）；
>     Ⅳ=**#44 落地形态=_recover_locked 增"审批认领"分诊支**（#44 原文两案取后案；钩子侧 resume(approval_id=X) 废案——三窗口推演：W0 decide 后未 resume=awaiting 无租约、租约扫描结构性看不见；W1/W2 T3 已翻 running 后崩=_resume_locked T3 CAS(awaiting→running) 必打空静默 return；W3 execute 后 attach 前崩=换入口重执行走新幂等键=真双写）。分诊支设计：查该会话最新 approved∧event_id IS NULL 单→定位其 approval_requested 之后有无匹配 (tool_name,args) 的 tool_call——无→补 decided 事件（若缺）→precheck→execute(approved=True)→attach→按挂起 run 重建 fill 续跑；有且已配终局→仅补 attach 修审计链、不重执行（W3 防双写）。拒绝族孤儿（决案后崩）v1 显式接受弃置话术语义（不执行方向安全），登记已知边界；
>     Ⅴ=worker 受控缝形状：`build_gateway(*, session_factory=None, redis=None, client=None)`、`build_session_lock(*, redis=None, engine=None)`（全缺省=现行为，API 进程零改动；providers/EmbeddingClient 的 client 缝既有——base.py:49/embeddings.py:68）；mock 通路任务局部化=client.py 增显式安装缝（--pool=solo 串行前提文档化）；任务体=owner NullPool 读身份/对账 + app NullPool+install_tenant_guard+tenant_context 包恢复全程（M3.4 决策 B 同款）+任务局部 redis/httpx/mock client finally 归还；同进程 default_lease_owner 一致=steal→钩子→resume 同 owner 重入（store.py:547-551）；
>     Ⅵ=扫描任务落 `workers/hitl.py` 新模块（reaper.py 不 import apps 边界保持、仅修 :42 注释）：beat 每 `Settings.approval_scan_interval_s=60.0`（新字段接 recovery_limit 后）触发——(1) ApprovalStore(owner).expire_due() 批量翻 EXPIRED；(2) **对账 sweep**：run_state=awaiting 的会话取最新审批单、status≠pending 即 tenant_context 内 resume(approval_id)（EXPIRED 分支现成——实况块 #7；同时兜住 W0/撤回/拒绝路径的已决未续跑孤儿，含 M3.2 取消端点崩溃窗）；单单隔离 try/except（reap_once P6 同款）；ResumeHook 实装同模块（读 sessions 取租户→装配 spec→resume(approval_id=None)，#44 认领在 L2 分诊支内、钩子保持薄）；
>     Ⅶ=测试区间预告修正：§5.2 的 +12–18 系写作时未含拍板Ⅰ承接（受控缝+钩子）与 #44 L2 修复，实际预计 +24–34，逐交付实数对账。
>     **交付① ✅（2026-07-26 验收完成，提交 `aee4abb` 已推送，测试 754→766，CI 绿——用户确认）**——apps/support/revalidate.py（build_precheck+REVALIDATORS 两枚：拒绝面与 mock 执行器逐字对齐/未登记 fail-closed）+ create_app 接线 precheck + tests/apps/test_revalidate.py 12 测。
>     **交付⑤ ✅（2026-07-26 验收完成，提交 `2fed126` 已推送，零测试增量，六段全 PASS——用户实跑）**——demo_hitl.ps1 六段真实链路（§4.9 四段+对抗④+TOCTOU 加演——名分：00 §7.2"批准后先重跑前置校验"的实证面）+ demo_hitl_helper.py（seed/mark-refunded/expire=时钟注入/sweep=直调生产 expire_approvals 任务体/status 四面取证）+ README 索引两行；均 AI 直写（demo_ 族特许惯例）。超时段不等真实 TTL：expires_at 时钟注入+直调任务体（beat 每 60s 调同款——§4.9"演示可用可注入时钟加速"兑现）。偏差 (50)：**AI 脚本首跑解析炸（用户跑门抓出）**——.ps1 存成 UTF-8 无 BOM，Windows PowerShell 5.1 对无 BOM 源文件按 ANSI 代码页（中文系统=GBK）解析，中文注释乱码撕碎字符串终结符、满屏 parse error；修=加 BOM+文件头编码警示注释，5.1 解析器 ParseFile 实测 OK；教训=**06 §4 编码家族第四刀：管道/落盘/curl 载荷之外，PS1 源文件本身含中文必须 UTF-8 with BOM**（Python/YAML 无此约定差异——PS 5.1 独有，pwsh 7 缺省 UTF-8 无此坑）。**六段实录要点**：批准段事件序与 test_resume_approved_executes_and_completes 七事件尾同构（真实链路≡单测世界）；TOCTOU 段三面物证（approved∧event_id=空・无 tool_call 事件・订单零二次退款）；超时段 sweep expired=1 waiting=1 kicked=1、订单全程 paid；四会话全归 idle。
>     **—— M3.9 步收口 ✅（2026-07-26）**：五交付五提交（`aee4abb`/`6e47fb0`/`5b77bcf`/`a0689af`/`2fed126`），测试 754→**792**（+38=12/11/6/9/0；拍板Ⅶ 修正区间 +24–34 上浮 4——名分：celery 契约面 +2、sweep 防误杀与单单隔离 +2；§5.2 原表 +12–18 系写作时未含拍板Ⅰ承接与 #44 L2 修复，14i 拍板Ⅶ 开工当天已修正）；§5.2 点名三文件对账：test_revalidate 落 tests/apps/ ✓、test_approvals→**test_approvals_api**（偏差48 改名）✓、test_reaper_approvals 职责由 **test_hitl** 承担（"reaper 审批任务"形态被拍板Ⅵ 对账扫描取代，文件名随形态走）。**#8/#44 翻 ✅**（00 §10.1 已登记带凭证）。00 §7.3 M3.9 行 + 08 §0.1 基线 792/`2fed126` + §0-bis M3.9 增量节 + 题库 136–142 均已回填。下一步 **M3.10 SSE 双通道+聊天页**（L；开工先执行 §4.10 并对照本头部实况块；开工核对必含：**C22 PG LISTEN/NOTIFY 实装**（#37/U4，断连兜底 after_seq 轮询）、`GET /v1/sessions/{id}/events` 归本步（U14：operator+ 限本租+最小审计留痕）、帧协议 D11 补 ADR-007 缺口（U5：消息重置帧）、OutputGuard 逐帧前提（实况块 #10："逐字符≡整段"不变量、句子级缓冲首字延迟 D14）、Redis 进行中消息缓冲+重连整条重推、`?after_seq` 与 Last-Event-ID 双源取 max、SSE 演示 curl.exe -N（§7 陷阱 15）、ChatFrame 帧词汇=M3.8 已备之前身）。
>     **交付④ ✅（2026-07-26 验收完成，提交 `a0689af` 已推送，测试 783→792，CI 绿——用户确认）**——worker 跨 loop 受控缝+workers/hitl.py：`new_redis_client`/`new_http_client` 等价提取（单例与任务局部实例唯一配置源）、`build_gateway(*, session_factory/redis/client)`+`build_session_lock(*, redis/engine)` 参数化（缺省=现行为零改动）、mock client `set_mock_client` 安装缝（--pool=solo 串行前提）、config +`approval_scan_interval_s=60.0`、hitl.py（`sweep_once` 对账=expire_due 翻转+"awaiting×最新单已决"全集踢 resume(approval_id)、`_task_runtime` 任务局部装配（app NullPool+guard+tenant_context/任务局部 redis·httpx·mock）、`resume_session` 真钩子 import 时注册=拍板Ⅰ收尾）、celery include+beat 第二条、reaper.py 注释修正。tests/workers/test_hitl.py 7 测+test_celery_app +2（783→792 预告；sweep 直测全注入=reap_once 同口径，装配壳真实链路归交付⑤ demo）。
>     **交付③ ✅（2026-07-26 验收完成，提交 `5b77bcf` 已推送，测试 777→783，CI 绿——用户确认）**——#44 修复：runtime.py `_recover_locked` 增 a+ 审批认领分诊支（新 helper `_find_unattached_approved`：最新 approved∧event_id IS NULL 单；三窗分路=从未执行→decided 补写若缺+precheck+execute(approved=True)+attach／write-ahead 悬挂→原幂等键 reexecute+attach／已有终局→取回落盘结果只补 attach 绝不重执行；一律按挂起 run 重建 fill 续跑=与 _resume_locked APPROVED 同构；悬挂工具与认领单不匹配=响亮 RuntimeError）+ tests/runtime/test_recover_approved_claim.py 6 测（777→783 预告）。**先红实测（AI 跑，2026-07-26）**：未修代码 5 红 1 绿——五红全为断言红（恢复把已批准调用弃置、直接 LLM 续跑=#44 症状原样现形），1 绿=a支 优先序回归钉（现行本就成立）。veto 认领路径单据保持未回填=已知边界（拍板Ⅳ 注记，与 _resume_locked veto 行为一致）。偏差 (49)：**AI 测试稿缺陷（用户跑门抓出）**——W3 测试复用预翻 T3 的帮手（W1/W2 形态），真实 resume 的 T3 CAS 被预翻打空安静返回、崩不到 attach（DID NOT RAISE）；修=帮手加 flip_t3 开关、W3 传 False；教训=**崩溃模拟夹具的"预置状态"必须与被模拟的崩溃点逐一对表——多预置一步=把被测路径短路成 no-op**（T5 CAS 判定权/T3 输家安静语义的测试面回旋镖）。
>     **交付② ✅（2026-07-26 验收完成，提交 `6e47fb0` 已推送，测试 766→777，CI 绿——用户确认）**——api/approvals.py（POST /v1/approvals/{id}：授权序 401→403 角色→404→403 跨租→409 CAS；owner 查读缝+tenant_context(单据租户) 内 decide+同步消费 resume）+ create_app 第八注入参 approvals_lookup（缺省 get_owner_session_factory）+ tests/api/test_approvals_api.py 11 测。偏差 (48)：§5.2 点名的 tests/api/test_approvals.py **basename 撞车** tests/runtime/test_approvals.py（M2.2 审批店测试；无包结构下 pytest 测试模块名须全仓唯一——M3.2 mypy 双 conftest 撞名的 pytest 面变体），改名 test_approvals_api.py。
> 14j. **M3.10 开工核对与拍板（2026-07-26；用户裁决"全按建议"，本块为差异权威）**：核对实况四条——⑴逐 token 不在事件流（loop.py:440-448 TextDelta 聚合内部消化、events.py:43 token 帧非 AgentEvent）→通道层拿不到增量、必须 loop 开缝；⑵OutputGuard 不变量与 D14 首字延迟代价"在 M3.10 兑现"系 M2.8 预埋原文（guardrails.py:406-411、_finish_text docstring）；⑶run() "定死"注记=M2 时点语，additive keyword 缝经拍板合法（M3.8 拍板Ⅱ 先例）；⑷计划 sse.ChatFrame 与 M3.8 service.ChatFrame 撞名（写作时点后者不存在）。**拍板六项（全按建议）**：
>     Ⅰ=切分四份：①L2 受控缝逐 token 出流 / ②POST 通道全链（sse.py+service 流式化+chat.py StreamingResponse+Redis msgbuf）/ ③GET 通道全链（触发器迁移 D10+notify.py+stream.py+events_view.py U14）/ ④chat.html+真实链路验收+步收口；
>     Ⅱ=**L2 受控缝第三处：`run`/`resume` 增 keyword-only `text_sink: Callable[[str], Awaitable[None]] | None = None`**（sink 是每请求物、不挂进程级 runtime 构造；经 _assemble 穿透给每 run 一个的 AgentLoop）；_llm_step 逐帧改造：sink 在场时每 LLM 调用建 guard、TextDelta 到达即 feed、放行段 await sink；_finish_text 复用流中 guard 收尾——**事实不变量：事件流与 sink 在场与否无关（观察者不改变事实）**；sink 异常降级（warning+本 run 停止推送，绝不拖垮事实生产）；工具轮前置文本照推（llm_result payload 有痕）、持尾丢弃、命中只停推不写审计事件（v1 边界）；两处已知通道-事件分岔显式接受：final_check 命中（已推流不可撤回、事件存 SAFE_REPLY 为准、GET 重连整条重推校正）与 StreamInterrupted 作废重发（通道见过被作废段）；备选两案否决（等 assistant_message 整段=违 ADR-007 动机；msgbuf 轮询=API 层正是拿不到增量的一方，死结）；
>     Ⅲ=帧类型统一：扩展 service.ChatFrame（additive `seq: int | None = None`；kind 开放 str 补 error/message_reset 两词），sse.py 只做 encode_frame 与帧构造——计划 sse.ChatFrame 独立 dataclass 作废（撞名，计划修正登记）；
>     Ⅳ=FAQ 直答流式段过 OutputGuard（02 §2⑨"通道上生效"字面；guard 参数取自 build_agent_spec(tenant)）；handoff 回执/FALLBACK 话术=运行时模板沿 M2.8 豁免不过守卫；
>     Ⅴ=done 帧 usage 从本 run 事件流 llm_result.usage 累计（计划"usage_ledger 聚合"不可行：账本按 request_id 无 run 关联、时间窗脆——计划修正登记）；FAQ 直答轮 usage=null 诚实缺席；
>     Ⅵ=数值照计划：LISTEN 通道 aegis_events、payload session_id:seq、降级轮询 2s、msgbuf aegis:msgbuf:{sid} TTL 3600、响应头 Cache-Control: no-cache+X-Accel-Buffering: no。测试区间修正 +18–28（原 +12–18 未含 L2 sink 面）。
>     **交付④ ✅（2026-07-26 验收完成，提交 `3dd5d03` 已推送，测试 829→830，CI 绿——用户确认）**+**—— M3.10 步收口 ✅（2026-07-26）**：四交付四提交（`e75d30e`/`a5170d8`/`d1d2275`/`3dd5d03`），测试 792→**830**（+38=6/18/13/1；14j 修正区间 +18–28 上浮 10——名分：sse_frames 帧词汇 parametrize 全表 +7、msgbuf/直答守卫/页面路由系 §4.10 蓝图未列面；§5.2 原表 +12–18 未含拍板Ⅱ L2 面）；§5.2 点名三文件全落地（test_sse_frames/test_stream_resume/test_chat_sse）。**#37 翻 ✅**（00 §10.1 带实证注记）；U5 已回填 ADR-007（message_reset 帧名+EventSource×Authorization 折衷两注记）；U14 归属兑现。真实链路验收五幕全 PASS（批准后续跑帧瞬时推达=双探针实证）。00 §7.3 M3.10 行 + 08 §0.1 基线 830/`3dd5d03` + §0-bis M3.10 增量节 + 题库 143–149 均已回填。下一步 **M3.11 种子评测集+演示数据**（M；开工先执行 §4.11 并对照本头部实况块；开工核对必含：种子集 15–20 条文件形态（≥10 隔离对抗+5 知识库外，落表归 M4.4——§7 陷阱 11 勿越步建表）、每租户 10–20 篇语料**显式含 FAQ 文档**（M3.6 后置修订⑶ 守卫补集）、种子订单脚本正式化（M3.7 拍板Ⅲ 承接）、coupon_threshold 与 approval_ttl_s 种子值定值、**L3 行为 cassette 录制**（预算写死、M2.6 格式、基准会话集登记表 L3 行补缺、M4.3 消费）、calibrate_retrieval_threshold 语料扩容后复跑复核（M3.5④）、INTENT_PROMPT/SYSTEM_PROMPT"定了不动"自录制时点正式生效）。
>     **交付④ 原发内容（2026-07-26）**——chat.html 单文件聊天页（**用户特许 AI 直写**，demo 资产族）+ main.py `/chat` FileResponse 路由 + 真实链路验收五幕预告。**计划外定案：双通道都用 fetch 手写解析、不用原生 EventSource**——EventSource 无法携带 Authorization 头，原生用法只剩"JWT 进 URL 查询串"一条路（违安全底线：凭证不进 URL/日志）；改为 fetch+自记 Last-Event-ID+手动重连循环，服务端 id:/Last-Event-ID 协议原样（未来上 cookie 认证即可切回原生 EventSource——ADR-007 的"原生 EventSource"表述在 Bearer 认证形态下的诚实折衷，登记待回填 ADR-007 注记）。重连语义=事件流重建（清面板由 replay 重画+message_reset 盖半句——"服务端是唯一事实源"的 UI 直译）。偏差 (55)：**AI 指令模板缺陷（用户实跑抓出）**——幕C 坐席批准的单行命令用 `curl.exe -d "{\"k\":\"v\"}"`，PS 5.1 原生传参吞 `\"` → 服务端收到裸键名 JSON → 422"Expecting property name enclosed in double quotes"；讽刺面：demo_hitl.ps1 早已用"UTF-8 临时文件+-d @file"绕开、单行模板却裸奔（**06 §4 编码/引号家族第五刀：PS 5.1 给原生 exe 传含引号 JSON 一律临时文件或改 Invoke-RestMethod，curl.exe 只留给 -N 流式**）；修=幕C 改 Invoke-RestMethod 模板。偏差 (56)：**幕C"页面没变"实证定位（AI 双探针：服务端 httpx 探针+浏览器面板全流程复现均瞬时推达）**——根因非代码缺陷：用户排障期间页面刷新/新会话，JS 状态（含挂着的重订阅流）随页面消失且每次载入随机新 sid，批准推给了无人订阅的旧会话；暴露演示页可用性缺口=**无重入既有会话的通路**；修=sid 输入框去 readonly（粘旧 id+【断线重连】即重订阅任意会话看历史）；教训=**事件溯源 UI 的会话身份必须可携带——前端状态天生易失，"重入+重放"通路是标配件不是锦上添花**（服务端本就支持，缺的只是前端把手）。
>     **交付③ ✅（2026-07-26 验收完成，提交 `d1d2275` 已推送，测试 816→829，CI 绿——用户确认）**——GET 通道全链：迁移 `d41be6a90c27`（D10 触发器：AFTER INSERT ON events→pg_notify('aegis_events', session_id:seq)）+ api/notify.py（EventNotifier：独立 asyncpg 原生连接 LISTEN（§7 陷阱 7 不从池借）/建连-守连-重连后台任务/断连或未启动=wait_for 按轮询节拍返回（C22 兜底、测试 ASGITransport 不跑 lifespan=天然降级路径）/伪唤醒安全=等待方一律重查）+ api/stream.py（重订阅：after_seq×Last-Event-ID 双源取 max/事件译帧每帧 id:=seq/msgbuf 在场回放后先发 message_reset/活尾 wait-重查-推/关流判据=批内 loop_terminated 或已归 idle·failed 且无增量（直答类无终止事件）/矩阵 user 本人 404+operator 403）+ api/events_view.py（U14：operator 限本租 403 点名/admin 平台级/会话定位复用 approvals_lookup 平台查读缝/审计=结构化日志一行/原文 JSON=M4.1 底座）+ main.py（十注入参：+notifier/+msg_redis、lifespan 启停 LISTEN、两 router）。测试 +13=test_stream_resume 5/test_events_view 5/test_notify 3（含真 PG LISTEN 集成一条、时序断言取宽量级阈=豁免线内）。816→829 预告。测试稿自纠一处：message_reset 期望序与协议真实序矛盾（已完结会话回放批 done 必先于重置帧）——场景改为"进行中会话重连"的真实形态。偏差 (53)：**AI 测试稿缺陷（用户跑门抓出）——活尾并发测试把"流式请求"与"续写任务"两协程跑在同一条 SAVEPOINT 连接上**，两任务交错开/回滚各自 savepoint 把栈搞乱（`sa_savepoint_16 does not exist`）；修=两条并发测试改真提交独立引擎（NullPool+真 commit+finally 过滤式清理——test_rls 先例）；教训=**SAVEPOINT 单连接夹具是单任务串行世界的工具，凡测试内起并发协程碰 DB 一律真提交独立引擎**（与偏差49"崩溃模拟预置状态"同族：夹具的隐含前提要与测试形态逐一对表）。偏差 (54)：asyncpg 无 py.typed（首次直接 import）→ pyproject mypy override `asyncpg.*`（celery 5.5 同款先例；不引 asyncpg-stubs 三方桩=四个方法的类型收益不抵供应链面）。
>     **交付② ✅（2026-07-26 验收完成，提交 `a5170d8` 已推送，测试 798→816，CI 绿——用户确认）**——POST 通道全链：api/sse.py（encode_frame 字节面单点）+ service.py 流式化（ChatFrame +seq/队列解耦生产消费/**断连不取消生产者**=观察者离场事实生产不中断（GET 重连补收）/_TokenEmitter 先写 msgbuf 后入帧（顺序承诺）/直答过 OutputGuard 拍板Ⅳ（PII 命中截断实测）/done.usage 从 llm_result 累计拍板Ⅴ/兜底②替换语义流式保持=pending 押后终局裁决）+ chat.py SSE 化（200 路一律 event-stream；**peek 首帧**保 M3.2 锁 409 契约；流中异常译 error 帧；取消/awaiting 短流）+ main.py msg_redis（生产链才接缓冲，测试形态 None）。测试 +18=test_sse_frames 11+test_chat_sse 7；test_admission 200 路三测随协议换轨（预扫命中：M3.2 占位 JSON 协议退役的预定冲击）；test_service 帧形状保持零改动=收敛证明。798→816 预告。偏差 (52)：**AI 测试稿缺陷（用户跑门抓出）——固定 id "tenant-a" 撞本地库 seed_demo 真实种子行**（tenants_pkey 冲突；SAVEPOINT 只回滚自家写入、藏不住已提交残留——M2.10"全局相等断言"/M2.11"残留×固定 id"/M3.5(28) 同族教训**第四度复发**，本次是 tenant 行插入变体、CI 裸库绿本机红）；修=该文件 tenant/session/approval id 全部随机化（_tid/_sid 帮手）；教训升级为硬规则候选：**测试凡 INSERT 带 PK 的行，id 必随机——无例外，包括"看起来不会有人用"的表**。
>     **交付① ✅（2026-07-26 验收完成，提交 `e75d30e` 已推送，测试 792→798，CI 绿——用户确认）**——L2 逐 token 受控缝：loop.py（__init__ +text_sink/_push_text 降级单点/_llm_step 流中 feed+push/_finish_text 双模式收尾）+ runtime.py（TextSink 别名+run/resume keyword 缝经 _assemble/_run_locked/_resume_locked/_recover_locked 穿透）+ tests/runtime/test_text_sink.py 6 测（792→798 预告）。偏差 (51)：**additive 缝的两类既有测试面冲击（用户跑门抓出，AI 预扫不足）**——⑴test_runtime 签名快照钉=M2 契约钉，缝获准后钉子随契约演进（修=位置前缀锁死+text_sink 必须 KEYWORD_ONLY 缺省 None 的**新钉**，比删钉强）；⑵M3.9② _SpyRuntime.resume 覆写因基类签名扩展成 Liskov 不兼容（mypy [override] 抓获；修=spy 补收 keyword 参数）。教训=**L2 开 additive 缝时主动扫两类冲击面：signature 快照测试与测试替身覆写**（grep "inspect.signature\|class.*AgentRuntime"）。
>     **—— M3.7 步收口 ✅（2026-07-25）**：四交付四提交（`974b0be`/`3df3cc3`/`95faef2`/`6865ba8`），测试 704→**732**（+36=8/14/14；§5.2 预告 +20–30 上浮 6——名分：①RLS 前置义务 4+模型测试 4 系 M3.3 后新增义务与计划未点名文件、②config prod 禁令 1、③#43 拍板Ⅰ新增契约面+#38 清单 CI 化）；§5.2 点名三文件 test_mock_backend/test_tools_ownership/test_tools_contract 全落地。**#6/#38/#43 三项翻 ✅**（00 §10.1 已登记）。00 §7.3 M3.7 行 + 08 §0.1 基线 732 + §0-bis M3.7 增量节 + 题库 130–132 均已回填。下一步 **M3.8 主 Agent 装配+转人工**（开工先执行 §4.8 并对照本头部实况块；开工核对必含：**#44** 审批恢复丢批准——ResumeHook 认领前查"该会话 approved 且未 attach_event"单（实况块 #7 修向）、**FAQ 直答守卫+INTENT_PROMPT 修订**（M3.6 后置修订⑴⑵，§4.8 决策与口径已挂）、AgentSpec **9 字段**全注入（owned_values 按用户/entry_classifier 按租户 config——实况块 #2）、`LoopPolicy(approval_ttl_s)` 从租户 config 注入（实况块 #8）、工具面白名单 A=订单/物流/退款+tickets、B=订单/优惠券（§4.8 决策）、ResumeHook 真钩子 register_resume_hook 进程级注册（实况块 #9））。

> 14k. **M3.11 开工拍板与交付实录（2026-07-26 拍板／2026-07-27 收口；用户裁决"全部按建议"+**特许本步数据/测试/脚本全量 AI 直写**——生产包 `aegis/` 零改动故规约第 1 条无冲突面；本块为差异权威）**：
>     开工对账：基线多一笔 `75292f7`"ruff format重新提交"（main.py 一空行=M3.10 收口后用户格式化补笔，核证无害；message 未写"为什么"照登提交纪律偏差）；余项全合（tag 三枚/测试 830/工作区净/tenant-a documents 11 done 含 returns-demo 残留=观察项不清理）。
>     **拍板六项**：1=coupon_threshold=**50**（B 侧 approval_threshold 对应物，与 A 200 拉开量级）；2=approval_ttl_s 两租户**显式 3600**（=LoopPolicy 默认显式落种子，消灭"默认值巧合相等"挂点）；3=语料每租户 **10 篇**（下限档，扩充归 M4.5）；4=评测集 **20 条**=iso10+okb5+ret3+nor2；5=record 脚本 **AI 直写**（(b) 案，calibrate/measure/demo 族先例扩展）；6=cassette 落 **tests/cassettes/l3/ 子目录**（成组管理、M4.3 按目录消费）。
>     交付三份：①语料 20 篇+seed_demo 正式版+test_seed_script 6 测（`d55cb8f`，830→836）；②seed.jsonl 20 条+evals/README+test_seed_cases 6 测（`e62f139`，836→842）；③record_l3_cassettes+五盘录制（8 调用 6,695 token ¥0.006 全 PASS）+冒烟 3 测+cassettes README §5/§6+calibrate 复跑 **0.35 维持**（`5c1f5a1`，842→845）。
>     偏差八条：
>     (57) `stmt.excluded.items` 命中 ColumnCollection.items() **方法**非同名列（bound method 延迟到 JSON 序列化才炸）——修=下标 `excluded["items"]`；教训：**列名撞容器协议方法（items/keys/values/get/update）时 excluded 访问必须下标形式**；
>     (58) **既有测试冲击**：test_approvals 两条对全表扫描 `expire_due` 的全局相等断言被本地真实残留 pending 单暴露（页面演示遗留 × now+2h 视角入列；另一条按真实时钟一小时内潜伏红，一并修）——修=过滤式断言（M2.10 教训原文、M3.5(28) 同族），断言强度不降（本测试三单翻/不翻仍逐一点名）；
>     (59) 计划 §4.11 示例 must_not_contain 含产品名「灵犀」——按"**判回答不判 query 复述**"纪律修正（复述产品名零泄漏，禁现表只放他租户事实字面）；evals/README §3 判据两纪律成文（另一条=判据强度随语料几何定：语义域远才断 fallback、自有近邻文档降为 no_leak 防误杀）；
>     (60) **importlib×dataclass×future-annotations 新教训**：模块含 @dataclass 时装载必须先 `sys.modules[spec.name]=module` 再 exec_module——dataclasses 反解字符串注解查 `sys.modules[cls.__module__]`，未注册得 None 当场 AttributeError；M2.11 惯用法的隐藏前提（record_long_dialog 无模块级 dataclass 侥幸未踩）；
>     (61) 首录盘 1 自检**误杀实录**：模型答「不属于本超市服务范围…建议联系官方客服」=合法越界声明兜底形态，四词信号集未覆盖——修=信号集拓宽（不属于/不销售/无法/不提供）+README fallback 词表收录三形态（**录制实测反哺判据文档**，M4.4 judge 受益）；
>     (62) calibrate **B 检前提过期**（M3.5④ 写作时点 B 空库，"空集"是廉价判据）：扩容后 threshold=0 观察位必返 top-5 B 自家块（WHERE+RLS 结构保证）——口径修订=**字面核证**（零 A 字面+过阈值条数如实报告；B 语义近邻命中自家售后属合法=评测集 no_leak 判据的实测印证）；二轮实测 0.35 维持、分离窗收窄 [0.334,0.452]、「优惠券」0.334 距阈 0.016 挂 M4.5 留意；
>     (63) 冒烟测试 skip 形态：cassette 未录制时 pytest.skip 指路（资产依赖测试的诚实形态；资产入库后 CI 必在不 skip）；
>     (64) 测试 +15 对 §5.2 预告 +4–8 上浮 7——名分：语义锚/引用一致性双向 lint（+4）与语料生命周期（+2）系计划未列面、冒烟端到端回放 2 条系 M4.3 前哨。
>     **—— M3.11 步收口 ✅（2026-07-27）**：三提交 `d55cb8f`/`e62f139`/`5c1f5a1`，测试 830→**845**；00 §7.3 行、08 §0.1+§0-bis M3.11 增量节、题库 150–154、记忆档案均已回填。下一步 **M3.12 毕业验收+整编**（M；开工先执行 §4.12 并对照本头部实况块；开工核对必含：**四大对抗进 CI**（对抗②缓存隔离=00 §7.2 唯一未实证面，cache._key 前缀直测+端到端一条）、perf_m3.py/fallback_rate_m3.py 两真实脚本（兜底率分母=okb 5 条、未触发逐条人工归因、实测值超设计值=修正记录不改口径）、`reports/m3_acceptance.md`、毕业四件 tag `m3-support`、**§10.1 #40 atlas 补 L3 篇**、08 §0-bis M3 增量整编归位各章、§5.2 全里程碑实数对账）。

> 14l. **M3.12 开工拍板与交付实录（2026-07-28 收口=M3 毕业；拍板三项全按建议：两真实脚本 AI 直写／08 整编轻量案（§1/§6/§9 实拆+§0-bis 常驻档案，原"拆入各章"承诺修订）／atlas L3 篇范围）**：
>     交付三份：①test_adversarial.py 7 测四对抗集中面（`ae3490e`，845→852，预告区间内）；②perf_m3+fallback_rate_m3+prompt 规则 3 具体化+五盘重录+m3_acceptance.md（`8cc58ba`）；③毕业整编（atlas L3 篇/08 轻量整编/00 对账/记忆）零代码提交。
>     偏差五条：
>     (65) **兜底率三轮闭环实录**：R1 3/5=60%（okb-03/04 真编造——模型先验填充赠品品牌/供应商，抽象禁令"绝不编造"拦不住具体品类）→处置=规则 3 禁令具体化到事实品类清单；R2 4/5=80%（okb-02「暂未在知识库中配置」=合法兜底变体、判据信号集漏报）→信号集二轮反哺（+暂未/暂无）；R3 5/5=100% PASS。评测集抓真实缺陷→修复→复测的第一个完整闭环；
>     (66) **prompt 冻结后首次修订的重录纪律实跑**：SYSTEM_PROMPT_TEMPLATE 变更→按 M2.6 README §3 附五盘重录（¥0.0063 全 PASS）；冒烟不红的原因=匹配键 (session_id,scope,序号) 刻意不含 prompt 哈希——纪律运转的首个实例；
>     (67) **对账面 RLS 盲区（M3.5(32) 家族第三次现形）**：两脚本 `_spend` 用 app 引擎在 tenant_context 外读 usage_ledger=静默空集（tokens=0 且预算护栏盲飞）——修=对账切 owner 维护面（D4"对账面也算维护面"）；三次现形形态谱：叶子自包裹（M3.5）/无身份读配置（M3.8 幕C）/上下文外读账本（本步）；
>     (68) 启发式判据**假阳性面**实录：R1 okb-02"不提供分期付款服务"同为无据断言、只因方向撞词被判触发——三层判定架构定案（机器绊线→人工归因→M4.4 LLM judge），信号集 docstring 与 evals/README 双落档；
>     (69) perf 口径②样本 12 单尾 3112ms（首轮）/2655ms（复跑）超 2.5s 但口径是 P95——逐样本值入凭证如实可见，不做截尾。
>     **—— M3 毕业 ✅（2026-07-28）**：§6 验收对账清单七项全勾（四对抗 CI+凭证／00 §7.2 四条全 PASS／基线 852=B553+299 逐步有账／CI 全绿零真实调用／m3_acceptance.md 落盘／tag `m3-support`／00+08+atlas+记忆+题库 155–158 全回填）。下一步 **M4.0 开工走查**（新会话按 CLAUDE.md 七步启动；开工核对必含：§10.1 挂 M4.0 五项——#3 缓存 QPS 放大复核/#4 alembic 往返可选/#24 密钥与依赖扫描/#29 熔断缓存 Redis 触点粘滞化裁决/#41 思考模型遗留复核；M4.3 消费面=L3 五盘+M2 基准表+回放红绿有效性验证；M4 真实调用口径=仅 M4.4/M4.6）。

---

## §0 开工核对清单（M3.0 强制执行；任何一项对不上：先停下报差异、修订本计划，再动手）

M3 距写作时点隔着整个 M2 后半程，核对项比 M2 计划更多更严。逐项执行，在仓库根（本 repo） 运行命令。

| # | 核对项 | 命令 / 动作 | 预期 |
|---|---|---|---|
| 0-1 | M2 已毕业 | `git tag` + `git log --oneline -5` | tag `m2-runtime` 存在；HEAD 为 M2.13 毕业提交（**不再是 `014ec21`**） |
| 0-2 | 测试基线数 | `uv run pytest -q --collect-only \| Select-Object -Last 3` | 收集数 = 00 §6.3 M2 毕业登记数（记为 **基线 B**；本计划写作时点 301 已过时，§8 一律用"B+增量"表述） |
| 0-3 | 热身教材 | Read `docs/retro-m2.md`（00 §10.1 #35） | 文件存在且已通读——它是 M2 接口对齐表与一次 run 完整旅程的地图；**不存在则先停**（说明 M2 毕业动作未完成） |
| 0-4 | 【开工核对】会话锁 | Read `aegis/core/locks.py`（M2.9 交付） | 核对锁的获取/释放/看门狗 API 真实签名与 PG advisory 降级入口；M3.2 全部按实际签名引用 |
| 0-5 | 【开工核对】ContextBuilder 槽位 | Read `aegis/runtime/context.py`（M2.5 交付） | 核对检索槽位/长期记忆槽位的注入形状（callable 签名、返回类型、预算裁剪归属）；M3.5 接入按实际形状 |
| 0-6 | 【开工核对】前置校验重跑挂点 | Read M2.9 交付文件（预计 `aegis/runtime/` 内 HITL 恢复路径） | 核对"批准后先重跑前置校验再执行"的挂点名字与谓词签名（00 §10.1 #8：M2.9 只留挂点，M3.9 实装校验逻辑） |
| 0-7 | 【开工核对】AgentLoop 与事件生产 | Read `aegis/runtime/loop.py` + `aegis/runtime/runtime.py` | `AgentRuntime.run(spec, session_id, user_input)` 已实现（签名定死，runtime.py:39）；**核对 user_message 事件由谁写**（02 §2 ④ 说 API 层写；若 M2.7 循环内已写，M3.2 绝不能双写） |
| 0-8 | 【开工核对】审批/挂起/恢复实况 | Read M2.9 落地代码 | `ApprovalStore.create` 的生产调用方已存在；恢复单入口（"先取会话锁再恢复"）的函数名与调用方式；`approval_requested/approval_decided` 事件由谁写 |
| 0-9 | 【开工核对】workers 引导 | Read `aegis/workers/`（M2.10 最小引导） | Celery app 模块名、reaper 任务名与调度方式（beat 周期）；M3.4 摄取任务、M3.9 审批到期扫描都挂进同一 app |
| 0-10 | 【开工核对】cassette 基建 | Read M2.6 交付（cassette 格式 + FakeGateway + 录制器） | M3.11 录制 L3 行为 cassette 按 M2.6 的格式与"轮次按调用源分计数"（C10）执行 |
| 0-11 | 【开工核对】出口守卫 | Read `aegis/runtime/guardrails.py`（M2.8；02 §8 规划名 guards.py 已被缝蓝图修正——m2.8 §3 D1） | 流式出口句子级缓冲检查的接口形状——M3.10 SSE 通道要把 token 流过这道守卫（02 §2 ⑨） |
| 0-12 | 迁移链头 | `uv run alembic heads` | 记下实际 head（写作时点为 `74da3bf5d6ab`；M2.5–M2.13 若加了迁移以实际为准）——M3.1 新迁移的 down_revision 指向它 |
| 0-13 | EventType 快照 | Read `aegis/runtime/events.py:21-38` | 写作时点 14 类；若 M2 期间增删，本计划涉及事件类型处逐一复核 |
| 0-14 | Settings 快照 | Read `aegis/core/config.py` | 写作时点末字段为 `fault_injection_mode`（config.py:59）；M3 新增字段追加于其后，命名不与 M2 新增字段冲突 |
| 0-15 | 00 对账 | 重读 00 §7 全章 + §10.1 #6/#7/#8/#13/#17–#22 状态 | 挂 M3 的横切项无一在 M2 期间被提前处置或改口 |
| 0-16 | m2.x 计划偏差 | 逐个查看 `docs/plans/m2.*.md` 头部「实际落地偏差」块 | 本计划引用的 M2 契约以偏差登记后的实况为准 |
| 0-17 | 基础设施 | `docker compose -f deploy/docker-compose.yml up -d`；`docker exec aegis-postgres psql -U aegis -d aegis -c "SELECT default_version FROM pg_available_extensions WHERE name='vector'"` | PG/Redis 健康；pgvector 可用版本 ≥ 0.8.0（ADR-006 硬下限；00 §1 登记实际 0.8.4） |
| 0-18 | 真实调用前提 | `.env` 含 `DASHSCOPE_API_KEY`；百炼控制台消费限额告警已设（06 §5） | M3 开发调试用真实调用（§3.1），预算闸门与控制台告警是两道兜底 |
| 0-19 | 【用户拍板】批 | §3.4 全部拍板项在 M3.0 会话内逐条过 | 长期记忆 #20 必须先裁决，M3.5 范围随之定型 |

---

## §1 目标与定位

- **本里程碑做什么**（00 §7.0）：平台第一次接上业务与用户——多租户 RAG、业务工具、HITL 业务闭环、SSE 对外接口。四大对抗场景全绿才算数（00 §7.2）。
- **三层位置**：M3 全部新代码落在 L3（`aegis/apps/support/`）、API 层（`aegis/api/`）、workers（`aegis/workers/`）与 web（`aegis/web/`）；对 L1 仅两处受控扩展（embedding 通道、预算读路径注入缝），对 L2 **零修改**（依赖倒置：prompt/工具/策略/租户配置全部经 `AgentSpec` 注入——02 §1）。
- **面试叙事位置**：本里程碑供养 00 §7.2 面试考点五连（意图路由为什么用小模型 / 切块与召回 / HITL 挂起态存哪 / RLS 为什么必须 SET LOCAL / 带 WHERE 的 HNSW 召回两层表述）。
- **分层纪律**：`import-linter` 契约现为 `apps → runtime → gateway → core`（pyproject.toml:49-60）。M3.1 必须把新包纳入层定义（§4.1），否则新代码不受 CI 分层门保护——这是 00/02 未显式写出的隐含动作。

---

## §2 契约事实源

### 2.1 M3 消费的既有接口（已 Read 源码核实，M2.4 时点）

| 名字 | 签名 / 形状 | 出处 |
|---|---|---|
| `AgentSpec` | `system_prompt: str; tools: tuple[ToolDef, ...] = (); policy: LoopPolicy = LoopPolicy(); context_config: ContextConfig = ContextConfig(); model_tier: Tier = "standard"; sub_agent_policy = SubAgentPolicy.DISABLED; tenant_config: Mapping[str, Any] = field(default_factory=dict)` | spec.py:130-147 |
| `LoopPolicy.session_token_budget` | `int = 50_000`；生产值由 L3 从租户配置注入（docstring 明言 M3.1） | spec.py:56-57, 64 |
| `ContextConfig` | `memory_budget: int = 1_000`、`retrieval_budget: int = 3_000`（0=显式关闭该层） | spec.py:92-97 |
| `ToolContext` | `tenant_id/user_id/session_id/run_id/tool_call_id`，全 str 必填非空；`tool_call_id` 即幂等键透传下游 | tools.py:37-54 |
| `RiskPolicy` | `Callable[[Any, Mapping[str, Any]], bool]`——(已校验参数, 租户配置) → 是否需审批 | tools.py:57-59 |
| `@tool` 装饰器 | `tool(*, side_effect, risk_policy=None, risk_exempt=False, timeout_s=None, retries=0, name=None)`；C15：写工具须 risk_policy 或 risk_exempt | tools.py:126-134, 100-103 |
| `ToolRegistry` | `__init__(tools: Iterable[ToolDef] = ())` / `add` / `get→ToolDef\|None` / `specs()→tuple` 保插入序 | tools.py:165-190 |
| `EventType` | 14 类含 `USER_MESSAGE/APPROVAL_CANCELLED/APPROVAL_EXPIRED/HANDOFF` | events.py:21-38 |
| `EventWriter` | `open(factory, session_id, run_id, *, sleep=…, id_factory=…) -> EventWriter`（读流尾接续 seq）；`append(event_type, payload) -> AgentEvent`；单写者前提=已持会话锁 | store.py:319-336, 338, 288 |
| `ApprovalStore` | `create(*, approval_id, session_id, tenant_id, tool_name, args, expires_at)`；`decide(approval_id, *, approved: bool, operator_id: str) -> bool`（CAS+过期 fail-closed C7）；`cancel(approval_id) -> bool`（不查过期）；`expire_due(*, now: datetime \| None = None) -> list[str]`（RETURNING 单号） | store.py:401-476 |
| `RunState` | `idle/running/awaiting_approval/failed` | store.py:41-47 |
| `ApprovalStatus` | `pending/approved/rejected/cancelled/expired` | store.py:58-65 |
| `OutcomeKind` | `ok/error/result_unknown/needs_approval/disabled` | executor.py:24-31 |
| `ToolExecutor.__init__` | `(tools, events, *, tenant_id, user_id, tenant_config, default_timeout_s=30.0, fail_streak_limit=2, result_token_budget=3_000, summarize=None, sleep=…)` | executor.py:90-103 |
| `AgentRuntime.run` | `async def run(self, spec: AgentSpec, session_id: str, user_input: str) -> AsyncIterator[AgentEvent]`——M2 定死不再动 | runtime.py:39-43 |
| `GatewayLike` | `def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...` | runtime.py:20-30 |
| `Tier` | `Literal["fast", "standard", "strong"]` | gateway/schema.py:14 |
| `LLMRequest.tenant_id` | `Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")`——租户 id 字符集硬约束 | gateway/schema.py:54 |
| `LLMRequest.deadline_s` | 首块预算秒，`gt=0` | gateway/schema.py:60 |
| `build_gateway() -> LLMGateway` | L3/API 拿网关的唯一组装入口；现注入 `monthly_token_budget=s.tenant_monthly_token_budget` | gateway/factory.py:18, 45 |
| 月度预算闸门现路径 | `LLMGateway.complete` 内：`_meter.month_spend(tenant_id)` ≥ `_monthly_token_budget` → 抛 `BudgetExceeded`；读挂→fail-open 放行告警 | gateway/router.py:225-234 |
| `MeteringRecorder.month_spend` | `(tenant_id: str) -> int`；本月 `date_trunc('month', now())` 起 SUM(prompt+completion)、排除 cached | gateway/metering.py:113-125 |
| `Settings` | `tenant_monthly_token_budget: int = 0`（config.py:55，M3.1 切走的"从"端）；`database_url`/`redis_url`（config.py:28-29） | core/config.py |
| `get_session_factory()` | `-> async_sessionmaker[AsyncSession]`，`expire_on_commit=False` | core/db.py:34-39 |
| `get_redis()` | 快速失败三件：connect 1s / read 2s / `Retry(NoBackoff(), 1)`——M3 新增 Redis 触点沿用此客户端 | core/redis.py:12-26 |
| `estimate_tokens(text: str) -> int` | CJK≈1 token/字、其余≈4 字符/token（C25：护栏用估算） | core/tokens.py:11-17 |
| `RateLimiter.wait_take` | `(scope, rate, capacity, *, max_wait=10.0, cost=1.0) -> bool`；桶 key `aegis:rl:{scope}`；降级本地桶=全局/副本数 | gateway/ratelimit.py:130-138 |
| 五表实际列 | 以 migration `74da3bf5d6ab` 为准（**tenant_id 均 String(64) 非 UUID**；tool_invocations 列名 `tool_name` 非 02 写的 `tool`） | migrations/versions/74da3bf5d6ab |

### 2.2 M2.5–M2.13 将交付、M3 依赖的契约（写作时点**不存在**，只有文档描述——全部【开工核对】）

| 挂点 | 契约描述（文档出处） | M3 消费步 |
|---|---|---|
| `core/locks.py` 会话锁 | owner token + Lua compare-and-delete 释放 + 看门狗续期；锁被占→409；Redis 挂降级 session 级 `pg_advisory_lock` + `hashtext` 稳定哈希（ADR-005 角色5、00 §6.1 M2.9 行） | M3.2 复用、M3.9 恢复入口 |
| ContextBuilder 检索/记忆槽位 | 六层预算中"长期记忆与本轮检索两层在 M2 只有注入接口，实现随 M3 RAG"（spec.py:88-89；00 §10.1 #7） | M3.5 接入 |
| 前置校验重跑挂点 | "批准后前置校验重跑的挂点（校验逻辑 M3 注入）"（00 §6.1 M2.9 行；#8） | M3.9 实装 |
| 恢复单入口 | "审批回调只做状态翻转，实际恢复统一走'先取会话锁再恢复'的单入口"（02 §2） | M3.9 |
| reaper 引导 | Celery beat 周期任务扫租约（00 §6.1 M2.10 行）；`ix_approvals_expiry` 索引已为 M3.9 建好（store.py:151-153） | M3.9 挂到期扫描 |
| FakeGateway/cassette | 匹配键=会话 id+轮次、轮次按调用源分计数（C10）、事件等价性归一化（C31）（00 §6.1 M2.6 行） | M3.11 录制 |
| 出口守卫 | 句子级滑动缓冲增量检查 + 终局复检（00 §6.1 M2.8 行） | M3.10 通道接线 |

### 2.3 M3 提供给后续里程碑的接口（缝的另一端）

| 交付物 | 消费者 |
|---|---|
| `GET /v1/sessions/{id}/events`（trace JSON，operator+ 限本租户） | M4.1 trace 查询 API 在其上加 PII masker |
| `GET /v1/usage`、tenants 表/`token_budget_monthly` | M4.2 预算使用率 gauge（#23）、M4.6 成本实验 |
| `evals/cases/seed.jsonl`（15–20 条）+ L3 行为 cassette | M4.3 CI 回放回归、M4.4 落表迁入（eval_cases/eval_runs **M4.4 才建**，M3 不建——00 §8.1） |
| `scripts/seed_demo.py`（两租户全量演示数据可重建） | M5.4 demo、02 §5 备份口径（"种子脚本全量重建"） |
| SSE 双通道 + 单文件聊天页 | M5.2 压测（locust SSE client）、M5.3 Nginx 演示、M5.4 demo |

---

## §3 设计决策与口径

### 3.1 真实调用口径（单列，全里程碑有效）

00 §7.0 原文：「M3 开发调试与验收演示使用真实百炼调用（意图分类/对话/embedding 均过网关计量，月度预算闸门兜底）；**CI 仍零真实调用**（回放/夹具驱动）。」

执行细则：
1. **测试与 CI**：pytest 内一律 FakeGateway/respx/夹具，`DASHSCOPE_API_KEY` 缺省空值即天然拦截（config.py:21）；embedding 测试用 respx 桩或注入假 EmbeddingClient；
2. **开发调试**：本机手工跑 API/worker 时走真实百炼——全部经网关计量入 usage_ledger，`.env` 设 `TENANT_MONTHLY_TOKEN_BUDGET` 为非 0 值兜底（建议 2_000_000）；
3. **两处脚本化真实调用**：M3.11 cassette 录制（预算写死在脚本常量）与 M3.12 性能实测/兜底率实测（同）；
4. 违反此口径 = 违反 CLAUDE.md 硬规则 3（零真实调用红线，M3 口径见 00 §7.0），交付即返工。

### 3.2 关联 00 §2.2 口径（本里程碑直接消费的行）

| 口径 | M3 落点 |
|---|---|
| 失败哲学分野（安全 fail-closed / 增强 fail-open） | 归属校验、审批租户匹配、RLS = fail-closed；意图分诊挂→直走主 Agent 标准档（C34） |
| ID 关联模型（X5）：trace_id ≡ session_id | done 帧的 trace_id 就填 session_id，不新造 id |
| 跨副本事件通知（C22）：PG LISTEN/NOTIFY，LISTEN 断连兜底=after_seq 轮询，**实装 M3.10** | §4.10（00 §7.1 M3.10 行漏写此项，本计划补上——见附录问题 U4） |
| Redis 依赖故障处置（复盘补丁二）：快速失败 + 降级粘滞 | M3.2 入站限流、M3.10 消息缓冲沿用 `get_redis()` 共享客户端，不另配 |
| token 计数（C25）：护栏用估算 | 检索预算裁剪、会话预算注入均用 `estimate_tokens` |
| 429 配额风暴（C30 冻结） | M3 不做配额熔断账，前置防线=月度预算+控制台告警 |

### 3.3 本计划替未来定下的决策（蓝图未覆盖、有唯一合理答案；编号 D1–D12，各步引用）

| # | 决策 | 理由 |
|---|---|---|
| D1 | tenants/users ORM 落 **`aegis/core/tenancy.py`**（不落 apps） | 认证（api）、预算闸门（gateway）、配置注入（apps）三层都要读租户；分层契约 `apps→runtime→gateway→core` 下，gateway 与 apps 都能 import 的层只有 core——这是层契约强制出的唯一解。`migrations/env.py` 须加 `import aegis.core.tenancy  # noqa: F401`（导入即注册，schema-infra 包附9 的隐性契约） |
| D2 | RLS 事务钩子用 **`SELECT set_config('app.tenant_id', :tid, true)`**（第三参 true=事务级，等价 SET LOCAL 且可带绑定参数）；策略 `USING (tenant_id = current_setting('app.tenant_id', true))`——**text 比较，无 `::uuid`**；`current_setting` 第二参 true：未设置返回 NULL → 策略不命中 → 空集（fail-closed） | 02 §7.2 的 `::uuid` 照抄必翻车：全库 tenant_id 均 `String(64)`（74da3bf5d6ab:29,72），演示租户 id 形如 `tenant-a`（schema.py:54 字符集）——素材包 E1 高危项。SET 语句不能绑参数，拼字符串有注入面，set_config 是函数调用可绑定 |
| D3 | 低权角色 `aegis_app`（LOGIN，dev 密码 `aegis_app`）由 M3.3 迁移幂等创建；**应用运行时引擎切 `Settings.database_url_app`**（新字段，默认 `postgresql+asyncpg://aegis_app:aegis_app@localhost:5432/aegis`），alembic/env.py 与维护面保持 owner `database_url` | owner 默认绕过 RLS（02 §7.2）；迁移必须由 owner 跑（要 DDL 权）；两条连接串分开是"兜底防线真实存在"的前提 |
| D4 | 维护面（reaper/beat/nightly 对账）用 **owner 引擎、不做逐租户 SET LOCAL**；逐租户 Celery 任务（摄取）从任务参数取 tenant_id 设上下文（#18 的处置） | reaper 要跨租户扫 sessions/approvals，以 aegis_app 身份+RLS 会看见空集；维护面是平台特权路径，不冒充任何租户，文档声明即诚实答案 |
| D5 | L1 新增独立 embedding 通道：**`aegis/gateway/embeddings.py` 的 `EmbeddingClient`** + `MeteringRecorder.record_embedding(...)` + `factory.build_embedding_client()`；**不动 `LLMGateway.complete`** | ADR-006 要求 embedding 过网关计量入 usage_ledger，但现网关只有 chat 形状的 `complete`（router.py:190 附近）——通道必须新增；独立类而非塞进 LLMGateway：embedding 无档位/无流式/无缓存语义，塞进去污染判别联合契约 |
| D6 | 入站限流复用 `gateway.ratelimit.RateLimiter`，scope 前缀 **`inbound:{tenant_id}`** | Lua 令牌桶+降级本地桶已实装且经压测（0.19% 精度）；API 层（最上层）import gateway 不违反分层；重写一份=双维护 |
| D7 | FAQ/缓存直答轮**照写 user_message + assistant_message 事件**（messages 投影随之产生），素材包 E11 留白的裁决 | trace 完整性与 usage 对账都要求"每轮有事实"；缓存命中网关本就记 cached 行（metering），事件侧不写会造成账/迹不一致 |
| D8 | 意图分类失败（异常/输出不可解析）→ **返回 `Intent.AGENT`**（直走主 Agent 标准档） | 00 §2.2 C34 行原文"意图分诊挂→直走主 Agent 标准档"，fail-open |
| D9 | mock 业务系统经 **`httpx.ASGITransport` 进程内调用**（真 HTTP 语义、零网络）；orders 与写操作去重落 PG（`mock_orders`、`mock_write_ops` 两表），tickets/coupons 台账内存字典 | 幂等去重必须跨进程崩溃存活（恢复期"凭幂等键安全重发"是 M2.10 语义），只能落 PG；orders 是归属校验的事实源也须稳定；tickets/coupons 无对抗用例依赖，内存即可（重启即清，文档声明） |
| D10 | 跨副本事件通知用 **PG 触发器**：`AFTER INSERT ON events` → `pg_notify('aegis_events', session_id \|\| ':' \|\| seq)`，迁移落地；LISTEN 用独立 asyncpg 原生连接 | C22 选型 PG LISTEN/NOTIFY 已裁决；触发器方案让 L2 `EventWriter` 零改动（事务提交才发信，语义天然正确） |
| D11 | GET 重订阅通道帧协议 = POST 五帧词汇 + **`message_reset` 帧**（半条消息整条重推的载体，ADR-007:33 只有语义无帧名，素材包 E5 缺口在此补齐）；SSE `id:` 字段 = 事件 seq（Last-Event-ID 续传与 after_seq 同构） | 详表见 §4.10 |
| D12 | tenants.config 治理（#21）：**种子脚本初始化、运行期只读**（无修改端点）；变更=改种子重跑或手工 SQL，并在 README/02 加一段治理声明 | 00 #21 原文"v1 可种子只读+一段话"——照此收口，不做管理端点（范围纪律） |

### 3.4 【用户拍板】清单（M3.0 会话逐条过，拍板结果当天回填本文件与 00）——**已全部拍板（2026-07-24）：七项均按建议**，结果与影响见头部实况块 #14；本表保留建议原文供追溯

| # | 事项 | 建议 + 理由 |
|---|---|---|
| P1 | **长期记忆写路径（00 §10.1 #20，评审 C24）**：砍出 v1（01/03 同步删叙事）or 补数据模型+生成步骤 | **建议砍出 v1**。全库无长期记忆表、写路径（谁在何时写入）零出处（素材包 E4）；补齐=新表+写时机+提取策略+测试，至少 2 天且不在 00 §7.1 任何步骤行内（做了即扩权）。砍后 M3.5 只做 RAG 检索接入，`ContextConfig.memory_budget` 槽位保留为接口证据（spec.py:88-89 措辞本就允许）。若拍板"补"，需先在 00 §7.1 增补步骤行再动手 |
| P2 | **JWT 信任根（#17）**：算法/密钥托管/轮换 | **建议**：HS256 对称签名 + `Settings.jwt_secret: SecretStr`（环境变量托管，与 DASHSCOPE_API_KEY 同一纪律）+ 依赖 PyJWT。轮换：`Settings.jwt_secret_previous: SecretStr = SecretStr("")`——验签先试 current 再试 previous（双密钥窗），轮换=旧值挪 previous、新值上 current，无需踢在线用户。理由：单体+单租户签发方，RS256 的公私钥分离收益为零、密钥管理成本翻倍；v1 无 KMS（K8s/云设施是非目标）。终端用户 token TTL 建议 2h，坐席/管理员 8h |
| P3 | **月度预算闸门读路径切换（#13）+ 热路径优化（#22）**：切换机制与缓存策略 | **建议**：`LLMGateway.__init__` 增参 `monthly_budget_resolver: Callable[[str], Awaitable[int]] \| None = None`（None=沿用现 int，全部既有测试零改动）；factory 注入 `TenantDirectory.monthly_budget`（进程内 TTL 缓存 60s）。#22 选**短缓存**不选 Redis 计数器：预算是软闸门 fail-open（router.py:223-229 注释），短缓存过冲上界=TTL×QPS×单次 token，可接受；Redis 计数器要双写对账+新降级面，复杂度倒挂。month_spend 的 SUM 本身走 `ix_usage_tenant_created` 复合索引（metering.py:117），演示量级不是瓶颈，同样纳入 60s 缓存即可 |
| P4 | **M2 五表是否补 FK 指向 tenants/users** | **建议不补**。既有 6 表本就零 FK（schema-infra 包 A.8，事件溯源表间引用靠应用层+唯一约束）；补 FK 使种子脚本/测试夹具产生强顺序耦合，且对隔离没有增益（隔离靠 WHERE+RLS，不靠参照完整性）。00 M3.1 行"与 M2 五表的既有列对齐"按"类型对齐（String(64)）+不补 FK"理解 |
| P5 | **RLS v1 覆盖范围**：仅带 tenant_id 列的表（tenants/users/sessions/approvals/usage_ledger/documents/chunks/mock_orders/mock_write_ops）vs 给 events/messages/tool_invocations 补 tenant_id 列再全覆盖 | **建议前者**。三张事件/投影表无 tenant_id 列（74da3bf5d6ab），补列要动 `EventWriter` 写路径=修改 M2 冻结面；四大对抗场景（00 §7.2）涉及 chunks/缓存/orders/approvals，全在覆盖内。events 的越权防线=端点矩阵（终端用户不可见）+会话归属校验（#19），在 02 §7.3 本就有"events 纳入 PII 管控"的应用层答案。作为已知取舍写进文档（面试可讲）。若拍板补列，工作量 +1 天且需过 M2 回放兼容评估 |
| P6 | **documents/chunks 拆表方案**（素材包 E9：02 §3 两表合并行，拆法是决策非事实） | **建议**按 §4.4 表设计：source/status 归 documents，text/embedding/embedding_model 归 chunks，chunks 冗余 tenant_id（WHERE+RLS 必需）+ `UNIQUE(document_id, seq)`，embedding 可空支撑断点续传 |
| P7 | **坐席/管理员登录形态**：最小登录端点 vs `scripts/mint_token.py` 脚本签发演示形态——02 §7.1（02:198）与 00 §7.1 M3.1 行原文均为"坐席/管理员 = 平台账号登录 + RBAC"，且 00 §10.3 非目标清单只有"精美前端"没有"登录"；users 表设计也无凭证列——砍登录是取舍不是既定事实，须拍板 | **建议 mint_token 脚本形态**：v1 演示无真实坐席用户，登录端点=新增凭证列+口令哈希+一套登录测试，对四大对抗与面试叙事零增益；拍板后同步修订 02 §7.1 表述或在 02 侧登记取舍 |

### 3.5 数值留白（**实测后定**，禁止现在填死——素材包 E7）

| 参数 | 占位建议 | 定值时机 |
|---|---|---|
| embedding 批量上限（每次 API 调用文本条数） | 常量 `EMBED_BATCH_SIZE = 10` 起步 | M3.4 按百炼当时文档+实测 |
| 检索分数阈值（全低于阈值=检索失败） | `RETRIEVAL_SCORE_THRESHOLD = 0.35`（余弦相似度）占位 | M3.5 用租户 A 语料实测校准，M3.11 检索质量子集复核 |
| top_k | 5（00 M3.5 行唯一给定值，直接采用） | — |
| 小租户精确扫描阈值 | `EXACT_SCAN_MAX_CHUNKS = 10_000` | M3.5 实测 |
| 缓存命中 <50ms / 首 token <2.5s | 设计值 | M3.12 本地口径实测修正（00 §7.2 明言"实测修正记录"） |

---

## §4 实施蓝图（每步一章；章内微缩模板：目标/契约事实源/决策与口径/实施蓝图/测试蓝图/验收/陷阱）

> 通用约定：新建文件均需带模块 docstring（一句话职责+文档锚点，仓库既有风格）；生产代码由用户亲手敲（00 §2.1），本蓝图给签名与算法步骤不给整段实现；新增 ORM 模块必须同步在 `migrations/env.py` 顶部加 import（否则 autogenerate 失明）。

### §4.0 M3.0 开工走查（S；00 §7.1）

**目标**：把"写作时点的未来"校准成"开工时点的现实"。零代码交付，产出=核对记录+拍板记录+M3 全景图讲解。

**执行序**：
1. 通读 `retro-m2.md`（#35 热身教材）→ 读 `docs\07-handoff-guide.md` + `docs\08-code-map.md` 对应节（00 §12 通用规定：每个里程碑/步骤开工必读；08 是接口事实源快照，与 §0 各【开工核对】互为印证）→ 重读 02 §3/§7/§9 + ADR-005/006/007 + 01 §5 + 00 §7；
2. 逐项执行 §0 清单 0-1…0-18，把 0-4…0-11 八个【开工核对】的**真实签名**回填进本文件对应章节（当天修订，plans/README §4 纪律）；
3. 三个 M2 挂点专项核对（00 M3.0 行点名）：ContextBuilder 检索槽位（0-5）、risk_policy（已存在，tools.py:79——核对 M2.9 接电后的消费路径）、前置校验重跑挂点（0-6）；
4. §3.4 七项【用户拍板】逐条裁决（P1 长期记忆最优先——M3.5 范围随之定型）；
5. 给用户 M3 全景图（步骤地图+契约走查+首步预告），确认后进 M3.1（00 §2.1 第 6 条）。

**验收**：核对记录落在会话内且本文件已按实况修订；七项拍板有结论并回填 00（#13/#17/#20/#21 等状态列）。

**陷阱**：
- 症状：跳过 retro-m2 直接开写 → 原因：自认为素材包够用 → 正解：素材包是 M2.4 快照，M2.5–M2.13 的接口只有 retro-m2 与源码有；
- 症状：拿本计划的签名当事实引用 → 原因：混淆计划与代码 → 正解：信任序（plans/README §2）代码最高，本文件【开工核对】处全部以 Read 结果为准。

---

### §4.1 M3.1 业务底座与认证（L；00 §7.1）

**目标**：tenants/users 两表落库并与既有五表对齐；FastAPI 入口起步；JWT 认证 + 端点×角色矩阵；月度预算闸门读路径切到 tenants 表；`GET /v1/usage`（矩阵行内端点，00 §7.1 步骤行漏列——附录 U13，本步一并落地，否则 §2.3 对 M4.2 的承诺落空）。

**契约事实源**：02 §3（两表关键字段）、02 §7.1（凭证形态+矩阵）、00 §10.1 #13/#17/#19/#21/#22、gateway/factory.py:45（预算现注入点）、router.py:225-234（闸门现实现）、metering.py:113-125（month_spend）。

**决策与口径**：D1（tenancy 落 core）、D12（config 治理）、P2/P3/P4/P7（拍板后执行）；矩阵原样引用 02 §7.1：

| 端点 | user | operator | admin |
|---|---|---|---|
| `POST /v1/chat`、`GET /v1/sessions/{id}/stream` | ✅ 仅本人会话 | — | ✅ |
| `GET /v1/sessions/{id}/events`（完整 trace） | ❌ 终端用户不可见（trace 含 system prompt/内部工具名——开放即出口防护旁路泄漏） | ✅ 仅本租户 | ✅ |
| `POST /v1/approvals/{id}` | ❌ | ✅ 仅本租户（强制 `operator.tenant_id == approval.tenant_id`） | ✅ |
| `POST /v1/kb/documents`、`GET /v1/usage` | ❌ | ✅ 仅本租户 | ✅ |

"仅本人会话"机制（#19，素材包 E12 的补设计）：会话首次出现时由 chat 端点用 JWT 身份创建 `SessionRecord(tenant_id=tid, user_id=sub)`；此后 chat/stream 端点一律校验 `session.tenant_id == token.tid and session.user_id == token.sub`，不满足 → 404（不回 403：不泄露会话存在性）。operator/admin 读 events 校验 `session.tenant_id == token.tid`（admin 平台级放行，矩阵 ✅ 无限定）。

**实施蓝图**

新增依赖：`uv add fastapi uvicorn pyjwt`（fastapi/uvicorn 至今不在 pyproject——schema-infra 包 B.1 核实）。

新建/修改文件：

| 文件 | 内容 |
|---|---|
| `aegis/core/tenancy.py`（新） | ORM 两表 + 只读目录 |
| `migrations/versions/xxxx_tenants_users.py`（新，autogenerate 后人工核） | 建表 |
| `migrations/env.py`（改） | +`import aegis.core.tenancy  # noqa: F401` |
| `aegis/api/__init__.py`、`aegis/api/main.py`（新） | `def create_app() -> FastAPI`（组装在边缘：app.state 挂 gateway/session_factory/redis/directory） |
| `aegis/api/auth.py`（新） | JWT 签发/验签 + FastAPI 依赖 |
| `aegis/api/usage.py`（新） | `GET /v1/usage`（`require_roles(OPERATOR, ADMIN)`，operator 强制过滤本租户——矩阵行）：读 usage_ledger 出明细与聚合（02 §9 口径："明细到请求；聚合：租户/会话/模型/天"）；聚合用裸 SQL（00 §2.2 数据访问口径），无新表无新依赖（U13） |
| `aegis/core/config.py`（改） | +`jwt_secret: SecretStr = SecretStr("")`、`jwt_secret_previous: SecretStr = SecretStr("")`、`jwt_user_ttl_s: int = 7200`、`jwt_staff_ttl_s: int = 28800`（P2 拍板后定案） |
| `aegis/gateway/router.py`（改，受控） | `LLMGateway.__init__` +`monthly_budget_resolver: Callable[[str], Awaitable[int]] \| None = None`；闸门处 resolver 优先、None 落回 int（P3） |
| `aegis/gateway/factory.py`（改） | 注入 resolver=`TenantDirectory(...).monthly_budget` |
| `pyproject.toml`（改） | import-linter layers 更新为（自上而下）：`"aegis.api : aegis.workers"`、`"aegis.apps"`、`"aegis.runtime"`、`"aegis.gateway"`、`"aegis.core"`（api 与 workers 同层互不 import） |
| `scripts/seed_demo.py`（新，M3.11 扩充） | 先落 tenants/users 种子（#21：种子即初始化入口） |

表结构（列级；类型对齐既有口径：id 全 String(64) 应用侧生成、时间列 `DateTime(timezone=True)`+`server_default=func.now()`、枚举存字符串列）：

`tenants`：

| 列 | 类型 | 约束 |
|---|---|---|
| id | String(64) | PK（形如 `tenant-a`，须匹配 schema.py:54 字符集） |
| name | String(128) | NOT NULL |
| config | JSONB | NOT NULL（含 `approval_threshold`、`tools`、`session_token_budget` 等，解释权在 L3——spec.py:136-138） |
| token_budget_monthly | BigInteger | NOT NULL，**独立列不进 config**（00 M3.1 行加粗强调） |
| created_at / updated_at | DateTime(tz) | server_default now() |

`users`：

| 列 | 类型 | 约束 |
|---|---|---|
| id | String(64) | PK |
| tenant_id | String(64) | NOT NULL，index（不带 FK——P4 建议） |
| role | String(16) | NOT NULL；合法值由 `class Role(StrEnum): USER/OPERATOR/ADMIN` 代码层守护，不用 PG ENUM（store.py:5-7 同款口径） |
| display_name | String(128) | NOT NULL default '' |
| created_at | DateTime(tz) | server_default now() |

`aegis/core/tenancy.py` 精确签名：

```python
class Role(StrEnum): USER = "user"; OPERATOR = "operator"; ADMIN = "admin"   # 三行分写
class TenantRecord(Base): ...   # 上表
class UserRecord(Base): ...     # 上表

class TenantDirectory:
    """租户目录只读层：认证/预算/装配三处消费方共用；带 TTL 进程缓存（#22）。"""
    def __init__(self, factory: SessionFactory, *, cache_ttl_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic) -> None: ...
    async def get_tenant(self, tenant_id: str) -> TenantRecord | None: ...
    async def get_user(self, user_id: str) -> UserRecord | None: ...
    async def monthly_budget(self, tenant_id: str) -> int: ...   # 未知租户返回 0（=闸门关闭，语义与现 config 默认一致）
```

`aegis/api/auth.py` 精确签名：

```python
@dataclass(frozen=True, slots=True)
class Principal:
    user_id: str; tenant_id: str; role: Role

def issue_token(*, user_id: str, tenant_id: str, role: Role,
                ttl_s: int, secret: str, now: Callable[[], int] = ...) -> str: ...
    # claims: sub / tid / role / iat / exp；alg=HS256
def decode_token(token: str, *, secret: str, previous: str = "") -> Principal: ...
    # 先试 secret 再试 previous（P2 双密钥窗）；jwt.decode 必须显式 algorithms=["HS256"]
async def current_principal(request: Request) -> Principal: ...          # FastAPI 依赖：解 Authorization: Bearer
def require_roles(*roles: Role) -> Callable[..., Awaitable[Principal]]: ...  # 依赖工厂：矩阵的执行器
```

预算闸门切换算法（router.py 改动 ≤10 行）：
1. `budget = await self._monthly_budget_resolver(req.tenant_id) if resolver else self._monthly_token_budget`；
2. resolver 自身抛异常 → 与现 month_spend 读失败同路：fail-open 放行 + warning（成本闸门哲学不变）；
3. `budget <= 0` → 该租户闸门关闭；其余逻辑（month_spend 比较、BudgetExceeded 文案）不动。
不变量：resolver=None 时行为与 M2.4 完全一致（既有 gateway 测试零改动即全绿）。

关键不变量：
- 密钥零硬编码：`jwt_secret` 缺省空串时 `issue_token/decode_token` 直接抛 ValueError（与 openai_compat 空 key 快速失败同款哲学）；
- Role/矩阵纪律：所有受保护端点用 `require_roles` 依赖声明，不在 handler 体内散写 if；
- dev 演示 token 由 `scripts/mint_token.py`（新，~30 行）签发；**登录形态按 P7 拍板执行**（02 §7.1 原文是"平台账号登录 + RBAC"，脚本签发是本计划建议的取舍，未拍板前不得定死）。

**测试蓝图**：`tests/api/test_auth.py`（issue/decode 往返、过期拒、坏签名拒、previous 密钥窗、空密钥炸、require_roles 403/401）、`tests/core/test_tenancy.py`（两表默认值、directory 缓存命中不查库【注入 clock】、未知租户预算 0）、`tests/gateway/test_budget_resolver.py`（resolver 优先、异常 fail-open、None 落回 int）、`tests/api/test_usage.py`（user 角色 403【矩阵】、operator 只见本租户行、聚合与预置 usage_ledger 行对得上）。预期 +22–32。

**验收**：迁移 upgrade/downgrade 往返 OK；`uv run uvicorn aegis.api.main:create_app --factory` 起服务，`/healthz` 200；矩阵测试全绿；`lint-imports` 过新层定义。

**陷阱**：
- 症状：PyJWT `decode` 不传 `algorithms` 也能跑 → 原因：库为向后兼容留的坑，alg 混淆攻击面 → 正解：**必须**显式 `algorithms=["HS256"]`；
- 症状：新表在 autogenerate diff 里不出现 → 原因：env.py 忘加 import → 正解：D1 注明的那行；
- 症状：ORM 侧 default 值裸 SQL 插入报 NOT NULL → 原因：`default=` 只在 SQLAlchemy 层生效（schema-infra 包 A.8 通用陷阱）→ 正解：种子脚本走 ORM 或显式给全列。

---

### §4.2 M3.2 API 层入站三件（M；00 §7.1）

**目标**：入站限流（租户维度）；会话互斥（复用 core/locks.py，占用→409）；awaiting_approval 消息准入；user_message 事件落盘。

**契约事实源**：02 §2 ③④（两级限流分工、锁语义、消息准入）、ADR-005 角色5（锁完整语义）、EventWriter（store.py:319-382）、`RunState.AWAITING_APPROVAL`（store.py:46）、`ApprovalStore.cancel`（store.py:444）、`EventType.USER_MESSAGE/APPROVAL_CANCELLED`（events.py:25,34）、#19（归属校验，机制已在 §4.1 定）。

**决策与口径**：D6（复用 RateLimiter）；准入规则 02 §2 原文——awaiting_approval 时新消息**不开新循环**，系统提示"有待审批操作进行中"；用户明确取消 → `approval_cancelled` 事件 + 审批单置 cancelled + 挂起 run 优雅终止（终止路径走 M2.9 机制，【开工核对】0-8）。"明确取消"的判定：**不做自然语言猜测**——请求体带显式字段 `cancel_pending_approval: bool = false`，前端给取消按钮（弱模型高发错误：想用 LLM 判断"用户是不是想取消"——这是安全动作，必须确定性信号）。

**实施蓝图**

新建/修改：

| 文件 | 内容 |
|---|---|
| `aegis/api/chat.py`（新） | `POST /v1/chat` 的入站前半（本步交付到"落盘 user_message + 占位响应"；SSE 化在 M3.10） |
| `aegis/api/ratelimit.py`（新） | 入站限流依赖 |
| `aegis/core/config.py`（改） | +`inbound_rate: float = Field(default=2.0, gt=0)`、`inbound_burst: float = Field(default=5.0, gt=0)`（每租户入站 QPS，演示值） |

请求/响应形状（02/ADR 未定义请求体——本计划显式设计）：

```python
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")  # 客户端持有；首见即建会话
    message: str = Field(min_length=1, max_length=4000)
    cancel_pending_approval: bool = False
```

入站处理编号算法（chat 端点前半，顺序即 02 §2 ①→④）：
1. `Principal` 依赖解析（401 未带/无效 token）；
2. 入站限流：`RateLimiter.wait_take(f"inbound:{p.tenant_id}", inbound_rate, inbound_burst, max_wait=0)`——**max_wait=0 即问即答**，超限直接 429 + `Retry-After`（入站层不排队；排队是出站层保护供应商的语义，两级分工 02 §1）；
3. 会话解析：读/建 SessionRecord + #19 归属校验（不符→404）；
4. 会话互斥：取 `core/locks.py` 会话锁【开工核对 0-4 签名】；被占 → **409** `{"detail": "上一条消息处理中"}`；
5. 消息准入：`run_state == awaiting_approval` 时——(a) `cancel_pending_approval=True`：查该会话 pending 审批单 → `ApprovalStore.cancel`（CAS，False=已被别人翻转，按当前实况走）→ 写 `approval_cancelled` 事件 → 经 M2.9 终止路径优雅收尾 → 返回取消确认；(b) 否则**不开新循环**，返回 200 提示帧/JSON"有待审批操作进行中"（本步 JSON，M3.10 换 approval_pending 帧语义）；
6. user_message 落盘：`EventWriter.open(factory, session_id, run_id=新生成)` 后 `append(USER_MESSAGE, {"content": msg})`——**前提是第 4 步已持锁**（EventWriter 单写者前提，store.py:288）。【开工核对 0-7】若 M2.7 循环内已写 user_message，则本步只传原文进 run、绝不双写。

不变量：
- 锁必须覆盖"写 user_message→run 结束"的全程，释放在流结束/异常路径统一 finally；
- 429/409/404/401 分工不许混：限流 429、互斥 409、归属 404、认证 401。

**测试蓝图**：`tests/api/test_admission.py`（未带 token 401 / 他人会话 404 / 限流 429 带 Retry-After / 锁被占 409【锁用假实现或真 Redis fixture `r`】/ awaiting_approval 不开新循环 / 显式取消翻转审批单+落 approval_cancelled 事件 / user_message 落盘且 seq 接续）。httpx `ASGITransport` + `create_app` 驱动。预期 +10–16。

**陷阱**：
- 症状：并发两请求都拿到锁 → 原因：用了 `redis.set` 无 NX 或忘 owner token → 正解：只用 core/locks.py 原语，不徒手写 Redis 锁（ADR-005 角色5 的 Lua CAD 语义已实装）；
- 症状：409 后会话永久锁死 → 原因：异常路径没释放锁 → 正解：锁的持有用 async context manager（若 M2.9 未提供则在本步包一层），finally 保证释放；
- 症状：取消后 run 没停 → 原因：只翻了审批单没触发终止 → 正解：终止走 M2.9 单入口（0-8 核对到的路径），不自造停法。

---

### §4.3 M3.3 RLS + 连接池租户上下文（L，显式 1–2 天；00 §7.1）

**目标**：每事务 SET LOCAL 租户上下文（SQLAlchemy 事务钩子）；低权连接角色；RLS 策略；两条集成测试（裸 SQL 空集、并发不串）。

**契约事实源**：02 §7.2 第 1 层全文（钩子/LOCAL 原因/低权角色/USING/测试要求）、00 §10.1 #18、00 §11 第 3 条砍法预案（超时→先保应用层隔离，RLS 移 M4）。

**决策与口径**：D2（set_config + text 比较，**照抄 02 的 `::uuid` 必翻车**）、D3（aegis_app 角色 + database_url_app）、D4（维护面 owner 引擎）、P5（覆盖范围拍板）。

**实施蓝图**

新建/修改：

| 文件 | 内容 |
|---|---|
| `aegis/core/tenant_ctx.py`（新） | 租户上下文 ContextVar + 引擎事件钩子 |
| `aegis/core/config.py`（改） | +`database_url_app: str = "postgresql+asyncpg://aegis_app:aegis_app@localhost:5432/aegis"` |
| `aegis/core/db.py`（改） | `get_engine()` 改读 `database_url_app`；+`get_owner_engine()/get_owner_session_factory()`（维护面与 alembic 用，D4） |
| `migrations/versions/xxxx_rls.py`（新，**手写不 autogenerate**） | 角色 DDL + ENABLE RLS + 策略 |

`aegis/core/tenant_ctx.py` 精确签名：

```python
current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)

@contextmanager
def tenant_context(tenant_id: str) -> Iterator[None]: ...   # set/reset token，请求中间件与 Celery 任务共用

def install_tenant_guard(engine: AsyncEngine) -> None:
    """在 engine.sync_engine 上挂 'begin' 事件：事务一开始就执行
    SELECT set_config('app.tenant_id', :tid, true)。tid 为 None 时设空串——
    current_setting 返回 '' 不匹配任何租户，RLS fail-closed。"""
```

钩子伪代码（唯一允许的棘手处，≤15 行）：

```python
@event.listens_for(engine.sync_engine, "begin")
def _set_tenant(conn):
    tid = current_tenant_id.get()
    conn.exec_driver_sql(
        "SELECT set_config('app.tenant_id', %s, true)", (tid or "",)
    )
```

迁移 DDL 要点（编号步骤）：
1. 角色幂等创建：`DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='aegis_app') THEN CREATE ROLE aegis_app LOGIN PASSWORD 'aegis_app'; END IF; END $$;`（dev 口令；生产走 secrets——02 §5 备份口径同款声明）；
2. 授权：`GRANT USAGE ON SCHEMA public` + `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aegis_app` + `ALTER DEFAULT PRIVILEGES ... GRANT ...`（未来新表自动带权）+ `GRANT USAGE, SELECT ON ALL SEQUENCES ...`（BigInteger 自增列需要）；
3. 对 P5 拍板的覆盖表逐张：`ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;` + 策略样例：

```sql
CREATE POLICY tenant_isolation ON sessions
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
```

（`tenants` 表本身策略比较 `id`；`USING` 管 SELECT/UPDATE/DELETE，**`WITH CHECK` 必须写**否则 INSERT 不受限也可能被默认拒——见陷阱）；
4. downgrade：DROP POLICY + DISABLE RLS + 权限回收（角色保留，幂等）。

#18 落点（本步文档+代码双落）：请求路径由 API 中间件在 Principal 解析后 `tenant_context(p.tenant_id)`；Celery 摄取任务在任务体首行 `tenant_context(task_tenant_id)`；reaper/nightly 对账走 owner 引擎（D4），在 02 §7.2 补一句声明。

关键不变量：
- alembic 永远用 owner URL（env.py 现读 `get_settings().database_url` 不动）；
- 应用运行时引擎（get_engine）连 aegis_app；测试夹具连什么由 conftest 决定（见测试蓝图）；
- 空上下文=空集：任何忘设租户的代码路径读到 0 行而非全量行。

**测试蓝图**：`tests/core/test_rls.py`（集成，依赖本地 PG，无则 skip 同 conftest 惯例）：
- `test_bare_sql_without_context_returns_empty`：以 aegis_app 直连（`create_async_engine(database_url_app)`），不设上下文裸 `SELECT * FROM sessions` → 0 行（先用 owner 连接种 2 租户数据）；
- `test_bare_sql_with_context_sees_only_own_tenant`；
- `test_concurrent_two_tenants_do_not_leak`：`asyncio.gather` 两协程各自 `tenant_context` 下查询多轮，断言互不见对方行（02 §7.2 点名的并发测试）；
- `test_insert_wrong_tenant_rejected`（WITH CHECK 生效）；
- `test_owner_engine_bypasses_for_maintenance`（D4 语义留证）。
注意：这些测试**不能用** `db_conn` 外层回滚夹具（RLS 行为要真提交+真角色）——新建独立 fixture `rls_engine`，测试自理清数据（TRUNCATE 种子表）。预期 +6–10。

**验收**：两条 02 §7.2 点名测试绿；`uv run alembic downgrade -1 && upgrade head` 往返 OK；停表演示：aegis_app 裸 psql 查询空集截图/记录留档。

**陷阱**：
- 症状：策略里 `::uuid` 报 `invalid input syntax for type uuid: "tenant-a"` → 原因：02 §7.2 规划文本与实装列型漂移（String(64)）→ 正解：D2 的 text 比较；这是本计划附录 U1 号上游问题；
- 症状：`SET LOCAL` 后查询仍然全量可见 → 原因：连接是 owner/超级用户（表 owner 默认 BYPASS）→ 正解：确认 `current_user` 是 aegis_app；测试里第一步就断言 `SELECT current_user`；
- 症状：`SET LOCAL ... 会话变量丢失` 且日志有 `SET LOCAL can only be used in transaction blocks` WARNING → 原因：钩子挂错事件（连接级而非事务级）→ 正解：挂 `"begin"` 事件（BEGIN 之后触发）；
- 症状：`current_setting('app.tenant_id')` 抛 `unrecognized configuration parameter` → 原因：漏了第二参 → 正解：`current_setting(..., true)` 未设返回 NULL；
- 症状：INSERT 全被拒 → 原因：只写 USING 没写 WITH CHECK（或反之）→ 正解：两个子句都写；
- 症状：CI 里 aegis_app 连不上 → 原因：CI service 容器只有 aegis 用户，角色由迁移创建、口令在迁移里——CI 顺序"先 alembic 后 pytest"（ci.yml:63-67）天然满足，但**本地首次跑测试前必须先 upgrade head**（conftest 的 create_all 不会建角色/策略）→ 正解：§8 指令块本步把 alembic 放 pytest 前。

---

### §4.4 M3.4 摄取流水线（L；00 §7.1）

**目标**：documents/chunks 迁移（vector(1024)+embedding_model+HNSW）；Celery 摄取任务（解析→切块→批量 embedding→入库，断点续传）；`POST /v1/kb/documents`。

**契约事实源**：ADR-006 全文（模型/维度/批量上限实测/断点续传/换模型灰度/摄取过网关计量）、02 §6（慢活不进事件循环）、02 §8（workers/ 落点）、06 §4（Windows Celery `--pool=solo`）、ADR-005 角色4（broker=Redis；Redis 挂摄取暂停是已接受降级）、00 §10.1 #18。

**决策与口径**：D5（EmbeddingClient）、P6（拆表拍板）、批量上限实测留白（§3.5）。

**实施蓝图**

新增依赖：仅 `uv add pgvector`（提供 `pgvector.sqlalchemy.Vector` 列类型）——celery 已随 M2.10 交付③引入（`uv add "celery>=5.5"`，m2.10 §4.0/§8），到 M3.4 时已在 pyproject，勿重复 add。

新建/修改：

| 文件 | 内容 |
|---|---|
| `aegis/apps/support/__init__.py`、`rag/__init__.py`（新） | 包占位 |
| `aegis/apps/support/rag/models.py`（新） | DocumentRecord/ChunkRecord ORM |
| `aegis/apps/support/rag/ingest.py`（新） | 解析+切块纯函数 |
| `aegis/gateway/embeddings.py`（新） | EmbeddingClient（L1 受控扩展，D5） |
| `aegis/gateway/metering.py`（改） | +`record_embedding` |
| `aegis/gateway/factory.py`（改） | +`build_embedding_client()` |
| `aegis/workers/ingest.py`（新） | Celery 任务（挂进 M2.10 的 app——【开工核对 0-9】app 模块名） |
| `aegis/api/kb.py`（新） | `POST /v1/kb/documents` |
| `migrations/versions/xxxx_documents_chunks.py`（新） | `CREATE EXTENSION IF NOT EXISTS vector` + 两表 + HNSW |
| `migrations/env.py`（改） | +`import aegis.apps.support.rag.models  # noqa: F401` |

表结构（P6 建议方案，拍板后执行）：

`documents`：

| 列 | 类型 | 约束 |
|---|---|---|
| id | String(64) | PK 应用侧 uuid |
| tenant_id | String(64) | NOT NULL index（RLS 覆盖表） |
| source | String(256) | NOT NULL（文件名/来源标识） |
| status | String(16) | NOT NULL；`class IngestStatus(StrEnum): PENDING/PROCESSING/DONE/FAILED` 代码守护 |
| error | Text | NULL |
| chunk_count | Integer | NOT NULL default 0（ORM 侧） |
| meta | JSONB | NOT NULL |
| created_at / updated_at | DateTime(tz) | server_default now() |

`chunks`：

| 列 | 类型 | 约束 |
|---|---|---|
| id | BigInteger | PK autoincrement |
| document_id | String(64) | NOT NULL index（不带 FK，P4 同款口径） |
| tenant_id | String(64) | NOT NULL index——**冗余列**，WHERE 过滤与 RLS 都靠它，绝不能省 |
| seq | Integer | NOT NULL；`UNIQUE(document_id, seq)`（断点续传的幂等锚） |
| text | Text | NOT NULL |
| embedding | `Vector(1024)` | **NULL**（先落文本后回填向量=断点续传的实现基座） |
| embedding_model | String(64) | NULL（回填时同步写 `text-embedding-v4`；换模型灰度列，ADR-006） |
| meta | JSONB | NOT NULL |
| created_at | DateTime(tz) | server_default now() |

HNSW 索引（迁移内手写）：`CREATE INDEX ix_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);`（余弦距离；`<=>` 算子，相似度 = 1 − 距离）。另建普通索引 `ix_chunks_tenant_id`。

`aegis/gateway/embeddings.py` 精确签名：

```python
EMBED_BATCH_SIZE = 10  # 实测后定（§3.5）；百炼 /embeddings OpenAI 兼容端点

class EmbeddingClient:
    def __init__(self, *, base_url: str, api_key: str,
                 meter: MeteringRecorder | None = None,
                 limiter: LimiterLike | None = None,          # 复用出站限流，scope="provider:bailian-embed"
                 client: httpx.AsyncClient | None = None,     # None→shared_client()（DI 同适配器惯例）
                 model: str = "text-embedding-v4", dimensions: int = 1024) -> None: ...
    async def embed(self, texts: Sequence[str], *, tenant_id: str) -> list[list[float]]:
        """≤EMBED_BATCH_SIZE 条一批；空 key 抛 AuthError（openai_compat 同款快速失败）；
        429/5xx 复用 base.raise_for_status 翻译 + 有限退避重试（读语义可重试）；
        成功后 meter.record_embedding 计量（fail-open：记账失败不拖垮摄取）。"""
```

`MeteringRecorder.record_embedding` 签名：

```python
async def record_embedding(self, *, tenant_id: str, request_id: str, model: str,
                           prompt_tokens: int, session_id: str | None = None) -> None:
    # 一行 UsageRecord：tier="embedding", provider="bailian", completion_tokens=0, cached=False
    # tier 列 String(16) 自由值，不改 Tier 字面量（Tier 是 chat 档位契约，别动）
```

Celery 任务与断点续传算法（`aegis/workers/ingest.py`）：

```python
@celery_app.task(name="aegis.ingest_document", bind=True, max_retries=5)
def ingest_document(self, document_id: str, tenant_id: str) -> None: ...
```

编号步骤（任务体内 asyncio.run 驱动 async 实现；全程 `tenant_context(tenant_id)`——#18）：
1. 置 documents.status=PROCESSING；
2. **切块幂等**：`chunks WHERE document_id=? ` 已有行则跳过切块（重试进场即续传）；否则 `ingest.split_text(text) -> list[str]` 落 chunks（embedding=NULL），`UNIQUE(document_id, seq)` 兜底并发重复；
3. **向量回填循环**：`SELECT id, text FROM chunks WHERE document_id=? AND embedding IS NULL ORDER BY seq LIMIT EMBED_BATCH_SIZE` → `EmbeddingClient.embed(batch)` → 逐行 UPDATE embedding+embedding_model → 循环到空集。**一批失败：Celery retry（指数退避），已回填的批次因 IS NULL 谓词天然不重跑**——这就是"断点续传，一批失败不重跑全量"（ADR-006）的全部实现；
4. 空集后置 status=DONE + chunk_count；`max_retries` 耗尽置 FAILED + error。

`ingest.split_text` 签名：`def split_text(text: str, *, target_tokens: int = 400, overlap_tokens: int = 50) -> list[str]`（按段落聚合到目标预算，`estimate_tokens` 做尺——切块策略是面试考点，参数进 docstring）。

`POST /v1/kb/documents`（operator+，`require_roles`）：请求 `{"source": str, "text": str}`（v1 纯文本 JSON，不做 multipart——演示语料是 md/txt，砍掉文件解析复杂度）；行为：落 documents(PENDING) + chunks 不动 → `ingest_document.delay(doc_id, principal.tenant_id)` → `202 {"document_id": ..., "status": "pending"}`。

**测试蓝图**：`tests/apps/test_ingest_split.py`（纯函数：预算内/超长段落切开/overlap 生效/空文本）、`tests/gateway/test_embeddings.py`（respx：批量请求形状含 dimensions=1024、429 重试、空 key AuthError、计量行落库 tier="embedding"）、`tests/workers/test_ingest_resume.py`（集成：预置一半 chunks 已有向量，注入假 EmbeddingClient 记录调用——断言只补 NULL 批次；一批注入异常→状态仍 PROCESSING 且已回填行不回滚）。Celery 任务测试**直接调用任务函数体**（不起 worker）。预期 +14–20。

**验收**：`uv run alembic upgrade head` 后 `\d chunks` 见 vector(1024)+HNSW；本地起 worker（`uv run celery -A aegis.workers.<app模块> worker --pool=solo`——【开工核对 0-9】）+ 真实上传 1 篇文档全链路 DONE；usage_ledger 出现 embedding 行。

**陷阱**：
- 症状：迁移报 `type "vector" does not exist` → 原因：忘 `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`（镜像带扩展但库内未启用——schema-infra 包附7）→ 正解：本迁移第一句；
- 症状：autogenerate 生成的迁移缺 Vector 类型 import → 原因：alembic 不认识第三方类型 → 正解：迁移文件手工补 `from pgvector.sqlalchemy import Vector`，HNSW 索引一律手写 op.execute；
- 症状：Windows 本地 worker 起不来/任务卡死 → 原因：prefork 池不支持 Windows（06 §4 第 1 坑）→ 正解：`--pool=solo`；
- 症状：Celery 任务里 `RuntimeError: no running event loop` → 原因：任务是同步上下文 → 正解：任务体 `asyncio.run(_ingest_async(...))` 单点入口；
- 症状：重试后 chunks 翻倍 → 原因：切块步不幂等 → 正解：步骤 2 的"已有行则跳过"+唯一约束兜底；
- 症状：embedding 计量把 Tier 字面量改了 → 原因：弱模型顺手扩枚举 → 正解：tier 列是自由字符串，`Tier` 是 chat 契约（schema.py:14）**禁改**。

---

### §4.5 M3.5 多租户检索（L；00 §7.1）

**目标**：WHERE tenant_id + RLS 兜底的向量检索；召回完整性（iterative_scan / 小租户精确扫描）；轻量重排；阈值兜底；（若 P1 拍板"补"）长期记忆双过滤——默认按"砍出 v1"编写。

**契约事实源**：ADR-006（两层表述背熟：越权隔离=WHERE+RLS 硬保证；召回完整性=iterative_scan relaxed_order 或小租户精确扫描）、02 §7.2 第 3 层、00 M3.5 行（top-5/阈值/轻量重排）、spec.py:95（retrieval_budget=3_000）、00 §10.1 #7（槽位接入）。

**决策与口径**：重排是模块边界（`rerank.py` 内替换，cross-encoder 列 v2——00 §10.3）；阈值/精确扫描阈值实测后定（§3.5）；P1 裁决决定本步是否含长期记忆（默认不含）。

**实施蓝图**

新建：

| 文件 | 内容 |
|---|---|
| `aegis/apps/support/rag/retrieve.py` | Retriever（ADR-006 点名的隔离边界文件——"换实现不动调用方"） |
| `aegis/apps/support/rag/rerank.py` | 轻量重排纯函数 |

精确签名：

```python
@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: int; document_id: str; text: str
    similarity: float          # 1 - cosine距离
    score: float = 0.0         # 重排后综合分（rerank 填）
    meta: Mapping[str, Any] = field(default_factory=dict)

RETRIEVAL_SCORE_THRESHOLD = 0.35   # 占位，实测后定（§3.5）
EXACT_SCAN_MAX_CHUNKS = 10_000     # 同上

class Retriever:
    def __init__(self, factory: SessionFactory, embedder: EmbeddingClient,
                 *, top_k: int = 5, threshold: float = RETRIEVAL_SCORE_THRESHOLD) -> None: ...
    async def search(self, tenant_id: str, query: str) -> list[RetrievedChunk]:
        """空列表 = 检索失败（全部低于阈值或无语料）——调用方走兜底话术，宁可说不知道。"""
```

`search` 编号算法：
1. `embedder.embed([query], tenant_id=...)` 取查询向量；
2. 事务内（钩子已 set_config——RLS 兜底生效）查租户 chunk 数（进程内缓存 60s）；
3. `count <= EXACT_SCAN_MAX_CHUNKS` → `SET LOCAL enable_indexscan = off`（精确扫描：万级全扫既正确又够快，ADR-006 备选即主选的合法性来自租户规模设定 01 §5）；否则 → `SET LOCAL hnsw.iterative_scan = relaxed_order`（pgvector ≥0.8.0）；
4. SQL：`SELECT id, document_id, text, meta, 1 - (embedding <=> :qvec) AS similarity FROM chunks WHERE tenant_id = :tid AND embedding IS NOT NULL ORDER BY embedding <=> :qvec LIMIT :k*3`（取 3 倍候选喂重排；**WHERE tenant_id 显式写，绝不"反正有 RLS"**——应用层强制是第一防线，02 §7.2）；
5. `rerank.rerank(query, hits)` → 按 score 降序取 top_k；
6. `所有 score < threshold` → 返回 `[]`。

`rerank.py` 签名与规则（00 M3.5 行："关键词覆盖+元数据规则"）：

```python
def keyword_coverage(query: str, text: str) -> float: ...
    # CJK 二元组 + 非 CJK 词的覆盖率 ∈ [0,1]，零分词依赖（与 tokens.py 同哲学）
def rerank(query: str, hits: Sequence[RetrievedChunk]) -> list[RetrievedChunk]: ...
    # score = 0.7 * similarity + 0.3 * keyword_coverage；meta 规则位（如 meta["priority"] 加成）留注释挂点
```

ContextBuilder 槽位接入（#7）：【开工核对 0-5】拿到 M2.5 槽位真实形状后，在 M3.8 装配处把 `Retriever.search` 适配成槽位需要的 callable；检索文本注入前用 `estimate_tokens` 裁进 `retrieval_budget`（3_000，spec.py:95）；**检索结果按 M2.8 口径包裹"不可信数据"标记**（02 §7.3——具体标记格式以 M2.8 实装为准，【开工核对 0-11】）。长期记忆若 P1 拍板砍：`memory_budget` 保持槽位空置；本步与 03 §3 的"tenant_id+user_id 双过滤"叙述由拍板结果同步修订文档。

**测试蓝图**：`tests/apps/test_rerank.py`（纯函数：覆盖率单调、CJK/英文混合、空 query）、`tests/apps/test_retrieval.py`（集成，假 embedder 注入固定向量：跨租户不可见【对抗①的单测版】、阈值全低返回空、top_k 截断、IS NOT NULL 过滤半成品 chunk、iterative_scan/精确扫描分支各跑一次【断言 SET 语句可用事件捕获或小/大数据集行为】）。预期 +12–18。

**验收**：租户 A 语料真实检索（开发调试真实 embedding）命中合理；租户 B 查 A 专有名词返回空；`retrieve.py` 是检索唯一入口（Grep 无第二处 `<=>` 查询）。

**陷阱**：
- 症状：`SET hnsw.iterative_scan` 报 unrecognized parameter → 原因：pgvector <0.8 或扩展未升级 → 正解：§0 0-17 已核版本；容器重建后重跑 `CREATE EXTENSION`/`ALTER EXTENSION vector UPDATE`；
- 症状：小租户偶发漏召回 → 原因：HNSW 索引内后过滤（ADR-006 两层表述的第二层）→ 正解：本步的两个开关就是答案，别去调 ef_search 碰运气；
- 症状：`<=>` 返回的是距离却当相似度比阈值 → 原因：余弦**距离**（0=同向）→ 正解：`1 - 距离`，阈值语义=相似度下限；
- 症状：SET LOCAL 不生效检索走了索引 → 原因：SET LOCAL 在事务外 no-op → 正解：确认查询与 SET 同事务（session.begin 块内）。

---

### §4.6 M3.6 意图路由（M；00 §7.1）

**目标**：fast 档单次分类调用（**不是 Agent**——ADR-002 决策 2：无循环、无工具）：FAQ 直答（含精确缓存命中直接流式返回）/ RAG / 工具 / 转人工 四分支。

**契约事实源**：02 §2 ⑤（时序：FAQ/缓存命中→直接流式返回旅程结束；复杂意图→启动循环）、ADR-002 决策 2、02 §4 档位语义（fast=意图分类）、00 §2.2 C34（分诊挂→直走主 Agent 标准档）、02 §4 缓存红线（"租户 A 高频问题在 B 侧不得命中"→ M3 对抗②）。

**决策与口径**：D7（直答轮照写事件——E11 裁决）、D8（fail-open→AGENT）。

**实施蓝图**

新建 `aegis/apps/support/intent.py`：

```python
class Intent(StrEnum):
    FAQ = "faq"          # 直答：单次调用即回，旅程结束
    RAG = "rag"          # 知识型：主 Agent（检索注入）
    TOOL = "tool"        # 业务操作型：主 Agent（工具）
    HANDOFF = "handoff"  # 用户点名人工/投诉升级：直接转人工
    AGENT = "agent"      # 分诊失败的 fail-open 落点（C34）：主 Agent 标准档

INTENT_PROMPT = "..."   # 分类 prompt 常量：要求只输出 faq/rag/tool/handoff 四词之一

async def classify(gateway: GatewayLike, text: str, *, tenant_id: str,
                   session_id: str) -> Intent:
    """一次 fast 档调用（LLMRequest(tier="fast", deadline_s=10.0, ...)），
    消费流至 stop 拼接文本；strip 后不在四词表 → Intent.AGENT；
    任何网关异常（六类）→ Intent.AGENT（fail-open，C34）。绝不重试、绝不带工具。"""

async def answer_faq(gateway: GatewayLike, question: str, *, tenant_id: str,
                     session_id: str, faq_digest: str) -> AsyncIterator[str]:
    """FAQ 直答：单次 fast 档调用（system=租户 FAQ 摘要 faq_digest，来自 tenants.config["faq"]），
    流式产出文本。同问重复到达时由网关精确缓存命中直接回放（<50ms 验收即此路径）。"""
```

分支接线（chat 服务层，M3.8/M3.10 汇合处）：
- `FAQ` → `answer_faq` 流式直出 → **写 assistant_message 事件（D7）** → done；
- `RAG`/`TOOL`/`AGENT` → 启动主 Agent（`AgentRuntime.run`）——v1 主 Agent 同时具备检索与工具，RAG/TOOL 的区分只影响是否预热检索（RAG 分支先跑 Retriever 一次注入首轮），不产生两个不同 Agent（ADR-002 单 Agent 决策 1）；
- `HANDOFF` → M3.8 `create_handoff` 直通。

不变量：classify 的请求**不带 tools、不进循环**；缓存隔离无需本步做任何事——`ExactCache._key` 天然带租户前缀（cache.py:38-42），对抗②测试在 M3.12 验证这一点。

**测试蓝图**：`tests/apps/test_intent.py`（FakeGateway/手写 stub：四词各归其类、大小写/空白容错、幻觉输出→AGENT、网关抛 GatewayExhausted→AGENT、请求断言 tier=="fast" 且 tools==[]）。FAQ 直答事件落盘断言并入 M3.10 集成测试。预期 +8–12。

**验收**：四分支单测全绿；开发调试实测一次分类延迟（fast 档应 <1s，记录供 M3.12 参考）。

**陷阱**：
- 症状：分类结果偶发"faq。"/"分类：faq" → 原因：模型加料 → 正解：解析做 strip+去标点+子串匹配白名单，仍不中→AGENT，**不要**为此上 JSON mode 或重试（一次调用的口径是 ADR-002 红线）；
- 症状：把意图路由写成带工具的小循环 → 原因：弱模型把"路由"脑补成 Agent → 正解：ADR-002 决策 2 原文"**不是 Agent**（无循环、无工具）"。

---

### §4.7 M3.7 模拟业务系统 + 工具五件（L；00 §7.1）

**目标**：进程内 FastAPI 子应用（延迟/错误率注入可配）；orders/logistics/tickets/refunds/coupons 五工具；**幂等键下游去重实装（#6 闭环）**；归属校验在工具实现内强制。

**契约事实源**：02 §7.2 第 2 层（LLM 可控参数与注入参数严格分离；归属校验 `order.user_id == ctx.user_id`；对抗③）、tools.py:37-59（ToolContext/RiskPolicy）、executor.py 生命周期（write-ahead 键即 `ctx.tool_call_id`）、02 §5 故障表（"双击发送不产生两笔退款"）、01 §5（两租户工具面：A=订单/物流/退款，B=订单/优惠券）、00 §11（coupons 可砍半天）。

**决策与口径**：D9（ASGITransport + PG 双表）；退款阈值从 `tenant_config["approval_threshold"]` 读（01 §5：200 是租户 A 配置项非常量）。

**实施蓝图**

新建：

| 文件 | 内容 |
|---|---|
| `aegis/apps/support/mock_backend/__init__.py`、`app.py` | `mock_api = FastAPI()` 子应用 + 故障注入中间件 |
| `aegis/apps/support/mock_backend/models.py` | MockOrderRecord / MockWriteOpRecord ORM（env.py 加 import） |
| `aegis/apps/support/mock_backend/client.py` | `def mock_client() -> httpx.AsyncClient`（ASGITransport 懒单例，仓库 global 单例惯例） |
| `aegis/apps/support/tools/{orders,logistics,tickets,refunds,coupons}.py` | 五个 `@tool` |
| `migrations/versions/xxxx_mock_backend.py` | 两表（RLS 覆盖名单内，见 §4.3） |
| `aegis/core/config.py`（改） | +`mock_latency_ms: int = 0`、`mock_error_rate: float = 0.0`（注入可配，prod 校验器同故障注入哲学） |

表结构：

`mock_orders`：`id String(64) PK / tenant_id String(64) idx / user_id String(64) idx / status String(16)（paid/shipped/delivered/refunded）/ paid_amount Numeric(12,2) / items JSONB / created_at`。

`mock_write_ops`（**#6 的事件 id 去重表**）：

| 列 | 类型 | 约束 |
|---|---|---|
| idempotency_key | String(64) | **PK**——值=透传的 tool_call 事件 id（tools.py:40-41 契约的下游端） |
| kind | String(16) | NOT NULL（refund/coupon） |
| tenant_id | String(64) | NOT NULL idx |
| payload | JSONB | NOT NULL（订单号/金额/结果快照） |
| created_at | DateTime(tz) | server_default now() |

mock 端点（`mock_api` 内，路径挂主 app `/mock` 前缀）：
- `GET /orders/{order_id}`（query 参数 tenant_id/user_id 由工具注入——mock 系统信任内部调用方）；
- `GET /logistics/{order_id}`（由订单派生伪轨迹）；
- `POST /tickets`；
- `POST /refunds`：**去重算法**（编号，唯一伪代码点）：

```
1. key = 请求头 Idempotency-Key（缺失 → 400，逼调用方永远带键）
2. INSERT INTO mock_write_ops(idempotency_key, kind='refund', ...)
   ON CONFLICT (idempotency_key) DO NOTHING
3. rowcount == 0 → SELECT 既有行 → 返回其 payload + {"duplicate": true}（200，不再执行）
4. rowcount == 1 → 校验订单可退（status/金额）→ UPDATE mock_orders 置 refunded
   → payload 回填结果 → 返回 {"duplicate": false, ...}
```
- `POST /coupons`：复用同表 kind='coupon' 同算法（半天规模来源）。

故障注入中间件：按 `mock_error_rate` 概率回 503、`mock_latency_ms` 注入延迟——演示"工具超时→X1 结果不明→查询确认"的剧本用（executor.py 的 RESULT_UNKNOWN 话术在真实链路上演）。

五工具签名（description 即 docstring 给模型看的说明书——tools.py:126-148 机制）：

```python
# tools/orders.py
@tool(side_effect=SideEffect.READ)
async def order_query(ctx: ToolContext, order_id: str) -> dict: ...
# tools/logistics.py
@tool(side_effect=SideEffect.READ)
async def logistics_query(ctx: ToolContext, order_id: str) -> dict: ...
# tools/tickets.py（低危写显式豁免——与演示工具集三形态对齐）
@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def ticket_create(ctx: ToolContext, title: str, detail: str = "") -> dict: ...
# tools/refunds.py
def refund_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    return bool(args.amount > tenant_config.get("approval_threshold", 200))
@tool(side_effect=SideEffect.WRITE, risk_policy=refund_needs_approval)
async def refund_apply(ctx: ToolContext, order_id: str, amount: float) -> dict: ...
# tools/coupons.py（补发有面额上限：本计划定死"带闸门"，与退款同款写工具形态一致——C15）
# coupon_threshold 为本计划新增的租户 config 键（00/01/02 均无出处——租户 B 侧 approval_threshold 的对应物，
# 值在 M3.11 种子脚本给定并回填 02 §3 config 说明）；缺省 0 = 任意正面额都挂审批（安全闸门 fail-closed 缺省）
def coupon_needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    return bool(args.amount > tenant_config.get("coupon_threshold", 0))
@tool(side_effect=SideEffect.WRITE, risk_policy=coupon_needs_approval)
async def coupon_grant(ctx: ToolContext, order_id: str, amount: float) -> dict: ...
```

工具体内不变量（每个工具第一段）：
1. **归属校验 fail-closed**：查单后 `order.tenant_id != ctx.tenant_id or order.user_id != ctx.user_id` → 返回 `{"error": "订单不存在或无权操作"}`（**不区分两种失败**——不泄露他租户/他人订单存在性；对抗③在此被拒）；
2. 写工具调 mock 时请求头 `Idempotency-Key: ctx.tool_call_id`（#6 契约闭环——M2.4 透传的钥匙第一次真的开锁）；
3. 工具返回 dict（executor `json.dumps` 序列化，executor.py:210）；错误也用 dict 回业务话术，**不抛业务异常**（异常只留给基础设施——executor.py:5-6 分界）。

**测试蓝图**：`tests/apps/test_mock_backend.py`（去重：同 Idempotency-Key 双击仅一笔 + duplicate 标记；缺键 400；订单状态流转）、`tests/apps/test_tools_ownership.py`（对抗③单测版：用户 A 的 ctx 报用户 B 订单→"不存在或无权"；跨租户同理；错误文案不泄露差异）、`tests/apps/test_tools_contract.py`（五工具 schema 快照：ctx 不在 parameters_schema、写工具闸门/豁免声明齐全【C15 类型层本就拦，但 L3 工具集编成清单钉死】、refund 阈值边界 200/200.01）。预期 +20–30。

**验收**：真实链路（开发调试）让 Agent 查单退款一次成功；双击重发演示 `duplicate: true`；对抗③话术正确。

**陷阱**：
- 症状：ASGITransport 下 mock 的 startup 钩子没跑 → 原因：ASGITransport 不触发 lifespan → 正解：mock_api 不用 lifespan，状态初始化走迁移+种子脚本；
- 症状：金额比较偶发错 → 原因：float 金额 → 正解：库列 Numeric(12,2)，比较在 SQL/Decimal 侧做；工具参数 float 进来立即 `Decimal(str(amount))`（executor `_kwargs` 保真类型的哲学延伸）；
- 症状：把归属校验做成 risk_policy → 原因：混淆两道闸门 → 正解：归属是**权限**（fail-closed 拒绝，02 §7.2 第 2 层），risk_policy 是**风险**（放行但要人批）；归属校验必须在工具体内，闸门谓词里没有 ctx；
- 症状：LLM 幻觉 `user_id` 参数被接受 → 原因：工具签名把身份参数暴露了 → 正解：身份只从 ctx 来（tools.py:112-113 机制拦 ctx，但**不要**在业务参数里再开 user_id 口子）。

---

### §4.8 M3.8 主 Agent 装配 + 转人工（M；00 §7.1）

**目标**：`apps/support/agent.py` 组装 AgentSpec（prompt/工具集/策略/租户配置注入）；handoff（转人工=工单+上下文摘要）；检索失败/循环达上限的兜底话术。

**契约事实源**：spec.py:130-157（AgentSpec 全字段+防呆）、spec.py:56-57（session_token_budget 由 L3 注入）、ADR-007:38-39（v1 转人工=创建工单+上下文摘要）、`EventType.HANDOFF`（events.py:38）、02 §2 兜底路径、`AgentRuntime.run`（runtime.py:39）。

**决策与口径**：工具面按租户 config 白名单（01 §5：A=订单/物流/退款，B=订单/优惠券；tickets 为 00 §7.1 M3.7 行五工具之一，A 侧因 handoff 建工单需要而加装——本计划决策，01 §5 无此项）；system prompt 是平台规则+租户名的模板常量，不进库（prompt 变更走代码提交——M4.3 "prompt 变更 PR 附重录 diff"依赖它可 diff）；**FAQ 直答守卫（M3.6 后置修订⑴，14f——本步承接）**：service.py 分支接线处，FAQ 分支仅当会话无历史（首条消息）才走 answer_faq 直答，有历史判 faq 一律按 AGENT 进主 Agent——封"指代上文的跟进问"上下文盲窗，确定性判定不靠分类器判自足性；**同笔顺路交付 INTENT_PROMPT 修订（后置修订⑵）**：faq 行加"仅当消息不依赖上文即可完整理解"限定+末尾跟进问排除句（M3.11 录制前的免费修订窗，intent.py 一处字符串）。

**实施蓝图**

新建：

| 文件 | 内容 |
|---|---|
| `aegis/apps/support/agent.py` | 装配器 |
| `aegis/apps/support/prompts.py` | `SYSTEM_PROMPT_TEMPLATE`、`FALLBACK_NO_RETRIEVAL`、`FALLBACK_LOOP_LIMIT` 等话术常量 |
| `aegis/apps/support/handoff.py` | 转人工 |
| `aegis/apps/support/service.py` | chat 编排层（intent→分支→run 的汇合点；M3.2 端点收敛调用它，M3.10 流式化它） |

精确签名：

```python
# agent.py
ALL_TOOLS: dict[str, ToolDef] = {...}  # 五工具注册清单（name→ToolDef），模块级常量

def build_agent_spec(tenant: TenantRecord) -> AgentSpec:
    """依赖倒置的落点：
    1. tools = tuple(ALL_TOOLS[n] for n in tenant.config.get("tools", []))——未知名报 ValueError（配置错启动炸）；
    2. policy = LoopPolicy(session_token_budget=int(tenant.config.get("session_token_budget", 50_000)))
       其余阈值走默认（spec.py:61-66）；
    3. context_config：默认；P1 若砍长期记忆→ ContextConfig(memory_budget=0)（显式关闭，spec.py:87-89 允许）；
    4. tenant_config = dict(tenant.config)（原样透传，运行时不解释——spec.py:136-138）；
    5. model_tier = "standard"。"""

# handoff.py
async def create_handoff(*, factory: SessionFactory, session_id: str, tenant_id: str,
                         user_id: str, reason: str, summary: str) -> dict:
    """经 mock_client 调 POST /mock/tickets 建工单；summary 取 sessions.summary
    （M2.5 滚动摘要投影，store.py:85）非空则用之，否则拼最近 messages 3 条；
    工单号+reason 进返回 dict。handoff 事件由调用方（service 层持 EventWriter 者）写——
    单写者纪律，本函数不碰事件流。"""

# service.py
class ChatService:
    def __init__(self, *, gateway: GatewayLike, factory: SessionFactory,
                 directory: TenantDirectory, retriever: Retriever) -> None: ...
    async def handle(self, *, principal: Principal, session_id: str,
                     message: str) -> AsyncIterator[ChatFrame]: ...
    # ChatFrame 是 M3.10 帧模型（本步先定义数据类，M3.2 的占位响应即消费其非流式子集）
```

兜底路径接线（02 §2）：
- 检索空（Retriever 返回 []）→ 注入 `FALLBACK_NO_RETRIEVAL` 指令（"明确告知知识库无此内容，建议转人工"），不硬答——"宁可说不知道"（00 M3.5 行）；
- run 终止原因 ∈ TERMINATION_GATES（spec.py:40-45）中的 MAX_ITERATIONS/TOKEN_BUDGET_EXCEEDED → service 层补发 `FALLBACK_LOOP_LIMIT` 话术 + `create_handoff(reason="loop_limit")` + handoff 事件；
- 用户点名转人工（Intent.HANDOFF）→ 直通 create_handoff。

不变量：L3 绝不 import `aegis.gateway.providers.*` / router 内部件（02 §1"L3 不直接碰供应商 SDK"）；ChatService 只见 `GatewayLike` 与 `AgentRuntime`。

**测试蓝图**：`tests/apps/test_agent_assembly.py`（租户 A/B 配置→工具面正确且顺序稳定、未知工具名炸、预算注入进 policy、memory_budget=0【若 P1 砍】、tenant_config 原样透传【断言 spec.tenant_config["approval_threshold"]==200】）、`tests/apps/test_handoff.py`（工单创建、summary 回退拼接、reason 进 payload）。run 全链路行为用 FakeGateway cassette（M2.6 基建）驱动 1–2 条端到端（检索空→兜底；正常工具轮）。预期 +8–12。

**验收**：真实调用演示租户 A 全链路（查单→退款 80 元→直接执行）；租户 B 只见自己的两个工具（trace 里 tools 列表可证）。

**陷阱**：
- 症状：`AgentSpec` 构造即炸"工具名重复" → 原因：ALL_TOOLS 清单与租户 config 拼接时重复引入 → 正解：spec.py:154-157 防呆是帮手不是敌人，装配器用 dict 去重语义；
- 症状：给 B 租户也装了 refunds"反正闸门会拦" → 原因：弱模型图省事 → 正解：工具面=攻击面，白名单按租户 config，一个不多；
- 症状：service 层自己 new EventWriter 又在 run 里有一个 → 原因：不了解单写者约束 → 正解：一次 run 一个写者（store.py:288），事件写入归属按 0-7/0-8 核对的 M2.7/M2.9 实况分配。

---

### §4.9 M3.9 HITL 业务闭环（L；00 §7.1）

**目标**：审批 API（approve/reject，强制同租户）+ curl 演示；expires_at 超时（reaper 扫描 + approval_expired 事件）；用户撤回（M3.2 已建）；**批准后前置校验重跑（#8 实装，TOCTOU 显式防）**；approval_pending 提示。

**契约事实源**：`ApprovalStore` 四方法（store.py:401-476；decide 过期 fail-closed C7、expire_due RETURNING+可注入时钟）、`ix_approvals_expiry`（store.py:151-153，"M3.9 reaper 消费"）、02 §2 ⑩（挂起/重订阅/恢复单入口）、02 §7.1 矩阵行+02 §7.2 后注（跨租户 403 对抗④）、00 §10.1 #8、审批单不挂 tool_invocation FK 的口径（store.py:146-147）。

**决策与口径**：审批单 `expires_at` 生成值 = 创建时刻 + `tenants.config.get("approval_ttl_s", 86400)`（租户可配，缺省 24h——02 未给值，唯一合理答案：跟审批阈值同属租户配置）；reaper 扫描周期 60s（beat 配置，演示可用可注入时钟加速）。

**实施蓝图**

新建/修改：

| 文件 | 内容 |
|---|---|
| `aegis/api/approvals.py`（新） | `POST /v1/approvals/{approval_id}` |
| `aegis/apps/support/revalidate.py`（新） | 前置校验谓词（注入 M2.9 挂点） |
| `aegis/workers/reaper.py`（改，M2.10 交付基础上） | +审批到期扫描任务 |
| `scripts/demo_hitl.ps1`（新） | curl 演示序列（用 `curl.exe` 非 PS 别名——Windows PowerShell 5.1 中 `curl` 是 Invoke-WebRequest 别名，06 §4 未收录、属同族 PowerShell 坑） |

审批 API 形状：

```python
class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]

# handler 编号算法：
# 1. require_roles(OPERATOR, ADMIN)；
# 2. 读审批单；operator 且 principal.tenant_id != approval.tenant_id → 403（对抗④；admin 平台级放行——矩阵 ✅ 无限定）；
# 3. ApprovalStore.decide(approval_id, approved=..., operator_id=principal.user_id)
#    → False = 已过期/已翻转（C7 fail-closed 语义原样透出）→ 409 {"detail": "审批单已失效或已处理"}；
# 4. True → 触发恢复：走 M2.9 "先取会话锁再恢复"单入口【开工核对 0-8 的函数】——
#    API 层只做状态翻转+踢一脚恢复，绝不在 handler 里执行工具（02 §2 恢复调度原文）。
```

前置校验重跑（#8 实装；防 TOCTOU——批准时订单状态/可退余额可能已变）：

```python
# revalidate.py
async def revalidate_refund(args: Mapping[str, Any], ctx: ToolContext) -> str | None:
    """None=通过；str=拒绝原因。重查 mock 订单：status 仍可退？paid_amount ≥ args['amount']？
    归属校验整套重跑（批准不豁免权限）。"""
REVALIDATORS: dict[str, Revalidator] = {"refund_apply": revalidate_refund, "coupon_grant": ...}
```

注入方式按【开工核对 0-6】的挂点真实签名；语义定死：重跑失败 → **不执行工具**，按"审批拒绝"路径回填 `f"前置校验失败，操作未执行：{原因}"` 给模型（fail-closed；审批的是参数快照 approvals.args——store.py:159，重跑对象就是这份快照）。

reaper 到期扫描任务（编号）：
1. beat 每 60s 触发 `expire_approvals` 任务（owner 引擎——D4）；
2. `expired_ids = await ApprovalStore.expire_due()`（CAS 批量翻 EXPIRED，与坐席 decide 赛跑由 rowcount 裁决——store.py:391-396）；
3. 逐单：取会话锁 → 写 `approval_expired` 事件 → 该 run 按闸门 6 终止（`TerminationReason.CANCELLED`——spec.py:36 注释"取消/HITL 拒绝或超时"）→ run_state 复位。步骤 3 复用 M2.9 恢复单入口的"拒绝/超时"分支【开工核对】。

approval_pending 提示：service 层在 outcome=NEEDS_APPROVAL→挂起完成后产出 `approval_pending` 帧（M3.10 帧表）载荷 `{approval_id, tool_name, expires_at}`；M3.9 先以 JSON 形态返回（M3.2 占位协议），M3.10 换帧。

**测试蓝图**：`tests/api/test_approvals.py`（**对抗④**：A 坐席批 B 单 403；admin 放行；user 角色 403【矩阵】；approve→decide True→恢复入口被调【假恢复 spy】；过期单 decide→409；重复决策 409）、`tests/apps/test_revalidate.py`（余额不足拒、状态已退拒、通过 None、归属重跑拒）、`tests/workers/test_reaper_approvals.py`（可注入时钟：到期单翻 EXPIRED+事件落盘+终止路径触发；未到期不动——复用 `expire_due` 既有单测思路，见 tests/runtime/test_approvals.py:test_expire_due_with_injected_clock 风格）。预期 +12–18。

**验收**（对齐 00 §7.2 第三条）：退款 >200 必挂审批；审批期间提示可见；批准→**先重跑前置校验**→执行→自动续跑；超时/撤回各演示一次（`scripts/demo_hitl.ps1` 四段：挂起/批准/超时/撤回）。

**陷阱**：
- 症状：批准后直接执行工具跳过重跑 → 原因：图快 → 正解：TOCTOU 是本步存在的理由（00 M3.9 行加粗"显式防"）；重跑失败路径必须有测试；
- 症状：reaper 翻了 EXPIRED 但 run 永远挂着 → 原因：只翻单没走终止 → 正解：步骤 3 三件事一个都不能少（事件+终止+复位），且都在持锁下做；
- 症状：坐席窗口批准与 reaper 同秒赛跑双赢 → 原因：臆想的并发 bug → 正解：CAS 已保证恰一个赢家（store.py:391-396），测试断言输家拿 False 即可，别加锁叠床架屋；
- 症状：demo 里 PowerShell `curl` 报参数错 → 原因：`curl` 是 Invoke-WebRequest 别名 → 正解：`curl.exe`（06 §4 未收录，属同族 PowerShell 坑）。

---

### §4.10 M3.10 SSE 双通道 + 聊天页（L；00 §7.1）

**目标**：`POST /v1/chat` SSE 流式；`GET /v1/sessions/{id}/stream?after_seq=N` 重订阅通道；进行中消息 Redis 缓冲、重连整条重推；跨副本事件通知（PG LISTEN/NOTIFY——C22，00 步骤行漏写、本计划补）；单文件聊天页。

**契约事实源**：ADR-007 全文（双通道决策、五帧、续传两边界、Nginx 两坑）、02 §2 ⑨⑩⑮（出口守卫在通道上生效、挂起换通道、done 帧内容）、02 §9（端点表）、00 §2.2 C22 行 + X5（trace_id ≡ session_id）、ADR-005 角色1（进行中消息缓冲的 Redis 角色）、events.py:43（"SSE 逐 token 是通道问题"——token 帧不是 AgentEvent）。

**决策与口径**：D10（PG 触发器 NOTIFY）、D11（GET 通道帧协议补全）。

**帧协议全表（ADR-007 五帧逐个列出 + E5 缺口补齐；SSE 线格式 `event:`=帧名、`data:`=JSON、GET 通道另带 `id:`=seq）**：

| 帧 | 通道 | data 字段 | 语义 |
|---|---|---|---|
| `token` | POST/GET | `{"text": str}` | 增量文本（已过 M2.8 出口守卫的句子缓冲——02 §2 ⑨） |
| `tool_status` | POST/GET | `{"tool_name": str, "status": "running"\|"ok"\|"error"\|"result_unknown"\|"disabled"}` | 工具进度（值域=OutcomeKind 词汇，executor.py:24-31） |
| `approval_pending` | POST/GET | `{"approval_id": str, "tool_name": str, "expires_at": str}` | 挂起提示；客户端收到后关 POST 流、改挂 GET 通道（ADR-007:17-19） |
| `done` | POST/GET | `{"trace_id": str, "usage": {"prompt_tokens": int, "completion_tokens": int}}` | trace_id ≡ session_id（X5）；usage 从本轮 usage_ledger 聚合 |
| `error` | POST/GET | `{"message": str}` | 终止性错误（六类网关异常的用户话术投影） |
| `message_reset` | **仅 GET** | `{"text": str}` | 重连/续跑首帧：进行中 assistant 消息**整条重推**，前端覆盖半句话（ADR-007:33 语义的帧名落地，D11） |

**实施蓝图**

新建/修改：

| 文件 | 内容 |
|---|---|
| `aegis/api/sse.py`（新） | 帧模型 + 编码器 |
| `aegis/api/chat.py`（改） | 占位响应换 `StreamingResponse(media_type="text/event-stream")` |
| `aegis/api/stream.py`（新） | GET 重订阅端点 |
| `aegis/api/notify.py`（新） | LISTEN 管理器 |
| `aegis/api/events_view.py`（新） | `GET /v1/sessions/{id}/events`（矩阵：operator+ 限本租户；终端用户 ❌；00 步骤行未写归属，本计划排入本步——U14）——M4.1 trace API 的底座，本步只出原文 JSON；**审计留痕**：每次访问写一行结构化日志（principal.user_id/role/tenant_id + session_id——02 §7.3"仅 operator+ 可访问**且留审计**"的最小落地；审计事件化/落表随 M4.1 masker 一并加固，在 02 §7.3 侧登记推迟） |
| `migrations/versions/xxxx_events_notify.py`（新） | AFTER INSERT 触发器（D10） |
| `aegis/web/chat.html`（新） | 单文件聊天页（无构建链——01 §5） |

精确签名：

```python
# sse.py
@dataclass(frozen=True, slots=True)
class ChatFrame:
    event: Literal["token", "tool_status", "approval_pending", "done", "error", "message_reset"]
    data: Mapping[str, Any]
    seq: int | None = None    # GET 通道回放事件时填=events.seq，编码为 SSE id:
def encode_frame(f: ChatFrame) -> str: ...   # "event: ...\ndata: {...}\n\n"（data 单行 JSON，ensure_ascii=False）

# notify.py
class EventNotifier:
    """独立 asyncpg 原生连接 LISTEN aegis_events；按 session_id 分发唤醒。
    连接断开→自动降级：等待方转 after_seq 轮询（间隔 2s），恢复后自愈（C22 兜底口径）。"""
    async def start(self) -> None: ...
    async def wait_for(self, session_id: str, *, timeout_s: float) -> None: ...
    async def stop(self) -> None: ...

# stream.py 端点算法（编号）：
# 1. 认证+归属校验（#19：user 仅本人会话，operator 本步不需要——矩阵该端点 user ✅/admin ✅）；
# 2. after_seq = max(query 参数, Last-Event-ID 请求头)（EventSource 重连自动带后者——ADR-007:18）；
# 3. 回放：SELECT events WHERE session_id=? AND seq>after_seq ORDER BY seq——
#    翻译成帧（assistant_message→token 整段、tool_call/result→tool_status、approval_*→approval_pending、
#    loop_terminated/handoff→done/error 话术）；每帧带 id:=seq；
# 4. 若 Redis 缓冲有进行中 assistant 半条 → 先发 message_reset(整条现状)；
# 5. 进入活尾：EventNotifier.wait_for 唤醒→增量查→推帧；run 结束（done/error）→ 关流。
```

Redis 进行中消息缓冲（ADR-005 角色1）：key `aegis:msgbuf:{session_id}`，value=当前 assistant 已生成全文，`SETEX` TTL 3600；POST 流每过守卫放行一段就 append（`SET` 全量覆盖，值小）；done 时 DEL。Redis 挂 → 缓冲跳过（快速失败客户端），重连时 message_reset 只含已落盘部分——降级留痕日志，不拖垮主链路（00 §2.2 复盘补丁二口径）。

触发器迁移（D10）：

```sql
CREATE OR REPLACE FUNCTION notify_aegis_event() RETURNS trigger AS $$
BEGIN PERFORM pg_notify('aegis_events', NEW.session_id || ':' || NEW.seq); RETURN NULL; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_events_notify AFTER INSERT ON events
  FOR EACH ROW EXECUTE FUNCTION notify_aegis_event();
```

聊天页要点（单文件 `chat.html`，原生 JS）：fetch 手写 POST 流解析（几十行——ADR-007 后果栏）；收到 `approval_pending` 关 POST 流开 `EventSource('/v1/sessions/{id}/stream?after_seq=N')`；`message_reset` 覆盖当前气泡；发送按钮在 409 时禁用并提示（02 §2 ③ v1 策略）；token 从 `scripts/mint_token.py` 拿了填输入框（演示形态）。

部署清单条目（写进 README/部署段，M5.3 消费）：Nginx `proxy_buffering off` + `proxy_read_timeout` 调大（ADR-007:26-27）；uvicorn `--timeout-graceful-shutdown` 设短值（02 §5 crash-only）。

**测试蓝图**：`tests/api/test_sse_frames.py`（encode_frame 线格式快照、六帧 data 字段齐全性、id: 仅 GET 帧带）、`tests/api/test_stream_resume.py`（预置事件流→after_seq 续传帧序正确、Last-Event-ID 优先级、归属 404、message_reset 在缓冲存在时先发【fixture `r` 预置 msgbuf】）、`tests/api/test_chat_sse.py`（FakeGateway 驱动 POST 流：token…done 帧序、approval_pending 出现后流关闭、error 帧对 GatewayExhausted 的翻译、FAQ 直答轮 user/assistant 事件落盘【D7 断言点】）。LISTEN/NOTIFY 集成测 1 条（真 PG：insert 事件→wait_for 在超时前返回）；轮询降级单测（notifier 注入断连）。预期 +12–18。

**验收**：聊天页全旅程可用（直答/工具/审批挂起→重订阅续收）；断网重连半条消息整条重推肉眼可见；`curl.exe -N` 能看裸帧。

**陷阱**：
- 症状：本地流式没问题、加 Nginx 后一次性吐全文 → 原因：proxy_buffering（ADR-007 两坑之一）→ 正解：部署清单条目，M5.3 复验；
- 症状：GET 通道换 tab 后重复收整段历史 → 原因：EventSource 重连未带 after_seq/Last-Event-ID 处理 → 正解：id: 字段必须每帧都写，服务端优先信 Last-Event-ID；
- 症状：LISTEN 用了 SQLAlchemy 池里的连接，随事务归还后失聪 → 原因：LISTEN 绑定物理连接 → 正解：EventNotifier 用独立 `asyncpg.connect()` 原生连接（不从池借）；
- 症状：NOTIFY 在测试里收不到 → 原因：payload 在事务提交才发（这是特性），测试没 commit → 正解：真提交（不用回滚夹具）；
- 症状：token 帧绕过出口守卫直发 → 原因：把守卫当 L2 内部事 → 正解：02 §2 ⑨——流式出口检查就是为这条通道设计的，接线【开工核对 0-11】；
- 症状：`StreamingResponse` 首帧迟迟不出 → 原因：反压/缓冲，或忘 `headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}` → 正解：加头 + 每帧后确保 flush（yield 即 flush，勿在生成器里攒批）。

---

### §4.11 M3.11 种子评测集 + 演示数据（M；00 §7.1）

**目标**：15–20 条种子用例（≥10 隔离对抗 + 5 知识库外，文件形态——落表在 M4.4）；L3 行为 cassette 录制（预算写死）供 M4.3 CI 回归；每租户 10–20 篇语料；种子订单脚本。

**契约事实源**：00 M3.11 行、01 §5（两租户设定：A 数码商城/产品手册+售后政策，B 生鲜超市/配送范围+会员规则；"两租户数据互相不可见是验收场景"）、01 §6（评测集 ≥30 条中 M3 出 15–20）、ADR-006:65（含检索质量子集：标注 query→应命中 chunk）、M2.6 cassette 基建（【开工核对 0-10】）。

**决策与口径**：用例文件形态定为 **JSONL**：`evals/cases/seed.jsonl`（一行一例，M4.4 迁表时字段即列）；语料落 `data/corpus/{tenant-a,tenant-b}/*.md`；录制脚本预算常量写死（§3.1 第 3 条）。

**实施蓝图**

| 文件 | 内容 |
|---|---|
| `evals/cases/seed.jsonl`（新） | 15–20 条 |
| `evals/README.md`（新） | 字段说明+判据（M4.4 判据文档的前身） |
| `data/corpus/tenant-a/*.md` ×10–20、`data/corpus/tenant-b/*.md` ×10–20（新） | 演示语料（A：产品手册/售后政策含"退款>200 需审批"叙述；B：配送范围/会员规则；**两租户各含 FAQ 文档**——M3.6 后置修订⑶：FAQ 直答守卫收窄后，老会话里的自足 FAQ 问走主 Agent 检索路径，语料里没有 FAQ 内容=只能"宁可说不知道"，比直答更糟，14f）——语料内容 AI 直写（非生产代码） |
| `scripts/seed_demo.py`（改，M3.1 起步版扩全） | tenants(config 含 approval_threshold=200【A】/tools/faq) + users（每租户 user×2 + operator×1 + admin×1，跨用户订单对抗需要两个 user）+ mock_orders 种子 + 语料摄取触发 |
| `scripts/record_l3_cassettes.py`（新） | L3 行为 cassette 录制 |

用例 schema（JSONL 行）：

```json
{"id": "iso-01", "kind": "isolation", "tenant_id": "tenant-b", "user_id": "u-b1",
 "query": "灵犀降噪耳机 Pro 的保修政策是什么", 
 "expect": {"behavior": "fallback_or_handoff", "must_not_contain": ["灵犀", "保修 24 个月"]},
 "note": "A 租户专有产品名在 B 侧必须检索不到（对抗①素材）"}
```

`kind` 值域：`isolation`（≥10 条：跨租户知识/跨用户订单/跨租户审批各若干）/ `out_of_kb`（5 条：两租户知识库都答不了的问题，expect=fallback_or_handoff——M3.12 的 ≥95% 触发率分母）/ `retrieval`（检索质量子集：`expect.chunk_source` 标注应命中文档，ADR-006:65）/ `normal`（少量正例防"全拒也满分"）。

cassette 录制脚本要点：
1. 预算常量写死：`MAX_REAL_CALLS = 40`、`MAX_TOKENS = 100_000`（超即中止报错——00 M3.11 行"预算上限写死"）；
2. 录制清单（供 M4.3 行为断言）：隔离对抗 ×2（跨租户检索空、跨用户退款拒）、预算触发 ×1（session_token_budget 调小逼 TOKEN_BUDGET_EXCEEDED）、HITL 挂起-批准续跑 ×1、正常工具轮 ×1；
3. 全部经 M2.6 录制器与格式（敏感字段不入 cassette——M2.6 既定纪律）；产物落 `tests/cassettes/l3/`（目录名以 M2.6 实际布局为准【开工核对 0-10】）。

**测试蓝图**：`tests/evals/test_seed_cases.py`（文件 lint：JSONL 可解析、字段齐全、kind 配比达标 ≥10 isolation + ≥5 out_of_kb、id 唯一）；`tests/apps/test_seed_script.py`（种子脚本幂等：跑两遍不重复不报错——upsert 语义）。cassette 驱动的回放测试主体归 M4.3，本步只加 1–2 条冒烟（cassette 能被 FakeGateway 加载回放）。预期 +4–8。

**验收**：`uv run python scripts/seed_demo.py` 一键重建两租户全量演示数据（02 §5 备份口径兑现）；用例文件 lint 绿；cassette 录制在预算内完成并可回放。

**陷阱**：
- 症状：脚本相对路径把语料/用例写到别处 → 原因：cwd 依赖（记忆档案"脚本落盘锚定项目根"教训）→ 正解：`Path(__file__).resolve().parents[1]` 锚定仓库根；
- 症状：对抗用例只写"查不到"类 → 原因：偷懒 → 正解：isolation ≥10 条必须覆盖三面：知识（检索）、数据（订单归属）、动作（审批跨租户）；
- 症状：录制脚本跑飞烧钱 → 原因：循环重试无预算断路 → 正解：MAX_* 常量在循环头强制检查，超限 raise。

---

### §4.12 M3.12 毕业验收 + 整编（M；00 §7.1）

**目标**：00 §7.2 全量对账；性能口径实测（缓存命中 <50ms、未命中首 token <2.5s，本地口径实测修正）；报告落盘；毕业四件（tag `m3-support`）。

**契约事实源**：00 §7.2 毕业验收汇总四条（原样）、00 §13 毕业清单模板、02 §7.1 后注/02 §4 缓存红线（对抗②④文本）。

**实施蓝图**

| 交付 | 内容 |
|---|---|
| `tests/apps/test_adversarial.py`（新） | **四大对抗**进 CI（回放/夹具驱动，零真实调用）：① 跨租户检索不可见（B 查 A 语料→空）；② 租户 A 高频问题在 B 侧缓存不命中（同 prompt 两租户→cache key 不同，断言 B miss——可直测 `ExactCache._key` 前缀 + 端到端一条）；③ 水平越权退款被拒（A 用户报 B 用户订单）；④ A 坐席批 B 审批单 403 |
| `scripts/perf_m3.py`（新，真实调用） | 两口径实测：同问二连发（第二发应 <50ms 缓存命中）；未命中首 token 延迟 ×20 样本 P50/P95。**实测值若超设计值：修正记录而非改口径**（00 §7.2"本地口径实测修正"） |
| `scripts/fallback_rate_m3.py`（新，真实调用） | 5 条 out_of_kb 用例逐条跑：兜底/转人工触发率 ≥95%（种子集口径）；未触发逐条人工归因写进报告——**不承诺 100% 零编造**（00 §7.2 原文，绝对值是被攻击点） |
| `reports/m3_acceptance.md`（新） | 四对抗结果 + 两性能数字（含口径限定语）+ 兜底率 + 归因 |
| 毕业四件 | CI 全绿 → tag `m3-support` → 记忆更新 → 00 更新（§7 标 ✅ + §6.3 式对账表 + §10.1 翻转 #6/#7/#8/#13/#17/#18/#19/#21/#22【#20 按拍板】）+ 本文件头部回填「实际落地偏差」 |

**验收对账（缺一不算毕业，00 §7.2 原样）**：
- [ ] 四大对抗全绿；
- [ ] 精确缓存命中 <50ms；未命中首 token <2.5s（本地口径，实测修正记录）；
- [ ] 退款超阈值（租户 A 配置 200 元）必挂审批；期间 approval_pending 提示；批准后先重跑前置校验再执行、自动续跑；超时/撤回各演示一次；
- [ ] 知识库外问题兜底/转人工触发率 ≥95%（种子集口径），未触发逐条归因。

**陷阱**：
- 症状：把对抗测试写成真实调用 → 原因：混淆验收演示与 CI → 正解：CI 版走回放/夹具（§3.1），真实版只在演示脚本；
- 症状：性能数字没口径直接进报告 → 原因：简历数字纪律松动 → 正解：00 §2.2"简历数字纪律"——数字必带口径与凭证文件；
- 症状：验收清单"应该都对" → 原因：弱模型高发的对账偷懒 → 正解：00 §2.1 第 9 条逐项点名+收集数核对，绝不对未核查部分说全对。

---

## §5 测试蓝图（里程碑汇总）

### 5.1 目录与风格

- 测试目录镜像源码分层（00 §2.2）：新增 `tests/api/`、`tests/apps/`、`tests/core/`（tenancy/rls/tenant_ctx）、`tests/workers/`、`tests/evals/`；每个新目录带空 `__init__.py` 不需要（现仓库无），但 mypy `explicit_package_bases` 已开（pyproject.toml:43）允许重名 conftest；
- 命名与断言风格学 `tests/runtime/test_executor_exec.py`：中文 docstring 一句话点明契约、`assert x.kind is OutcomeKind.OK` 用 is 比枚举、DB 断言开新 session `select(...)`.scalar_one()、测试局部 `@tool` 定义即用；
- fixture 复用：`db_session_factory`（SAVEPOINT 包裹、形状=SessionFactory——tests/conftest.py）、`r`（真 Redis db9）、`dead_r`（降级路径）；新增：`app_client`（httpx.AsyncClient+ASGITransport(create_app())，tests/api/conftest.py）、`principal_headers(role)`（签好 token 的头工厂）、`rls_engine`（§4.3，真提交语义）、`fake_embedder`（固定向量注入）；
- async 测试零装饰器（`asyncio_mode = "auto"`，pyproject.toml:47）；涉本地 PG/Redis 的测试沿用"无则 skip、CI 必在"惯例（tests/conftest.py:19-21）。

### 5.2 每步新增测试数区间（收集数口径，含 parametrize 展开）

| 步 | 主要测试文件 | 区间 |
|---|---|---|
| M3.1 | tests/api/test_auth.py、tests/core/test_tenancy.py、tests/gateway/test_budget_resolver.py、tests/api/test_usage.py | +22–32 |
| M3.2 | tests/api/test_admission.py | +10–16 |
| M3.3 | tests/core/test_rls.py | +6–10 |
| M3.4 | tests/apps/test_ingest_split.py、tests/gateway/test_embeddings.py、tests/workers/test_ingest_resume.py | +14–20 |
| M3.5 | tests/apps/test_rerank.py、tests/apps/test_retrieval.py | +12–18 |
| M3.6 | tests/apps/test_intent.py | +8–12 |
| M3.7 | tests/apps/test_mock_backend.py、test_tools_ownership.py、test_tools_contract.py | +20–30 |
| M3.8 | tests/apps/test_agent_assembly.py、test_handoff.py | +8–12 |
| M3.9 | tests/api/test_approvals.py、tests/apps/test_revalidate.py、tests/workers/test_reaper_approvals.py | +12–18 |
| M3.10 | tests/api/test_sse_frames.py、test_stream_resume.py、test_chat_sse.py | +12–18 |
| M3.11 | tests/evals/test_seed_cases.py、tests/apps/test_seed_script.py | +4–8 |
| M3.12 | tests/apps/test_adversarial.py | +6–10 |
| **合计** | | **+134–204**（毕业时全仓 ≈ 基线 B + 134–204） |

区间是承诺下限不是天花板；每步交付时用 `uv run pytest -q --collect-only` 实数对账并在 00 §6.3 式表格登记（M2.4 曾错报 12 实为 11——收集数只认命令输出不认心算）。

> **毕业实数对账（2026-07-28）**：合计实增 **+299**（553→852），对预告 +134–204 上浮 95；
> 逐步实数=+35/+12/+8/+47/+26/+15/+36/+22/+38/+38/+15/+7，名分逐条在各步收口行与 14 块（上浮主因=计划未列面，见头部毕业回填注）。

---

## §6 验收对账清单（文件级）

- [ ] §4.0–§4.12 各章"验收"栏逐项勾完（每步交付会话内清单对账，00 §2.1 第 9 条）；
- [ ] 00 §7.2 四条毕业汇总全绿（§4.12 原样复刻）；
- [ ] 全部【开工核对】条目在 M3.0 已回填实况、【用户拍板】已有裁决且回填 00；
- [ ] `uv run pytest -q` 收集数 = 基线 B + 实际新增（逐步累计有账）；
- [ ] CI 全绿（含 lint-imports 新层定义）且**零真实调用**；
- [ ] `reports/m3_acceptance.md` 落盘；tag `m3-support` 推送；
- [ ] 00 更新：§7 标 ✅ + 实际交付对账表 + §10.1 状态翻转；本文件头部「实际落地偏差」回填；`docs\08-code-map.md` 对应节更新（00 §10.1 #36 维护纪律、§13 第 5 项）；记忆档案更新；深挖题入 `interview-questions.md`（本里程碑至少收 00 §7.2 考点五连原文：意图路由为什么用小模型／切块策略对召回的影响／HITL 挂起态存哪·超时未审批怎么办／RLS 为什么必须 SET LOCAL／pgvector 带 WHERE 召回两层表述；另加第六题：SSE 双通道断线答法——ADR-007:52-53）。

---

## §7 陷阱与常见错误（跨步通用；各步特有坑见 §4 各章）

**库真实行为坑**

1. 症状：RLS 策略建了但测试怎么查都全量可见 → 原因：连接身份是表 owner（`aegis`），owner 默认绕过 RLS → 正解：应用/测试连 `aegis_app`（D3）；面试考点顺手背：这正是"低权角色不建，兜底防线等于没有"（02 §7.2）。
2. 症状：`SET LOCAL` 无效且无报错 → 原因：语句在事务外执行是 no-op（仅 WARNING）→ 正解：挂 `"begin"` 事件钩子；用 `set_config(..., true)` 还能带绑定参数。
3. 症状：pgvector 查询 `operator does not exist: vector <=> numeric[]` → 原因：参数没走 pgvector 类型适配 → 正解：ORM 列用 `pgvector.sqlalchemy.Vector`，裸 SQL 绑定时向量转字符串 `'[0.1,0.2,...]'::vector` 或经 `pgvector.asyncpg` 注册 codec。
4. 症状：HNSW 建索引极慢/内存告警 → 原因：先灌数据后建索引 vs 边插边建的权衡 → 正解：演示量级（每租户万级下）无所谓，别调参数；量级焦虑时重读 ADR-006 规模边界。
5. 症状：Celery 任务在 Windows 静默不消费 → 原因：prefork 池（06 §4 第 1 坑）→ 正解：本地 `--pool=solo`；演示/压测走容器。
6. 症状：redis-py 一次故障拖 3 秒 → 原因：绕过 `get_redis()` 自建客户端吃了默认 retries=10 → 正解：M3 新增 Redis 触点（入站限流/消息缓冲/锁）一律用共享客户端（core/redis.py:12-26 快速失败三件已配好）。
7. 症状：`asyncpg` LISTEN 收不到通知 → 原因：用了池化连接或通知在未提交事务里 → 正解：独立原生连接 + 等真提交（§4.10 陷阱详条）。
8. 症状：PyJWT 验签"什么算法都过" → 原因：`decode` 未锁 `algorithms` → 正解：显式 `algorithms=["HS256"]`（§4.1）。

**口径误读坑**

9. 症状：照 02 §3 建表/引用列名（如 tool_invocations 的 `tool` 列）→ 原因：02 §3 是规划快照，与已落库 migration 有列级漂移（素材包 E2）→ 正解：表结构一律以 `migrations/versions/` 实文件为准；实列名是 `tool_name`。
10. 症状：RLS 策略照抄 `::uuid` → E1 高危，见 §4.3；本计划已改 text 比较（D2）。
11. 症状：M3 建了 eval_cases/eval_runs 表 → 原因：02 §3 把它们列在核心表 → 正解：建表归 M4.4（00 §8.1），M3.11 明文"文件形态维护"——越步即扩权。
12. 症状：给终端用户开 `GET /v1/sessions/{id}/events`"方便调试" → 原因：忘了矩阵 ❌ 的理由 → 正解：trace 含 system prompt/内部工具名，开放即出口防护旁路泄漏（02 §7.1）。
13. 症状：意图分类失败重试三次 → 原因：把增强层当主链路 → 正解：C34 fail-open 一次调用直落 AGENT（D8）。

**Windows / PowerShell 坑（06 §4）**

14. 症状：演示脚本输出中文乱码/凭证文件是 UTF-16 → 原因：PS 5.1 管道编码与 Tee-Object 默认 → 正解：`$PROFILE` 钉 UTF-8 + `Out-File -Encoding utf8`，或直接 pwsh 7；凭证落盘沿用 M1/M2 的既有做法。
15. 症状：SSE 演示 `curl` 不流式 → 正解：`curl.exe -N`（禁缓冲），不是 PowerShell 别名（此坑 06 §4 未收录，属同族）。

**弱模型高发错误（本计划的护栏所在）**

16. 症状：凭记忆写接口（如给 `LLMGateway` 发明 `embed()`、给 `ApprovalStore` 发明 `get()`）→ 原因：训练分布里的"常见形状"不是本仓库形状 → 正解：写任何调用前 Read 目标文件；本计划 §2.1 表只减少查找成本，**不豁免 Read**。
17. 症状：顺手重构 M2 代码（"顺便把 executor 的 X 改优雅"）→ 正解：M3 对 L2 零修改是本里程碑红线（§1）；L1 只许 §4.1/§4.4 两处受控缝。
18. 症状：一次交付塞两步/提前做 v2 项（审批页、语义缓存、坐席 WebSocket）→ 正解：00 §2.1 第 5 条一次一步 + §10.3 边界表先查再动。
19. 症状：收集数错报（"新增 12 个测试"实为 11）→ 正解：只报 `--collect-only` 命令输出的差值，M2.4 偏差登记是前车之鉴（00 §6.3）。
20. 症状：交付正文被工具调用吞掉（只见命令不见讲解）→ 正解：四件套完整成文后再发；讲解与代码是给用户敲代码用的，不是可选装饰。
21. 症状：新 ORM 模块建了表、autogenerate 却生成 drop 其他表的 diff → 原因：env.py 忘 import 新模块（schema-infra 包附9）→ 正解：D1/§4.4/§4.7 三处都点名了这一行；生成迁移后**人工通读 diff** 再跑。
22. 症状：测试直接连生产 `.env` 的真实 key 跑出账单 → 正解：pytest 内禁真实调用是红线（§3.1）；测试构造 Settings() 干净实例（config.py:72 缝隙）不读 .env 的 key 字段。

---

## §8 指令块模板（每步交付末尾给用户；命令在仓库根（本 repo） 执行）

依赖变更步先行（仅 M3.1 / M3.4 需要）：

```powershell
uv add fastapi uvicorn pyjwt          # M3.1；预期 pyproject/uv.lock 更新，Resolved N packages
uv add pgvector                       # M3.4；同上（celery 已随 M2.10 引入，勿重复 add）
```

含迁移的步（M3.1/M3.3/M3.4/M3.7/M3.10）在 pytest 前插入：

```powershell
uv run alembic upgrade head           # 预期：Running upgrade <旧head> -> <新revision>，无 traceback
```

标准八连（顺序即 00 §2.1 第 3 条，不许调换）：

```powershell
uv run ruff format .                  # 预期：N files reformatted 或 already formatted（首跑后应稳定为 unchanged）
uv run ruff check .                   # 预期：All checks passed!
uv run pytest -q                      # 预期：全绿；收集数 = 基线B + 本步累计新增（区间见 §5.2；实数以 --collect-only 为准）
uv run mypy .                         # 预期：Success: no issues found in N source files
uv run lint-imports                   # 预期：Contracts: 1 kept, 0 broken（M3.1 起层定义含 api/workers）
git add <本步逐个点名的文件>            # 绝不 git add .（防连带未交付文件）
git commit -m "feat(<scope>): <主题>" -m "<为什么：设计动机+文档锚点>"   # scope∈ api/apps/workers/core/gateway
git push                              # 预期：CI 全绿（含 alembic upgrade head 步——ci.yml:63-64）
```

真实调用类脚本（M3.11 录制、M3.12 实测）单独成块并前置提醒：确认 `.env` key、预算常量、百炼控制台额度；产物路径逐一列出（`tests/cassettes/l3/`、`reports/`）。

毕业步追加：

```powershell
git tag m3-support && git push origin m3-support   # 预期：CI 对 tag 分支全绿
```

---

## §9 完成后动作（每步毕业当天 + 里程碑毕业时）

1. **00 更新**：步骤行标 ✅、§6.3 式"实际交付对账"登记（提交号+测试数流水）；口径变更当天落 §2.2；
2. **本文件回填**：头部「实际落地偏差」块（无偏差也写"无偏差"——plans/README §4）；被现场推翻的决策当天改本文件 + 00 登记，不许只改代码；**同步更新 `docs\08-code-map.md` 对应节**（00 §10.1 #36 维护纪律：每步毕业时回填计划偏差块 + 更新 08 对应节）；
3. **横切清单翻转**：#6（M3.7）、#7（M3.5）、#8（M3.9）、#13/#17/#19/#21/#22（M3.1/M3.2）、#18（M3.3/M3.4）、#20（M3.0 拍板）；
4. **深挖题入库** `docs/interview-questions.md`：每步收尾 3–5 题（§4 各章面试锚点已埋）；
5. **记忆更新**：`memory/aegis-agent-platform.md` 在里程碑毕业时重写为 M3 状态（含新教训）；
6. 下游预告：M4.0 将消费本里程碑的 trace 端点/usage/种子集/cassette（§2.3），毕业对账时确认四者形态已定型并在 00 §8 对应行无需改口。

---

## 附：发现的上游文档问题（写作对账中发现；**不擅自改上游**，列此待用户/当班模型处置；编号 U1–U14，与 §3.4 拍板项 P1–P7 是**两套独立命名空间**，2026-07-10 修订改前缀防查错表）

| # | 问题 | 出处 | 建议处置 |
|---|---|---|---|
| U1 | 02 §7.2 RLS 策略样例 `current_setting('app.tenant_id')::uuid` 与实装列型冲突：全库 tenant_id 均 String(64)，演示租户 id `tenant-a` 非 UUID——照抄运行期报错 | 02 §7.2 vs migrations/74da3bf5d6ab:29,72、gateway/schema.py:54 | M3.3 落地后修订 02 §7.2 为 text 比较（本计划 D2 已按 text 设计） |
| U2 | 02 §3 与已落库 schema 列级漂移：events 多 run_id；sessions 多 lease_generation/recovery_count；tool_invocations 列名 `tool_name` 非 `tool` 且多 4 列；messages 多 event_id | 02 §3 vs 74da3bf5d6ab | 建议 M3.0 顺手回填 02 §3（或至少加"以 migration 为准"脚注） |
| U3 | 02 §3 users 行说明"所有业务表都带 tenant_id"与事实不符：events/messages/tool_invocations 无 tenant_id 列——RLS 全覆盖因此不可能，v1 覆盖范围需拍板（本计划 P5） | 02 §3 vs 74da3bf5d6ab | 拍板后在 02 §7.2 登记覆盖范围与取舍 |
| U4 | 00 §7.1 M3.10 行未提跨副本事件通知，但 00 §2.2 C22 行明言"实装 M3.10"——只按步骤行文开发会漏 | 00 §2.2 vs 00 §7.1 | 本计划 §4.10 已纳入；建议 00 M3.10 行补一句 |
| U5 | ADR-007 只定义 POST 通道五帧；GET 重订阅通道的"消息重置帧"有语义无帧名/字段，帧协议不完整 | ADR-007:14-19, 30-33 | 本计划 D11/§4.10 帧表补齐；建议回填 ADR-007 |
| U6 | 02 §3 documents/chunks 两表合一行，列归属未拆——拆法是设计决策非文档事实 | 02 §3（documents/chunks 行） | 本计划 P6 拍板后回填 02 §3 |
| U7 | ADR-006 要求"embedding 调用同样过网关计量"，但 L1 网关无任何 embedding 通道，00 M3.4 行也未说明需扩 L1——存在"以为网关已有 embed 方法"的脑补陷阱 | ADR-006:37-38 vs aegis/gateway/*（Grep 无 embedding） | 本计划 D5 以受控扩展落地；建议 00 M3.4 行注明"含 L1 embedding 通道新增" |
| U8 | 02 §2 时序 ④ 说 API 层写 user_message，M2.7（未交付）循环内是否也写未定——双写风险 | 02 §2 vs M2.7 交付实况 | 【开工核对 0-7】裁决后回填本计划 §4.2 |
| U9 | FAQ/缓存直答轮的事件与投影是否产生，02/00 均未写明（涉 trace 完整性与 usage 对账） | 02 §2 ⑤ 留白 | 本计划 D7 已裁决（写全事件）；建议 02 §2 补注 |
| U10 | 检索 top-5/分数阈值数值只在 00 M3.5 行出现"top-5"，阈值全库无数值；embedding 批量上限 ADR-006 明言实测为准——均为显式留白，任何现在填死的数字都是编造 | 00 M3.5、ADR-006:34-35 | 本计划 §3.5 以"占位+实测后定"处理 |
| U11 | plans/README §5 已登记 m2.5–m2.12 八份计划文件，写作时点 docs/plans 目录尚无（并行撰写中） | plans/README §5 vs 目录实况 | **已解决（2026-07-10 交接工程落档，00 §10.1 #36 ✅）**：八份均已落盘，0-16 核对项照常执行 |
| U12 | retro-m2.md（#35）为 M2 毕业后交付，写作时点不存在——M3.0 前置依赖 | 00 §10.1 #35 | §0 0-3 已设停止条件 |
| U13 | `GET /v1/usage` 在 02 §9 端点表与 02 §7.1 矩阵均有、本计划 §2.3 承诺给 M4.2（#23 gauge）/M4.6，但 00 §7.1 的 13 个 M3 步骤行均未列——只按步骤行开发会漏，承诺落空 | 02 §9、02 §7.1 vs 00 §7.1 | 本计划已排入 M3.1（§4.1，读 usage_ledger）；建议 00 M3.1 行补一句（同 U4 处置方式） |
| U14 | `GET /v1/sessions/{id}/events` 在 02 §7.1 矩阵与本计划 §2.3 均有（M4.1 trace API 底座），但 00 §7.1 各 M3 步骤行均未写其归属；02 §7.3 还要求该访问"仅 operator+ 可访问**且留审计**" | 02 §7.1/§7.3:233 vs 00 §7.1 | 本计划随 M3.10 交付（§4.10，含最小审计留痕）；建议 00 M3.10 行补注归属 |
