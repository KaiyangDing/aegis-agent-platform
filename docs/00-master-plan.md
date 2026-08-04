# 00 · Aegis 全景开发规划（M0→M5 执行主文档）

> **地位**：本文档是开发路径的**执行主文档**——每个新会话开工前必读，步骤级计划以本文档为准。
> [04-roadmap.md](04-roadmap.md)（v1.1）保留为规划期基线；**与任何设计文档的口径冲突时，
> 以本文档（§2.2 口径表）为准**，并在发现冲突当天同步修订对应设计文档（已同步案例见 §10.1 #16）。
> **版本**：v1.5 · 2026-07-10（v1.1：M1 毕业时点创建，创建当日五视角校审 25 项归位；
> v1.2：M2 开工前 7 维对抗评审落档——44 确认 + 5 存疑，报告 `review-2026-07-07-m2-preflight.md`，
> 处置分布：8 条纯文档修订已完成（README/01/02/03/05/ADR-003/ADR-005），口径决策批挂 M2.0，
> 建表落位挂 M2.2，其余见 §6.1 各步标注与 §10.1 #17–#28；
> v1.3：复盘补丁二落档——限流降级粘滞化 + Redis 客户端快速失败 + 压测稳态口径，
> 见 §2.2 末行 / §5.2 / §6.3 / §10.1 #29；
> v1.4：目标岗位确认（AI Agent / AI 应用开发）——LangGraph 素养升必做：
> M2 对照文档 + 迷你复刻 spike + 简历应用岗调序，登记 §10.1 #32–#34；
> v1.5：**模型交接工程落档**（2026-07-10，Fable 5 → Opus/Sonnet 交接）——新增
> `CLAUDE.md` 双入口（仓外上层目录与仓库根）、`docs\07-handoff-guide.md`（接续驾驶手册）、
> `docs\08-code-map.md`（M2.4 代码地图快照）、`docs\plans\`（M2.5–M5.6 步骤级详细计划，
> 消费规则见 plans\README.md），§0 启动清单同步升级，登记 §10.1 #36）
> **维护纪律**：每个里程碑毕业时更新对应章节（标 ✅、登记实际交付与偏差、回填横切清单）；
> 过程中发生的口径变更当天落档到 §2.2，不留"口头约定"。

---

## 0. 新会话启动清单（每个新 session 的第一件事，按序执行）

1. 读记忆文件 `memory/aegis-agent-platform.md`（项目状态、协作规约、教训档案）；
2. 读 `docs\07-handoff-guide.md` 全文（接续开发驾驶手册：协作规约操作化、红线清单、
   高发错误对策——2026-07-10 交接工程新增，**接续模型不读它不许动手**）；
3. 读本文档 **§1–§3** 定位当前里程碑，再读**当前里程碑章节**全文与 **§10 横切清单**；
4. 按 **§12 文档地图**读该里程碑的必读设计文档；
5. 读当前步骤对应的 `docs\plans\` 计划文件，**先执行其「§0 开工核对清单」**
   （逐项 Read 源码核对签名/常量/测试数，对不上先修计划再动手——plans\README.md §1）；
6. 仓库对账：`git tag`、`git log --oneline -5`、`uv run pytest -q` 的收集数与本文档
   **§6.3 实际交付对账最末行**登记的基线核对（M2.4 时点：**301 个测试**全绿，HEAD `014ec21`；
   M1 毕业基线 133 供历史参照）；
7. 按协作规约（§2.1）开工：**先给本里程碑全景图**（步骤地图 + 契约走查 + 首步预告），
   经用户确认后再进入第一步交付。

---

## 1. 项目一页纸

- **身份**：求职者的简历项目。企业级多租户客服 Agent 平台（Aegis），证明"造平台"而非"用平台"的能力。
  **目标岗位：AI Agent / AI 应用开发**（2026-07-08 确认）——项目定位不变（05 §3 深挖表即应用岗考纲），
  简历策略加配框架素养凭证（§10.1 #32–#34）。
- **三层架构**：L1 LLM 网关（与 Agent 无关）→ L2 自研 Agent 运行时 Harness（与业务无关）→
  L3 多租户客服业务；横切：可观测 / 安全 / 交付。依赖方向严格单向（L3→L2→L1），import-linter 在 CI 强制。
- **要解决的七类工程问题**（面试背稿统一口径）：循环失控、工具不可信、上下文爆炸、上游故障、
  并发与成本、不可观测、不安全。一句话："LLM 是 CPU，Aegis 是操作系统"（ADR-001）。
- **演示场景**：虚构 SaaS「云杉电商」两个租户——A 数码商城（订单/物流/退款，退款 >200 元过审批，
  阈值是租户 A 的配置项）、B 生鲜超市（订单/优惠券补发）。两租户数据互相不可见是核心验收场景。
- **成功标准**（01 §6）：15 分钟 demo 跑通全部亮点；评测集 ≥30 条 + 双流水线；压测报告两组口径；
  成本对照实验两组数字 + 口径说明；每篇 ADR 支撑 5 分钟以上面试深挖。
- **非目标**（01 §4 硬性红线，v1/v2 均不做）：多渠道接入（只做 Web+REST）/ 精美前端 /
  模型训练微调 / K8s 实操 / Agent 市场低代码 / 多区域容灾——范围核对入口统一在 §10.3。
- **技术栈**：Python 3.13 + uv + FastAPI + SQLAlchemy async + PG16/pgvector0.8.4 + Redis7 + Celery；
  百炼 API（OpenAI 兼容模式，httpx 直连不用 SDK——ADR-003 v1.2）；Windows 11 本地开发
  （Celery 本地 `--pool=solo`，生产形态以容器为准）。

---

## 2. 全局约束（所有里程碑共同遵守）

### 2.1 协作规约（学习者模式；2026-07-09 合并重写，替代历次补丁形态）

**分工**：
1. 生产代码**用户亲手敲**（AI 给完整代码 + 逐段解释）；架构与口径决策**用户拍板**（AI 给建议与理由）
   （**单步例外**：M2.10 经用户 2026-07-17 指示由 AI 直写全部代码、用户验证提交——05 §4 叙事已同步注记）；
2. 测试代码 **AI 直接写入/修改**（2026-07-09 修订），测试讲解保留在交付里；
3. 验证与 git 指令**用户执行**——AI 每次交付给完整指令块并标预期结果，顺序：
   `ruff format .` → `ruff check .` → `pytest -q` → `mypy .` → `lint-imports` →
   `git add 指定文件` → `commit -m 主题 -m 为什么` → `push`；
   **仅用户要求"验收"时 AI 代跑核对**（2026-07-09 修订；ruff format 为必给项）；
4. 设计文档 / 本文档 / 记忆档案由 AI 直接维护，口径变更**当天落档**，不留口头约定。

**交付节奏**：
5. 每次交付只给一步（L 规模的步先给切分计划再逐份交付）；交付**四件套**：
   设计讲解（架构位置 + 文档锚点）/ 完整代码 + 逐段解释 / 落盘位置 + 完整指令块 /
   验收检查点（清单对账）——~~常见报错排查表~~（2026-07-09 取消：报错由用户反馈后现场排查）；
6. 目录按需创建，不提前铺空壳；里程碑开工先给全景图（步骤地图 + 契约走查 + 首步预告），用户确认再开工。

**提交与验收**：
7. 小步提交、一次一个主题、message 写"为什么"；里程碑打 tag；**已推送历史不改**；
8. **提交落地属于验收**：一步没提交就不算完成；
9. **验收做清单对账**：逐项点名新增测试/文件 + pytest 收集数核对，绝不对未核查部分说"全部正确"。

**学习机制**：
10. ~~每步理解自查~~（2026-07-07 取消）；模块收尾面试深挖题~~当场问答~~改为**集中存入
    `docs/interview-questions.md`**（2026-07-09；含 M0/M1 复盘连环炮），用户开发完毕后统一自测（先答、AI 补充）；
11. 报错用户先读 traceback 定位（"我觉得是 X 因为 Y"式提问）；随时可质疑设计——改文档比改代码便宜。

**会话边界**：
12. **按里程碑开新会话**：边界 = **§13 毕业清单 6 项全部勾完**才切换
    （2026-07-10 修订：超长会话可在**步**边界切换——该步已收口且记忆/本文档已更新即可，
    M2.4 后即按此切换过一次；新会话仍按 §0 启动清单开工）。

### 2.2 全局工程口径（跨里程碑不许漂移，M1 期间沉淀）

| 口径 | 内容 |
|---|---|
| 失败哲学分野 | 安全闸门 fail-closed；成本闸门 fail-open（如月度预算）；缓存与计量故障**绝不拖垮请求**（隔离+自愈） |
| 半截不换路 | 两层镜像：网关流级中断抛 `GatewayStreamInterrupted`（死因在 `__cause__`）；运行时"半截 llm_call"作废重发。首块后不再横跳供应商 |
| 网关异常契约 | L2 只见**六类**（2026-07-07 C6 升级）：请求级·可降级 `GatewayExhausted` / `BudgetExceeded` / `TenantQuotaExceeded` / `GatewayOverloadedError` + 请求级·确定性拒绝 `GatewayRejected`（**不降级**，bug 信号，终止原因 gateway_rejected）+ 流级 `GatewayStreamInterrupted`；**ProviderError 家族永不穿出网关** |
| 熔断记账 | **429 不进熔断账**（限流是配额信号不是健康信号；M1 实装定稿——02 §4 规划期"每次失败计入熔断窗口"的旧表述已同步修订，见 §10.1 #16）；熔断按 provider 粒度，误伤再细化为 provider:model |
| 数据访问 | 报表/聚合用裸 SQL，实体用 ORM；值用 `lru_cache`，资源（引擎/客户端）手动 global 单例 |
| 测试纪律 | 时序敏感断言不进 CI（本地演示脚本承载）；测试目录镜像源码分层 |
| 安全底线 | 密钥只从环境变量读、`.env` 永不入库；错误文本源头打码；prod 禁故障注入；端口绑 127.0.0.1 |
| tenant_context 配对纪律（(58)，M4.4③ 落档） | 身份恒由边界建立，且**每个新的出边界调用点**（网关/DB/工具）必须核对其所在协程链的租户上下文在场：`with tenant_context(...)` 包住完整消费段（流式=包到流耗尽），裸 `set` 只许 auth 一处且不 reset 是刻意（请求生命周期即作用域）；脚本/评测/维护面的新调用点开工核对必查此项——实锚三例：M3.5 偏差(32) 叶子自冒充、M4.2① 计划伪码 RLS 空集、M4.4④ judge 裸调用 42501 |
| 术语统一 | 终止条件共 **7 类**，除"正常完成"外 **6 项构成防护闸门**，对外统一说"六道终止闸门" |
| 简历数字纪律 | 没实测不写任何数字；每个数字有凭证文件（`reports/`）与口径说明；简历与交付物逐词对得上 |
| 上下文成本意识 | M1 会话实测：输入原始 1.29 亿 token（96% 缓存读）折全价当量 1844 万、输出 82 万——上下文是 Agent 系统第一大账单，M2 上下文工程引用此数据 |
| 超时语义（2026-07-07 评审 C1 裁决） | L1 三段超时：connect 5s / **首 token 25s / 块间空闲 30s**，整流时长不设上限；`LLMRequest.deadline` 向下传播，router 开新尝试前查剩余预算不够则不开；L2 闸门 #2 的"LLM 90s"= 传给网关的 deadline——**嵌套约束由传播机制保证，不靠人肉算术**；故障注入器含"挂起/慢流"模式。**2026-07-17 补注（M2.11 实录揪出）**："首块"实装为解析后首 chunk（resilience.py `anext`）——思考型模型先流 reasoning_content 而适配器不消费，会把计时器饿死；处置=百炼请求统一 `enable_thinking: false`（openai_compat）；若未来入池关不掉思考的模型，须实装"首个活性信号"（§10.1 #41） |
| 异常契约六类（C6 裁决） | 请求级新增 **`GatewayRejected`**：全部候选均为确定性拒绝（Auth/BadRequest）时抛出——L2 **不降级**、终止 run 报"配置/协议错误"（bug 信号不许被兜底话术掩盖），终止原因枚举含 `gateway_rejected`；其余五类语义不变 |
| token 计数（C25 裁决） | **护栏用估算、账单用实测**：`core/tokens.py` 启发式估算器（CJK≈1 token/字、其余≈4 字符/token），六层预算/会话闸门/单请求闸门全用估算值（±15% 容差，预算数字自带余量）；计费以供应商 usage 回填 ledger 为准，不引入 tiktoken |
| 辅助 LLM 调用失败分野（C34 裁决） | **fail-closed 只指确定性安全闸门**（权限/归属校验/审批/RLS）；LLM 增强层失败一律 **fail-open 降级到确定性兜底 + 审计事件**：入口分类器挂→仅规则库+打标；滚动摘要挂→截断兜底；意图分诊挂→直走主 Agent 标准档；工具结果摘要挂→硬截断。**2026-07-11 M2.5 拍板细化**：滚动摘要失败的留痕 = 结构化 `logger.warning`（含 session_id/run_id/异常文本），M2 显式豁免"审计事件"字面——不为失败留痕扩 14 类事件枚举；需事件级审计时走显式扩枚举流程（03 §5 表 + events 快照测试 + M2.6 归一化规范三处联动，plans\m2.5 §3.2 拍板项 4） |
| ID 关联模型（X5 裁决） | 三层：**trace_id ≡ session_id**（对外，一次会话即一条 trace）；**run_id** 每次 AgentLoop 启动新生成（events 列，恢复计数 C9 的依据）；request_id = 网关单次调用（既有）；usage_ledger 经 session_id 关联 |
| 429 配额风暴（C30 裁决，冻结） | 持续性配额耗尽（账号级/欠费）显式排除在 v1 故障模型外：前置防线 = 月度预算闸门 + 控制台限额告警；升级路径 = 独立配额熔断账（v2） |
| 跨副本事件通知（C22 裁决） | 选型 **PG LISTEN/NOTIFY**（事务提交即通知，与事实源同生命周期，不给 Redis 加新降级面）；LISTEN 断连兜底 = `after_seq` 轮询；实装 M3.10，M2 不动代码 |
| Redis 依赖故障处置（2026-07-08 复盘补丁二） | 共享客户端**快速失败**：connect 1s / read 2s / `Retry(NoBackoff(), 1)`——redis-py 8 默认 retries=10+指数抖动退避（一次失败拖 ~3s）与"各消费方自带降级"是重复兜底；降级**粘滞化**：降级期直走本地兜底，每 5s 一个顺路探针自愈（本地探测令牌，领取无 await 天然互斥，与熔断半开同构）——限流器已实装，熔断/缓存/计量触点归位 §10.1 #29；压测口径 = **预热后稳态计时**，冷启动/故障检测延迟单独上报为"首发请求耗时" |
| 展示层 PII 打码单点（M4.1 拍板②） | 全仓打码唯一入口 = `aegis/obs/masking.py`（**复用** `guardrails.PII_RULES_V1` 同一张表——出口守卫与展示打码两个消费面零复制零漂移）；events 永存原文（02 §7.3），脱敏只发生在展示出口；masker **绝不抛异常**（故障=占位顶替，展示层不许拖垮查询）。日志/导出等新展示面接入一律 import 此单点，不自造正则、不复制常量 |

---

## 3. 里程碑总览与当前位置

| 里程碑 | 内容 | 规划基线 | 依赖 | 状态 | tag |
|---|---|---|---|---|---|
| M0 | 工程底座 | 0.5 周 | — | ✅ 2026-07-04 | `m0-foundation` |
| M1 | L1 LLM 网关 | 2 周 | M0 | ✅ 2026-07-06（133 测试） | `m1-gateway` |
| M2 | L2 Agent 运行时 | 2.5 周 | M1 | ✅ 2026-07-17（548 测试） | `m2-runtime` |
| M3 | L3 客服业务（RAG/工具/HITL/SSE） | 2 周 | M2 | ✅ 2026-07-28（852 测试） | `m3-support` |
| M4 | 治理层（可观测/评测/成本实验） | 1.5 周 | M3 | ⬜ **下一个** | `m4-governance`（预定） |
| M5 | 交付收口（压测/演示/简历回填） | 1 周 | M4 | ⬜ | `v1.0`（预定） |

- **节奏**：规划基线按 15–20 小时/周估算，剩余 M2–M5 = 7 周 + ≥1 周缓冲。
  实际节奏远快于基线（M0+M1 规划 2.5 周，实际 3 天），**周数只用于管理相对规模，不预设完成日期**。
- **步骤规模标注**（M2 起使用）：S ≈ 1 次交付；M ≈ 2–3 次交付；L ≈ 4 次以上交付或含实验。
  参照系：M1 全程 **19 次提交 / 13 步**（含 3 次 chore/refactor 辅助提交，未列入 §5.1 对账表）。
  各里程碑标题的步数**含 M×.0 开工走查步与毕业步**（M1 时代无独立开工步）。
- 每个里程碑以"可演示 + 可验收"收尾——中途停下简历也不是空的。时间不够时按 §11 砍法执行。

---

## 4. M0 · 工程底座 ✅（tag `m0-foundation`，2026-07-04）

### 实际交付对账（步骤 → 提交）

| 步 | 内容 | 提交 |
|---|---|---|
| M0.1 | 仓库初始化 + uv 工程（`.gitignore` 首个提交即含 `.env`；`pyproject.toml`+`uv.lock` 入库） | `c7d41b2` `27d068e` |
| M0.2 | 分环境配置（pydantic-settings + SecretStr 密钥防泄漏；dev/staging/prod） | `2a0bb8d` `1443f16` |
| M0.3 | docker-compose 基础设施（pgvector/pg16 + redis7，健康检查 + 数据卷持久化） | `79c9aa5` |
| M0.4 | GitHub Actions 质量门（uv sync --frozen + ruff + mypy + pytest） | `10b12db` |
| M0.5 | import-linter 分层契约（apps→runtime→gateway→core）接入 CI | `b926586` |

验收兑现：`docker compose up` 一键起基础设施、CI 全绿、分层反向依赖被 CI 拦截。

---

## 5. M1 · L1 LLM 网关 ✅（tag `m1-gateway`，2026-07-06，133 测试全绿）

### 5.1 实际交付对账（步骤 → 提交）

| 步 | 内容 | 提交 |
|---|---|---|
| M1.1 | 统一协议层：LLMRequest/LLMChunk 判别联合、errors 两级契约 | `d35ca57` |
| M1.2 | 百炼 OpenAI 兼容适配器（非流式）：格式与错误双翻译 + DI + respx 全覆盖 | `c7cf2d1` |
| M1.3 | 真流式：SSE 解析、include_usage、chunk 顺序不变量、中途断线语义；项目装为可编辑包 | `e607669` |
| M1.4 | tool-call 双向映射：去程说明书/历史工具轮，回程按 index 组装增量碎片 | `c4b2159` |
| M1.5 | 受控重试：首块前安全窗口（anext）、可重试白名单、指数退避+满抖动、Retry-After 优先、双重预算 | `71f3613` |
| M1.6 | 熔断器：Redis 三键状态机（TTL 即迁移）、SET NX 半开探测互斥 | `5584eb4` |
| M1.7 | 出站限流：Lua 令牌桶（原子读-改-写、Redis TIME 时钟）+ 精度压测脚本 | `882f078` |
| M1.8 | 总装：档位路由 / fallback 矩阵 / 故障注入装饰器 / 探针单发 / 两条安全红线 | `410fdd5` |
| M1.9 | 精确缓存：租户前缀 key、语义本体哈希、完整流才入库（完整性守卫）、回放盖 cached 章 | `1e3dd67` |
| M1.10 | 四视角审计加固 A/B/C（21 项修复，+32 测试；异常契约在 B 定稿） | `aa3d5fe` `f52a617` `a06fb92` |
| M1.11 | 计量与预算：SQLAlchemy async DB 底座、usage_ledger + alembic 首迁移（`ab31f1ad`）、真实/缓存双路记账、**租户月度预算闸门（fail-open）** | `84329bd` `f9879de` |
| M1.12 | Redis 全灭降级：限流本地桶（配额=全局/副本数）、熔断 fail-open+本地计数、影子账本；停容器实录通过 | `97e3a94` |
| M1.13 | 毕业实验：30% 注入 1000 次实测 + 熔断延迟塌缩演示 + 四维对账脚本，报告落盘 | `65fbce5` |

补充：Anthropic 适配器（桩测试，接入即用）在适配器阶段一并交付。

### 5.2 简历数字第一批（凭证除注明外均为 `reports/m1_fault_injection.txt`，M5 回填简历）

| 指标 | 实测值 | 口径 |
|---|---|---|
| 端到端成功率 | **100%**（1000/1000） | 仅主供应商注入 30% 失败、重试≤3、1 层同档 fallback、缓存关、并发 10、限流放宽 20 QPS |
| 延迟 | P50 0.98s / P95 1.89s / **P99 2.42s** | 同上实验 |
| fallback 次数 | 22 次（qwen-flash→qwen-turbo） | 理论 0.3³×1000=27，同量级吻合 |
| 熔断延迟塌缩 | closed 态 294–1161ms（4 次）→ 触发打开的第 5 次 748ms → 打开后 **1.0–1.3ms** | 100% 注入单候选；毫秒级失败证明零穿透（连重试层都没进） |
| 限流精度误差 | **0.19%**（524/525，预热后稳态口径，2026-07-08；共享桶与降级本地桶**双模式同值**；降级故障检测延迟实测 1046ms，上界=connect 超时 1s） | 凭证 `reports/m2_ratelimit_degraded.txt`（口径注记含于凭证本体：计数=按 HTTP 调用、预热稳态计时）；旧口径 0.76%（含冷启动计时）凭证 `m2_ratelimit_retest.txt` 保留 |
| 账本对账 | 成功 1000 次 vs 账本 1000 行一致；token 27758；实验成本 **¥0.0079** | 四维聚合：租户/会话/模型/天 |

注意：简历表述须带口径（"30% 故障注入下"）。熔断**恢复闭合时间**尚无实测数字（TTL 30s 是设计值）——
这是 04 M1 验收（"上游恢复后 X 秒内自动闭合，X 实测记录"）的**未尽项，不降级为可选**：
归位 M5.4 无条件补测（§10.1 #10，验收已挂进 §9.2）。

### 5.3 M1 遗留项（已全部登记进 §10.1 横切清单）

- **单请求 token 预算闸门未实装**（现仅有租户月度闸门，`config.py` 只有 `tenant_monthly_token_budget`）；
- 缓存命中的 QPS 放大效应 → M4 复核；alembic check/downgrade 往返 → M4 可选加固；
- 出站限流计数口径为"按 HTTP 调用"（重试第 2/3 次尝试暂不过闸）——口径以本文档为准
  （原实验报告实际未含此注记，M2.0 复测落盘时补注——评审 C26），保持口径；
- ~~限流精度 0.76% 无落盘凭证~~ 已补：2026-07-07 复测落盘（§10.1 #12 ✅）；熔断恢复闭合时间无实测（→ M5.4 补测，§10.1 #10）；
- 05 简历模板"Qwen/**DeepSeek 实测**"尚无凭证——fallback 实测仅 qwen-flash→qwen-turbo（同为 Qwen 系）；
  ~~qwen-plus↔deepseek-v3~~ **qwen3.7-plus↔glm5.2**（2026-07-16 模型池变更，deepseek-v3 退役）
  容灾切换实录 → M5.4 补录（§10.2），无凭证则同步修改 05 简历表述（"DeepSeek"→"GLM"）。

---

## 6. M2 · L2 Agent 运行时（2.5 周基线，14 步）✅ 2026-07-17 毕业（tag `m2-runtime`，548 测试）

### 6.0 定位与红线

- **定位**：技术含量最高的一段，"模型是租来的，Harness 才是自己的"（03 号文档全文是本里程碑的详设）。
- **真实 API 红线**：**测试与 CI 全程零真实调用**。仅允许两处一次性真实调用，预算上限写死：
  ① M2.11 录制长对话基准 cassette；② M2.12 毕业真实冒烟（只断言不变量）。
- **消费的 M1 契约**：L2 只见 §2.2 的六类网关异常（C6 后含 `GatewayRejected`）；`LLMGateway` Protocol 见 03 §7。
- **L3 依赖倒置**：prompt / 工具集 / 策略 / 租户配置全部由上层注入（AgentSpec），
  M2 测试用演示工具集（runtime 测试专用），运行时对"客服"一无所知。

### 6.1 步骤计划

| 步 | 内容 | 规模 | 文档锚点 |
|---|---|---|---|
| M2.0 ✅ | **开工走查**：重读 03 全文 + 02 §2/§3/§5 + **评审报告 §1/§2**；M2 全景图讲解；契约走查（网关五类异常——时为五类，本步 C6 裁决后升六类、LLMGateway Protocol）；`runtime/` 目录骨架；【开工核对】单请求预算闸门是否此时补（§10.1 #1）；顺手复测限流精度并落盘 `reports/`（§10.1 #12，报告须注明"按 HTTP 调用"计数口径——评审 C26）；**评审口径决策批（2026-07-07 已全部按建议裁决，定稿见 §2.2 末七行）**：① 超时语义拆分——首 token 超时/块间空闲超时两参数 + L1 单候选最坏耗时 < L2 单步预算的嵌套约束 + 故障注入器补"挂起/慢流"模式（C1，blocker）；② 网关异常契约细分——确定性拒绝（AuthError/BadRequest）与可降级耗尽分开，并给终止原因枚举留位（C6）；③ token 计数口径——tokenizer 选型与"估算即可"的适用边界（C25）；④ 辅助 LLM 调用（守卫分类/摘要/意图路由）失败分野——哪些 fail-open 哪些 fail-closed（C34）；⑤ ID 关联模型——session/run/request 三层与 trace_id 落点（X5）；⑥ 429 持续配额耗尽形态的口径——登记或显式冻结（C30）；⑦ 跨副本事件通知机制选型——Redis pub/sub / PG LISTEN-NOTIFY / 轮询，三选一（C22，实装在 M3.10）；**五段文档声明**：优雅停机（crash-only 立场）/ 模型版本钉扎 / OTel 关系 / 备份思路 / 数据生命周期（C35/C36/C37/C41/C21） | M | 03 全文、评审报告 |
| M2.1 ✅ | **核心抽象**：AgentSpec（含 `sub_agent_policy=DISABLED` 预留位）/ LoopPolicy / ContextConfig / ToolDef / ToolContext / AgentEvent 类型；AgentRuntime 门面与 AgentLoop 内部驱动的命名分工 | M | 03 §1 |
| M2.2 ✅ | **EventStream 底座**：alembic 迁移**五表**（sessions 含 run_state/lease_owner/lease_expires_at/summary、events 含 seq/schema_version/payload 原文、**messages——对话原文投影表**、tool_invocations、approvals 含 expires_at/五态）；事件类型枚举入库（枚举本体随 M2.1③ 落 `runtime/events.py`）；单写者 seq + `(session_id, seq)` 唯一约束；**投影同事务派生**（messages/tool_invocations/summary）；**事件写入短退避重试 3 次仍失败 → 终止本次 run 返回明确错误**（PG 挂=服务不可用，显式接受——02 §5）；tenant_id/user_id/operator_id 沿用 M1 口径为不带 FK 的普通列（tenants/users 表 M3 建）；**评审落位四件**：`lease_generation` fencing 列 + 围栏三协议——续租失败 loop 立即自毁 / 唯一约束冲突与 generation 失配 = 终态围栏信号绝不退避重试（与 PG 故障重试路径显式区分）/ write-ahead 插入成功是执行副作用的前置（C2，blocker）；summary 投影口径（C8，2026-07-09 裁决）：**加 `summary_updated` 事件类型**——payload 存摘要全文与覆盖轮次；摘要是 LLM 产物不可确定重算，不入事件流则回放无法重建投影（枚举与投影派生随 M2.2 交付③落地，03 §5 表已同步）；恢复次数上限列 + `run_state=failed` 的进入路径（C9）；审批状态翻转用 CAS——`UPDATE approvals SET status=… WHERE id=… AND status='pending'`（C11） | L | 03 §5、02 §3/§5、评审报告 §2 |
| M2.3 ✅ | **工具注册**：`@tool` 装饰器、docstring+类型注解自动生成 tool schema（ctx 参数不暴露给模型）、risk_policy 挂点、timeout/retries/**side_effect 读写标记**元数据（恢复期"仅读可重发"由此机器判定——评审 X2）、**有副作用工具注册期防呆**（未声明 risk_policy 或显式豁免即注册报错——评审 C15）、dispatch 表自动构建 | M | 03 §4 |
| M2.4 ✅ | **ToolExecutor**：七步生命周期（Pydantic 严格校验 → 权限三层 → 风险闸门 → write-ahead 落盘 → asyncio.timeout 执行（读可退避重试/写绝不自动重试）→ 结果规范化（超预算 fast 档摘要）→ 事件+审计投影）；**幂等键=tool_call 事件 id 透传下游**；错误回填给模型（**写工具超时/结果不明时回填"结果未知，禁止重试该操作"并引导查询确认**——模型自发重试会生成新幂等键使下游去重失效，评审 X1）、同一工具连败 2 次本轮禁用 | L | 03 §4 |
| M2.5 ✅ | **ContextBuilder**：六层预算编译（system 1.5k / 长期记忆 1k / 会话历史 4k / 本轮检索 3k / 工具结果 3k / 余量 ≥4k）；滚动摘要（最老一半轮次 fast 档压缩，产物写 `summary_updated` 事件、sessions.summary 由投影同事务派生——C8；预热 = 阈值 0.8 同步确定点执行，2026-07-11 拍板，plans\m2.5 §3.2）；**长期记忆与本轮检索两个槽位只做注入接口**（实现在 M3 RAG）；events 原文永远是事实源 | L | 03 §3 |
| M2.6 ✅ | **FakeGateway 录制回放基建**：cassette 格式定义、**匹配键=会话 id+轮次**（非 prompt 哈希；C10 后"轮次"精确含义=按调用源分道的**道内序号**——2026-07-11 括注）、回放器 + 录制器、重录流程文档（M4 CI 回归依赖此流程）、敏感字段不入 cassette；本步用**手写最小 cassette** 驱动测试，真实录制在 M2.11；**"轮次"按调用源分计数**——主循环/守卫分类/结果摘要/滚动摘要各自独立序号，任一序列错位必须响亮失配而非静默错配（评审 C10）；**事件等价性归一化规范**——写明哪些字段参与"逐事件一致"断言、哪些豁免（时间戳/事件 id 等），M2.12 与 M4.3 消费（评审 C31） | L（显式 2–3 天） | 03 §7、04 M2 |
| M2.7 ✅ | **AgentLoop 总装**：循环骨架（组装上下文→调网关→解析→分支）；**7 类终止条件逐个接电**（正常完成 + 六道闸门：最大轮数 10 / 单步超时 LLM 90s·工具 30s / 会话 token 预算 / 重复调用哈希窗口 3 次 / 协议违规纠错 2 次 / 用户取消·HITL 拒绝或超时）；含"诱导死循环"对抗用例；会话级预算闸门在此接电（三级预算的 L2 一级）；闸门 #6 本步只接取消信号与终止处理路径，HITL 拒绝/超时的真实触发源与其单测随 M2.9 交付 | L | 03 §2 |
| M2.8 ✅ | **Guardrails v1**：入口（注入规则库 + fast 档可疑度分类，回放驱动测试）；检索/工具结果包裹"不可信数据"标记；**流式出口句子级滑动缓冲增量检查**（system prompt 片段/内部工具名/PII 正则前缀匹配，命中截断替换）；终局整体复检 + 审计告警事件；**PII 出口守卫必须区分"本人数据 vs 他人泄漏"**——客服场景必须能向用户输出其本人手机号/地址，无条件正则截断会误杀合法回答，归属口径在本步敲定（评审 C23——2026-07-17 定案 owned_values 允许清单，见 §6.3） | L | 03 §6、02 §2⑨ |
| M2.9 ✅ | **HITL 挂起-恢复**：会话锁原语落 `core/locks.py`（owner token + Lua CAD + 看门狗，ADR-005 角色5，M3 API 层复用；**Redis 不可用降级为 PG advisory lock**——**session 级 `pg_advisory_lock` + 专用连接持有显式释放 + `hashtext(session_id)` 稳定哈希**（事务级 xact lock 首事务提交即释放撑不住跨事务 run、Python `hash()` 跨副本不稳定——评审 C4 修正），保住互斥而非放弃，停 Redis 验证纳入本步测试，ADR-005/02 §5）；risk_policy 命中→审批单（expires_at）→ `approval_requested` 事件 → run_state=awaiting_approval → 挂起（进程可下线）；审批回调**只做状态翻转**，恢复统一走"先取会话锁再恢复"单入口；批准后前置校验重跑的**挂点**（校验逻辑 M3 注入）；**审批决策路径校验 `expires_at`**——过期单拒绝翻转，fail-closed（评审 C7）；闸门 #6 的"审批超时"在 M2 用**可注入时钟**模拟触发做单测（reaper 到期扫描实装在 M3.9，M2 毕业项不悬空——评审 C7） | L | 03 §5、02 §2⑩ |
| M2.10 ✅ | **恢复调度**：运行中 loop 周期续租；reaper（Celery beat 周期任务，`workers/` 最小引导，Windows 本地 `--pool=solo`）扫描"租约过期且 running"抢租恢复；两类恢复语义——半截工具调用（凭幂等键安全重发）/ 半截 LLM 调用（作废重发，接受文本不同）；**kill -9 崩溃恢复验证**（已做，凭证 `reports/m2_kill9_recovery.txt`）；**恢复次数上限接电**——同一会话恢复超限（3 次——P3 拍板定死，"如"去掉）置 `run_state=failed` 并记审计事件，堵"毒会话让 reaper 无限抢租→恢复→再崩"（评审 C9，failed 的进入路径在此闭合）；Redis 全灭时 reaper 随 broker 停摆为已接受降级（02 §5/ADR-005 已登记——评审 C7） | L | 03 §5、06 §4 |
| M2.11 | **长对话基准与滚动摘要验收**：一次性真实调用录制 30–40 轮长对话 cassette（预算上限写死进脚本）；回放下触发 ≥2 次滚动摘要且能答出第 1–5 轮埋入的关键事实。**基准会话集构成登记**（04"录制基准会话集"在此收窄）：真实录制长对话 ×1 + 覆盖各终止原因/工具序列用例的手写 cassette 若干（M2.6 格式）；L3 隔离/预算行为用例的 cassette 由 M3.11 录制 | M | 04 M2 验收 |
| M2.12 | **毕业实验与整编**：回放模式**中断-恢复事件序列与不中断逐事件一致**（强断言进 CI）；真实冒烟只断不变量（无重复副作用/seq 连续合法/合法终止）；HITL 挂起-恢复端到端演示（必保路径）；验收清单对账、面试深挖题、报告落盘 `reports/`；LangGraph 对照文档落档（§10.1 #32） | M | 04 M2 验收 |
| M2.13 | **毕业四件**：CI 全绿 → tag `m2-runtime` → 记忆更新 → 本文档更新（§6 标 ✅ + 偏差登记）→ 开新会话 | S | §13 模板 |

### 6.2 毕业验收汇总（对账口径，缺一不算毕业）

- [x] 六道闸门各有单测，含"诱导死循环"对抗用例（M2.7④ adversarial 四盘 + test_loop_termination）；
- [x] 回放模式：中断-恢复后事件序列与不中断运行**逐事件一致**（CI 强断言）——M2.12①
  `test_recovery_replay.py` 三形态 8 测试（提交 `d0857de`）；
- [x] 真实模型冒烟只断不变量：无重复副作用（tool_invocations 幂等键核验）、事件 seq 连续合法、
  到达合法终止——`reports/m2_real_smoke.txt`（¥0.001004，双工具往返）；
- [x] 30–40 轮长对话触发 ≥2 次滚动摘要，第 1–5 轮埋入事实可召回——M2.11
  `reports/m2_long_dialog_recording.txt` + 回放 8 测试；
- [x] **必保路径 HITL 挂起-恢复**全绿（审批回调→状态翻转→单入口恢复）——M2.9 测试 +
  `reports/m2_hitl_demo.txt`（CAS 二次 decide=False、审计链 event_id≡幂等键）；kill -9 已提前于
  M2.10 完成（`reports/m2_kill9_recovery.txt`）；
- [x] 停容器降级两条（02 §5）：停 Redis——`reports/m2_degradation_redis.txt`（降级 PG advisory
  并发恰一互斥）；停 PG——`reports/m2_degradation_pg.txt`（退避后 EventStoreUnavailable 明确终止、
  write-ahead 核验式成立；实录抓出 OS 级连接错误白名单盲区，修复 `98e2549`）；
- [x] 测试与 CI 全程零真实 API 调用——结构保证：真实调用只在 scripts/（record_long_dialog +
  smoke_agent_real，两处例外均已消耗），tests/ 全 FakeGateway，ci.yml 无密钥注入。

**面试考点**：事件溯源 vs 快照；write-ahead+幂等键透传为什么才是真幂等（裸 order_id 做键为什么错）；
恢复由谁调度（租约/reaper/锁单入口三件分开答）；上下文压缩丢信息怎么办（摘要服务 prompt、events 原文兜底）。

### 6.3 实际交付对账（进行中——毕业时补全）

| 步 | 内容 | 提交 |
|---|---|---|
| M2.0 ✅ | 开工走查+评审处置（2026-07-07）：7 项口径裁决落 §2.2 + 五段文档声明落档；限流精度复测凭证 0.76%（#12 ✅）；超时语义重构——首块 25s/空闲 30s/deadline 传播/注入器 hang·midstream 模式（C1）；`GatewayRejected` 第六类异常（C6）；`core/tokens.py` 估算器 + 单请求预算闸门（C25 / #1 ✅）。测试 133→**150** | `0a71488` `3a89c95` `f176b1e` |
| 复盘补丁 ✅ | M0/M1 代码级复盘（2026-07-08，`docs/retro-m0-m1.md`）中用户揪出**降级熔断半开缺陷**：原 `fails=0` 违反主路径自家不变量（探测失败应立即重开），且每半开周期向坏上游漏 threshold 个请求。两步修复：① 对齐重开不变量（threshold-1）；② 升级为三键状态机**完整进程内镜像**（本地探测令牌互斥堵挂起场景 25s 并发泄漏窗，镜像令牌作废/归还，四镜像点各有单测）。测试 150→**154**。跨副本多探针为降级期显式接受（日志留痕） | `0d8ea74` `4f9e3f4` |
| 复盘补丁二 ✅ | 停 Redis 打压测（2026-07-08 用户主动实验）暴露：限流降级"每调用都撞挂掉的 Redis"——redis-py 8 默认 retries=10+指数抖动退避，每次失败拖 ~3.3s，10s 压测进攻坍缩到 60 次尝试（88.57% 误差量的是进攻没打出去，降级桶判定本身无误），违反"故障绝不拖垮请求"口径。修复三件：① try_take 降级**粘滞** + 5s 顺路探针自愈（本地探测令牌与熔断半开同构，三新增单测钉死粘滞/恢复/顺延）；② 共享客户端快速失败 connect 1s/read 2s/NoBackoff×1（core/redis.py，dead_r fixture 同款收紧）；③ 压测脚本预热——故障检测排除在稳态计时窗外，单独上报首发耗时（在线 29ms / 降级 1046ms≈connect 超时上界）。双模式精度 **0.19%**（524/525），凭证 `m2_ratelimit_degraded.txt`。测试 154→**157** | `f18c6a7` |
| M2.1 ✅ | 核心抽象三交付（2026-07-08）：①终止原因枚举 + LoopPolicy/ContextConfig（TERMINATION_GATES 钉死"六道闸门"口径，gateway_rejected 在七类之外）；②ToolDef/ToolContext/AgentSpec（side_effect 必填、写工具禁自动重试为类型不变量，tenant_config 对运行时不透明，Tier 复用 L1）；③EventType 13 类（时点值；M2.2 随 C8 增 `summary_updated` 至 **14 类**，代码为准）+ AgentEvent（seq 必填/无时间戳=确定性回放前提）+ AgentRuntime 门面与 GatewayLike 协议（mypy 静态锁真网关兼容）。事件类型枚举从 M2.2 提前至此。测试 157→**214** | `75f29c1` `fe8b3e4` `6d02897` |
| M2.2 ✅ | EventStream 底座四交付（2026-07-09）：①五表迁移 `74da3bf5d6ab`——(session_id,seq) 唯一约束、C2/C9 列落位（lease_generation/recovery_count）、reaper 与审批到期扫描索引、conftest 上移全仓、迁移模板根治旧式注解；②单写者写入器——内存 seq+约束兜底、IntegrityError 按事件 id 分诊（幽灵写入=成功/围栏=EventWriteFenced 终态不重试 C2）、瞬态白名单退避 0.1/0.2/0.4 耗尽抛 EventStoreUnavailable、SessionFactory 按形状声明；③投影同事务派生——纯函数、ProjectionError 掀翻整个 append 事务、payload 契约机器强制、`summary_updated` 落地（C8 裁决）；④审批 CAS——decide 查过期 fail-closed（C7）/cancel 不查/expire_due RETURNING+可注入时钟（C11）、`_rowcount` 单点消化存根缝隙。**偏差登记**：C9 的 failed 进入路径按原计划留 M2.10 行为闭合；规约三修（测试 AI 直写/指令块用户执行含 ruff format/深挖题集中 `interview-questions.md`）；CI 加 ruff format 门（`e430d83`）。测试 214→**251** | `4f60fa1` `02173df` `5bfe39f` `4cef2a1` |
| M2.3 ✅ | 工具注册两交付（2026-07-09）：①`@tool` 装饰器——签名+docstring 一次解析产 schema / args_model / handler 三消费者（同源防漂移），ctx 强制首位并从 schema 剔除（身份模型不可见），六种防呆 import 时爆炸（`ToolRegistrationError`）；ToolDef 演进 +`args_model`（母版，schema 是导出物）+`risk_exempt`，**C15 下沉到类型层**（写工具裸奔构造即拒、豁免留档可审计、与 risk_policy 互斥）；②`ToolRegistry`——重名注册期拒绝 / 幻觉工具名返 None（机制不定政策，处置归 M2.7 闸门 #5）/ `specs()` 保序喂注入面（回放确定性一环）+ **演示工具集**三形态（读/写带闸门/写豁免）落 `tests/runtime/conftest.py` 不进产品包；mypy 开 `explicit_package_bases`（双 conftest 撞名修复）。测试 251→**277** | `a44c78e` `270d938` |
| M2.4 ✅ | ToolExecutor 三交付（2026-07-10），七步生命周期全线通电：①前厅——JSON/args_model 严格校验（**lax+extra=forbid 口径定案**：宽容度与导出 schema 自洽）、风险闸门 **fail-closed**（谓词崩溃=阻断）、连败 2 次本轮禁用（熔断微缩版，账随实例每 run 归零）、五结局契约 `ToolOutcome`（工具世界不抛业务异常）；②执行核心——write-ahead 幂等键经 ctx 透传（echo 实证同一把钥匙）、超时取更严 min()、读退避重试写恒单次、**X1 结果不明**（写超时→RESULT_UNKNOWN 封死重试引导查询）、基础设施异常裸传播、`EventSink` 按形状声明（async def 版）；③规范化——预算收缩用 tokens 同一把尺（C25 三兑现）、摘要钩子 fail-open 硬截断+summarize_error 留痕（**C34 两方向**：安全闸门往死里收/增强层往活里放）、injected 收缩产物随事件留痕（X4，"可确定重算不留痕"公理）、digest 单行进投影。**偏差登记**：①预告收集数错报 12（实为 11），账已对平。测试 277→**301** | `d9a8a73` `8cc635e` `014ec21` |
| M2.5 ✅ | ContextBuilder 三交付（2026-07-11，新建 `runtime/context.py` 唯一生产文件）：①注入面+四简单层——`MemoryProviderLike`/`RetrievalProviderLike` 两 Protocol 槽位（实装 M3.5）、system 超预算 fail-loud（D15）、记忆按分截断/检索保序（D13）、工具结果**层聚合确定性折叠**（D6，单条收缩已归 M2.4，绝不二次调 LLM）；②会话历史层+滚动摘要——**四拍板项全按建议定案**（轮次定义/预热 0.8/同步确定点执行/`logger.warning` 留痕；C34 细化当天落 §2.2，03 §3 已回写）、分轮 JOIN 排除当前 run（D4）、触发式 `need>0.8×budget_h`、`summary_updated` 三键 payload（D7）经投影同事务落 sessions.summary（C8）、**try 只包 summarize——事件写入失败裸传播不吞**（计划伪码偏差当天登记 plans/m2.5 §4.3）；③future-import 一行修复收口。**偏差登记**：交付③三个收口测试提前进①②（③收缩为微调+毕业动作）；交付②曾误删 future import（AI 交付稿笔误，③补回）；期间用户自行入库仓库根 CLAUDE.md 产生 4 笔试验提交（含 message="test"，已推送不改历史，07 附1 已登记）。测试 301→**329** | `61695a3` `f9b0902` `3fde910` `c3eb8ce` |
| M2.6 ✅ | 录制回放基建三交付（2026-07-11，新建 `runtime/replay.py` 唯一生产文件 + `tests/cassettes/` 资产，零改既有文件）：①cassette 格式定稿——顶层三键/entry 两键、载入构造期防呆（版本/道名白名单/StopChunk 收尾）、os.replace 原子落盘 UTF-8/LF、**D2 拍板：request 侧只记摘要域四键（prompt 原文不落盘，PII 红线机械保证）**、手写 minimal_demo + 重录流程 README（M4.3 引用）；②FakeGateway——匹配键 `(session_id, scope, 道内序号)` 非 prompt 哈希（03 §7）、四道独立游标（C10）、游标先推进后 yield（D6）、CassetteMismatch 全诊断、`scoped_view` 直通不动 L1 schema（D10）、start_cursors 续跑偏移（M2.12 消费）；③Recorder——半截流不入带（D5，与缓存完整性守卫同哲学）/异常不吞不译/aclose 归还连接 + **C31 归一化定稿** `normalize_events`（id 别名化 e1..eN、approval a1..aM、墙钟与 usage 顶层豁免、summary/result 原文参与——M2.12/M4.3 断言本体）。**偏差登记**：normalize_event 伪码默认值 `{}`→`None`（ruff B006，计划已修）；开工核对回写三处上游文档漂移（§10.1 #39）。测试 329→**365**，全程零容器依赖零真实调用 | `70907f9` `3f772c0` `8bec868` |
| M2.7 ✅ | AgentLoop 总装四交付（2026-07-11，新建 `runtime/loop.py` + `runtime.py` 接电重写，仅两处生产文件）：①骨架+文本直答链——`_Tap` 事件外流（D16：yield 序≡seq 序、产出=落盘 I4）、user_message 恒首事件（I5/**D19 定案：由 loop 写入**，M3.2 经 run() 兑现不旁路）、run_id 每次新生成（X5）、**P1/P2 拍板均按建议**（取消信号 asyncio.Event 注入 / 身份读 sessions 行，无行 ValueError 零事件）、token 计数种子从事件流重建（D8 会话级）、**I3 显式接线**（executor 超时/预算显式传 policy/context_config——08 §8 #10"默认值巧合相等"挂点闭合）、两枚 summarize 钩子 `_make_summarizer` 经 scoped_view 分道（D15/C10：tool_digest→executor、summary→builder）；②工具分支——五结局一律回填继续（**K3 占位**：NEEDS_APPROVAL 单点分支留 M2.9 接缝，approvals 零行）、闸门 #4 连续计数器（D4 canonical_json 规范形键序抖动不重置/D5 打断不清零再犯即杀/**I8 打断那次无 tool_call 事件**）、D6 幻觉名计入闸门 #5；③异常矩阵——六类四组处置（Exhausted/Overloaded→step_timeout；预算类→token_budget_exceeded 带 cause 分层 D9；**Rejected 零兜底话术 C6/I9**；StreamInterrupted 作废重发 D10 死因随 detail 留痕），`_fail_llm_step` 钉 **I6 配对不变量**（M2.10 半截判据），不接 GatewayError 基类、基础设施异常裸穿；④诱导死循环对抗四盘 cassette 文件入库（同参死循环/空输出/换参续跑/token 烧穿——`tests/cassettes/adversarial_*.json`，供 M4.3 复用），四类失控全部有界终止。**偏差登记**：内部签名三处微调与测试命名映射见 plans/m2.7 偏差块；交付④预告曾误报"新增 35"（实为 36，账已对平——预告数字复核教训再犯一次）。测试 365→**401** | `cce29f0` `311283a` `a7c0e62` `6b7f22e` |
| 模型池变更 ✅ | 账号额度收窄（2026-07-16）：qwen-flash/turbo/plus/max 与 deepseek-v3 退役，routes/prices 切至 **qwen3.7-plus/qwen3.7-max/glm5.2**（fast=standard 同链首选 qwen3.7-plus，glm5.2 接任同平台异族容灾——provider 仍 bailian 零适配器改动）；smoke/debug 两脚本模型名同步；test_factory 断言同步（fast[0]=qwen3.7-plus）；文档已落档（06 §5 档位表重写、本文档五处 deepseek→glm 改注、08 §3.1/§9.1 快照更新、记忆档案）。价目为演示值，**首次真实调用须核对 API 回显名与价目表 key 并回填实价**（#28 注）。测试 **401 不变** | `c0633a9`；其上另有 dependabot 三合并（setup-uv 8.3.2 / mypy≥2.2.0 / ruff≥0.15.21），**HEAD=`26053f6`** |
| M2.10 ✅ | 恢复调度四交付（2026-07-17；六拍板 P1–P6 均按建议；**本步全部代码 AI 直写、用户验证提交——§2.1 第 1 条单步例外**）：①租约原语——config +4 字段（60s/20s/30s/limit 3）+ `LeaseStore` 六方法 CAS（**同 owner 重入**支撑 steal→resume 交接、**NULL 幽灵兜底**进扫描、release 清 recovery_count=干净收尾证明非毒会话）+ runtime `_pump_with_lease` 租约伴飞（心跳独立 task/事件间检查/正常耗尽才 release/**LeaseLost 自毁零事件**——C2 协议一二接电）；②恢复语义——`RECOVERY_ABANDONED` 第 **16** 类事件 + executor `reexecute` 窄入口（**原幂等键重执行**跳①–④复用⑤⑥⑦，以原 id 闭合投影）+ `_recover_locked` 四支分诊（尾终止仅修状态/悬挂工具 fill 配对/悬挂 LLM 作废重发与干净缝代码合流）+ 重建器 `approved_*→fill_*` 泛化（审批与崩溃同构复用）；③workers——celery 5.5 入依赖+layers、`reap_once` 纯 async 直测零 broker（薄壳 NullPool 独立引擎防跨 loop）、`ResumeHook` 注册点（未注册只抢租，C9 兜底自洽）、**C9 终局判定权在 T5 transition**（偏差 #7：mark_failed 因 NULL 兜底可重入废弃→clear_lease）；④kill -9 实录**四断言全 PASS**（write-ahead 后真 kill→reaper 注入时钟认领→单入口续跑；副作用恰一次幂等键账本自证/seq 连续 1..9/合法终止/计数归零），凭证落盘。**过程自抓三缺陷**（mark_failed 可重入/脚本 owner 不匹配/DyingFactory 配额 3→4）+ **用户首跑抓一课**：全库扫描函数的测试断言必须过滤式（AI 试跑残留污染 6 红——脚本加自清理根治，教训入 plans 偏差 #10）。测试 495→**531**（+36=17/7/12 恰中区间上限）。**CI 首推抓出时序敏感断言**（自家 §2.2 纪律违反——本地调度掩盖隐含时序假设；修正=断言只钉语义不变量"终止收尾类事件缺席"，不钉在途事件的竞态命运，`16e84bf`；与"过滤式断言"合为一对：断言只钉语义承诺不钉环境巧合——空间与时间各一课） | `2af377c` `7dccdbf` `3df455a` `de39165` `16e84bf` |
| M2.9 ✅ | HITL 挂起-恢复三交付（2026-07-17，新建 `core/locks.py` + `runtime` 四文件接线；P1 拍板方案 A + 两处会话中定案）：①锁原语——`SessionLock` 协议 + `RedisSessionLock`（SET NX / **Lua CAD 释放与比对续期**（owner token 身份凭证，防迟到释放误删他人锁）/ `hold_session_lock` 看门狗（续期失败 lost 置位即停——不重试不切后端 D13，兜底=(session_id,seq) 唯一约束））；②PG advisory 降级（**C4 三件套**：session 级 pg_try_advisory_lock / 专用 AUTOCOMMIT 连接显式释放（异常路径 invalidate 物理销毁防带锁归池）/ hashtext 服务端稳定哈希）+ `FailoverSessionLock` 粘滞切换（5s 顺路探针同限流器范式；**锁占用 False 不是故障绝不误降级**；持锁中途后端固定）+ **停 Redis（dead_r）互斥保住**（00 §6.2 毕业行闭合）；③挂起-恢复——挂起链路（开单 expires_at=`LoopPolicy.approval_ttl_s`（P1 方案 A，默认 1h）→ approval_requested → T2 → `_SUSPENDED` 哨兵干净收尾**无 loop_terminated**（D2））+ `resume()` 恢复单入口（**"审批回调只做 decide CAS"D1**；四结局分诊：批准→`execute(approved=True)` 通行证+`attach_event` 审计链+**事件流重建 working**（K2② 定案：llm_result 含模型侧 id/tool_result 取 injected 或同参 dumps/(name,args) 语义配对/弃置补话术防悬空 400；**保事实不保字节**——打断话术无事件不重建）+`loop.resume_run` 续跑；拒绝/撤回/超时→对应事件+CANCELLED 终止（**闸门 #6 三触发源闭合**，超时 C7 可注入时钟））+ `SessionStateStore.transition` CAS 状态机 **T1–T4 全接电**（T5 留 M2.10）+ **三重互斥**（decide CAS×会话锁×transition CAS，并发 resume 单赢家有测试）+ `PrecheckHook` 挂点（D19 否决回填不终止，M3.9 注入）。**会话中定案**：`lock=None`=无锁直通（get_redis 单例跨 event loop 炸+30 构造点零改动；M3.2 必须显式 build_session_lock）；续跑入口新造（计划预期"复用既有 API"落空）。**偏差登记**：plans/m2.9 头部 5 条（含既有测试两处冲击：DyingFactory 配额 2→3、M2.7 K3 占位测试删除）；验收时 `test_half_open_grants_exactly_one_probe` 高负载偶发一次（复跑三次绿，M1 时序缝备查 M4.0）。测试 459→**495**（+36=11/11/14 净，区间 [30,40] 内） | `184a485` `ab4fcd8` `578b37f` |
| M2.8 ✅ | Guardrails v1 三交付（2026-07-17，新建 `runtime/guardrails.py` + 三挂点接线，D6/D7/D8 三拍板均按建议获准）：①入口防线——14 条规则库（规则名与档位是契约、8 良性样本钉零误杀）+ `build_classifier`（fast 档、guard 道视图、**严格白名单解析**："High."/"高"一律 ValueError 转 fail-open）+ D3 综合裁决只抬不压（StrEnum 裸 max 字典序陷阱→`_SEVERITY_ORDER` 显式序，测试钉死）+ C34 fail-open（分类器挂→仅规则库+`classifier_error` 留痕）；②包裹+出口——`wrap_untrusted` 防伪标记改写（payload 恒存原文 X4）、`OutputGuard` 纯同步确定性状态机（**句界+定长伪句双规则切分**——计划"整 buffer 伪句"因破坏逐字符≡整段不变量而修正、尾窗抓跨句拼出、D15 打码摘录 ≤40 字符）、**C23 定案：`owned_values` 允许清单规范化（剔 `[-\s]`）字面等价→本人 PII 放行、其余截断**、PII 四规则（银行卡显式 v2）；③接线——`GUARDRAIL_TRIGGERED` 第 **15** 类事件（无投影 miss=noop 零 store 改动）、AgentSpec +`owned_values` **+`entry_classifier`（会话中拍板：分类器按租户开通、默认关——规则库是无条件底座，增强层不让既有 452 测试陪跑 guard 道）**、ContextBuilder +`entry_notice`（D9 预案生效）、**挂点③聚合 feed 定案**（改造收敛在 `_finish_text` 单点、`_llm_step` 零改动——确定性不变量保证与 M3.10 逐帧行为一致，08 §5.10 预警兑现）、挂点②五结局一律包裹（闸门 #4 打断话术除外：运行时模板非外部数据）、`UNTRUSTED_NOTICE` 恒拼 system（loop 侧拼接，spec 原文不动；OutputGuard 片段集用 spec 原文防机制说明误杀）、防线命中一律 `COMPLETED`（D10）。**偏差登记**：plans/m2.8 头部偏差块 7 条；§5.3 第 8 条快照测试并入 test_events 更新。测试 401→**459**（+58 = 31/20/7，计划区间 40–60 内；另 lockfile 同步 chore `bc63ba3`） | `66b5d22` `9e8efe6` `553fb20` |
| 模型池变更二 + C1 盲区修复 ✅ | M2.11 录制五连败揪出双缺陷（2026-07-17，根因链 plans/m2.11 偏差 #8–#12）：①**幻影 glm5.2**——07-16 入池未实测，实为 404 model_not_found，三档 fallback 断链两日；充值解锁后池重构 **fast=qwen-flash→turbo / standard=qwen-plus→turbo / strong=qwen3.7-max→plus**（便宜优先回归 M1 形态；qwen3.7-plus 退出路由价目保留；入池三验纪律落 06 §5）；②**思考型模型饿死首块计时器**——qwen3.7 系默认先流 reasoning_content 而适配器不消费，25s 卡解析后首 chunk 被饿死，且隐藏思考 token 计费虚高（探针实测 54→4 塌缩）——百炼请求统一 `enable_thinking:false`（§2.2 C1 补注；残留盲区与三验纪律挂 §10.1 #41）。"同平台异族容灾"叙事作废（#28 已注）。测试 **531 不变**（test_factory/test_openai_compat 断言同步） | `90060c9` `61e89d7` |
| M2.11 ✅ | 长对话基准三交付（2026-07-17，**真实调用例外①消耗**，00 §6.2 第 4 条闭合）：①录制脚本 `scripts/record_long_dialog.py`——40 轮剧本/五埋点（1-5 轮埋、11-12 轮复述强化、36-40 探针）/预算三上限+`SESSION_TOKEN_BUDGET=400_000`（闸门 #3 会话级累计口径，默认值必超）/**六道自检先于落盘**（摘要≥2/覆盖≥12/探针全中/全轮 completed/零护栏/零 fail-open）/剧本与判据经 importlib 供测试复用（I1）；②真实录制 `tests/cassettes/long_dialog.json`（main 40+summary 2，session `464da844`）+凭证 `reports/m2_long_dialog_recording.txt`（42 调用/83,212 token/**¥0.0678**/覆盖 (1,11)(1,21)/五探针逐字中/#28 对照闭合）——**六跑迭代 ≈¥0.55 收敛**：摘要枚举丢弃/C34 fail-open 回放分歧/CJK 专名采样变异/时间格式归一四类失败模式+幻影候选+思考饿死，六项真实缺陷各现形一次、全部被自检拦在落盘前，零坏资产入库；③回放验收 8 测试+基准会话集登记表（cassettes README §6，12 行补缺 0，L3 归 M3.11）。**偏差 14 条**登记 plans/m2.11 头部（要点：剧本加固经用户特许 AI 直写=单点例外；交付③首跑环境依赖 5 红→回放 cassette 重绑定随机会话修复；第二笔提交 message 与首笔重复=提交纪律偏差）。深挖题 63-69 入库。测试 531→**539** | `8a2d4de` `3679e7f` |
| M2.12 ✅ | 毕业实验三交付（2026-07-17）：①中断-恢复逐事件一致 CI 强断言——`test_recovery_replay.py` 三形态 8 测试（等价判据=C31 归一化+半截步折叠+剔 run 簿记键 {iteration,input_tokens_est}；确定性中断=monkeypatch EventWriter.append——计划 CrashSink 的无缝实现；比较器/harness 各有自证），539→547；②毕业实验四件——真实冒烟 `smoke_agent_real.py`（三不变量+成本顶 ¥0.10，实测 **¥0.001004** 双工具往返，**真实调用例外②消耗，M2 配额清零**）+ HITL 演示 + 停 Redis 锁降级实录（并发恰一互斥）+ 停 PG 实录，四凭证进 reports/；**停 PG 实录抓出真缺陷**：asyncpg 建连 OS 级错误（非 dbapi.Error）未经 SQLAlchemy 包装裸穿 append 白名单——`fix(runtime)` 白名单纳入 OSError + 回归测试（先验证现行代码红再转绿），547→**548**；③`docs/compare-langgraph-m2.md` 落档（#32：1.0 世代/四覆盖面/命运表 14 行/主权章/行数账≈600:3300:200 估算）+ 深挖题 70–74。偏差 10 条 plans/m2.12 头部（#7 缺陷候选 finally 次生异常挂 M4.0） | `d0857de` `d4abb40` `98e2549` |
| 复盘补丁五 ✅ | M2 全量复盘站 13 追问（2026-07-21）揪出判死谓词竞态：C9 判死只查 count+run_state、**不查租约活性**——并发 reaper 恰在 count=limit-1→limit 抢到并正在执行第 limit 次**合法**恢复时，另一 reaper 快照见 count=limit∧running → T5 判死+clear_lease 掐掉进行中的最后一次合法救援（围栏保安全零正确性损失——被掐方 LeaseLost 自毁零事件，但"被允许开始却被同伴处决"语义不净）。修=`_session_snapshot` 增 keyword-only `now` 参数、返回四元组新增 **lease_alive 在 DB 端算**（时钟纪律 func.now()/now 可注入；`and_(is_not(None), > cutoff)` 布尔列永不 NULL），判死分支**活租约让行**（无为——对手死后租约过期下轮照常宣判，最坏延迟一个 TTL）；steal 路径本要求过期、不受影响。测试=钩子模拟竞态交错（处理 A 会话的钩子期间"对手"抢走 B 会话），**先红后绿**；既有 9 测全用过期租约零冲击。测试 552→**553** | `b0e438b` |
| 复盘补丁四 ✅ | M2 全量复盘站 9 追问（2026-07-18）坐实入口规则库语言不对称：14 条里唯 `tool_probe` 无英文对应（plans/m2.8 §规则表计划期即缺、非实现漏敲；对照 override/prompt_probe/role_hijack/mode_jailbreak/bypass 皆双条）。英文探工具面（"list your available tools"）此前入口不打 MEDIUM 标——**召回缺口非洞穿**（工具名真外泄由出口 OutputGuard tool_name 守卫兜底，语言无关）。补第 15 条 `tool_probe_en`（三分支：your/available/internal+tools｜list/enumerate+tools｜what tools do you have/are available/can you use-call-access；MEDIUM）+ 误杀防线一条业务英文良性样本；采样验证 5 攻击命中/5 良性放行（"which tool should I use"/"what functions does this coupon support" 皆放行）。规则名集合是契约=只加不改，历史回放安全。测试 550→**552** | `a138bbd` |
| 复盘补丁三 ✅ | M2 全量复盘站 7 追问（2026-07-19）揪出"最新轮盲窗"：肥摘要独占历史层版面时，uncovered 近轮既无原文席位、又最晚进摘要（收编从最老吃起），摘要长度无生成期上界使盲窗可慢性化。**三改法两轮否决后终裁只改 prompt 版面**：`_SUMMARY_PROMPT_SHARE=0.5`——`_compose_history` 确定性收口内**有 uncovered 排队时**摘要至多占 allowed×份额（无人排队不设限、版面不白扣）。落库 clip 被否（租户策略 history_budget 不得污染不可变事实——X4/cs-11 口径，与 executor result 全文+injected 同族）；生成侧 max_tokens 被否（解码级硬截断把半句残话写进事实源、触顶信号被钩子静默吞）。残余边界显式接受：摘要生成长度理论无界，跑飞代价=summarize 成本（ledger 可见），prompt 已由份额保护。事实链零触碰（payload/`_SUMMARIZE_PROMPT`/cassette 原样）。测试 548→**550**（cs-14 份额咬合+最新轮进场 / cs-15 无队列不裁；cs-11"事件存全文"口径经议保留） | `b628ce4` |

---

## 7. M3 · L3 客服业务（2 周基线，13 步）✅ 2026-07-28 毕业（tag `m3-support`，852 测试）

### 7.0 定位

平台第一次"接上业务与用户"：多租户 RAG、业务工具、HITL 业务闭环、SSE 对外接口。
安全对抗用例是本里程碑的灵魂——**四大对抗场景全绿才算数**（见 7.2）。
**真实调用口径**：M3 开发调试与验收演示使用真实百炼调用（意图分类/对话/embedding 均过网关计量，
月度预算闸门兜底）；CI 仍零真实调用（回放/夹具驱动）。

### 7.1 步骤计划

| 步 | 内容 | 规模 | 文档锚点 |
|---|---|---|---|
| M3.0 | **开工走查**：重读 02 §3/§7/§9 + ADR-005/006/007 + 01 §5；M3 全景图；核对 M2 留下的注入挂点（ContextBuilder 检索槽位、risk_policy、前置校验重跑挂点） | S | §12 地图 |
| M3.1 | **业务底座与认证**：tenants（config jsonb 含 approval_threshold 等；**token_budget_monthly 为独立列**——02 §3）/ users（role 三档）表迁移，与 M2 五表的既有列对齐；**月度预算闸门读路径从 config.py 切到 tenants 表【开工时敲定】**（§10.1 #13）；FastAPI 入口 `api/`；终端用户短期 JWT（sub+tid）+ 坐席/管理员平台账号 RBAC；**端点×角色矩阵**（02 §7.1：终端用户不可见完整 trace）；`GET /v1/usage` 一并落地（02 §9/§7.1 既有端点，plans/m3-detailed U13 补记 2026-07-24——M4.2 gauge 与 M4.6 成本实验的底座） | L | 02 §7.1 |
| M3.2 | **API 层入站三件**：入站限流（租户维度，与 L1 出站限流分工明确）；**会话互斥**（复用 core/locks.py，锁被占返回 409；awaiting_approval 时消息准入规则——不开新循环、用户明确取消走 approval_cancelled）；user_message 事件落盘 | M | 02 §2③ |
| M3.3 | **RLS + 连接池租户上下文**（已知坑，显式 1–2 天）：每事务 `SET LOCAL app.tenant_id`（SQLAlchemy 事务钩子）；**低权连接角色**（无 BYPASSRLS，owner 默认绕过 RLS）；策略 USING 子句；集成测试：绕过 Repository 的裸 SQL 返回空集、并发双租户请求不串上下文 | L | 02 §7.2 |
| M3.4 | **摄取流水线**：documents/chunks 迁移（vector(1024) + embedding_model 列 + HNSW 索引）；Celery worker：解析→切块→text-embedding-v4 批量调用（走网关计量，限流/重试/**断点续传**——一批失败不重跑全量）→入库；`POST /v1/kb/documents` 异步任务 | L | ADR-006、02 §8 |
| M3.5 | **多租户检索**：WHERE tenant_id + RLS 兜底；召回完整性——`hnsw.iterative_scan=relaxed_order` 或小租户精确扫描；轻量重排（关键词覆盖+元数据规则）；top-5 分数阈值，全低于阈值=检索失败走兜底（宁可说不知道）；RAG 检索结果接入 ContextBuilder 检索槽位（#7）；~~长期记忆检索 tenant_id+user_id 双过滤接入~~（**P1/#20 拍板砍出 v1，2026-07-24**：memory 槽位保留接口、恒空置） | L | ADR-006 §3、03 §3 |
| M3.6 | **意图路由**：fast 档单次分类调用（不是 Agent）：FAQ 直答（含精确缓存命中直接流式返回）/ RAG / 工具 / 转人工 | M | 02 §2⑤、ADR-002 |
| M3.7 | **模拟业务系统 + 工具五件**：进程内 FastAPI 子应用（延迟/错误率注入可配）；orders / logistics / tickets / refunds / coupons（coupons 复用退款骨架，半天）；**幂等键下游去重实装**（退款服务按透传的事件 id 去重——M2 契约在此闭环）；归属校验 `order.user_id == ctx.user_id` 在工具实现内强制 | L | 02 §8、03 §4 |
| M3.8 | **主 Agent 装配 + 转人工**：`apps/support/agent.py` 组装 AgentSpec（prompt/工具集/策略/租户配置注入）；handoff（转人工=工单+上下文摘要）；检索失败/循环达上限的兜底话术 | M | 03 §1、02 §2 |
| M3.9 | **HITL 业务闭环**：审批 API（approve/reject，强制 `operator.tenant_id == approval.tenant_id`）+ curl 演示（审批页 stretch）；expires_at 超时（reaper 扫描 + approval_expired 事件）、用户撤回、**批准后前置校验重跑**（订单状态/可退余额——TOCTOU 显式防）；approval_pending 提示帧 | L | 02 §2⑩、03 §4③ |
| M3.10 | **SSE 双通道 + 聊天页**：`POST /v1/chat` 流式（token/tool_status/approval_pending/done/error 帧）；`GET /v1/sessions/{id}/stream?after_seq=N` 重订阅通道（断线重连与审批后续跑统一入口，原生 EventSource）；进行中消息 Redis 缓冲、重连整条重推（消息重置帧）；**PG LISTEN/NOTIFY 跨副本事件通知实装**（§2.2 C22/#37，U4 补记 2026-07-24）；`GET /v1/sessions/{id}/events`（operator+ 限本租户，含最小审计留痕）归本步（U14 补记）；单文件聊天页 | L | ADR-007、02 §9 |
| M3.11 | **种子评测集 + 演示数据**：15–20 条（**≥10 条租户隔离对抗 + 5 条知识库外**），先以文件形态维护（落表在 M4.4）；**将隔离/预算等 L3 行为用例录制为回放 cassette（预算上限写死），供 M4.3 CI 回归消费**；每租户 10–20 篇文档语料；种子订单脚本（1 天） | M | 04 M3 |
| M3.12 | **毕业验收 + 整编**：7.2 全量对账；性能口径实测（缓存命中 <50ms、未命中首 token <2.5s，本地口径实测修正）；报告落盘；毕业四件（tag `m3-support`） | M | §13 模板 |

### 7.2 毕业验收汇总

- [x] **四大对抗全绿** ✅：CI 集中面 `test_adversarial.py` 7 测（`ae3490e`）+ 各步行为面与真实实录（凭证 `reports/m3_acceptance.md` §1）；
- [x] 性能两口径 ✅：缓存命中中位 **10.2ms**（<50）/ 首 token **P50=1408 / P95=2239ms**（<2500）——无修正项（凭证 §2）；
- [x] 审批阈值链路 ✅：demo_hitl 六段（2026-07-26，含 TOCTOU/超时/撤回）+ demo_chat 幕 A 直执 + L3 hitl 盘重录再证（凭证 §3）；
- [x] 兜底触发率 ✅：**5/5=100%**（≥95%；三轮闭环 60→80→100——R1 真编造→prompt 规则 3 具体化+五盘重录、R2 判据漏报→信号集反哺；逐条归因入凭证 §4；绝对值以 M4.5 扩集复测为准）。

**面试考点**：意图路由为什么用小模型；切块策略对召回的影响；HITL 挂起状态存哪、超时未审批怎么办；
RLS 在连接池下为什么必须 SET LOCAL；pgvector 带 WHERE 的召回怎么保证（两层表述）。

### 7.3 实际交付对账（进行中——毕业时补全）

| 步 | 内容 | 提交 |
|---|---|---|
| M3.0 ✅ | 开工走查（2026-07-24，零代码）：§0 十九项核对全过（基线 553/`b0e438b`；核对实况 14 条登记 plans/m3-detailed 头部——要点：user_message 由 loop 写、PrecheckHook=(tool_name,args) 无 ctx、审批 TTL 走 LoopPolicy 注入、检索槽位无 user_id 且预算装填归 builder、层序须升 workers、#42/#43/#44 实锚确认）；**P1–P7 全按建议拍板**（#20 翻 ✅ 长期记忆砍出 v1，01/02/03/00 叙事同步修订）；02 §3 补"以 migration 为准"对账注（U2）、§7.1 M3.1/M3.5/M3.10 行补记（U4/U13/U14） | 无代码提交 |
| M3.1 ✅ | 业务底座与认证四交付（2026-07-24）：①tenants/users 两表迁移 `6304edbb4760` + `core/tenancy.py`（Role 三档/TenantRecord 含 token_budget_monthly 独立列/TenantDirectory 60s TTL 只读目录）+ seed_demo 起步版（2 租户 8 用户 upsert 幂等）；②`api/` 起步——auth.py（HS256 双密钥窗、require+algorithms 双锁、**弱钥 <32B 升硬错误**（RFC 7518，PyJWT 告警实录触发）、空钥/弱钥 ValueError 与坏 token 401 分家）+ main.py create_app 工厂 + mint_token.py（P7）+ **层契约五层化 `aegis.api \| aegis.workers` 置顶**（`\|`=互不 import，源码查证纠正计划 `:` 写法）；③预算闸门切表——`monthly_budget_resolver` 注入缝三态（值/静态/None=读挂 fail-open）+ factory 注入 TenantDirectory.monthly_budget（**#13/#22 闭合**；resolver=None 行为与 M2.4 一致由既有测试零改动作证）；④`GET /v1/usage`（U13：明细+模型/天/会话三聚合裸 SQL；operator 点名他租显式 403；金额以精确小数字符串出线——pydantic v2 Decimal 缺省，"钱不过 float"延伸到线上）。**偏差 7 条**登记 plans/m3-detailed #14a（要点：交付稿三缺陷均用户跑门抓出——mypy dict 不变性/PyJWT 弱钥告警/Decimal 序列化认知错，教训各入库）；深挖题 103–107。测试 553→**588**（8/16/4/7 累计 +35，M3.1 预告区间 22–32 上浮 3——安全面与聚合对账加固） | `9e7e72d` `3a41a50` `43db3a5` `69b2e93` |
| M3.2 ✅ | API 入站三件（2026-07-24）：入站限流依赖工厂 `rate_limited`（租户维度 `inbound:{tid}`、即问即答 429+Retry-After=Lua 桶真实提示——try_take 替代 wait_take(max_wait=0)，偏差 ⑼）；`POST /v1/chat` 入站前半——首见建行+归属 404（**#19 ✅**）、矩阵 operator"—"=403、awaiting_approval 准入不开新循环、**显式取消**（ApprovalStore.cancel CAS→M2.9 拒绝族路径收尾，绝不覆盖赢家）、user_message 经 run() 由 loop 写绝不双写（U8 兑现）；**锁全权归 runtime**（端点预取会自撞——偏差 ⑻，SessionLockHeld 统一 409，except 阶梯先裸穿事实源三类）；create_app 五注入参+`build_session_lock()` 生产接线现场。**交付稿缺陷一枚探针定位**：future-annotations×依赖工厂闭包=注解反解失明、参数退化必填 query 全量 422——修=ratelimit.py 弃 future import；教训与 3.14 升级评估落 #45、题 108。测试 588→**600**（+12） | `d2bd55d`（另 scripts 索引 chore `ebb0cf9`） |
| M3.3 ✅ | RLS + 连接池租户上下文两交付（2026-07-24，显式 1–2 天步实际一天收口、超时预案未启用）：①隔离基建——`core/tenant_ctx.py`（ContextVar 每任务独立副本 + `tenant_context` set/reset + **"begin" 事务钩子**：`text()` 具名绑定 `set_config(..., true)` 事务级注入，**计划伪码 `exec_driver_sql+%s` 在 asyncpg 是语法错、探针实证改定**；不残留亦探针实证）+ db.py **双轨引擎**（app=`aegis_app` 无 BYPASSRLS+挂钩子 / owner=维护面 D4 不冒充租户）+ **手写迁移** `c895f9007bf7`（角色幂等/GRANT+DEFAULT PRIVILEGES/五表 ENABLE RLS+**USING·WITH CHECK 双子句**）+ RLS 六测（真提交独立引擎；02 §7.2 两条点名测试——裸 SQL 空集/并发双租户不串——全绿）；②接线——auth 验签即设上下文（#18 请求路径）、usage `tenant_context(target)`（RLS 下 admin 跨租户视图前提）、seed/mint 切 owner。前置义务：M3.4/M3.7 新表迁移自带 ENABLE RLS；M2 演示脚本随用随修（M5.4 统一过）。测试 600→**608**（+8） | `1c08806` `d73e098` |
| M3.4 ✅ | 摄取流水线四交付（2026-07-24 单日收口；开工拍板 A–E+过程拍板 F/G 全按建议）：**①**知识库两表（迁移 `7fe5de25a9ca`：EXTENSION 首句/vector(1024)/HNSW 余弦手写/两表 RLS 双子句——M3.3 前置义务兑现）+rag/models.py（P6 落地：chunks 冗余 tenant_id、embedding 可空=续传锚、UNIQUE(document_id,seq)）；**②**L1 受控缝第二处（D5）——gateway/embeddings.py（切批 EMBED_BATCH_SIZE=10/按 index 归位/三重形状校验 fail-loud/白名单与退避尺复用 resilience/计量 fail-open）+`record_embedding`（tier="embedding" 自由串）+`build_embedding_client` **双参数化 session_factory+client**（Celery 每任务新 event loop，DB 池与 HTTP keep-alive 都绑旧 loop——校验真探针实证）+**拍板 F：embedding 用量计入月度预算**（month_spend 不分 tier=预算管真实花销）；**③**切块+任务——split_text 三级降级（段落聚合/句界/硬切窗；overlap 种子装不下即丢，越界块缺陷被双路校验独立揪出、elif→if 一词修复+回归钉子）+workers/ingest.py（薄同步壳+ingest_once 四步：PROCESSING→切块幂等（UNIQUE 兜底并发）→**IS NULL 批量回填每批独立事务=断点续传全部实现**→DONE 清 error；壳=asyncio.run+指数退避 5 重试+FAILED 消毒落列）+**拍板 G：documents 补 text 列**（迁移 `c28efda87e6a`——计划内在矛盾的最小修复：wire 签名只带两 id×原文无居所，meta 塞原文/消息携带/API 切块三替代全否决）+**#18 就此闭合**（任务局部 app 引擎+guard+tenant_context 包全程）；**④**api/kb.py（先落库后投递/enqueue 失败 503 行留 PENDING=ADR-005 角色4 诚实降级）+create_app 第六注入参 enqueue（决策 A 落地：轻量 producer send_task 按 INGEST_TASK_NAME 投递，api 零 workers import，wire 常量落 apps 两端同源+include 钉子测试）。**真实链路验收 PASS**（202→worker"摄取完成"→documents=done(1 块)→usage_ledger embedding 行 28 token/¥0.000014——#18 运行时证据+F 账本落地；M3 真实调用口径 ✓）。质检工艺演进实录：①②四路对抗校验工作流→③双 Agent→④影子排练（轻量流程定型：副本全链排练 ≈3 分钟；ruff 对 CJK 按宽 2 计列的翻车根因记档）；累计消化 47 findings，血账两条（split_text 死分支越界块/shared_client 跨 loop 炸）。偏差 (23)–(27) 登记 plans 14d；测试 608→**655**（+47=11/14/15/7，§5.2 预告 +14–20 上浮均逐条有名分）；深挖题 117–123 | `55ea421` `f8fa77e` `6e5f769` `993d1c4` |
| M3.5 ✅ | 多租户检索四交付（2026-07-25 单日收口；开工拍板Ⅰ–Ⅲ全按建议：#42 修案 (a)/查询侧不接 limiter/留白起步值）：**①**rerank.py（CJK 二元组+字母数字段覆盖率零分词、与 tokens.py 同一把尺；score=0.7×sim+0.3×cov；sorted 稳定同分保输入序；RetrievedChunk 住依赖下游=分层代价）；**②**retrieve.py Retriever 六步（embed 事务外/租户计数 60s 缓存 clock 注入/双开关召回：≤10_000 精确扫 else `hnsw.iterative_scan=relaxed_order`、SET LOCAL 与查询同事务/裸 SQL `CAST(:qvec AS vector)` 具名绑定/3×top_k 候选池/全低于 0.35 返空=宁可说不知道）——**用户评审揪出 AI 稿 tenant_context 自包裹缺陷并撤修**（叶子自冒充把 RLS"环境身份×参数租户"交叉核验短路成第一防线镜像，恰是对抗①泄漏方向；身份恒由边界建立；衍生 ContextVar 三形态探针：协程内 set 随 asyncio.run 生死/同步壳 set 粘线程上下文/--pool=solo 不 reset=跨任务静默串租）；**③**RetrievalProvider 槽位适配器（**#7 接电、#42 修案 (a) 落地，L2 零改动**：形状适配不裁剪/`wrap_untrusted(source="retrieval")` 注入面包裹/fail-open 留痕续跑，ContextBuilder 集成钉子两条）；**④**真实校准（**0.35 维持**：on-topic 0.45–0.60 全命中、off-topic 0.19/0.31 全拒答——「优惠券」sim=0.45 被 0.7 权重压回=重排真实战果；B 租户查 A 专有短语空集=**对抗①真实链路 PASS**；分离窗 [0.31,0.45]；脚本入库 calibrate_retrieval_threshold.py 供 M3.11 复核）。横切两笔：**偏差(22) 闭合**（known-first-party 钉死——AI --fix 盲吞 I001 假阳性致 CI 红/本机缓存绿事故实录）；test_usage 随机租户化（M3.4 真实残留×固定 id×全局相等断言=M2.10/M2.11 教训合体复发）。偏差 (28)–(34) 登记 plans 14e；测试 655→**681**（+26=12/9/5，§5.2 预告 +12–18 上浮 8 逐条有名分）；深挖题 124–127 | `c615482` `a7a3ba6` `9ff6e52` `0579055`+`43e3bfd` `c4f0829` `dac1f32` |
| M3.6 ✅ | 意图路由两交付（2026-07-25 单日收口；计划外微决策两项按建议：Ⅰ fail-open 捕获面 `except Exception`（C34 样板对齐，宽于计划字面"六类"——except GatewayError 会连 ProviderError 泄漏一并吞，收窄收益为零）/Ⅱ answer_faq deadline_s=10.0 同 classify）：**①**`apps/support/intent.py`（138 行）——Intent 五值 StrEnum（**AGENT=分诊失败落点，刻意不在 prompt 词表**）/INTENT_PROMPT（"定了不动"纪律，M3.11 cassette 语义）/_parse_intent **恰一词判据**（宽容只救格式："分类：faq"救回；绝不洗歧义："faq或rag"→AGENT）/classify（与 build_classifier 同构：fast 档单次无循环无工具**绝不重试**（ADR-002 决策 2）；失败落点 AGENT 而非 ValueError——兜底不是降级裁决而是"换一条同样正确的路"）/answer_faq（system=faq_digest 原文=prompt 政策归租户配置（机制不定政策）；**刻意不兜异常**：直答是主路径非增强层，处置权归 M3.8/M3.10）+test_intent.py 15 测；分支接线归 M3.8/M3.10、缓存隔离零代码（cache._key 租户前缀既有，对抗②归 M3.12）；**②**真实实测（用户实跑）：新鲜四调 2357/976/901/947 ms（首条含连接建立，**后三条 <1s 达标**）、重复问精确缓存命中 **8 ms**、分类 **4/4 全中**；**拍板 (37)**：实测脚本入库 `scripts/measure_intent_latency.py`（measure_ 新前缀族，M3.12/M5.2 复用）。偏差 (35)–(37) 登记 plans 14f；测试 681→**696**（+15，§5.2 预告 +8–12 上浮 3 有名分）；深挖题 128–129 | `d2475f9` `e79734f` |
| M3.7 ✅ | 模拟业务系统+工具五件四交付（2026-07-25 单日收口；开工拍板三项按建议：Ⅰ **#43 修案(a)** handler 转译 / Ⅱ **mock 不挂主 app**（tenant_id/user_id 裸参数，挂上=未认证水平越权入口，§4.7"挂 /mock 前缀"作废）/ Ⅲ 验收订单脚本自带）：**①**数据层——mock_orders（归属与可退性事实源）+mock_write_ops（**PK=idempotency_key=去重物质基础**）+手写迁移 `f4b8d2a97c31`（两表 RLS 双子句=M3.3 前置义务第三次兑现）；影子排练新增**影子库环节**（aegis_shadow 空库七级迁移链全量重放=裸库自举验证）；**②**mock 子应用——create_mock_api 工厂（create_app 同惯例）/四端点（伪轨迹=状态确定性派生零随机）/**去重单事务化**（claim ON CONFLICT DO NOTHING→撞键回放台账 payload+duplicate:true→首键校验+执行+回填同事务=**崩溃零中间态+失败不烧钥匙**、恰一次由唯一索引仲裁不靠应用层锁；同键二击参数不同也返首击快照=防模型紊乱参数重发）/故障注入中间件（X1"结果不明"剧本发生器；`_no_mock_injection_in_prod` 校验器同故障注入哲学）+client.py ASGITransport 懒单例；**③**工具五件+_shared 底座——**#38 声明清单 CI 化**/对抗③三路拒绝（他人/跨租户/不存在）**逐字节同话术**（泄露"存在但无权"=泄露他人单号有效性）/**#6 全链闭环**（Idempotency-Key=ctx.tool_call_id——M2.4 透传的钥匙首次开锁，台账主键即 write-ahead 事件 id）/**#43 落地**（post_write 单点，发出前/发出后分界，executor 零改动）/coupon_threshold 新租户 config 键缺省 0 fail-closed/409 业务拒绝回 dict 不进连败账；**④**真实链路三幕全 PASS（Agent standard 档查单退款 completed・工具序列恰 [order_query,refund_apply] / 同键二击 duplicate false→true / 越权读写统一话术）——demo_tools_acceptance.py 入库（AI 稿两处引用错被影子门抓获=硬规则 8 排练面）。偏差 (38)–(42) 登记 plans 14g；测试 704→**732**（+36=8/14/14，§5.2 预告 +20–30 上浮 6 有名分）；深挖题 130–132 | `974b0be` `3df3cc3` `95faef2` `6865ba8` |
| M3.8 ✅ | 主 Agent 装配+转人工三交付（2026-07-25 单日收口；开工拍板四项按建议：Ⅰ ResumeHook 挪 M3.9（00 行权威范围；worker 跨 loop 受控缝工程集中一步）/Ⅱ **L2 受控缝获准**（AgentRuntime +retrieval additive 参——§1"对 L2 零修改"修正为"零行为修改，additive 注入缝经拍板"）/Ⅲ 检索槽**每轮注入**不做"仅 RAG 预热"特殊化（RAG/TOOL 区分退化为分类语义）+FALLBACK_NO_RETRIEVAL 静态进模板/Ⅳ owned_values v1 恒空留缝（users 无 PII 列，00 §10.3 已档））：**①**prompts.py（模板四规则——规则3"宁可说不知道"静态化、规则4 计划外"审批拒绝如实转达不擅自重试"=X1 话术 prompt 侧镜像）+agent.py（ALL_TOOLS 货架/build_agent_spec：白名单点名未知名启动炸・去重保序・预算与 approval_ttl_s 注入・memory_budget=0・**9 字段注入面收尾**）+INTENT_PROMPT 修订（M3.6 后置修订⑵ 兑现，独立 fix 提交）；**②**handoff.py（摘要三档：sessions.summary→末三 messages→占位）+service.py（ChatFrame+ChatService：**FAQ 直答守卫**（无历史∧有摘要，判据=messages 计数；**先答后写**=失败零残留回落不双写）/HANDOFF 直通三事件/兜底② **FALLBACK 替换** loop 打断话术出帧（排练揪出双 token 帧后定案，X4 事实不丢）/租户缺行合成空配置留痕）+chat.py 收敛（PLACEHOLDER_SPEC 退役）+main.py 七注入参（**#7 生产接线收尾**）——admission 12 既有测试零改动全绿；**③**真实三幕全 PASS（A 全链退款 80 直执落库 refunded／**B FAQ 守卫实证：首问 faq_direct・跟进问「一般要多久？」completed**——M3.6 盲窗用户提问→修复→真实链路验证完整闭环／C 工具面 A 四件 B 二件）+seed config tools/faq 前移；**幕 C 首跑 FAIL 实录两课**：无身份读 tenant-b 配置被 RLS 挡成空集（对抗①防线在配置面开火）+A 面"正常"系 TenantDirectory 60s TTL 缓存残影——修=脚本每租户自声明身份（fix 单笔）。偏差 (43)–(47) 登记 plans 14h；测试 744→**754**（+22=12/10，§5.2 预告 +8–12 上浮 10 有名分）；深挖题 133–135 | `988cf20` `539e160` `0793b48` `2b7f417`（③ demo_chat_acceptance.py 入库，已含幕 C 身份自声明修）`e189772`（seed config tools/faq 前移；**提交纪律偏差**：message 未写"为什么"——M3.9 开工核补时登记，按红线 3 不改历史） |
| M3.9 ✅ | HITL 业务闭环五交付（2026-07-26 单日收口；开工拍板七项全按建议——plans 14i：切分五份 / revalidate 无身份闭包 / 审批 API owner 查读缝+特批冒充第五处 / **#44 取后案=_recover_locked 认领分诊支**（钩子侧换入口废案：三窗口推演 T3 CAS 在崩溃现场必打空）/ 受控缝参数化 / hitl 对账扫描（"awaiting×最新单已决"全集自愈、不信 expire_due 返回值、最新单判据防误杀）/ 测试区间修正 +24–34）：**①**revalidate.py（#8 实装：参数快照对业务事实的新鲜度、拒绝面与 mock 执行器逐字对齐、未登记工具 fail-closed；归属重校验由批准执行期 handler 以真实 ctx 重跑兑现——PrecheckHook 无 ctx 冻结面）+create_app precheck 生产接线；**②**api/approvals.py（授权序 401→403 角色→404→**对抗④跨租 403**→409 CAS 透出；同步消费 resume=chat 取消路径同形，崩溃窗恰由 ③④ 兜底=设计自洽）+第八注入参 approvals_lookup（RLS 下 403/404 判定需平台视角）；**③**#44 修复：_recover_locked a+ 审批认领分诊支+_find_unattached_approved（三窗分路：从未执行→decided 补写+precheck+原语义执行 / write-ahead 悬挂→原幂等键 reexecute / 已有终局→只补审计链**绝不重执行防双写**；**先红后绿**：未修代码 5 红实测留档）；**④**worker 跨 loop 受控缝（new_redis_client/new_http_client 配置源提取+build_gateway/build_session_lock 参数化+set_mock_client 安装缝+approval_scan_interval_s=60）+workers/hitl.py（sweep_once 对账+_task_runtime 任务局部五资源装配与 create_app 逐件对应+resume_session 真钩子 import 注册=**拍板Ⅰ收尾**+beat 第二条）；**⑤**demo_hitl.ps1 六段真实链路**全 PASS**（挂起提示/对抗④ 403/批准→#8 通过→执行→续跑・审计链 event_id 回填・事件序与单测七事件尾同构/**TOCTOU 否决实证**：approved∧event_id=空・订单零二次退款/超时：时钟注入+直调生产任务体 expired=1 kicked=1/撤回；四会话全归 idle）。**#8/#44 翻 ✅**。AI 稿三缺陷均用户跑门抓出：test_approvals basename 撞车（48）/W3 夹具预翻 T3 短路被测路径（49）/PS1 无 BOM 被 PS5.1 按 GBK 解析源文件（50，06 §4 编码家族第四刀）。偏差 (48)–(50) 登记 14i；测试 754→**792**（+38=12/11/6/9/0；拍板Ⅶ 修正区间 +24–34 上浮 4——celery 契约面与 sweep 防误杀/隔离各 +2 有名分）；深挖题 136–142 | `aee4abb` `6e47fb0` `5b77bcf` `a0689af` `2fed126` |
| M3.10 ✅ | SSE 双通道+聊天页四交付（2026-07-26 单日收口；开工拍板六项全按建议——14j：切分四份 / **L2 受控缝第三处 text_sink**（钩子侧不可行推演：sink=每请求物不挂进程级构造）/ 帧类型统一扩展 service.ChatFrame（计划 sse.ChatFrame 独立类作废=撞名）/ 直答过 OutputGuard / done.usage 从 llm_result 实测累计（计划"usage_ledger 聚合"不可行）/ 数值照计划）：**①**L2 逐 token 出流——`run`/`resume` keyword-only `text_sink`+_llm_step 流中 feed+_finish_text 双模式（**M2.8 D14 预埋的兑现**；guardrails.py:406-411 不变量=聚合↔逐帧行为一致；**事实不变量：事件流与 sink 在场与否无关（观察者不改变事实）**；sink 异常降级不拖垮 run；既有 792 全绿=等价性证明）；**②**POST 通道全链——sse.py 编码器/service 队列解耦生产消费（**断连不取消生产者**=事实生产不因观察者离场中断、GET 重连补收）/_TokenEmitter 先写 msgbuf 后入帧（顺序承诺）/chat.py SSE 化（**peek 首帧保 M3.2 锁 409 契约**、流中异常译 error 帧；M3.2 占位 JSON 协议退役）/直答流式过守卫（PII 命中截断实测）；**③**GET 通道全链——迁移 `d41be6a90c27` D10 触发器+notify.py（**C22/#37 实装**：LISTEN 独立原生连接不从池借、断连降级 after_seq 轮询、伪唤醒安全=一律重查）+stream.py（双源取 max 续传/id:=seq/message_reset/关流两判据：批内终止或 idle·failed 无增量——直答类无终止事件）+events_view.py（U14：operator 限本租 403/审计留痕一行/M4.1 底座）；**④**chat.html 单文件页（特许 AI 直写；**双通道 fetch 手写解析**——EventSource 带不了 Authorization、原生用法=JWT 进 URL 违安全底线，服务端协议原样 cookie 后可切回）+`/chat` 路由。**真实链路验收五幕全 PASS**（直答流式/工具流式/审批挂起→重订阅续收=**批准后续跑帧瞬时推达页面**（双探针实证：httpx 端到端+浏览器面板全流程）/断线 message_reset 整条重推肉眼可见/curl.exe -N 裸帧）。AI 稿五缺陷用户跑门与实跑抓出：签名钉+Liskov 覆写两类 additive 缝冲击面(51)/固定 tenant-a 撞种子第四度复发(52)/SAVEPOINT 夹具不支持测试内并发协程(53)/asyncpg 无 py.typed(54)/PS5.1 引号吞 JSON(55)；(56)=幕C"页面没变"实证定位（非代码缺陷：页面刷新丢会话——事件溯源 UI 重入通路补齐）。偏差 (51)–(56) 登记 14j；测试 792→**830**（+38=6/18/13/1；14j 修正区间 +18–28 上浮 10——帧词汇 parametrize 全表 +7、msgbuf/直答守卫/页面路由系蓝图未列面）；深挖题 143–149 | `e75d30e` `a5170d8` `d1d2275` `3dd5d03` |
| M3.11 ✅ | 种子评测集+演示数据三交付（2026-07-27 收口；**本步特许数据/测试/脚本全量 AI 直写**——用户授权，生产包 `aegis/` 零改动故规约第 1 条无冲突面；拍板六项全按建议=coupon_threshold=50/approval_ttl_s 显式 3600/每租户 10 篇/20 条配比/record 脚本 AI 直写/cassette 落 l3 子目录）：**①**演示语料 20 篇（两租户各 10、各含 faq.md=M3.6 后置修订⑶）+**语义锚双向 lint 进 CI**（A 含七天无理由退货/退款 200 审批/灵犀 24 个月且全库零「优惠券」=calibrate off-topic 不可命中面；B 含 50 元券审批且全库零 A 字面）+seed_demo 正式版（订单五单=M3.7 拍板Ⅲ承接；语料摄取三分支**幂等即省钱闸**：未变 DONE 整篇跳过零 API/未变未完续传/变更删块重建）（`d55cb8f`，830→836）；**②**evals/cases/seed.jsonl 20 条（iso10 三面 facet 化+okb5 近域 4 远域 1=M3.12 兜底率分母+ret3+nor2）+README 判据词表（**两纪律：判回答不判 query 复述、判据强度随语料几何定**）+六层 lint（身份/订单引用 importlib 对种子常量核对）（`e62f139`，836→842）；**③**L3 五盘 cassette 录制（台词与评测集同源、**spec 从种子常量构造=录制回放 I1 定义性同源**、检索 fail-open 空集不入带；预算写死 40 调用/10 万 token/¥2，实录 8 调用 6,695 token **¥0.006** 五盘全 PASS）+冒烟 3 测（budget/tool 盘 FakeGateway 端到端回放=M4.3 踏脚石）+README §6 登记表 L3 五行（M2.11 占位兑现）+**calibrate 复跑 0.35 维持**（分离窗收窄 [0.334,0.452]；「优惠券」0.334 距阈 0.016 挂 M4.5 留意；B 检口径修订空集→**字面核证**——扩容后 B 有自家售后语料，5 候选全 tenant-b 块零 A 字面=对抗①字面核证 PASS、评测集 no_leak 判据实测印证）（`5c1f5a1`，842→845）。AI 直写四缺陷影子门/实跑抓获（excluded["items"] 容器协议撞名/importlib×dataclass 须先注册 sys.modules/兜底信号集误杀越界声明形态/校准 B 检前提过期）+既有测试冲击一处（test_approvals 全局相等断言过滤式修复=M2.10 家族，本地残留 pending 单暴露）。偏差 (57)–(64) 登记 plans 14k；测试 830→**845**（+15=6/6/3；§5.2 预告 +4–8 上浮 7 逐条有名分）；深挖题 150–154 | `d55cb8f` `e62f139` `5c1f5a1`（另基线外 `75292f7`=M3.10 收口后用户 ruff format 补笔，核证无害照登；message 未写"为什么"计提交纪律偏差） |
| M3.12 ✅ | 毕业验收+整编三交付（2026-07-28 收口=M3 毕业；拍板三项全按建议：两真实脚本 AI 直写/08 整编轻量案/atlas L3 篇范围）：**①**tests/apps/test_adversarial.py 7 测=四大对抗**集中对账面**进 CI（每条带对照正例或零副作用断言防"全拒也满分"；②缓存隔离唯一无专项 CI 面的缺口补上）（`ae3490e`，845→852——§5.2 预告 +6–10 **区间内**）；**②**perf_m3.py（缓存中位 **10.2ms**/首 token **P50=1408 P95=2239ms** 两口径 PASS 无修正项）+fallback_rate_m3.py（okb 5 条分母/信号集/Trace 三处 importlib 复用=I1）+**兜底率三轮闭环 60→80→100**（R1 真编造：赠品品牌/供应商先验作答→**prompt 规则 3 具体化**（冻结后首次修订，按 M2.6 纪律附五盘重录 ¥0.006 全 PASS）→R2 判据漏报"暂未/暂无"合法变体→信号集二轮反哺→R3 **5/5=100% PASS**）+reports/m3_acceptance.md 四条凭证落盘（`8cc58ba`）；**③**毕业整编：**atlas L3 篇**（图组 D 两幅/闸门表 +14 L3 行/文件表 L3 节 15 行/数字卡 +7/边界 M3 条——#40 兑现）+**08 轻量整编**（§1 文件速览/§6.1-bis 迁移链 9 个+6.8 六表/§9.1-bis 脚本 23 个/§0-bis 收束为常驻档案——原"拆入各章"承诺按拍板修订）+00 毕业对账+记忆重写。**过程实录两笔**：两脚本 `_spend` 首跑账本全零=对账面 RLS 盲区（app 引擎在 tenant_context 外读 RLS 表静默空集、预算护栏盲飞——M3.5(32) 家族**第三次现形**，修=owner 维护面 D4）；启发式判据假阳性面实录（R1 okb-02"不提供分期"=方向碰巧对的无据断言撞词被判触发——语义终裁归 M4.4 judge，三层判定架构入凭证）。偏差 (65)–(69) 登记 14l；测试 845→**852**；深挖题 155–158 | `ae3490e` `8cc58ba`（tag `m3-support` 打于 `8cc58ba`） |
| 复盘补丁一 ✅ | M3 全量复盘站 4（2026-07-28）揪出摄取投递"至多一次"：`task_acks_late` 缺省 False=消息在任务执行**前**即 ack，worker 崩即消息永久消失、文档永久卡 PROCESSING 且无扫描器兜底——`ingest_once` 四步收敛的幂等性从未被投递侧兑现。修=`task_acks_late=True`+`task_reject_on_worker_lost=True`（三任务体可重放性逐个核实）；"beat 扫描重投"否决（超时判据必然误判慢而未死→结构性引入并发→须配租约）。新增不变量：任务时长 ≪ `visibility_timeout`。CI 钉子 `test_delivery_is_at_least_once`（回退=文档静默丢失零红灯）。kill -9 实录挂 M4.0。详 §10.1 #48。测试 852→**853** | `944e5ee` |
| 复盘补丁二 ✅ | 同站追问（"这里也走线程池吗"）揪出 kb 端点 async 体内直调同步 `enqueue`（send_task）阻塞 event loop——FastAPI `def`→线程池分诊只对**它自己调用的**路径函数/依赖生效；"毫秒级 v1 接受"论证只覆盖成功路径，broker 失联时建连超时（celery 5.6.3 默认 4s）×两层重试阻塞全进程并发。修=`await run_in_threadpool(...)` 一行（EnqueueFn 签名/503 分支零改动）+线程身份回归钉子（回退时无行为差异可测，唯一证词=执行线程≠loop 线程）。全 API 面同型普查挂 M4.0。详 §10.1 #49。测试 853→**854** | `6d2c531` |

---

## 8. M4 · 治理层（1.5 周基线，9 步）⬜

### 8.0 定位

让系统"可看、可评、可算账"。核心是**评测双流水线**（评审定稿：两者目的不同不可混）与
**成本对照实验**（口径干净到"没法被质疑是评测集凑出来的"）。
**真实调用口径**：仅 M4.4 离线评测与 M4.6 成本实验产生真实调用，预算上限各自写死在配置；
M4.3 回放回归零 token。

### 8.1 步骤计划

| 步 | 内容 | 规模 | 文档锚点 |
|---|---|---|---|
| M4.0 | 开工走查 + **M1/M2 遗留归位**（§10.1）：缓存命中 QPS 放大复核、alembic check/downgrade 往返（可选）、kill -9 若 M2 顺延在此补、单请求预算闸门若未补在此收口 | M | §10.1 |
| M4.1 | **trace 查询 API**：凭 trace_id 还原全链路每步输入输出与耗时（JSON；查看页 v2）；权限按端点×角色矩阵（仅 operator/admin、限本租户）；展示层统一 PII masker（events 存原文的口径在此兑现） | M | 02 §7.1/§7.3 |
| M4.2 | **Prometheus 指标 + /metrics**：成功率/P50/P99/token/工具成功率/转人工率/缓存命中率 | M | 04 M4 |
| M4.3 | **CI 回放回归流水线**：每次提交零 token；断言**行为轨迹**（终止原因、工具调用序列、隔离/预算硬约束）；prompt 变更的 PR 必须附重录 diff（重录流程 M2.6 已定义）；cassette 输入 = M2.6 手写用例 + M2.11 长对话 + M3.11 L3 行为用例；**红绿有效性验证：故意改坏一个硬约束，CI 必须变红** | L | 04 M4、03 §7 |
| M4.4 | **离线质量评测**：eval_cases/eval_runs 表迁移（02 §3，种子集从文件形态迁入落表；eval_runs 记录**当次实际模型名**——评审 C36 后半句，附A #2 回填，实装=judge_model 列回显）；真实调用 + LLM-as-judge（strong 档），nightly/手动触发，单次预算上限写死在配置；三类用例（检索质量/端到端/对抗）各有判据文档 | L | 04 M4、02 §3 |
| M4.5 | **评测集扩充**：种子 15–20 条 → **30–50 条**（三类用例覆盖） | M | 04 M4 |
| M4.6 | **成本对照实验 ×2（口径分开）**：① 档位路由降本——全唯一问题集（不受重复率污染）；② 精确缓存降本——声明分布假设的模拟流量（如 30% 历史复述）单独测；产出两个实测数字 + 口径说明，**不预设目标值** | L | 04 M4 |
| M4.7 | **设计文档迁入 repo + 应用容器化（#26/#31——M5.3 硬依赖，附A #1 回填）**：仓外源 docs 全量（含本文档）迁入仓库 `docs/`，此后文档变更走提交（"M5 前迁入"承诺在此兑现）；Dockerfile + api/worker/beat 编排 + migrate 先行；另挂观察池 M4.7 档修缮批（§10.1-bis）与 (67)(68) 前置件 | S→实际 L | 记忆档案、plans/m4 第八章 |
| M4.8 | 毕业验收 + 整编：8.2 对账、报告落盘、毕业四件（tag `m4-governance`） | S | §13 模板 |

### 8.2 毕业验收汇总

- [ ] 凭 trace_id 还原任一会话每步输入输出与耗时；
- [x] CI 回放回归红绿有效（改坏硬约束 → CI 红）——M4.3④ 凭证 `reports/m4_replay_redgreen.txt`（本地手法拍板；等价性=本地 pytest≡CI 第九道门全量无路径过滤 ci.yml:66-67，影子探针≡HEAD 代码等价）；
- [x] 两组成本数字 + 口径报告产出——**M4.6 达成（2026-08-03）**：`reports/m4_cost_routing.txt`（档位路由降本 **vs-strong 74.7%／vs-standard 18.9%**，双基线口径）+ `reports/m4_cost_cache.txt`（精确缓存降本 **21.9%** @30% 复述假设，请求级全命中自检 60/60 吻合）；两报告四段骨架（口径/原始数字/结果/威胁边界）+聚合 SQL+精确 sid 清单，数字经异形查询独立复算逐位吻合；
- [x] 评测集 30–50 条，双流水线各自跑通且有基线记录——**整条达成（M4.5）**：40 条（adv14/e2e14/ret12）+回放门（M4.3，955 内含）与离线评测（四轮批次迭代至稳定基线 **38/40**）双流水线各有凭证；judge 区分度实证（判分 1/2/5 三档+spot-check ±1 一致率 100%）。

**面试考点**：为什么回放测行为、真实调用测质量，两者不可互替；LLM-as-judge 偏差怎么校准；
成本数字怎么做到不可质疑（口径写死、集合构成公开）。

### 8.3 实际交付对账（进行中——毕业时补全）

| 步 | 内容 | 提交 |
|---|---|---|
| M4.0① ✅ | **开工走查（零代码，2026-08-03）**：七步启动 + plans/m4-detailed §0 十七项核对（**11 项对上、6 项须修计划**：`EventType` 14→**16**（M2.8/M2.10 各 +1，M4.3 断言事实源）／层契约四层→**五层**（`aegis.api \| aegis.workers` 置顶，M4.1 的 `aegis.obs` 插入位待拍板）／cassette **11 盘**（计划漏列 M2.7 对抗四盘）／应用入口**无模块级 `app`**（M4.7 容器 CMD 须 `--factory`）／docs 13→**16 篇**／reports 3→**11 件**）。**四项复核结论**：#3 命中路径不加限流（证据链两处行号）、#41 两项无残留动作、C5 无误伤记录故不做、#49 普查 `aegis/api/` 全面干净。**四枚缺陷候选全部实测复现并定级**（临时探针跑完即删，未提交）：③ P0（真副作用）／② P1（信息泄漏）／④ P2（能力声明不符）／① P3（纯体验，不修）。**两处记账修正**：③ 的"用户新问题被完全忽略"原述不成立（`_rebuild_working` 带全量事件）、① 顺带坐实"终局守卫在通道模式下止损≈0"属 D11 已接受边界 | 无代码提交 |
| M4.0② ✅ | **缺陷批处理五笔（2026-08-03，先红后绿：修前 7 红、三条反向对照修前即绿）**：①③ `_recover_locked` 认领判据加"该单 approval_requested 之后已有 loop_terminated 即跳过"（`84cca3f`，只读既有事实无新字段无新查询；四个真崩溃窗的共同特征恰是 loop_terminated 没写成，故不误伤）；②② precheck 订单派生拒因统一 `_STALE_TEXT`、细节只进 logger（`96390e0`；参数事实如金额形状保持具体=改判范围的边界线）；③④ stream 两处 SessionRecord 读改走 owner 缝（`85c10b2`）；④㊲ 退款闸门缺省 200→0 fail-closed（`29a3b8b`；全仓 20 处均显式给值，只影响漏配）；⑤(63) `_task_runtime` finally 五件释放各自保护（`b7fc59f`，表驱动写法让"顺序即协议"可读）。**测试 854→863**（+9：stale_claim 3／revalidate 2／tools_contract 1／test_rls M4.0 增量节 2／hitl 1），**修改既有测试 3 个**（拒因/缺省断言随行为改判）。**AI 盘点漏项一枚**：交付时报"修改既有 2 个"实为 3 个（漏 `test_refund_rejects_refunded_order`）——用户跑门抓出；根因=只盘自己动过的文件、未 grep 全仓"断言该行为输出"的测试，已补复查确认无第四处 | `84cca3f` `96390e0` `85c10b2` `29a3b8b` `b7fc59f` |
| M4.0③ ✅ | **CI 三道门 + #46（2026-08-03，测试 863→864）**：①`09d0c7b` gitleaks（SHA 实查、checkout 后第一道、`fetch-depth: 0`、`.gitleaks.toml` 两条经核实豁免）+ pip-audit（`uv run` 审当前 venv）+ `alembic check`（置于 upgrade head 之后）——**#24 两门与 #4 check 半边闭合**；②`54f3e28` HNSW 补 ORM 声明（**check 首跑即抓真实不一致**；探针实证修正 M3.4 §4.4 陷阱 2 口径="不认识 USING hnsw"只对生成面成立、比对面认得；否决 `include_object` 排除法=用"让门看不见"换"门变绿"）；③`cdaa407` **#46 翻 ✅**（`scalar_one_or_none` + 404 `from None`；钉子落 test_rls M4.0 增量节=跑在 RLS 在场的世界，#47 的又一块补丁）。**AI 交付稿缺陷第四次同族**（B904：`except` 块内 raise 未断异常链）——四次全部由用户跑门抓出，共性=交付前未过本地四门；教训登记 plans 偏差 ⓺ | `09d0c7b` `54f3e28` `cdaa407` |
| M4.0④a ✅ | **#29 Redis 触点降级粘滞化（2026-08-03，测试 863→873）**：熔断四触点 + 缓存两触点收口进"粘滞 + 5s 顺路探针"，范式与 `RateLimiter`/`FailoverSessionLock` 同构（**全项目第三处**）。两处拍板：探针只在 `allow()` 领；缓存粘滞放 router 不放 `ExactCache`。降级语义本身不变（ADR-005），两测试文件各留一条专测。最易写错处=`on_failure` 本地记账须先于跳过判断 | `3c57eaf` |
| M4.0④b ✅ | **三项实录与验证（2026-08-03）**：①**#48 摄取 kill -9 实录四断言全 PASS**（`7892666`，凭证 `reports/m4_kill9_ingest.txt`，零真实调用靠假 embedding 服务顶替上游）——**实录推翻原判断**：Windows 上 celery 恒无 event loop（`should_use_eventloop` 显式排除本平台，**与 pool 无关**）→ unacked 永不自动重投，补丁一在本地只兑现"消息不丢"一半，M4.7 Linux 才完整生效；实测数字=重复恰 1 批（上界）、**账本行数=理论批数 → 零重复计费**。②**gitleaks 门的真实形态查清**（`13a7962` 豁免精确化 + `179082a` 表述更正）——CI 日志实证 `--log-opts=-1` **只扫本次推送的 commit**，原注释"扫全历史"错误；全历史一次性扫描命中 6 处全为测试假串零真实密钥，已按**串形态**精确豁免（绝不按目录：把 tests 放进 paths 会让真 key 误提交也不报警）。③**红绿有效性验证通过**：探针分支开 PR 触发 `pull_request`，**CI 如期红在 gitleaks 步骤**，验完关 PR 删分支未合并——#24 完整闭合。**过程产出四个"门装了但没验过"的发现**（`tmp/*` 分支不触发 workflow／`example` 串撞 stopword=**假阴性伪装成通过**／action 只扫增量 commit／Push Protection 是更早的第 0 道防线），全部登记 §10.1 #24。**纪律入库**：探针必须先本地实证会被抓再推，否则"绿"零信息量 | `7892666` `13a7962` `179082a` |
| M4.0④c ✅ | **观察池 77 条三档归位（2026-08-03，纯文档）**：新建 **§10.1-bis 专属账本**（不并入 §10.1——25+ 条会让主表膨胀三倍并淹没跨里程碑主线，§10.1 只留指针 #51）。统计=升级 41／边界 17（已并入 atlas「已知边界汇总」，按认证·摄取检索·意图直答·工具下游·帧协议五面归档）／结案 2／已归位他处 4／已修 3。升级条目里程碑分布 M4.2×11（可观测面最集中）·M4.3×6·M4.4×3·M4.7×18·M5.2×1·零代码×2 | 文档（随 M4.0 收口提交） |
| M4.1① ✅ | **obs 包底座（2026-08-03，测试 873→890）**：`aegis/obs/`——masking.py（59 行：masker **复用 guardrails.PII_RULES_V1 同一张表**＝拍板②，四规则自带数字边界断言故无排序依赖；绝不抛异常、返新 dict 不改入参）+ trace.py（146 行：TraceEvent/TraceRun/TraceUsage/TraceView + `TraceAssembler.assemble(session: SessionRecord) -> TraceView`——单扫描分组配耗时：tool 直读 payload.latency_ms（与投影同源省一次 join，计划偏差⑸）／llm 配同 run 前一条 llm_call 的 created_at 差（pop 一次配对、重发覆盖=D10 语义）；**账本聚合包 `tenant_context(会话租户)`**＝(58) 防线，usage.py:65 先例；cost 沿用"钱不过 float"字符串契约）。层契约第二槽 **`aegis.apps \| aegis.obs`**＝拍板①（M4.0① 记录的"runtime 之下"方向经实测否决：低位够不到单点与 ORM、M4.2 已裁 runtime/gateway 不许 import obs＝收益为零）。+17 测（masking 8/assembler 9）；耗时断言=显式 UPDATE created_at 构造 DB 时钟（savepoint 世界 now() 冻结，红线 5 零时序断言） | `b0bbec5` |
| M4.1② ✅ | **trace 端点升级（2026-08-03，测试 890→893）**：`GET /v1/sessions/{id}/events` 响应升级 **TraceView + payload 过 masker**（02 §7.3"events 存原文、脱敏在展示层"从此为真）；鉴权序（404 缺失→403 operator 越界）与审计行保持 M3.10 形态——**跨租 403 沿用**＝拍板④（计划 §3-2 的 404 被实装+测试+题 142 取代，按信任序修计划不改代码）；`after_seq`/`limit`/`_MAX_EVENTS` 退役＝拍板⑤（全仓无生产消费方，分页 v2）。RLS 在场证人落 **test_rls M4.1 增量节**（admin 跨租账本聚合非空；**反向实证**：影子拆 tenant_context 包裹→测试红在 usage.requests `0==1`＝预测的静默空账形态，证人真的在看守）。+3 测（端点 5 改造+2 新、rls+1） | `b7abb5a` |
| M4.1③ ✅ | **候选② 信息面收口（2026-08-03，测试 893→894）**：`PrecheckVeto(observation, detail)` 双面 dataclass + `PrecheckHook` 返回 `PrecheckVeto \| None` + **第 17 类事件 `precheck_vetoed`**（扩枚举走 M2.5 拍板 4 预定义流程：03 §5 表加行／快照测试先红后绿／C31 核对——normalize 对顶层 approval_id 通用别名化**零改动**，`_rebuild_working` 正向匹配天然忽略，11 盘 cassette 零重录）；runtime 两调用位（`_resume_locked`/`_recover_locked` 认领支）同款落事件——**detail 只进事件 payload 与日志，绝不进模型上下文**（测试逐条钉"detail 不进 prompt"；模型面话术与 M4.0② 后逐字节一致=零行为变化）；revalidate `_stale()` 收口函数=observation/detail/日志三面一次成型。**影子门抓 AI 盘点漏项一枚**（test_recover_stale_claim 的 str 桩——首轮 grep 被 head_limit 截断漏看；"盘点必须全仓无截断"家族第四例，**首次拦在交付前而非用户门前**） | `0795f0c` |
| M4.1 收口 ✅ | **凭证 `reports/m4_trace_sample.json`（§8.2 第一条达成）**：演示库被 M4.0④b 往返清空后，走 **l3 cassette 零 token 回放重建**会话 `m41-trace-sample-f001c4aa`（tool_roundtrip 盘：FakeGateway 扮演 LLM=录制的 M3.11 真实模型输出、mock 后端真执行），再经 **create_app() 生产装配链**（RLS 世界/owner 查读缝/masker 出口）实拍：单 run 9 事件全链、耗时三处非空（llm 7ms×2=DB 时钟差、tool 14ms=executor 实测）、termination=completed、usage 全零字符串出线（回放不过计量的直接体现，诚实标注）。探针在 scratchpad 跑完即弃不入库 | `b25c07b` |
| M4.2① ✅ | **Prometheus 指标底座（2026-08-03，测试 894→903）**：`aegis/obs/metrics.py`——自有 REGISTRY（防重复注册炸点）+**11 族**（计划 10 族+拍板 3 增 `aegis_documents{tenant_id,status}`=⑫⑱观测半；#6 成本 gauge 保留）+`refresh_db_metrics`（表驱动七族+#23 特支；族间隔离失败留上次值绝不抛）+`render()`。**两条关键口径**：⑴刷新必须走**平台维护面 owner 工厂**——计划伪码 `refresh(get_session_factory())` 在 RLS 世界全空集零报错（**(58) 家族第三例，这次埋在计划伪码里**）；⑵**#23 分子复用 `MeteringRecorder.month_spend` 同一实现**（月窗 DB 端 date_trunc/cached 排除/索引路径三口径全继承，告警与拦截物理上不可能对不上）。依赖 +prometheus-client。+9 测（label 族过滤式/无 label 族 delta 式） | `80299de` |
| M4.2 修 ✅ | **CI 空库红一课（`ba372df`）**：`aegis_cache_requests` 是唯一无租户维度共享 label 族——CI 空库首刷查回零行不触发 set，gauge 保留**上一个测试世界**的旧值→delta 基线错位；本机 dev 库常驻真实账本行两刷都有行可 set 故影子门全绿=**影子门跑在非空库上结构性抓不到该分岔**（M2.11"环境依赖测试"教训的镜像版：本机绿 CI 红）。修=测试先 `CACHE_REQUESTS.clear()`，delta 在空库/脏库两世界都精确；生产零改动（label 消失保留旧值在生产不可达：账本只增不减） | `ba372df` |
| M4.2② ✅ | **/metrics 端点+中间件+chat 打点（2026-08-03，测试 903→909）**：`api/metrics_view.py`——端点刷新走 `approvals_lookup` 平台查读缝（(58) 防线兑现）+**纯 ASGI 计数中间件**（弃 BaseHTTPMiddleware：task-group 包装对 SSE 长流平添缓冲与取消语义风险；纯透传只窥 `http.response.start` 一帧，影子全量含全部 SSE 测试照绿为证）；path label=路由模板（`scope["route"].path_format`，防外部可控 URL 炸 label 基数），未匹配归并 `"unmatched"`；chat 打点=**首个 token 帧非首帧**（首帧可能是 tool_status——与 M3.12/M5.2 口径同轴），全程时长记 finally 含 error 收流（不数=幸存者偏差）。**02 §7.1 已补 /metrics 行**（拍板 1：无认证+只绑 127.0.0.1+生产应内网隔离）。+6 测（Counter 进程内累计 delta 天然精确） | `4b33295` |
| M4.2③ ✅ | **观察池 M4.2 档五处收口（2026-08-03，测试 909→918）**：㉓ `_parse_intent` 零/多词留痕（hits/len 不记原文——三条通 AGENT 的路条条有痕，分诊失败率可观测）；⑱ `GET /v1/kb/documents/{id}`（202 句柄兑现，staff 面与 events_view 同构）；⑥⑭(56) **kb+approvals 挂既有 rate_limited**（与 chat 同桶 `inbound:{tenant_id}`=拍板 4；429 先于一切 handler 逻辑，超限探测不出单据存在性；GET/stream 不挂=读不花钱/占连接归部署面）；(61) sweep 批上限 100+`ORDER BY id` 定序（无序 LIMIT=随机领批）+触顶警告+`SweepReport.failed` 第四账+`latest is None` 不可能态留痕；(74) stream 回放 `_REPLAY_BATCH=500` **分批≠截断**（批满立刻续扫；终止判据与 message_reset 等存量排空——否则跨批终止早退丢事件）。**影响面盘点提前做**：挂限流让 test_kb/test_approvals_api 既有测试真打 limiter，harness 补宽容桩（否则落真 RateLimiter+get_redis=M2.9 跨 loop 炸点）。+9 测 | `5a17bf8` |
| M4.2 收口 ✅ | **凭证 `reports/m4_metrics_sample.txt`（§8.1 M4.2 行 #23 验收点）**：`scripts/demo_metrics_acceptance.py`（用户裁决入库为项目资产，Path 锚定根；README 已登记）——拍板 2 例外恰 3 轮真实 chat 实跑：**预算比 0.0008025 → 0.003145 肉眼上升**、11 族全量 exposition（中间件按路由模板计数、首 token 直方图 3 样本落 2.5–5s 桶=真实档延迟）、扫密干净；ratio 不升即硬失败不落盘=凭证不掺假。移位五条（拍板 5）：㊺→M5.2／(67)(68)→M4.7 前／(72)→M5.4 前／(77)→M5.4，登记 §10.1-bis | 凭证 chore（随收口提交） |
| M4.3① ✅ | **回放行为回归底座（2026-08-03，测试 918→933）**：`tests/replay/` expectations.json（manifest：11 盘四键期望，termination 必填+tool_sequence/forbidden_output/required_event_types 可选；**期望先于断言从 README §6"覆盖"列+录制自检推导非抄输出**——tool_loop 期望执行 2≠盘内意图 4 即证据）+ test_behavior_regression.py（装置+15 测试：完整性**三向**盘面≡manifest≡DRIVERS／POSIX 键／extract 自检／机械噪声剔除自检／参数化 11 盘）。三族三种装配住 DRIVERS 注册表（M2 演示工具族 importlib 复装 runtime conftest 不复刻定义／长对话族 I1／L3 族按盘挂 mock+decide→resume 审批动作+预算注入）；事件从**事实源全量读**（decide 落的 approval_decided 不经 yield 流）；**iso_rag/iso_refund/hitl 三盘历史首次端到端回放一次全绿**；minimal_demo 补终答条目升级为可回放资产（README §6 承诺兑现；修改既有条目数断言 1）。四偏差：conftest 不建（无包结构 import 不可靠+项目"道具不进 conftest"样式）／参数化基数 11 非 15–25（M3.11 实录 5 盘）／replay_session 单签名改注册表／**C31 消费点=forbidden 扫描面非等价比对**（剔机械噪声键 iteration/input_tokens_est/digest——哈希 hex 撞数字禁词，隔离断言不押巧合） | `5240b09` |
| M4.3② ✅ | **#47 薄层+三枚证人（测试 933→944）**：test_rls **M4.3 增量节**三条——TenantDirectory 无身份读配置=None 静默空（M3.8 幕 C 实录 CI 化；负例先行防缓存粘连）／MeteringRecorder 双面（本租真落库 owner 核数"非零 sanity"+跨租 42501；cached=True 短路 compute_cost=零价目依赖）／**㉚ mock 回放读跨租撞键响亮 NoResultFound 绝不静默借用**（唯一索引仲裁不看 RLS+回放 SELECT 无租户过滤的组合形态首次有 CI 作证）+同租 duplicate:true 健康对照；**㉞** test_app_surface 路由零交集（用 mock 自身路由集对主 app 求交、APIRoute 滤框架路由=断言面自动扩大）；**(53)** 对齐矩阵七例（恰等上限+coupon-refunded-passes 两刀刃；主守方向="更严=批准后白拒无人兜"；顺序纪律 revalidate 纯读先跑）。**(62) 核对更正**：注册面证人 test_module_import_registers_real_hook 已在（M3.9④ 拍板Ⅰ收尾）——站 10"零证人"表述系**复盘免测试段盲区** | `360078a` |
| M4.3③ ✅ | **观察池修缮 (73)（测试 944→945）**：stream `_translate` 译 user_message（带 seq 参与 Last-Event-ID 续传）+ChatFrame 词汇表扩条+chat.html 蓝气泡重建（resubscribe 清面板后用户侧从事件流长回来，重放不再是半边对话）；**POST 侧刻意不发**（用户消息本地已有）——差集从"无人知道"变**双 docstring 声明**。影响面三处断言改判+sse_frames 词汇参数化 7→8；**影子门再抓盘点漏项**（grep 命中文件只看注释命中行、漏同文件第三处帧序列断言——纪律追加：**影响面 grep 命中文件后读全部相关断言，不只看命中行**，家族第五例、连续第二次拦在交付前） | `ac09505` |
| M4.3④ ✅ | **红绿凭证+PR 纪律+断言边界（收口件，945 不变）**：`reports/m4_replay_redgreen.txt`——改坏闸门 #3（loop.py:289 阈值×10；**影子副本执行、本仓 git 零触碰**——本仓探针被权限分类器拦下反证纪律，影子≡HEAD 探针前全量 945 为证）→**恰 1 红**：budget 盘 CassetteMismatch"main 道耗尽已录 0 条"（**响亮失配比终止断言红得更早更响**=C10 兑现）；token_burn 不红=预算×10 后仍先于轮数触发、行为轨迹没变——**门只对真行为变化红**（信噪比证明）→还原复绿 15/15。**候选① 弃用入凭证**：注释检索 WHERE tenant_id 在无 key 回放世界不可达（检索恒 fail-open 空集）——**红绿改坏点必须落在被测世界真正执行的语句上**（M4.0④b"探针先实证会被抓"纪律的回放版）。README **§7 PR 纪律**（C10 并列触发五步+新录盘四件事+manifest 维护）+**§8 断言边界四声明**（㊾ 前置文本不在场／㊼ 兜底话术互换=录兜底盘期望按事件面写／**㉜ 随机 id 不参与断言面+触发条件落档**（不加缝：现有 11 盘无 ticket 路径+断言非逐事件全等，无消费方的缝=注水）／**㉗ 重录门覆盖面=代码内 prompt 常量**：租户侧 digest 无门看守、FAQ 直答零 cassette 覆盖="既不绿也不红"如实声明，质量归 M4.4 与 ㉖ 同批）。计划 §6"隔离/预算≥10 例"按 11 盘实况修订为"对抗类盘全覆盖"（旧估算按 15–20 盘） | `1126c1e` |
| M4.4① ✅ | **评测双表落库+定义源迁 cases.json（2026-08-03，测试 945→949）**：obs/evaluation.py（两 StrEnum+双表 ORM；**+user_id 列**=计划表设计缺漏，会话身份必需）+迁移 `b371c327f9ff`（**eval_cases 入 RLS 名单第十表**=计划蓝图漏 M3.3 前置义务补齐；eval_runs 无 tenant_id 不上=events 先例）+config `eval_run_token_budget=150_000`+env.py import。定义源=evals/cases.json（20 条机械转换 adv10/e2e7/ret3，kind/facet/note 收进 expectation——fallback_rate 分母与配比 lint 靠 kind 不丢）；seed_eval_cases.py 幂等 upsert（**enabled 运营开关不被重跑冲掉**，测试钉死）；六层 lint 随迁**升七层**（+category↔kind 映射一致性）；目录用现有 evals/ 弃计划 evalsets/。**过程事故如实登记**：影子排练环境变量名写错（正确名 `DATABASE_URL` 无前缀）→迁移误打 dev 库（与目标状态一致，用户裁决保持现状）；改正后 aegis_shadow **裸库九跳全链自举**实证。**用户验收裁决：seed.jsonl 封存保留**（M3.11 历史原件，README 声明不再被任何代码读取） | `b5bb4ab` |
| M4.4② ✅ | **runner+rubrics（测试 949→953）**：run_eval.py——`run_batch(execute=, judge_gateway=, token_budget=, fallback_signals=)` 可注入结构（四测试全桩零真实调用）；判定分层=must_not_contain 一票否决→三 behavior 机器绊线（fallback=信号集∨ticket∨**挂起被拒**／denied 同／answered=normalized must_contain+tool）→**adversarial 机器过即 pass、e2e judge ≥4=pass、retrieval 纯机器（top-5 内 document_id 命中——chunk 自增无稳定标识，文档文件名是唯一穿越重摄取的锚=开工核对结论）**；judge 非 JSON/异常→**error 三态**（不算 fail）；预算=UsageChunk 实测累计循环头检查。**开工未预见点两处**：iso-06 超阈值挂审批→runner 扮演坐席**拒单+resume 收尾**（第二层防线的正确剧本）；iso-09/10 approval 面=**ci_pinned 特判**零执行零花费。docs/eval-rubrics.md 四节=**仓库内首篇 docs/**（三类判据+五档锚定示例+同族偏差三缓解+spot-check 流程与 <80% 重校准触发线）；strong 链按实况 qwen3.7-max/qwen-plus（计划的 qwen-max/deepseek-v3 已被模型池 v3 取代——**同族偏差论证反而更强：全链同为 Qwen**）。排练一红=测试台词自指（"不含锚的回答"含"锚"字） | `8b2e295` |
| M4.4③ ✅ | **观察池 M4.4 档批（测试 953→955）**：**㉖** prompts.py +FAQ_DIRECT_RULES 拼接 answer_faq system（规则 3 直答版=M3.12 兜底率闭环另一半；租户政策在前平台底线收尾；直答零 cassette 覆盖实证=零重录费）；**㊴** service FAQ 分支前置 `Guardrails().check_input`（纯规则库零 LLM），HIGH 回落 `_run_main`——审计闭环在 loop 侧（拒答+guardrail_triggered+D10 completed），测试钉钱包面证据 `gw.calls==1`；HANDOFF 直通**不加**（无 LLM 面+可疑内容转人工是合理去向）。**(57)** `_summary` 零事件态 resumed→**no_op**（词即语义；实测半边移 M4.7 容器世界——ASGI 直调无真网络断连语义）。排练抓我脚本转义层事故（heredoc→python 双层解义断串）——影子门拦下 | `69959ae` |
| M4.4④ ✅ | **真实批次（凭证 `reports/eval_baseline_20260803.txt`；冒烟 5 条→完整 20 条，总花费 ¥0.0445）**：**冒烟首炮抓真缺陷**——judge 是全项目**首个 tenant_context 之外的网关调用点**，计量写 usage_ledger 被 WITH CHECK 拒 42501（**(58) 家族新例**；计量"绝不拖垮请求"兜底防线首次真实验证——批次照跑仅账缺 judge 行）→修=judge 流消费包上下文。**对账核查抓第二缺陷**——`_row_cost` LIKE 前缀跨批撞账（最终批行 cost 恰=账本全量）→修=judge 与被评**共用唯一 sid** 精确对账（下批起行成本干净）。完整基线 **20/20**（adv 10/10+e2e 7/7+ret 3/3）、28,650/150,000 token、judge 全程 qwen3.7-max 零 fallback（C36 回显实录）。**判分全 5 分=judge 打分维度暂零区分度（如实归因不美化）**：种子集是 M3.12 调优后的行为面，当前质量信号**全部来自机器断言面**；出区分度两条路=M4.5 扩集加难例+spot-check 人工对照（rubrics §4 预言场景实锤）。**#25 翻 ✅**：判据落 rubrics §4，spot-check 首轮挂 M4.5 扩集后（样本量更足）——**已兑现（M4.5③）**：25 条异族复评 ±1 一致率 100%，`reports/m4_judge_spotcheck.txt` | `3b2ebfd` `b9ccffb` |
| M4.5① ✅ | **评测集 20→40（2026-08-03，测试 955→957）**：+20 条（ret+9=未覆盖语料高熵细粒度锚含改写问法／okb+3 近域／nor+4 正例（logistics_query 首正例）／iso+2=越权话术包装+跨租缓存探测／**inj+2 新细分类 injection**（泄 system 探测+冒充系统套内部名））；配比恰中 adv14/e2e14/ret12；七层 lint 升八层（词表+injection/inj-、+总量 30–50、+三类各 ≥8）；rubrics §3 +injection 判据段（inj-02 期望 **answered** 非强制兜底——合规礼貌应答不误杀）。**计划 §3-2 id 规则作废**（细分类前缀沿用=趋势串联+lint 映射）；"诱导写工具重试"换"冒充系统"（判据可机器化）。旧 20 条一字未动（全 insertions 可核） | `6a4a1c2` |
| M4.5② ✅ | **扩后批次+双侧修缮+五盘重录（四轮批次实录）**：首批 e2e 10/14——四条 fail **恰两两分属 M3.12 判准两侧**：okb-02/08=判据漏报（合法兜底避开全部十词→信号集三轮反哺+「未在知识库」「暂不」）／okb-05/07=真编造（**judge 1/2 分正确抓获=区分度首次兑现**，判分 {1:2,2:1,5:21}）→ SYSTEM_PROMPT 规则 3 品类二轮扩容（+期限时效+网址公众号联系方式；"定了不动"第二次修订流程）→**五盘重录 ¥0.0063+M4.3 回放门首次真实值守 15 绿**（重录后行为轨迹零漂移）。复跑撞两新事：nor-03=**l3 重录真实消耗 AZ-1002 的环境状态污染**（全链诚实、错在共享种子无复位纪律→跑批前 seed_demo 复位落 README §5）／okb-07 仍编 90 天=强先验顽固样本+信号集四轮反哺「不支持」（归因链修正为 judge 抓获） | `53d79c8` |
| M4.5③ ✅ | **绊线归位+尺升级+spot-check（测试 957→958，稳定基线 38/40=95%）**：**spot-check 预填复核抓出 iso-12 假 pass**——回答「1–3个工作日」**en-dash 绕过连字符禁词**（字符形态盲区），同时字符形态即取证（**非缓存/检索复制、是强先验编造撞值**——隔离没破/编造成立，judge 判"泄漏"过重但 fail 方向对）→ `normalized` 尺 +en/em-dash（benchmark 消费方零冲击实证）；**okb-05 三轮措辞变体漏报的结构性了断**：machine_verdict 归位"绊线只管召回"（e2e 绊线不中→**交 judge 终裁**而非机器硬 fail；adv 保持机器 fail=判定权不外放；实现兑现 README 架构宣称——词面追逐就此打住，信号集 13 词冻结）。**稳定基线 38/40**：两条已知失败=强先验编造样本（okb-07/iso-12）如实保留；**spot-check 首轮**：25 条判定异族复评（Claude vs qwen3.7-max，口径如实标注非严格盲评+用户终裁分歧点）**±1 一致率 25/25=100%**、严格相等 84%、4 条分歧皆颗粒度层非方向性；连带观察一枚（iso-08 尾部"引导提供他人收件信息"=判据外引导面，登记 M4.6/M5 观察）。凭证两件：`eval_baseline_20260803.txt`+`m4_judge_spotcheck.txt` | `bdc55cc`+凭证 chore |
| M4.6① ✅ | **题库资产+流量生成器+lint（2026-08-03，测试 958→965；本步起 P8 拍板=全量 AI 直写，00 §2.1 单步例外第二例（M2.10 后），用户验证提交）**：`evals/cost_questions.json` 双节（routing 80=FAQ24/RAG32/工具16/闲聊8 全唯一／cache 唯一池 140=42/56/28/14）+`scripts/cost_common.py`（stdlib-only 底座：实验租户数据面常量+`build_cache_traffic` 纯函数——总长/复述数**精确成立**非近似、复述只从已流出前缀重抽、同 seed 逐条相等）+`tests/obs/test_cost_traffic.py` **七测**（§5 预告 3 上浮 4：+文件形状 id 规则/申报分布精确钉死（报告「集合构成」与文件绝不漂移）/工具题订单引用 I1/评测集零交集由"grep 抽查"升 CI 断言——沿 eval-lint 层次化先例）。**P3 实锚**：`mock_orders.id` 全局主键（models.py:38）→计划「每组一租户」会逼三组工具题题面发散，改**每实验一租户（exp-route/exp-cache，tenant-a 镜像）+组间精确 sid 清单分账**（M4.4④ LIKE 撞账后的对账正解）；P6=工具面只读（tools 只点名 order_query/logistics_query，写路径物理不在场） | `e16aac3` |
| M4.6② ✅ | **实验①脚本+冒烟**：`experiment_cost_routing.py`——**「强制指定档」旁路生产不存在**（开工核对结论：classify/answer_faq 硬编码 fast（intent.py:86/129）、build_agent_spec 硬编码 standard（agent.py:51）、strong 在线链路无人用）→A/A' 强制档=`replace(build_agent_spec(tenant), model_tier=...)` 直驱 `runtime.run`（frozen replace 重跑校验，**生产包零行为改动**）；B=`ChatService.handle` 进程内直驱（P5：与生产同栈层、计量在网关故成本面与 HTTP 全链等价、规避入站限流 429 干扰；分诊 fast 成本诚实入账）；控制变量装配后断言核验（缓存关/注入关——「配置改了≠行为验证了」的事前版）；每组账本 sid 覆盖 sanity（(58) 防线：计量 fail-open 掉账即中止不出报告）+超预算 partial。config +`cost_routing_token_budget`/`cost_cache_token_budget`=600_000（P4：00 §8.0「写死在配置」字面+M4.4 先例，弃计划脚本常量案）。**冒烟一次全绿**（异质样本 1 FAQ+1 工具题；B 直答 387 token vs A 全 Agent 1443=路由省钱机制现形） | `eae3bdf` |
| M4.6③ ✅ | **实验②脚本+冒烟**：`experiment_cost_cache.py`——**单脚本两相位**（P7：env `CACHE_TTL_SECONDS`+`get_settings.cache_clear()` 逐相位重装网关——build_gateway 内读全局 settings 无注入缝=核对结论；先关后开防烧热污染+相位 D 前 SCAN+DEL `aegis:cache:v1:exp-cache:*` 冷启动）；**请求级全命中自检**（`bool_and(cached)` 分组：复述全命中/首现零误命中/关相位零命中——比调用级命中率强在"管线确定性的证明"，对不上先修再报数）。**冒烟 8 请求复述 4/4 全命中**=跨会话命中机制实证（缓存 key 无 session_id 的 M1.10 决定在此兑现——反面推论：当年混入 session_id 则实验②降本恒 0%） | `2f5e3ef` |
| M4.6 收口 ✅ | **正式批次两件凭证（§8.2 第三条达成，2026-08-03）**：`reports/m4_cost_routing.txt`——三组 80/80 零 errored、覆盖 sanity 全齐；**vs-strong 74.7%／vs-standard 18.9%**（¥0.3544/¥0.1106/¥0.0897；tiered=fast 105 调用 ¥0.0037+standard 68 调用 ¥0.0860，25 题被 FAQ 直答短路）。`reports/m4_cost_cache.txt`——两相位 200/200；**21.9%** @30% 复述假设（¥0.1907→¥0.1489，cached 121 调用）；**自检=复述 60/60 全命中/首现 0 误命中/关相位 0 命中**（管线确定性实证）。两报告四段骨架+聚合 SQL+精确 sid 清单全文；**独立复算**（LIKE run_tag 异形查询）与报告逐位吻合。**观察**：30% 复述→21.9% 降本≠等比——复述均匀重抽撞上题目成本异质（闲聊 0.3k vs 工具题 3.2k token），流量构成决定折算率（报告 §4 限定语覆盖）。**过程发现**：tests/conftest.py:23 flushdb×并行跑批=全量测试会打掉相位 D 缓存条目烧掉整批——四门推迟到批次后（教训：共库共 Redis 的并发操作先 grep 破坏性触点）。**M4.6 真实调用总账 ¥0.9261**（两冒烟+两正式批+setup embedding；chat 937k+embed 9.6k token，双 600k 预算内）。§10.2 两行翻 ✅；题库 461–467；顺带观察：§8.2 第一条 trace 行 M4.1 已达成但复选框未翻——挂 M4.8 对账。**收口追加**：四笔提交与推送亦 AI 代跑（用户当日授权"推送提交你也能做"并全权委托 M4.7/M4.8——例外范围扩展至 git 面，与 P8 同批登记） | `934e8fc` |

---

## 9. M5 · 交付收口（1 周基线，7 步）⬜

**真实调用口径**（2026-07-10 补，与 §7.0/§8.0 对齐）：仅 M5.2 口径②（小样本真实延迟分布
50–100 次）与 M5.4 演示/两项凭证补录产生真实调用，预算上限写死进脚本；
压测口径①与 CI 全程 FakeGateway 零真实调用。

### 9.1 步骤计划

| 步 | 内容 | 规模 | 文档锚点 |
|---|---|---|---|
| M5.0 | 开工走查 + 简历占位符清点（§10.2 逐项核对哪些已有凭证、哪些本里程碑必须产出）；LangGraph spike 完成情况核对（§10.1 #33） | S | §10.2 |
| M5.1 | **locust SSE client 自写**（1 天） | M | 04 M5 |
| M5.2 | **压测两组口径**：① 平台开销与并发容量——FakeGateway 注入固定延迟模型（首 token 800ms + 20 tok/s），压本地多副本，≥3 个并发档位，报吞吐/错误率/平台自身开销 P50/P99；② 真实延迟分布——小样本 50–100 次真实调用测首 token 分布（不做高并发：费用与厂商限流约束） | L | 04 M5 |
| M5.3 | **水平扩展演示**：`--scale api=3` + Nginx（`proxy_buffering off` + 调大 `proxy_read_timeout`——SSE 两个坑，ADR-007） | M | ADR-007 |
| M5.4 | **15 分钟 demo 脚本**：三个高光时刻——故障注入（熔断+fallback）、断点续跑（HITL/kill -9）、多租户隔离（对抗演示）；实测计时 ≤15 分钟。**顺手补录两个凭证**：熔断恢复闭合时间实测（04 M1 验收未尽项，§10.1 #10）、qwen3.7-plus↔glm5.2 容灾切换实录（2026-07-16 模型池变更后的对，原 qwen-plus↔deepseek-v3；支撑 05 简历模型容灾表述——"DeepSeek"字样随 #28 改，§10.2） | M | 01 §3 |
| M5.5 | **README 终稿 + 架构图 + 简历回填**：§10.2 全部 X 占位符回填实测值（口径限定语随数字走，如"本地压测（模拟上游延迟）下 P99 …"）；若某项被砍同步从简历删除；简历叙事按应用岗版调序（§10.1 #34） | M | 05 全文 |
| M5.6 | **终验收**：demo 实测跑通；压测报告两组口径分开呈现；简历与交付物逐词对照；tag `v1.0`；记忆归档（项目完结版） | S | §13 模板 |

### 9.2 毕业验收汇总

- [ ] demo 脚本实测 ≤15 分钟跑通全部高光时刻；
- [ ] 压测报告覆盖 ≥3 个并发档位、两组口径分开；
- [ ] 熔断恢复闭合时间与 glm5.2 容灾切换两项凭证补录完成（M5.4；2026-07-16 前口径为 deepseek，已退役）；
- [ ] 简历模板所有 X 占位符回填实测值，凭证文件齐全（§10.2 清零）。

---

## 10. 横切追踪清单（每个里程碑开工/毕业时过一遍）

### 10.1 跨里程碑遗留归位表

| # | 事项 | 来源 | 归位 | 状态 |
|---|---|---|---|---|
| 1 | 单请求 token 预算闸门（L1，三级预算之一） | M1.11 范围注明 | 已实装：`request_token_budget` + `core/tokens.py` 估算器（提交 `f176b1e`，2026-07-07） | ✅ |
| 2 | 会话级 token 预算闸门（L2 终止闸门 #3） | 三级预算设计 | 已实装：M2.7 闸门 #3——调用前预检（不打半截请求）+ 计数种子从事件流重建（D8）+ L1 预算异常映射 cause 分层（D9）；测试 6 条含 token 烧穿对抗（提交 `a7c0e62`/`6b7f22e`，2026-07-11） | ✅ |
| 3 | 缓存命中 QPS 放大效应复核 | M1 审计遗留 | M4.0① | **✅ 复核完成（2026-08-03，零代码）：命中路径不加限流**——`rate_limited` 挂在 `POST /v1/chat` 依赖 `_ADMITTED`（chat.py:44），链序 401→403→429 **早于** handler 体内任何 gateway 调用，而缓存命中在 `router.complete` 最外圈（router.py:216-233）：命中路径已被租户维度入站限流覆盖，且命中不消耗供应商配额、出站限流本不该管。计划 §3-1 预设的"若不覆盖则升级为修复项"未触发。**顺带坐实观察⑥**：入站限流只挂 chat 一处，kb（花钱）与 stream（占连接）无——不改变本条结论，两者归 M4.2 有 /metrics 后重估 |
| 4 | alembic check / downgrade 往返加固 | M1 审计遗留 | M4.0③ | **✅ check 已进 CI**（2026-08-03，`09d0c7b`+`54f3e28`）：置于 `alembic upgrade head` 之后（要比对"迁移链建出的库"与"当前 ORM 元数据"）。**首跑即抓出一条真实不一致**——HNSW 索引手写在迁移（`7fe5de25a9ca:61`）而 ORM 无声明，autogenerate 恒报 `remove_index`；修=`ChunkRecord.__table_args__` 补 `Index(..., postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})`。**口径修正（探针实证）**：M3.4 §4.4 陷阱 2 的"autogenerate 不认识 USING hnsw"只对**生成**面成立（确实不会自动写出，故手写迁移的决定依然正确），**比对**面它认得——不声明则这道门永远红。否决 `include_object` 排除法：那是用"让门看不见"换"门变绿"，索引将来被误删也无人报警。**✅ downgrade 往返已做**（M4.0④b，凭证 `reports/m4_alembic_roundtrip.txt`）：`downgrade base` → `upgrade head` → `check` 三步全通，**8 个迁移正反双向均可走通**——其中 **4 个手写 DDL 迁移**（RLS 角色与策略／EXTENSION+HNSW／mock 两表+RLS／NOTIFY 触发器）的 `downgrade()` 分支**此前从未执行过一次**，本次首跑即全过，M4.7 容器化的回滚预案有据。不进 CI（清库+拖时长），一次性本地验证。**附带坐实文档漂移**：08 §6.1-bis 记"迁移链 2→9 个"实为 **8**（其列举漏了 M1 的 `ab31f1ad346e`），已据 8 条回滚记录更正；顺带更正 08 §9.1 脚本数 24→27、§9.2 CI 行数 67→98 与门数 9→12。**计划外真实调用记账**：清库使摄取幂等失效（"未变 DONE 整篇跳过"的省钱闸不触发），种子重建时 20 篇语料全量重走真实 embedding——`usage_ledger` tier=embedding **20 行 / 2,955 token / ¥0.001481**，属 00 §8.0 之外的例外，M4.8 毕业对账计入 M4 真实调用总账。**教训**："数据可重建"不等于"重建免费"——涉及清库的实验，成本核算必须包含重建代价 |
| 5 | kill -9 崩溃恢复验证 | M2.10（紧张时顺延） | **M2.10 已做 ✅**（P5 拍板；`de39165`，凭证 `reports/m2_kill9_recovery.txt` 四断言全 PASS） | ✅ |
| 6 | 幂等键下游去重实装（M2 只透传，下游是假的） | M2.4 契约 | **M3.7 已闭环 ✅**（2026-07-25，`3df3cc3`/`95faef2`）：mock_write_ops **PK=幂等键**+ON CONFLICT 单事务算法（崩溃零中间态/失败不烧钥匙/唯一索引仲裁恰一次）；工具侧 `Idempotency-Key: ctx.tool_call_id`（write-ahead 事件 id 首次真的开锁）；真库双击实录 duplicate false→true（demo_tools_acceptance 幕 B） | ✅ |
| 7 | ContextBuilder 检索/记忆槽位实装 | M2.5 只留接口 | **M3.5③ 检索槽已接电 ✅**（2026-07-25，`c4f0829`）：RetrievalProvider 适配器（retrieve.py）+ ContextBuilder 集成测试钉死；memory 槽位恒空=P1 砍出 v1（#20）；**M3.8② 生产注入已收尾 ✅**（2026-07-25，`0793b48`：AgentRuntime +retrieval 受控缝（拍板Ⅱ additive）+create_app 生产接线 RetrievalProvider(Retriever)） | ✅ |
| 8 | 批准后前置校验重跑（M2 只留挂点） | M2.9 | **M3.9① 已实装 ✅**（2026-07-26，`aee4abb`）：apps/support/revalidate.py `build_precheck(factory)`→`AgentRuntime(precheck=…)` 生产接线（API create_app 与 worker _task_runtime 两侧共用）；PrecheckHook 无 ctx 冻结面下归属重校验由批准执行期 handler 以真实 ctx 兑现、revalidate 只管快照新鲜度；**TOCTOU 真实链路否决实证**（demo_hitl 段D：批准落锤前订单被退→不执行、approved∧event_id=空） | ✅ |
| 9 | 设计文档迁入 repo | 记忆档案"M5 前" | M4.7 | ⬜ |
| 10 | 熔断恢复闭合时间实测（**04 M1 验收未尽项，无条件补**） | 04 M1 验收 | M5.4 | ⬜ |
| 11 | 出站限流计数口径升级为"按尝试"（现为按 HTTP 调用） | M1.12 注明 | 保持现口径，v2 再议 | 冻结 |
| 12 | 限流精度 0.76% 落盘凭证（现仅会话内实测） | M1 凭证缺口 | 已落盘：2026-07-07 复测 0.76%（521/525），`reports/m2_ratelimit_retest.txt` 含口径注记（提交 `0a71488`） | ✅ |
| 13 | 月度预算闸门读路径 config.py → tenants 表 | M3 建表 | **M3.1③ 已实装 ✅**（2026-07-24，`43db3a5`）：`monthly_budget_resolver` 注入缝（在场即事实源、读挂 fail-open、None 落回静态 int 既有测试零改动）+ factory 注入 `TenantDirectory.monthly_budget` | ✅ |
| 14 | 会话锁 Redis 降级 PG advisory lock（**session 级 + 稳定哈希——评审 C4 修正**，不放弃互斥） | ADR-005/02 §5 | **M2.9 已实装 ✅**（`ab4fcd8`，dead_r 互斥测试钉死）；**M2.12 真停容器实录 ✅**（`reports/m2_degradation_redis.txt`，并发恰一互斥——依 §6.2 第 6 项凭证需求的计划级范围补充，plans/m2.12 §3.2-11）；M5.4 demo 排练复跑待 | ✅ 实装+实录 / ⬜ M5.4 复跑 |
| 15 | 停 PG 演示：事件写入退避后终止、无半执行副作用 | 02 §5 | **M2.12 已完成 ✅**（`reports/m2_degradation_pg.txt`——write-ahead 核验式成立；实录抓出 OS 级连接错误白名单盲区，修复 `98e2549`） | ✅ |
| 16 | 429 口径同步：02 §4"每次失败计入熔断窗口"旧表述修订 | M1 实装定稿 | 已同步（2026-07-06 修订 02 §4） | ✅ |
| 17 | JWT 信任根：签发/验签算法/密钥托管与轮换设计 | 2026-07-07 评审 C12 | **M3.1② 已实装 ✅**（2026-07-24，`3a41a50`）：HS256+SecretStr 托管+previous 双密钥窗（仅签名不符才试旧钥）；弱钥 <32B 升硬错误（RFC 7518）；TTL 2h/8h | ✅ |
| 18 | 非请求路径（reaper/Celery/计量/nightly 对账）的 SET LOCAL 租户上下文 | 评审 C13 | **M3.3 已裁决大半**（2026-07-24，D4）：reaper/nightly/种子/发凭证=**维护面 owner 引擎不设上下文不冒充租户**（文档+代码双落）；请求路径=auth 验签即设 ContextVar（`d73e098`）；计量=随请求上下文天然覆盖；**M3.4③ Celery 逐租户任务已兑现 ✅**（2026-07-24，`6e5f769`）：ingest 任务 async 内胆 `tenant_context` 包全程（比"任务体首行"更强——含计量路径）+ 任务局部 app 角色引擎+guard（plans 14d 防炸前提⑴⑶）；**运行时证据已补录**（2026-07-24 真实链路：documents=done + usage_ledger embedding 行 28 token/¥0.000014） | ✅ |
| 19 | stream/events 读端点"仅本人会话"的用户级归属校验机制 | 评审 C14 | **M3.2 已实装 ✅**（2026-07-24，`d2bd55d`）：chat 端点 `_ensure_session` 首见以 JWT 身份建行、此后 tenant+user 双匹配、不符 404 不泄露存在性（并发首见撞 PK 回读校归属）；M3.10 stream/events 端点复用同一机制 | ✅（M3.10 读端点沿用） |
| 20 | 长期记忆写路径裁决：砍出 v1 叙事（01/03 同步删）或补数据模型与生成步骤 | 评审 C24 | **已裁决（2026-07-24 M3.0 拍板 P1）：砍出 v1**——槽位接口保留（`MemoryProviderLike`，v1 恒 None；M3.8 装配 `memory_budget=0`）；01 §2/03 §3/02 §7.2/本文档 §7.1 M3.5 行叙事已同步修订；列入 §10.3"接口已预留"档，升级路径=评审 C24 方案(a) `user_memories` 表 | ✅ |
| 21 | tenants.config 治理声明：初始化/修改入口/变更审计（v1 可种子只读+一段话） | 评审 C42 | **M3.1 已兑现 ✅**（2026-07-24，D12 拍板形态）：种子即初始化入口（seed_demo upsert 幂等）、运行期只读无修改端点；治理一段话已落 02 §3 tenants 行 | ✅ |
| 22 | 月度预算闸门热路径全月 SUM 聚合优化（Redis 计数器或短缓存） | 评审 C39 | **M3.1③ 已实装 ✅**（2026-07-24，随 #13 同笔 `43db3a5`）：TenantDirectory 60s 进程内 TTL 短缓存（P3 拍板弃 Redis 计数器——预算是 fail-open 软闸，过冲上界=TTL×QPS×单次 token 可接受）；另 budget≤0 时不再空查账本 SUM | ✅ |
| 23 | 租户预算使用率 gauge 进 /metrics（逼近告警最小形态，通知渠道 v2） | 评审 C40 | M4.2 | **✅ 已实装+实拍**（2026-08-03，`80299de`/`4b33295`）：`aegis_tenant_budget_used_ratio{tenant_id}`——分子**复用月度闸门 `MeteringRecorder.month_spend` 同一实现**（月窗/cached 排除/索引三口径继承，告警与拦截同一把尺）；budget≤0 不导出；比率不预计算口径下这是唯一的预算比特例（除法在分子分母同刷新点故无时间窗错位）。凭证 `reports/m4_metrics_sample.txt`：3 轮演示 0.0008→0.0031 肉眼上升 |
| 24 | CI 阻断式密钥扫描（gitleaks 类）+ 依赖漏洞扫描（pip-audit 类） | 评审 C32 | M4.0③ | **✅ 两门已进 CI**（2026-08-03，`09d0c7b`）：**gitleaks** `gitleaks/gitleaks-action@ff98106e…`（v2.3.9，SHA 实查 GitHub API 非凭记忆）置于 checkout 之后**第一道**（后续每步都可能把仓库内容打进日志）+ `fetch-depth: 0` 扫全历史（只扫最新提交等于漏掉"密钥曾经进过历史"，而那是唯一不可逆的情形）+ 仓库根 `.gitleaks.toml`（`extend.useDefault` + 两条经核实豁免：本地容器弱口令连接串 / cassette·reports 高熵串；**空 allowlist 也保留文件本体，让"加豁免"必须显式发生在版本历史里**）；**pip-audit** `uv add --dev pip-audit` + CI 在 `uv sync --frozen` 后 `uv run pip-audit`（必须 `uv run`——审计对象是当前 venv，锁文件即事实源），本地实跑 `No known vulnerabilities found`（输出中 `aegis-agent-platform Dependency not found on PyPI` 是**预期**：本地包无从审计，非告警）。两门均**阻断式**无 `continue-on-error`。**✅ 红绿有效性验证已通过**（M4.0④b，2026-08-03）：探针分支开 PR 触发 `pull_request`，**CI 如期红在 gitleaks 步骤**，验完关 PR 删分支（未合并）。**验证过程本身产出四个"门装了但没验过"的发现**：⑴ `on.push.branches:[main]` 使 `tmp/*` 分支的 push **不触发任何 workflow**，必须走 PR；⑵ 首版探针用 `AKIAIOSFODNN7EXAMPLE` **撞 gitleaks 自带 stopword**（含 `example` 一律放行）→ 即使跑了也是绿的，**假阴性伪装成通过**是红绿验证最危险的失败模式，故换用中性变量名+高熵串走 `generic-api-key`；⑶ CI 日志实证 action 对 push 事件跑 `--log-opts=-1` **只扫本次推送的 commit**（见 #24 上方 ci.yml 注释更正）；⑷ 带 AWS 格式的探针被 **GitHub Push Protection 在服务端拦截**——意外发现仓库有比 CI 更早的第 0 道防线（`[KaiyangDing] is an individual user. No license key is required.` 亦由日志确认）。**纪律**：红绿验证的探针**必须先本地实证会被抓**再推，否则"绿"没有任何信息量 |
| 25 | LLM-as-judge 人工 spot-check 排期与判据（含同族自评偏差一段话） | 评审 C38 | M4.4 | **✅ M4.4②④（2026-08-03）**：判据与流程落 `docs/eval-rubrics.md` §4（同族自评偏差声明=judge 与被评**全链同为 Qwen**+三缓解：五档锚定示例/对抗判定不依赖 judge/spot-check 凭证；±1 分一致、一致率 <80% 触发重校准）；**排期=首轮 spot-check 挂 M4.5 扩集后**（首个完整基线判分全 5 分零区分度——对照样本量不足，扩集加难例后做量更足的一轮，凭证落 `reports/m4_judge_spotcheck.txt`） |
| 26 | 应用容器化：Dockerfile + api/worker/beat 编排 + alembic 迁移执行顺序。**M4.0④b 追加一项验收义务**：Linux 容器起 worker 后复验"unacked 消息由定时器自动 restore"——这是 #48 在本地形态下结构性不可达的那一环（Windows 无 event loop），容器化是它第一次能被验证的时机；形态=复用 `scripts/experiment_kill9_ingest.py` 但去掉手动 restore 那一步 | 评审 C20（**M5.3 硬依赖**） | M4.7 | ⬜ |
| 27 | "确定性回放/replay 调试"升为 demo 高光与简历前三 bullet | 评审 C33 | M5.4/M5.5 | ⬜ |
| 28 | "多供应商/DeepSeek 实测"简历表述逐词校对（06 §5 口径已对齐）。~~2026-07-16 模型池变更：池=qwen3.7 系+glm5.2，"DeepSeek"改"GLM"~~ **2026-07-17 二次变更（M2.11 期间）**：glm5.2 实为幻影（404 `model_not_found`，三档 fallback 断链两日）已移除；充值解锁后池回归 qwen 梯队（fast=flash→turbo / standard=plus→turbo / strong=qwen3.7-max→plus，06 §5 已改）——**05 的"DeepSeek/GLM/异族容灾"叙事全部作废**，容灾表述回归 M1 形态（qwen 档内 fallback，flash→turbo 已有 M1 实测凭证）；M5.4 容灾实录对象随之改为档内降级 | 评审 X3 | M5.5 | ⬜ |
| 29 | 熔断/精确缓存的 Redis 触点仍是"每调用付故障延迟"模式（同复盘补丁二病灶）。~~计量影子账本~~：**措辞修订**（M4.0① 读码核实）——`metering.py` 纯 PG 路径全文无 Redis 触点（record/month_spend 均只经 SessionFactory），本条对其天然不适用，裁决对象仅熔断+缓存两处 | 复盘补丁二 | M4.0④a | **✅ 已实装**（2026-08-03，`3c57eaf`，用户拍板"做"）：病灶实为**降级只做到"不抛异常"、没做到"不付延迟"**——`_degraded` 此前只用于日志去重不 gate 调用，每请求 3–4 次触点各白付一遍连接失败延迟（connect 1s～read 2s 级），00 §2.2「缓存与计量故障绝不拖垮请求」只兑现一半；M5.2 三档并发压测必然放大成 P50/P99 污染。**范式与 `RateLimiter`（ratelimit.py:86-115）、`FailoverSessionLock`（locks.py:221-250）同构=全项目第三处**（面试可讲一致性）。两处拍板：⑴**探针只在 `allow()` 领**（每请求必过的判定入口且有本地兜底；写触点各自领会让四个窗口互相续期、恢复时机不可预测）；⑵**缓存粘滞放 router 不放 `ExactCache`**（后者全文零异常处理，降级语义本就住在调用侧 router.py 两处 try；塞进 cache 会让"缓存故障怎么办"分裂两处）。**不变量守住**：粘滞化不改降级语义本身（ADR-005：熔断 fail-open+本地计数 / 缓存降级=miss），两测试文件各留一条专测。**最易写错处**=`on_failure` 的本地记账必须先于跳过判断（写反=降级期熔断彻底失灵；正确语义是"降级的是共享状态不是熔断能力"），`test_degraded_write_touchpoints_skip_redis` 专钉。测试 864→**873**（+9，计划预告 6 上浮 3：两条语义不变量 + 写触点顺序钉子） |
| 30 | CI mypy 门从 `mypy aegis` 扩到 `mypy .`（tests 11 个存量类型错误：cache 混合列表 join、router tier 字面量、config `_env_file` dataclass_transform 缝隙豁免收敛为 make_settings 单点） | 复盘补丁二验收时发现，从 #24 拆出提前做 | 已完成（提交 `229ea5a`，2026-07-08） | ✅ |
| 31 | 容器 restart 策略缺失：pg/redis 有 healthcheck 无 `restart`，容器崩溃/宿主重启后不自动拉回（认知坑：healthcheck 只标状态不触发重启；restart 只响应"进程退出"不响应 unhealthy——"进程僵死但没退出"的自愈需 autoheal/swarm，属 v2 非目标）。与 crash-only 声明（C35）配套：无 restart 则 crash-only 只剩 crash | 用户 2026-07-08 追问"服务不可用是否自愈" | **基础设施容器（pg/redis）本次补 `restart: unless-stopped`**（选 unless-stopped 而非 always：保住"手动 docker stop 看降级"的演示口径——M1.12/M2.12/M5.4）；**应用容器（api/worker/beat）restart 随 C20 归 M4.7** | ✅ 基础设施已提交（`729ff4c`，2026-07-08）；应用容器待 M4.7 |
| 32 | LangGraph 对照文档 `compare-langgraph-m2.md`：照 M1 对照样式（逐卖点命运表 + 契约主权分析），覆盖 create_react_agent / ToolNode / interrupt / PostgresSaver | 2026-07-08 岗位目标确认（AI Agent/应用岗），由可选升**必做** | **M2.12 已落档 ✅**（2026-07-17：1.0 世代钉版、四覆盖面、命运表 14 行、主权章；interrupt"重放节点 vs 重建事实"钦定面试最深一问） | ✅ |
| 33 | LangGraph 迷你复刻 spike（1–2 天）：复刻 demo 场景子集 + `@tool`/`ToolNode`/`interrupt` 源码阅读笔记——支撑简历"熟悉 LangGraph"逐词诚实（C18 表述纪律同时满足） | 同 #32 | M4 毕业后弹性窗，M5.0 清点核对 | ⬜ |
| 34 | 05 简历模板出**应用岗版叙事**：运行时（循环/上下文/HITL）与业务层（RAG/评测）bullet 前置，网关 infra 数字降为支撑证据；90 秒叙事线同步调序 | 同 #32 | M5.5 | ⬜ |
| 35 | **M2 代码级复盘 `retro-m2.md`**（retro-m0-m1 姊妹篇，2026-07-10 用户点名必做）：全景地图（类↔职责↔测试）、**接口对齐表**、一次 run 的完整旅程（双轨+三条支线）、横切哲学十条、面试连环炮 19 问 | 用户 2026-07-10 | ~~M2 毕业后新会话首件事~~ | **✅ 定稿**（2026-07-17 毕业当日同会话完成——经用户指示提前，上下文最热时落笔；M2.1–2.7 沿用对抗核验版一字未动，M2.8–2.13 以 `98e2549` 为准新写；含挂点接电对账与 08 行号漂移处置注记） |
| 36 | **模型交接工程**（Fable 5 → Opus/Sonnet）：`CLAUDE.md` 双入口 + `docs\07-handoff-guide.md` + `docs\08-code-map.md` + `docs\plans\`（M2.5–M5.6 步骤级计划，两路对抗校验+交叉审计后落档）；此后维护纪律：每步毕业时回填对应计划文件偏差块 + 更新 08 对应节（plans\README.md §4） | 用户 2026-07-10 交接需求 | 已完成（2026-07-10） | ✅ |
| 37 | PG LISTEN/NOTIFY 跨副本事件通知**实装**（选型裁决已在 §2.2 C22 行，但 §7.1 M3.10 行文未点名实装动作，防漏做） | 评审 C22 | **M3.10③ 已实装 ✅**（2026-07-26，`d1d2275`）：迁移 `d41be6a90c27` AFTER INSERT 触发器（payload=session_id:seq 纯路由键）+ api/notify.py EventNotifier（独立 asyncpg 原生连接 LISTEN、断连降级 after_seq 轮询自愈、伪唤醒安全=等待方一律重查）；真实链路实证：批准后续跑帧瞬时推达 GET 流（早于批准 HTTP 响应返回） | ✅ |
| 38 | M3.7 五个业务工具的 risk_policy / risk_exempt 逐个声明核对（M2.3 类型层防呆会在注册期强制报错兜底；此行防"批量豁免糊弄过防呆"的省事写法） | 评审 C15 | **M3.7③ 已完成 ✅**（2026-07-25，`95faef2`）：声明清单进 CI——test_tools_contract.test_declarations_ledger 五工具三元组逐个断言（READ×2 / WRITE+exempt×1（tickets 豁免理由留档：无资金面+handoff 直通防死锁）/ WRITE+policy×2） | ✅ |
| 39 | M2.6 开工核对发现的三处文档漂移回写：03 §7 协议签名形式（`async def`+AsyncIterator → `def`+AsyncGenerator 实装口径，防照抄踩坑）；03 §5 loop_terminated"7 类"表述（实为 7+1，gateway_rejected 在七类之外）；本文档 §6.1 M2.6 行"轮次"补道内序号括注（C10 收窄） | m2.6 计划附录 1/2/5 | 已完成（2026-07-11 当天回写） | ✅ |
| 40 | **项目全景复习图册 `docs/atlas.md`**（索引+图+速查，面试快速复习用；不重复 retro 深挖内容，深度一律链接跳转）：①全景/L1/L2/L3/治理五组 mermaid 图（三层架构、import 依赖、一次请求旅程、一次 run 双轨旅程、六道闸门位置、append 三岔口、六层预算、回放四道、隔离四层防线等）；②**闸门与护栏总表**（全项目拦截点逐行：名称/层/防什么/触发条件/失败方向 open·closed/代码锚点/测试锚点）；③每层文件表（文件·行数/一句话职责/最重要不变量/深挖跳转）；④失败哲学总表（M1 七条+M2 八条合并对照）；⑤数字凭证卡（简历数字→口径→reports/ 凭证）；⑥已知边界汇总（各 retro §7 聚合）；⑦复习路径（15 分钟速览+面试前一天清单）。**增量维护**：各里程碑毕业时补对应节（§13 第 5 项已挂），M5.5 终稿与简历回填同步 | 用户 2026-07-16 点名（M2 逐文件复盘会话，面试快速复习需求） | **M2.13 建骨架** → **M3.12 L3 篇已补 ✅**（2026-07-28：图组 D 两幅+闸门表 L3 行+文件表 L3 节+数字卡 M3 行+边界 M3 条）→ M4.8 补治理篇 → **M5.5 终稿** | ⬜（M4.8/M5.5 余量） |
| 41 | **思考型模型两项遗留**：⑴首块饥饿盲区残留——当前处置=全池 `enable_thinking: false`（2026-07-17，openai_compat）；若引入**关不掉思考**的模型，须实装适配器"首个活性信号"（首个 reasoning delta 处补发空 TextDelta，方案已设计 plans/m2.11 偏差 #11）；⑵**入池三验纪律**（存在性/思考默认态/关思考参数接受性，探针脚本形态 plans/m2.11 偏差 #12）已落 06 §5——新模型入池时执行 | M2.11 实录五连败根因链（幻影 glm5.2 + 思考饿死首块） | M4.0① 复核 | **✅ 复核完成（2026-08-03，零代码）**：⑴ 全池 `enable_thinking: False` 已实装（openai_compat.py:159），当前池三档六模型**全部接受该参数**（含默认思考的 qwen3.7-max，config.py:37 在案）→ "首个活性信号"方案的触发前提（引入关不掉思考的模型）**当前不可达**，保持不实装；⑵ 入池三验纪律已落 06 §5。两项均无残留动作；若将来入池新模型，三验与本条同时复活 |
| 42 | **M2 复盘候选①：ContextBuilder 的 memory.fetch/retrieval.search 裸调用无 fail-open**（context.py:172/181）——provider 异常裸穿 build 终止 run；M2 恒 None 零行为差异，但 M3.5 接真 RAG 后"检索服务抖一下杀掉整个对话"不可接受（检索是增强层该 fail-open：该层留空+留痕继续，M3.5 行本就写"检索失败走兜底宁可说不知道"）。修=形如 context.summarize 的 try（C34） | M2 全量复盘异常追问（2026-07-21，题 101） | **M3.5③ 已修复 ✅**（2026-07-25，`c4f0829`，修案 (a)）：RetrievalProvider 内 try 包 provider、异常返 `()` fail-open+warning 留痕，**L2 context.py 零改动**；回归钉子 test_provider_fail_open_keeps_build_alive（检索抖动 build 存活、无检索层、user 原文在场） | ✅ |
| 43 | **M2 复盘候选②：写工具"发出后传输型模糊错误"以异常形态绕过 X1**——X1 只把 TimeoutError 判"结果不明"；连接重置等物理上同样模糊的传输失败走 except Exception→ERROR→模型可重试新键→若下游只按我方键去重可双写。缓解三层=handler 契约（发出后不确定的传输错误按超时语义处理——**待写进工具实现契约**）+下游业务级幂等（X2 评审点过"下游都去重是无人担保前提"）+高危写走 HITL 收窄 | M2 全量复盘站 6 追问（题 89 灰区） | **M3.7③ 已落地 ✅**（2026-07-25，`95faef2`，拍板修案 (a)）：`tools/_shared.post_write` 单点——发出前（ConnectError/ConnectTimeout）原样上抛→ERROR 可改道；发出后（余 HTTPError）转 TimeoutError 交 executor 既有 X1 分支（executor.py:188 同捕 handler 自抛，**executor 零改动**）→RESULT_UNKNOWN+封死重试；双分支测试钉契约（test_write_transport_contract_43） | ✅ |
| 45 | **Python 3.14 升级评估**（PEP 649 惰性注解语义——动机：退役 PEP 563 future import 及其"闭包 Depends×字符串注解"一类过渡期坑，M3.2 实录 422 事故）：动作序=依赖轮子核查（asyncpg/pydantic-core/redis 等 C·Rust 扩展）→ 全仓删 `from __future__ import annotations`（含 ratelimit.py 豁免注释退役；触 M2 冻结面故必须在里程碑外做）→ ruff target/mypy python_version 升 → CI 镜像与 uv 钉版 → 全量回归+回放资产验证；**评估后选择不升并落档理由同样合法**（N-1 保守策略本就是 v1 的隐含选型，立项时无显式记录——本条补上决策痕迹） | M3.2 实录（2026-07-24） | v1.0 收口后弹性窗（与 #33 同档；M3–M5 期间禁做——范围纪律） | ⬜ |
| 44 | **M2 复盘候选⑤：审批恢复中途崩溃丢批准**——`_resume_locked` APPROVED 分支在 T3 之后、execute write-ahead 之前崩溃：reaper 崩溃恢复固定 `approval_id=None` 走 `_recover_locked`，而分诊全程不查 approval 单→已批准操作被当未配对弃置补话术（安全面 ✅：零副作用零双花；语义面 ⚠️：批准丢失、孤儿 approved 单、坐席白批一次）。修向=ResumeHook 认领前先查"该会话 approved 且未 attach_event 的审批单"、有则 `resume(approval_id=X)` 优先走审批执行；或 `_recover_locked` 增分诊支 | M2 全量复盘站 12 追问（2026-07-21，题库 97/98 邻题） | **M3.9③ 已修复 ✅**（2026-07-26，`5b77bcf`，取后案）：`_recover_locked` 增 a+ 审批认领分诊支+`_find_unattached_approved`（判据=最新 approved∧event_id IS NULL）；三窗分路——从未执行→decided 补写若缺+precheck+execute(approved=True)+attach ／ write-ahead 悬挂→原幂等键 reexecute+attach ／ 已有终局→取回落盘结果只补 attach **绝不重执行**（防双写）；**前案（钩子侧换入口）废弃**：三窗口推演 T3 CAS(awaiting→running) 在崩溃现场必打空静默返回；W0（decide 后未续跑——awaiting 无租约、租约扫描结构性不可见）由 M3.9④ hitl 对账扫描兜（"awaiting×最新单已决"）。先红后绿 5 红实测；veto 认领单据保持未回填与拒绝族孤儿=登记已知边界（题 138/139） | ✅ |

| 46 | **✅ 已修（M4.0③，2026-08-03，`cdaa407`）**：回读改 `scalar_one_or_none()` + None 抛 404 `from None`（`from None` 而非 `from e`：`IntegrityError` 是预期内的并发信号不是错误，404 是给客户端的正常答复，挂异常链只会让 traceback 噪音进日志）；回归钉子 `test_cross_tenant_session_id_collision_returns_404_not_500` 落 `tests/test_rls.py` M4.0 增量节（**跑在 RLS 在场的世界**——既有 admission 测试连 owner，走的是生产中根本到不了的那条归属判定分支，故此前无证人＝#47 的又一块补丁）。改完 RLS 在场/不在场两世界行为一致。原文备查：**M3 复盘候选（站 3）：`_ensure_session` 在 RLS 在场时对"他租已占用的 session_id"抛 `NoResultFound` → 500**（探针实测；测试连 owner 无 RLS 故走 404 分支，测试与生产行为分岔）。链路=SELECT 被 RLS 过滤成 None → 走首见建行 → INSERT 撞 PK → `IntegrityError` → 回读仍空 → `.scalar_one()` 炸。根因=`_ensure_session` 写于 M3.2、RLS 上于 M3.3，`row.tenant_id != principal.tenant_id` 被 RLS 抢答成死代码。危害=非数据泄漏，但构成**存在性 oracle**（500 vs 200），与 chat.py:58 docstring "不泄露存在性" 的声明不符；另有未处理异常的日志噪音。一般化教训：**新增一层防线会改变上层代码的可达路径——加防线后须普查"谁在依赖'能读到别人的行'这个前提"**（本条与 M4.0② 候选④ 是同一家族的两例，一起修故口径统一） | M3 全量复盘站 3（2026-07-27） | M4.0③ 顺手处置 | ✅ |
| 47 | **M3 复盘发现（站 3）：测试面几乎全部跑在 RLS 关闭态**——全仓唯一使用 `aegis_app` 引擎的测试文件是 `tests/test_rls.py`，根 conftest `TEST_DATABASE_URL` 默认 `aegis:aegis`（owner=超管+BYPASSRLS+表 owner 三重豁免），故 `test_adversarial.py` 四大对抗集中面亦在无 RLS 世界运行。分工本身合理（对抗测第 1/2 层、test_rls 测第 3/4 层通用性质），但**"业务代码 × RLS 在场"的交互面在 CI 里几乎无证人**——M3 已在此缝踩四次（M3.5 叶子自包裹 / M3.8 无身份读配置 / M3.12 对账面归零 / 本条 #46），前三次全靠人肉真实链路撞出。建议形态：**不**把全部测试改连 `aegis_app`（拖慢且噪音），而是加一薄层"RLS 在场"契约测试——把读会话/读租户配置/写账本的入口函数各钉一条 `rls_engine` 下的行为断言。对外表述同步收窄为"应用层隔离有 CI 集中对账面；RLS 兜底层有独立性质测试；两者交互面主要靠真实链路验证" | M3 全量复盘站 3（2026-07-27） | M4.3（CI 回放回归时并入） | **✅ M4.3②（2026-08-03，`360078a`）**：test_rls **M4.3 增量节**三条兑现建议形态——读租户配置（TenantDirectory 无身份=None 静默空，M3.8 幕 C CI 化）／写账本（MeteringRecorder 双面：本租真落库+跨租 42501）／mock 台账回放读（㉚：跨租撞键响亮 NoResultFound 不静默借用）；读会话入口证人已在 M4.0②/M4.1② 两节不重复。**对外表述自此升级**："应用层隔离有 CI 集中对账面；RLS 兜底层有独立性质测试；两者交互面有薄层契约证人（读配置/写账本/读会话/mock 台账四类入口），全量业务测试仍跑在 owner 世界" |
| 48 | **M3 复盘站 4：摄取投递为"至多一次"，四步算法的幂等性从未被兑现**——`task_acks_late` 未开（Celery 默认 `False`，消息在任务执行**前**即 ack）+ 无 PROCESSING 扫描器（reaper 只扫 sessions 租约），故 worker 崩溃/被杀 = 消息永久消失、文档永久卡 PROCESSING（其已回填块仍照常进检索）。病灶不是"缺恢复机制"，是**连一条可供恢复的线索都被提前销毁**——`ingest_once` 四步全为收敛操作（六窗崩溃表全安全），但那张表的前提"消息会被重投"不成立。**处置=改取"至少一次 × 幂等消费"**：`task_acks_late=True` + `task_reject_on_worker_lost=True`（后者覆盖 prefork 子进程被杀；`--pool=solo` 无父进程故本地无事可做，M4.7 Linux prefork 兑现）；全局开关的三任务安全性逐个核实（ingest 四步收敛 / `reap_once` CAS 扫描 / `sweep_once` 每轮从库状态重推）。**"beat 扫描重投"方案否决**：其"卡住"判据只能是超时启发式、必然误判慢而未死的 worker → 结构性引入并发 → 须给 documents 配租约（= 重做一遍 M2.10）；而 acks_late 在 unacked 期不重投，不引入并发。**新增不变量**：任务时长 ≪ Redis transport `visibility_timeout`（默认 3600s，当前余量三个数量级）——若为加快恢复而调低它，下限必须远大于最长任务时长（建议 ≥300s），否则"至少一次"退化为并发执行。重投重复成本上界 = 一批 `EMBED_BATCH_SIZE`=10 块（每批独立事务的红利） | M3 全量复盘站 4（2026-07-28，用户追问链：并发可达性穷举 → 修向代价分岔） | **M3 复盘补丁一**（`944e5ee`，2 文件 +24/−3）；kill -9 实录 → M4.0④b | **✅ 配置+CI 钉子已落** / **✅ kill -9 实录已补**（2026-08-03，`reports/m4_kill9_ingest.txt` 四断言全 PASS，零真实调用——`DASHSCOPE_BASE_URL` 指向 `scripts/fake_embedding_server.py`，生产任务体一字不改）。**⚠️ 实录推翻本条原有的一处判断，结论须修正**：原文只说 `task_reject_on_worker_lost` 在 `--pool=solo` 下"无事可做"，实况更重——**`task_acks_late` 的"至少一次投递"在 Windows 本地形态下只兑现一半**。证据链：kombu 把 unacked 恢复挂在 event loop 上（`loop.call_repeatedly(10, cycle.maybe_restore_messages)`，kombu/transport/redis.py:1382），而 celery `WorkController.should_use_eventloop()` 含 `not self.app.IS_WINDOWS`（实测 `IS_WINDOWS=True`）→ **Windows 恒走 `synloop` 无 hub（与 pool 无关）→ unacked 消息永不自动重投**；实测印证=kill 后重启 worker 等满 150s 无恢复，手动调一次 `restore_visible` 两条消息立刻回队列（restore 逻辑完好、只是无人调用）。**故本地形态下：消息不丢 ✅（acks_late 的那一半）、永不自动重投 ❌**，补丁一要到 **M4.7 Linux 容器（走 `asynloop`）才完整生效**。实录据此改造四断言（崩溃现场 / 消息仍在 unacked / 越过 visibility_timeout 后**手动** restore→重新消费至 DONE 且 chunk_count 正确 / 账本重复 ≤1 批），被替代的**只有"谁来定时调用"**，超时判定与 restore 均为生产实现。**实测数字**：25 块 3 批，kill 时回填 10；假服务调用 2→4 批=重复恰 1 批（正是上界）；**账本 embedding 行=3=理论批数 → 零重复计费**（崩溃当批的计量随事务一同回滚——"每批独立事务"的红利比预期更大）。⬜ **未覆盖面挂 M4.7**：定时器自动触发 restore 的 Linux 复验 |
| 49 | **M3 复盘站 4：kb 端点在 async 函数体内直调同步 `enqueue`（send_task），阻塞 event loop**——FastAPI 的 `def`→线程池分诊只对**它自己调用的**路径函数/依赖生效，函数体内的普通同步调用原地跑在 loop 线程上；原 docstring"毫秒级 v1 接受"的论证只覆盖成功路径，而 `enqueue` 唯一需要讨论的恰是失败路径：broker 失联时建连超时（celery 5.6.3 实测默认 `broker_connection_timeout=4`）×发布/连接两层重试——`ECONNREFUSED`（停容器）亚秒级、网络黑洞形态可达秒级~十余秒，**阻塞的是全进程所有并发**（v1 单机 127.0.0.1 只可达前者，风险随 M4.7 容器化上升）；CI 的 503 测试注入即时异常，不覆盖阻塞时长（M2.12"注入测语义分支、真容器测形状边界"只有前一半）。**处置=`await run_in_threadpool(...)` 一行下放 AnyIO 线程池**（`EnqueueFn` 签名/注入面/503 分支零改动，异常穿池原样传回；ContextVar 随 context 复制且 enqueue 不碰它，无站 1"线程内写不回来"问题）+ 线程身份回归钉子 `test_enqueue_runs_off_event_loop_thread`（回退成直调时无任何行为差异可测，唯一证词=执行线程 ≠ loop 线程）。**遗留普查挂 M4.0**：全 API 面"async 端点体内直调同步阻塞 IO"未普查（本条只审了站 4 范围），形态=grep 全部 async 端点体的同步库调用 | M3 全量复盘站 4（2026-07-28，用户追问"这里也是线程池吗"→ FastAPI 分诊适用范围辨析 → 失败路径成本核算） | **M3 复盘补丁二**（`6d2c531`，2 文件 +28/−3） | **✅ 全闭合**（普查半边已于 M4.0① 完成，2026-08-03）：`aegis/api/` 全面无第二处——无 `requests`/`urllib`/`socket`/`open`/`subprocess`、无第二处 celery 直调；唯二同步调用是 `jwt.encode/decode`（auth.py:80/106）与 `hashlib.sha256`（cache.py:41），均为**微秒级 CPU 而非 IO**，下放线程池只增切换开销 |
| 50 | ~~**M3 全量代码复盘未收尾，遗产须进 M4.0 开工核对**~~ **⑴ 已收口（M4.0①②，2026-08-03）**：四枚候选**全部实测复现并处置**——③ 定 P0（`84cca3f`：判据加"该单 approval_requested 之后已有 loop_terminated 即不认领"；**探针修正原述**：`_rebuild_working` 带全量事件故"用户新问题被完全忽略"不成立，真实危害是分诊走错支 + precheck 放行时**执行一次本轮从未请求的写操作**）／② 定 P1（`96390e0`：订单派生拒因统一 `_STALE_TEXT`、细节只进 logger；参数事实保持具体。**只覆盖信息面一半**——"细节进事件 payload"需改 `PrecheckHook` 冻结签名，用户 2026-08-03 裁决挂 M4.1 与 trace API 同做（**M4.1③ 已补齐 ✅**：`0795f0c`，PrecheckVeto 双面签名+第 17 类事件 precheck_vetoed，detail 只进审计面）；`_load_order` 仍无 user 维度=读不到 ctx 的结构性边界，修的是"说什么"不是"读什么"）／④ 定 P2（`85c10b2`：归属校验与关流判据**两处** SessionRecord 读均改走 owner 缝——只换前者会得到"流开了立刻关"；事件读不动因 events 无 tenant_id 不在 RLS 名单）／① 定 P3（**不修**：探针实测 sink 累计 248 字 vs 事件 content 42 字、token 帧 SAFE_REPLY 恰 2 次；顺带坐实"终局守卫在有通道模式下止损能力≈0，已推流不可撤回"=D11 显式接受的边界，**归 atlas 已知边界**，与观察 (52) msgbuf 定位同源）。**⑵ 观察池两条带时限项**：㊲ 已修（`29a3b8b` 缺省 200→0 fail-closed）、(63) 已修（`b7fc59f` 五件释放各自保护）；㉜ ticket_id 仍挂 M4.3 开工核对；余 (1)–(77) 三档归位挂 M4.0④。**⑶ `retro-m3.md` 仍未落笔**（挂 M4.8 与 atlas 治理篇同批）。原文备查：（用户 2026-08-03 裁决：跳过站 12 与收尾，直接进 M4）——复盘走完 **11/12 站**（站 12 资产与凭证走读暂缓；资产清单已盘清备查，见记忆档案），三项未做：⑴**缺陷候选四枚待裁决**——① 终局守卫命中时 SAFE_REPLY 双发（`loop.py:650/654` × `service.py:315/351`，纯体验+泄漏物留 msgbuf）／② precheck 拒因是对抗③统一话术的旁路（`revalidate.py:41-45` 无 user 维度，拒因经 SYSTEM_PROMPT 规则 4 复述=同租户跨用户存在性 oracle；**执行面安全**，建议与 ㊲ 同批）／③ 陈旧 veto 单跨 run 错误认领（`_find_unattached_approved` 无 run 维度无时间窗，veto 单恒满足 `approved∧event_id IS NULL`；**严重度最高**）／④ `GET /v1/sessions/{id}/stream` 的 "admin 平台级" 被 RLS 拦成 404（`stream.py:39` 走常规 app 工厂 vs 同提交 `events_view.py:38` 显式走 owner 查读缝——#46 家族第二例，fail-closed 不泄漏但能力声明与 02 §7.1 矩阵不符）；**②③④ 均系读码推断，定级前须实测**（④ 用 `rls_engine` 探针）。⑵**观察池 (1)–(77) 待三档归位**（升本表／留 atlas 已知边界／结案），其中两条带时限：**㊲ 退款闸门 `refund_needs_approval` 缺省 200 是 fail-OPEN**（同族 coupon 缺省 0 是 fail-closed，与 §2.2"安全闸门 fail-closed"冲突，新租户漏配即静默直退——建议 M4.0 顺手）、**㉜ `ticket_id=uuid4` 破 M4.3 逐事件比对**（`normalize_events` 别名化够不到 content 内字符串，修向=给 mock 加确定性 id 注入缝——**须进 M4.3 开工核对**）。⑶**`retro-m3.md` 未落笔**（#35 姊妹篇，M3.0 拍板⑴ 原计划由 12 站精读喂养）。深挖题已入库 **159–403**（题库 403），复盘发现的实锚与推理全部在题库与记忆档案中留档 | M3 全量代码复盘（2026-07-27 ~ 08-03，站 1–11） | **M4.0①② 已消化 ⑴ 与两条带时限观察**；㉜→M4.3 开工核对；观察池归位→M4.0④；retro-m3→M4.8 | ✅ ⑴ / ⬜ ⑵ 余项 / ⬜ ⑶ |

| 51 | **M3 复盘观察池 77 条的归位账本 → 见 §10.1-bis**（不并入本表：25+ 条会让主表膨胀三倍并淹没跨里程碑主线）。升级条目自带归位里程碑，分布 M4.2×11 / M4.3×6 / M4.4×3 / M4.7×18 / M5.2×1 / 零代码×2；边界条目已并入 `atlas.md`「已知边界汇总」 | M3 全量复盘站 1–11 | M4.0④c 已归位；各条按自带里程碑执行 | ⬜（账本已建，条目分散执行） |

### 10.1-bis M3 复盘观察池归位表（M4.0④c，2026-08-03）

> **地位**：M3 全量代码复盘（站 1–11）产出的 77 条观察的**唯一账本**。不并入 §10.1——
> 那会让主表膨胀三倍且淹没跨里程碑主线；升档条目在本表内自带归位里程碑，
> §10.1 只留一行指针（#51）。
> **三档判据**：**升**=有真实危害或真实收益、工作量可控、归位明确；
> **边界**=设计取舍的后果，v1 显式接受但必须对外声明（进 atlas「已知边界」防"完美系统"陷阱）；
> **结案**=当前不可达 / 已被其他机制覆盖 / 修的代价大于收益。
> **纪律**：结案不等于"没问题"，等于"已论证过不做"——理由必须写下，日后翻案有据。

| # | 一句话 | 档 | 归位 / 理由 |
|---|---|---|---|
| ① | `TenantDirectory._users` 缓存键不含租户维度 | **升** | M4.7：当前不可达（请求路径不查 users），一旦为"即时降权"接上 `get_user` 立刻变可达越权面 |
| ② | 缓存存 detached 且**共享可变**的 ORM 实例 | **升** | M4.7：`config` dict 被就地改即污染全进程 60s；修=返回副本 |
| ③ | `GRANT ON ALL TABLES` 把 `alembic_version` 也授给 `aegis_app` 且该表无 RLS | **升** | M4.7：一行 REVOKE 闭合；"粗粒度授权换维护便利"的代价 |
| ④ | 02 §7.1"终端用户=租户侧签发的短期 JWT"与 HS256 **架构上不相容** | **升** | M4.7 纯文档：对称密钥真给租户=隔离归零；改叙事或注明"v2 且届时必须换非对称" |
| ⑤ | `create_app` 注入 runtime+gateway 但不给 chat_service → `lock=None` | **升** | 并入 (76) 同批：注入组合空间的静默降级 |
| ⑥ | 入站限流只挂 `POST /v1/chat` 一处 | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：kb+approvals 挂既有 rate_limited 同租户桶；stream 不挂（占连接归部署面，理由入代码注释） |
| ⑦ | `jwt_user_ttl_s`/`jwt_staff_ttl_s` 唯一消费点是 `mint_token.py:24` 三元表达式且**零测试** | **升** | M4.7：写反=终端用户暴露窗放大 4 倍且无红灯；修=抽 `auth.ttl_for(role)` 顺带覆盖 |
| ⑧ | JWT 续约零机制 | 边界 | v1 正解=只做到期引导（401 detail 已带 `ExpiredSignatureError`）；**滑动过期是陷阱**（拆掉"短 TTL 压住无撤销"这条唯一对策），refresh 双票制=v2 |
| ⑨ | SSE 认证是**连接级一次性**，流内不重校验 exp | 边界 | 窗口由关流两判据收口在一次 run 时长内 |
| ⑫ | FAILED/PROCESSING 文档的已回填块**照常进检索** | **升** | **观测半 ✅**（M4.2，`80299de`/`5a17bf8`：`aegis_documents{status}` gauge+⑱ 状态端点——"运维看不见"已修）；**数据面半（检索 JOIN status）不改**：动 M3.5 冻结检索唯一入口换边角收益，v1 显式接受进 atlas 边界 |
| ⑬ | Celery 壳 `except Exception` 无差别重试**抵消** EmbeddingClient 的白名单 | **升** | M4.7：AuthError 被重试 6 轮 18 次注定失败；修=壳加 `except (AuthError, BadRequestError)` 直接 mark_failed |
| ⑭ | embedding 通道**只记账不受闸** | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：kb 上传挂租户同桶入站限流——烧穿速率被入站频次钳制（embedding 花销经拍板 F 计入 month_spend，月度闸门在 chat 侧仍兜总量）；"embedding 通道自带预算预检"不做=两道既有闸已覆盖风险面 |
| ⑮ | `_PROVIDER` 注释"各有各的账目"不精确（真分账维度是 tier） | 结案 | 纯注释，随手改；无行为面 |
| ⑯ | 切块产物非原文子串 + 无偏移列 → **引用溯源 v1 结构上不可能** | 边界 | 进 atlas；v2 需在切块期落 (start,end) 偏移 |
| ⑰ | 摄取链并发防护不成套且注释**放大**防护范围 | 边界 | v1 无可达并发路径（用户穷举确认）；处置=按 C30 先例显式冻结前提 + docstring 补前提声明 |
| ⑱ | 无 `GET /v1/kb/documents/{id}` | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：状态端点（status/chunk_count/消毒 error），staff 面口径与 events_view 同构；三种异常终态运维可见 |
| ⑲ | API 摄取入口无去重（同文两传=两套 chunks 稀释 top_k） | 边界 | v1 不修；对照=seed_demo 反有三分支幂等（两入口一幂等一不幂等，已声明） |
| ⑳ | CJK 范围 `一-鿿` 全仓三处内联无命名常量 | **升** | M4.7：tokens.py:15 / ingest.py:122 / rerank.py:24，"同一把尺"仅靠注释维系；修=core 导出常量一行 |
| ㉑ | `enable_indexscan=off` 后实际计划形态（bitmap vs seq）未 EXPLAIN 实测 | **升** | M5.2：精确扫成本量纲按租户行数还是全表未证，性能口径时顺手钉凭证 |
| ㉒ | **#42 实为半闭合**：`context.py:172` memory.fetch 裸 await 仍在 | **升** | 零代码：v1 恒 None 不可达，但 v2 实装若不知"fail-open 是 provider 义务"必复发；该义务只活在 RetrievalProvider docstring，`MemoryProviderLike` 定义处零提示 → §10.3 长期记忆升级路径补一句 |
| ㉓ | 三条通往 AGENT 的路只有第一条留痕 → **"分诊失败率"结构上不可观测** | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：`_parse_intent` 零/多词分支 warning（hits/len，不记原文）——三路条条有痕；结构化指标（计数器）待有真实流量再议 |
| ㉔ | `classify` docstring 承诺"解析 bug 也不该杀请求"，但 `_parse_intent` 在 try 外 | **升** | M4.7：今天不出事全靠它恰好是全函数=**未声明未测试的隐式前提**；对照组=guardrails 把解析放在被保护区内故是结构保证 |
| ㉕ | 恰一词判据把四词当等价代价（**handoff 误判有真副作用**且对否定语境盲） | 边界 | 概率极低 + 话术末句"您也可以继续补充说明"恰是缓冲；v1 不修 |
| ㉖ | **FAQ 直答通道的 system 只有 `faq_digest`** → 规则 3（禁编造）在直答路径不生效 | **升** | **✅ 已修（M4.4③，`69959ae`）**：FAQ_DIRECT_RULES 拼接 digest 之后（租户政策在前平台底线收尾）；开工实证直答**零 cassette 覆盖**——站 6"要付五盘重录费"的顾虑不成立，零重录费 |
| ㉗ | 租户侧 prompt（`tenants.config["faq"]`）不在"定了不动"纪律与 M4.3 重录门覆盖面内 | **升** | **✅ 已声明（M4.3④，`1126c1e`，README §8）**：核对实况="假绿"实为**零覆盖**（11 盘无 FAQ 直答盘）——落档为"重录门覆盖面=代码内 prompt 常量；租户侧 digest 无门看守，本门对 FAQ 直答质量**既不绿也不红**"；质量评测归 M4.4 与 ㉖ 同批裁决 |
| ㉘ | 直答失败回落时 POST 通道已推 token 不可撤回且**无 message_reset 分隔信号** | 边界 | 两通道投影分岔（GET 因"先答后写"零残留而干净）；M3.10"观察者不改变事实"哲学的一处例外 |
| ㉙ | `_claim_and_execute` 回放分支的 SELECT **不带租户过滤**（与 claim 的 INSERT 不对称） | **升** | M4.7（与 (54) 合并）：今天安全全靠"键是 uuid4 不可控"+"RLS 在场"两条外部条件；幂等键一旦改成业务可控值立刻变跨租户读台账 |
| ㉚ | mock 第二层防线取决于注入什么工厂（生产 app 引擎在场、测试全注入 owner 不在场） | — | **✅ 已修（M4.3②，`360078a`）**：test_rls M4.3 增量节——回放分支跨租撞键在 RLS 在场世界响亮 NoResultFound（不静默借用）+同租回放健康对照；"RLS 第二层由调用侧环境承担"docstring 首次有 CI 作证 |
| ㉛ | `app.state.tickets` 无界内存列表、无租户维度、只写不读 | 边界 | D9 已声明取舍；工单事实在事件流里（HANDOFF payload 含 ticket_id），mock 的 list 只是假下游收件箱 |
| ㉜ | `ticket_id=uuid4` 破 M4.3 逐事件比对 | — | **✅ 已声明（M4.3④，README §8）**：开工核对裁决**不加缝**——M4.3 实际断言形态是行为轨迹四键**非逐事件全等**，且现有 11 盘无任何 ticket 产生路径（无 handoff/兜底用例），无消费方的缝=注水；**触发条件落档**：录含 handoff/兜底盘或引入逐事件确定性断言前，先给 mock 加确定性 id 注入缝 |
| ㉝ | 跨 event loop 单例陷阱**三次现形、三种修法、零共性防线** | **升** | M4.7：判据=消费方有没有"你能塞参数进去"的时刻；最小机制形态=单例记录创建时 loop、不一致抛人话异常而非等 keep-alive 炸裸 RuntimeError |
| ㉞ | "mock 绝不挂主 app"是安全不变量但**只有 grep 能核、无 CI 证人** | — | **✅ 已修（M4.3②，`360078a`）**：tests/api/test_app_surface.py——用 **mock 自身路由集**对主 app 求零交集（APIRoute 滤框架路由），mock 新增端点断言面自动扩大，优于硬编码 `/refunds` |
| ㉟ | 归属校验到写请求之间的窗口，下游只兜状态不兜归属 | 边界 | **判据是窗口时长不是窗口是否存在**：普通调用毫秒级接受；HITL 可达 3600s 已由 M3.9 revalidate 覆盖 |
| ㊱ | 读侧 `raise_for_status()` 把协议错（400 类）与可重试故障（503）合流成同一种 ERROR | **升** | M4.7：与写侧 #43 的精细区分粒度相反；当前 mock 读端点只产 200/404/503 故不可达，真实化前必须复核 |
| ㊲ | 退款闸门缺省 fail-OPEN | — | **✅ 已修**（M4.0②，`29a3b8b`） |
| ㊳ | `ticket_create` 送出的幂等键被下游**静默丢弃**（`POST /tickets` 连 header 都不读） | **升** | M4.7（与 ㊽ 合并）："写工具一律带键"兑现率 2/3；修=`/tickets` 也走 `_claim_and_execute` |
| ㊴ | `entry_classifier` v1 从未开启，且**直答/直通两路连入口规则库都不在场** | **升** | **✅ 直答半已修（M4.4③，`69959ae`）**：FAQ 分支前置 check_input（纯规则库零 LLM），HIGH 回落 `_run_main`=审计闭环在 loop 侧、钱包面证据 gw.calls==1 有测试钉死；**HANDOFF 直通刻意不加**（无 LLM 调用面+可疑内容转人工恰是合理去向——理由落 service 注释）；entry_classifier 恒关是独立事实（表述纪律照旧） |
| ㊵ | docstring"配置错误启动炸"不符实：未知工具名是**每请求装配期** ValueError，无人接 → **500 空流** | **升** | M4.7：且发生在 `classify` 花完钱之后；真启动炸是 `@tool` import 期防呆 |
| ㊶ | `dict(tenant.config)` 只拷一层 + 无 CI 证人 | **升** | M4.7：钉子=一行 `is not` 断言 |
| ㊷ | 直答"先答后写"崩溃窗未登记（用户看到完整答案、事件流零记录、msgbuf 却有残影） | 边界 | 与"先答后写"的取舍成对（失败零残留 vs 崩溃窗） |
| ㊸ | 直答 LLM 流式**全程无会话锁**（锁只包 `_write_direct`）→ 并发窗内可被主 run 抢锁 | **升** | M4.7（与 ㊹ 合并）：用户看完答案却收 error 帧且答案不入事件流 |
| ㊹ | `_has_history` 判据读在锁外 | **升** | 并入 ㊸ 同批 |
| ㊺ | msgbuf **每 token 全量 SET**（字节量 O(N²)，1000 token≈50 万字节） | **升** | **移位 M5.2**（M4.2 收口拍板 5）：压测量化后再修（`aegis_chat_*` 直方图已能间接观测）；修=增量 APPEND 或按阈值批写 |
| ㊻ | **兜底路径②不 fail-safe**（预算类→500 空响应比不兜底信息量更少／循环类→error 帧／建单成功后崩→孤儿工单） | **升** | M4.7：`FALLBACK_LOOP_LIMIT` 自称"已生成工单"堵死"失败照发"修法；修向 (a) 加不承诺工单的话术+try ／ (c) `create_handoff` 走 `post_write`，两者正交 |
| ㊼ | **兜底轮话术互换**：用户唯一看到的那句不在任何可重放面，可重放面里那句从没到过用户 | **升** | **✅ 已声明（M4.3④，README §8）**：现有 11 盘无兜底用例撞不上；落档为"录兜底类 cassette 时 manifest 期望必须按**事件面**话术写，并知道它与用户所见不同"；话术互换本体的修复归 ㊻ 修向（M4.7）连带重审 |
| ㊽ | `create_handoff` 绕过 `post_write` 单点（无幂等键无 #43 分界） | **升** | M4.7（与 ㊳ 合并）：病根=契约被绑在"谁调用"而不是"这是一次外部写"上 |
| ㊾ | 帧译表只认 `assistant_message` → **tools 轮前置文本无事件**（"我帮您查一下"只在 `llm_result.text`） | **升** | **✅ 已声明（M4.3④，README §8）**：落档为"forbidden 扫描面=事件流语义域，前置文本不在场——若泄漏恰发生在该段本门不报警"；补前置文本入事件=事件协议扩展，非本步范围（v2 或 M4.7 前重审）。另 (73) 修复已消掉"user_message 两边都不译"那条差集 |
| ㊿ | `last_tool` 跨事件携带依赖"工具串行"**未声明前提** | 边界 | v1 串行是事实；并行工具一到两处译表同时错且无红灯（**帧协议比投影协议弱**——投影层靠 `tool_call_id` 不受影响） |
| (51) | 直答路 `OutputGuard` **三族里两族结构性空转**（片段集来自 `spec.system_prompt`，而该路实际 system 是 `faq_digest`） | **升** | 零代码（表述纪律）：真在岗只有 PII 族，对外表述须收窄；顺带核实演示语料 400 热线不匹配 `phone_cn` 不会误杀 |
| (52) | 终局替换只覆盖事件面**不覆盖 msgbuf** + msgbuf 定位从未论证 | 边界 | 站 11 已裁决：**写的时候当副本、读的时候当事实**；两个正解方向各有不可接受代价（降格→断线丢半句／升格→每 token 一次事件），v1 取中间态并接受后果 |
| (53) | revalidate 与 mock 拒绝面"逐字对齐"**无 CI 证人** | **升** | **✅ 已修（M4.3②，`360078a`）**：test_revalidate 对齐矩阵七例（同一订单事实两侧判定必须一致）——两刀刃=恰等上限（`>` 严格大于最易漂）与 **coupon-refunded-passes**（mock 不看状态，校验器不得更严=主守"批准后白拒无人兜"方向）；顺序纪律 revalidate 纯读先跑 |
| (54) | `_load_order` 是唯一无任何显式过滤的业务读（tenant 靠 RLS、user **结构上不可得**） | **升** | 并入 ㉙ 同批（"交叉核验退化成单层"第二例） |
| (55) | 直读 mock_orders 是 v1 形态前提，M4.7 真实化后三条理由全部反转 | 边界 | 前瞻边界，随 M4.7 复核 |
| (56) | **审批端点无入站限流**且最花钱（一次 POST 触发一次完整 Agent 续跑） | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：挂租户同桶 rate_limited，429 先于一切 handler 逻辑（超限探测不出单据存在性）；既有缓解（staff 凭证+CAS 恰一）叠加成三层 |
| (57) | 审批端点响应时长=整个 run，无流式无上界 | **升** | **✅ 措辞半已修（M4.4③，`69959ae`）**：零事件态 `resumed`→`no_op`（词即语义，零消费方断言）；**实测半边（断连后 run 是否跑完）移 M4.7**——ASGI 直调世界无真网络断连语义，归容器冒烟顺手；流式化改造不做（大改与评测无关，v2/M4.7 前评估） |
| (58) | **`with tenant_context` 与裸 set 不 reset 的配对纪律从未写下** | **升** | **✅ 已落档（M4.4③④）**：口径行进 §2.2（"tenant_context 配对纪律"——每个新出边界调用点必查上下文在场）；**M4.4④ 冒烟当场添第三例实锚**（judge 裸调用 42501）——口径行落档当天就被自己人踩中，防线价值自证 |
| (59) | 窗口三取回口径复制了 `_rebuild_working` 一份（runtime.py:581-583 vs :186） | 结案 | 重复但正确；抽取的耦合风险大于收益，留注释指认同源 |
| (60) | `lease.acquire`→`_pump_with_lease` 之间**无续租**，a+ 把这段拉长到含 precheck+工具执行+两次全事件扫描 | **升** | M4.7：`lease_ttl_s=60` 边际约 2× 且上界从未论证 |
| (61) | `sweep_once` **工作量无上界**（无 limit + 串行 + 每项一次完整 run）+ `SweepReport` 无 failed 计数 + `latest is None` 静默 continue | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：批上限 100+`ORDER BY id` 定序（无序 LIMIT=随机领批，余量可能挨饿）+触顶警告（silent cap 纪律）+failed 第四账+不可能态留痕；余量下轮 beat 自愈（每轮从状态重推的红利） |
| (62) | `register_resume_hook(resume_session)` **无 CI 证人**；一般化=worker 整条生产装配链在 CI 无证人 | — | **✅ 更正（M4.3② 核对，2026-08-03）**：注册面证人 `test_module_import_registers_real_hook` **早已存在**（tests/workers/test_hitl.py:150，M3.9④ 拍板Ⅰ收尾即有，断言 `reaper._resume_hook is hitl.resume_session`）——站 10"零证人"表述系**复盘免测试段盲区**（免测试段拍板让复盘对测试面的断言失准，流程教训）；"装配链逐件对应"的一般化本就归 (64)→M4.7 |
| (63) | `_task_runtime` finally 五个串行 await 无各自保护 | — | **✅ 已修**（M4.0②，`b7fc59f`） |
| (64) | `_task_runtime` 与 `create_app` 的"四件逐件对应"只是**人肉承诺**（机制上区分不了"有意不加"与"忘了加"） | **升** | M4.7：证据是 `msg_redis`（worker 无 `_TokenEmitter` 故不写 msgbuf → worker 驱动续跑期间重连收不到 `message_reset`）；**站 10 原举例 `text_sink` 已更正**（它是每请求物不是装配参数） |
| (65) | `text_sink` 穿透四路径，生产只有 `service.py:306` 一条带非 None sink（三处 resume 调用点全不传） | 边界 | resume 侧穿透生产空转、唯一证人是测试；与 (64) 同源 |
| (66) | **有通道模式下 tools 轮守卫命中零审计**（`_finish_text` 只在 text 分支调用，`guard.hit` 无人检查） | **升** | M4.7：不发 GUARDRAIL_TRIGGERED 不发 SAFE_REPLY、下轮换新实例即遗忘——"守卫命中必留审计"在 tools 轮不成立 |
| (67) | **断连不唤醒在途等待者**（`_run` finally 只置 `_conn=None` 不遍历 `_waiters`） | **升** | **移位 M4.7 前**（M4.2 收口拍板 5，与 (68) 合并）：改 notifier 守连循环风险中等、与 /metrics 无关——容器化前单独一笔做 |
| (68) | **无心跳、黑洞形态静默失聪** → 失效模式 25s 比设计好的降级模式 2s **慢 12.5× 且无日志** | **升** | **移位 M4.7 前**（与 (67) 合并）：修=守连循环加 `SELECT 1` 探针 |
| (69) | 单频道 `aegis_events` 全租户广播 | 边界 | v1 非泄漏（payload 仅路由键），代价在扩展性；分频道与"任意副本服务任意租户"冲突 |
| (70) | `poll_interval_s` **一个旋钮两用途**（降级节拍想调小 × 重连退避想调大，方向相反且从未分别论证） | 边界 | 站 5 口径⑵"能被单独拧的旋钮不该与别的旋钮有隐式耦合"同族潜伏；拆成两参数是 v2 |
| (71) | stream 端点 admin"平台级"被 RLS 拦成 404 | — | **✅ 已修**（M4.0②，`85c10b2`） |
| (72) | 两通道 `done.usage` **两口径**（POST=本 run／GET=after_seq 之后回放到的所有 llm_result） | **升** | **移位 M5.4 前**（M4.2 收口拍板 5）："指标口径撞上"经实装复核不成立——/metrics 用量来自账本不来自帧；真消费方是 demo 面，修=译表按 run_id 分段清零 |
| (73) | **`_translate` 不译 `user_message`** → 重放得到半边对话，且因 `resubscribe(true)` 先清面板，**在验收幕 D 标准路径上就会现形** | **升** | **✅ 已修（M4.3③，`ac09505`）**：stream 译表加 user_message 帧（带 seq 参与续传）+ChatFrame 词汇表扩条+chat.html 蓝气泡重建；**POST 侧刻意不发**（用户消息本地已有）——差集从"无人知道"升级为双 docstring 声明 |
| (74) | stream 首批回放**无上限**（`.all()` 全量）vs `events_view._MAX_EVENTS=1000` | **升** | **✅ 已修**（M4.2③，`5a17bf8`）：`_REPLAY_BATCH=500` **分批≠截断**（全量重放语义保持：批满续扫、终止判据与 message_reset 等排空——跨批终止不早退）；events_view 的截断是调试面语义，两种写法自此都是裁决过的 |
| (75) | **帧协议没有"消息边界"概念、`done` 在兼职** → 直答类不发 done，重放时多条直答连成一个气泡 | 边界 | v1 演示页可接受；真正的修法是引入 message_start/message_end 帧对=协议升级，归 v2 |
| (76) | **十注入参组合空间只验证两个角**，中间组合静默降级两实例 | **升** | M4.7（与 ⑤ 合并）：注入 runtime 不给 chat_service→`lock=None`；注入 runtime 不给 msg_redis→无 msgbuf（缺省赋值在 `if runtime is None` 分支内） |
| (77) | **真实断线不自动换轨**（`send()` catch 只留一行警告，只有演示按钮 `simulateDrop` 会 resubscribe） | **升** | **移位 M5.4**（M4.2 收口拍板 5）：演示打磨面（chat.html 客户端），与指标无关 |

**归位统计**：77 条中 **升级追踪 41 条**（含合并后实际工作项约 33 个）／**atlas 已知边界 17 条**／
**结案 2 条**（⑮ 纯注释、(59) 重复但正确）／**已归位他处 4 条**（㉚㉞(62)→#47；㉜→M4.3）／
**已修 3 条**（㊲(63)(71)，M4.0②）／**⑩⑪ 早已升 #46/#47**。
升级条目的里程碑分布：**M4.2 十一条**（可观测面集中）／**M4.3 六条**（回放门相关）／
**M4.4 三条**／**M4.7 十八条**（容器化与真实化前必须过的面）／**M5.2 一条**／**零代码两条**（㉒(51)）。

### 10.2 简历占位符回填清单（05 号文档的 X，全部凭证化）

| 占位符 | 产出于 | 凭证 | 状态 |
|---|---|---|---|
| 故障注入成功率 X% + P99 代价 X s | M1.13 | `reports/m1_fault_injection.txt`（100% / 2.42s，口径见 §5.2） | ✅ 待回填 |
| 档位路由降本 X% | M4.6 实验① | **✅ 已产出**（`reports/m4_cost_routing.txt`，2026-08-03）：**vs-strong 74.7%／vs-standard 18.9%**——双基线口径（防"基线选贵抬数字"）；80 条全唯一集（与评测集零交集 CI 钉死）、分布 30/40/20/10 声明性假设、缓存关闭、演示价目、B 组含 fast 分诊成本；数字可由 usage_ledger 复算（报告附 SQL+sid 清单）。M5.5 回填 05 | ✅ 待回填 |
| 精确缓存降本 X% | M4.6 实验② | **✅ 已产出**（`reports/m4_cost_cache.txt`，2026-08-03）：**21.9%**（30% 历史复述假设显式声明、seed=42 流量可精确重放；请求级全命中自检 60/60 与设计吻合；精确缓存上界口径=逐字节命中，语义缓存归 v2）。M5.5 回填 05 | ✅ 待回填 |
| 本地压测 P99 首 token X s | M5.2 口径① | 待产出 | ⬜ |
| 评测用例数 + 通过率基线 | M4.5 | **✅ 已产出**（`reports/eval_baseline_20260803.txt`）：**40 用例（三类 14/14/12）、稳定基线 38/40=95%**；口径=两条已知失败为强先验编造样本（okb-07 发票 90 天／iso-12 退款时效撞值）**如实保留不美化**——"95% 且能逐条说出那 5% 是什么"是比 100% 更硬的简历数字；judge 判分 spot-check ±1 一致率 100%（异族复评，`reports/m4_judge_spotcheck.txt`）。M5.5 回填 05 | ✅ 待回填 |
| 熔断恢复 X 秒闭合（04 M1 验收未尽项） | M5.4 | 待产出 | ⬜ |
| Qwen↔GLM 模型级容灾实测（qwen3.7-plus↔glm5.2；2026-07-16 前口径为 DeepSeek，已退役） | M5.4 | 待产出（无凭证则修改 05 简历表述） | ⬜ |

### 10.3 v1/v2 边界（防范围蔓延，动它之前先看这）

**01 §4 硬性非目标（v1/v2 均不做）**：多渠道接入（只做 Web+REST）、精美前端、模型训练/微调、
K8s 生产级部署（只写文档不实操）、通用 Agent 市场/低代码编排、多区域/异地容灾。

**规划期已裁剪进 v2**（04-roadmap 裁剪表，理由与替代方案见原文）：语义缓存（pgvector 方案已设计）、
A/B 灰度、坐席审批页（API+curl 替代，页面 stretch）、trace 查看页（JSON API 替代）、Ollama 本地档、
流式 tool-call 增量解析、坐席实时接管 WebSocket、独立部署模拟业务系统（永久简化为进程内子应用）。

v2 项的准备程度分三档，**表述不许拔高**（ADR-005"不假装已有"）：
- **接口已预留**：只读子 Agent（`AgentSpec.sub_agent_policy`，v1 恒 DISABLED——ADR-002）；
  长期记忆（`MemoryProviderLike` 槽位 + `memory_budget`，v1 恒 None——#20 拍板 2026-07-24；
  升级路径=评审 C24 方案(a)：`user_memories` 表 + 会话完成/handoff 时 fast 档提炼写入）；
  本人 PII 允许清单（`AgentSpec.owned_values` + OutputGuard C23 机制已由 M2.8 测试作证，
  v1 数据源恒空——users 表无 PII 列；升级路径=users 加列或会话级采集，M3.8 拍板Ⅳ 2026-07-25）；
- **模块边界已留**（换实现不动调用方）：cross-encoder 重排（`rerank.py` 内替换）、
  语义缓存（pgvector 方案含租户分区，ADR-005/006）；
- **仅文档声明、无任何预留**：Celery outbox 补投（v1 接受摄取暂停）、Redis 哨兵（单实例+文档说明）。

任何"顺手做了吧"的冲动 → 先在此表核对，非目标与 v2 项一律不做。

---

## 11. 风险与砍法（时间不够时，砍尾不砍头）

1. **最后砍 M1/M2**——网关 + 运行时是核心差异化，动它们等于放弃项目定位；
2. **可再砍**：coupons 工具（半天）、judge 校准缩为人工 spot-check、kill -9 演示并入 HITL 演示、
   长对话夹具 40 轮缩 30 轮；
3. **M3 RLS 集成若超时**：先保应用层隔离，RLS 移 M4（对抗用例照跑，兜底层后补）；
4. 每次砍完同步三处：本文档对应步骤标注、§10.2 简历清单（被砍项删除）、05 号文档简历模板。

---

## 12. 文档地图（哪个里程碑读哪些文档）

| 里程碑 | 必读 | 选读 |
|---|---|---|
| M2 | **03 全文**、02 §2/§3/§5、本文档 §6、**review-2026-07-07-m2-preflight.md §1/§2** | ADR-002/003（自研与单 Agent 论证）、ADR-005（锁语义） |
| M3 | 02 §3/§7/§9、ADR-005/006/007、01 §5、本文档 §7 | 03 §3/§4（槽位与工具契约回顾） |
| M4 | 04 M4 节、03 §7（回放契约）、本文档 §8 | 05（评测叙事） |
| M5 | 04 M5 节、**05 全文**、ADR-007（Nginx 坑）、本文档 §9 + §10.2 | 01 §6（成功标准终检） |

通用：每个新会话按 §0 清单执行（`CLAUDE.md` 会自动加载并指回本清单）；
**每个里程碑/步骤开工必读**：`docs\07-handoff-guide.md`（驾驶手册）+ `docs\08-code-map.md`
（接口事实源快照）+ 当前步骤的 `docs\plans\` 计划文件（消费规则 plans\README.md）；
面试准备期通读 05 + 全部 ADR。

---

## 13. 里程碑毕业清单（模板，6 项全部勾完才切会话；§2.1 第 7 条"核心四件"含于其中）

- [ ] **验收对账**：本文档该里程碑"毕业验收汇总"逐项点名核对（新增测试/文件 + pytest 收集数）；
- [ ] **报告落盘**：毕业实验/演示的原始凭证进 `reports/`；
- [ ] **CI 全绿 + tag 推送**（tag 名按 §3 总览表）；
- [ ] **记忆更新**：`aegis-agent-platform.md` 重写为新里程碑状态（含新教训）；
- [ ] **本文档更新**：里程碑标 ✅、登记实际交付与偏差、§10 横切清单状态翻转
  （**含** `docs\plans\` 对应计划文件头部的「实际落地偏差」回填与 `docs\08-code-map.md` 对应节更新——#36 维护纪律；
  **及 `docs\atlas.md` 对应节增量——#40 维护纪律，M2.13 建骨架起生效**）；
- [ ] 开新会话，从 §0 启动清单开始。
