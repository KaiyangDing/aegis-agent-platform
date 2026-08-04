# 08 · 代码地图与接口事实源快照（M2.4 基线）

> **写作基线**：M2.4 毕业，commit `014ec21`，**301 测试**全绿 · 撰写 2026-07-10（Fable 5 交接工程，00 §10.1 #36）。
> **实际落地偏差**：（各步毕业时按 §0 维护规则回填对应节，本行不删）

---

## §0 快照声明

### 0.1 基线三元组

| 项 | 值 | 核对命令（仓库根（本 repo）） |
|---|---|---|
| HEAD commit | ~~`014ec21`~~ ~~`c3eb8ce`~~ ~~`8bec868`~~ ~~`553fb20`~~ ~~`578b37f`~~ ~~`16e84bf`~~ ~~`3679e7f`（M2.11 收口）~~ ~~`98e2549`（M2 毕业，tag `m2-runtime`）~~ ~~`b0e438b`（复盘补丁三四五）~~ ~~`69b2e93`（M3.1）~~ ~~`993d1c4`（M3.4）~~ ~~`dac1f32`（M3.5）~~ ~~`e79734f`（M3.6）~~ ~~`95faef2`（M3.7③）~~ ~~`6865ba8`（M3.7）~~ ~~`2fed126`（M3.9⑤）~~ ~~`3dd5d03`（M3.10④）~~ ~~`5c1f5a1`（M3.11③）~~ ~~`8cc58ba`（M3.12②=M3 毕业提交，tag `m3-support`；M3.12 两提交 `ae3490e`/`8cc58ba`；基线外一笔 `75292f7`=用户 ruff format 补笔）~~ ~~`6d2c531`（M3 复盘补丁二；补丁一 `944e5ee`——两补丁产自复盘站 4，00 §7.3 末两行+§10.1 #48/#49）~~ ~~`b7fc59f`（M4.0②）~~ ~~`cdaa407`（M4.0③）~~ ~~`6805634`（M4.0 收口，2026-08-03；全程 13 笔见 00 §8.3）~~ ~~`b25c07b`（M4.1 收口，2026-08-03；四笔）~~ ~~`5a17bf8`（M4.2 代码面收口，2026-08-03；四笔+凭证 chore `70cc820`）~~ ~~`1126c1e`（M4.3 收口）~~ ~~`b9ccffb`（M4.4 收口，2026-08-03；六笔；迁移头 `b371c327f9ff` 评测双表 RLS 第十表）~~ ~~`f381048`（M4.5 收口，2026-08-03；四笔=`6a4a1c2`①/`53d79c8`②/`bdc55cc`③/`f381048` spot-check 凭证）~~ ~~`934e8fc`（M4.6 收口，四笔）~~ **`9aff73e`**（**M4.7 代码面收口**，2026-08-03；七笔=`4a06503`A/`72d4eb0`B/`ac872cc`C/`a20033e`+`0f86b23`D/`7a0392d`E/`9aff73e`F前置，另 M4.7-F 收口笔 `a9e36e7` 与 M4.8 毕业笔（含本注记）随后；M4.6 起提交推送亦 AI 代跑=00 §2.1 例外扩展；**tag `m4-governance` 打于 M4.8 毕业笔**；M3.1 起增量见 §0-bis） | `git log --oneline -1` |
| 测试收集数 | ~~301~~ ~~329~~ ~~365~~ ~~401~~ ~~459~~ ~~495~~ ~~531~~ ~~539~~ ~~548~~ ~~553（复盘补丁三四五）~~ ~~588（M3.1）~~ ~~600（M3.2）~~ ~~608（M3.3）~~ ~~655（M3.4）~~ ~~681（M3.5：+12 rerank/+14 retrieval 含适配器 5；test_usage 随机租户化零增）~~ ~~696（M3.6：+15 test_intent——classify 12+answer_faq 3）~~ ~~732（M3.7：+8 mock 模型与 RLS 增量/+14 mock 子应用与 config/+14 工具契约与行为）~~ ~~792（M3.9）~~ ~~830（M3.10）~~ ~~845（M3.11）~~ ~~852（M3.12：+7 test_adversarial 四大对抗集中面）~~ ~~854（M3 复盘补丁一 +1 `test_delivery_is_at_least_once`／补丁二 +1 `test_enqueue_runs_off_event_loop_thread`）~~ **863**（M4.0②：+3 `test_recover_stale_claim`／+2 revalidate 拒因面／+1 退款闸门 fail-closed 缺省／+2 test_rls M4.0 增量节（admin 平台级 + user 跨租对照）／+1 `_task_runtime` 资源释放；另**修改既有 3 个**——拒因/缺省断言随行为改判）~~ ~~864（M4.0③ +1 `test_cross_tenant_session_id_collision_returns_404_not_500`）~~ ~~873（M4.0④a +9：`test_breaker_sticky.py` 5 + `test_cache_sticky.py` 4；M4.0 全程 854→873=+19，②9/③1/④a9 逐项点名见 00 §8.3）~~ ~~894（M4.1 全程 +21：①+17=tests/obs 两文件（masking 8/assembler 9）／②+3=test_events_view 重写 7（5 改造+2 新）+test_rls M4.1 增量 1／③+1=`test_order_derived_detail_carries_specifics`——另快照测试升 17 类、veto 面 4 文件断言升级零增减）~~ ~~918（M4.2 全程 +24：①+9 tests/obs/test_metrics.py／②+6 tests/api/test_metrics_endpoint.py／③+9=intent 1+kb 3+approvals 1+hitl 3+stream 1；修复 `ba372df` 零增减）~~ ~~945（M4.3 全程 +27：①+15 tests/replay／②+11=rls 3+surface 1+对齐矩阵 7／③+1 词汇参数化，另修改既有 5／④纯文档）~~ ~~955（M4.4 全程 +10：①+4=test_evaluation_store 3+test_rls M4.4 增量 1，七层 lint 随迁零增减／②+4=test_eval_runner（预算中止/硬断言跳 judge/回显名/坏 JSON error）／③+2=service HIGH 回落 1+approvals no_op 1，另修改既有 1=answer_faq request_shape 改判／④+0 真实批次凭证）~~ ~~958（M4.5 全程 +3：①+2=test_seed_cases 八层 lint／③+1=绊线召回器归位；②+0 纯数据与重录）~~ ~~965（M4.6 +7=test_cost_traffic 七测）~~ **989**（M4.7 +24：A+3 notify（假连接注入）/B+8 底座组/C+8 服务层组/F+5 loopcheck） | `uv run pytest --collect-only -q` 末行 `989 tests collected` |

**CI 门数（M4.0③ 起 9→12）**：checkout（`fetch-depth: 0`）→ **gitleaks**（全历史密钥扫描，配置 `.gitleaks.toml`）→ setup-uv → `uv sync --frozen` → **`uv run pip-audit`** → ruff format --check → ruff check → mypy → lint-imports → `alembic upgrade head` → **`uv run alembic check`** → pytest。三道新门均为阻断式（无 `continue-on-error`）；红绿有效性验证挂 M4.0④。
| 快照日期 | ~~2026-07-10~~ ~~2026-07-11~~ ~~2026-07-17（M2 毕业）~~ ~~2026-07-24（M3.0 走查 + M3.1–M3.4 收口）~~ ~~2026-07-25（M3.5–M3.8 收口）~~ ~~2026-07-26（M3.9/M3.10 收口）~~ ~~2026-07-27（M3.11 收口）~~ 2026-07-28（**M3 毕业**） | — |
| 既有 tag | `m0-foundation`、`m1-gateway`、`m2-runtime`、`m3-support`、**`m4-governance`（M4.8）** | `git tag` |

### 0.2 本文是什么、不是什么

- **是**：M2.4 时点全仓**接口事实源的操作快照**——每个签名/常量/表列/测试数都经 Read 源码核实，标注 `文件:行号`。接续模型在引用任何既有接口前，先查本文对应节，再 Read 源码复核（信任序：**真实代码 > 00 §2.2 > plans 计划 > 本文 > 02/03/04 叙述**——本文是快照，代码先动一步就旧一步）。
- **不是**：教学复盘。`retro-m2.md`（00 §10.1 #35，M2 毕业后另写）承担"为什么这样设计、一次 run 的旅程、面试连环炮"的叙事——两者**不互相替代**：本文答"接口长什么样"，retro 答"为什么长这样"。

### 0.3 维护规则（当班模型职责，00 §13 毕业清单第 5 项）

1. **每步毕业时**更新本文对应节，并在**节首**加一行「**更新于 M2.x**（commit `xxx`）」；
2. 发现整节已与代码脱节：先在节首标 **⚠️STALE（发现于 M2.x）**，再修——不许静默改写；
3. 只增改不删：被替换的旧事实用 ~~删除线~~ 保留一版；
4. 各步预计触碰的节（更新时逐节核对）：

| 步 | 预计更新节 |
|---|---|
| M2.5 ContextBuilder | §1、§5（新增 context.py 节）、§7、§8（槽位#2 部分接电/#11 部分：summary_updated） |
| M2.6 FakeGateway/cassette | §1、§5、§7、§8（#7 接电） |
| M2.7 AgentLoop | §1、§5（loop.py + 接线实况）、§7、§8（#1/#3/#10/#13 接电，#11 部分：llm 双事件/assistant_message/loop_terminated） |
| M2.8 Guardrails | §1、§5、§7 |
| M2.9 HITL + core/locks.py | §1、§3（locks 节）、§5、§7、§8（#5/#6 接电） |
| M2.10 恢复调度 + workers | §1、§6（若加列）、§7、§8（#8 租约列群/#9 recovery_count·failed 接电）、§9（workers/Celery） |
| M2.11–M2.13 | §7、§9（reports 凭证） |

> 注：§8 挂点归属以其「谁来接电」列为准，本表仅作更新提示——毕业核对时务必通读 §8 全表，不止勾本行列出的编号。

---

## §0-bis M3 增量接口速览（M3.1 建，M3.12 毕业整编收束）

> 形态说明（**M3.12 拍板轻量案**）：快照面三处已实拆更新（§1 文件地图/§6.1-bis+6.8 迁移与六表/§9.1-bis 脚本），
> 接口签名增量以本节为**常驻档案**不再拆入 §3/§4/§5——08 是导航快照、硬规则 8 恒 Read 源码兜底，
> 全量拆入的漂移风险大于收益（原"M3.12 拆入各章"承诺按拍板修订，2026-07-28）。

**新表两张**（迁移 `6304edbb4760`，down_revision=`74da3bf5d6ab`；均无 FK——P4）：
`tenants`（id String64 PK / name String128 / config JSONB NOT NULL / token_budget_monthly BigInteger / created_at·updated_at tz now()）；
`users`（id String64 PK / tenant_id String64 idx / role String16 / display_name String128 default "" ORM 层 / created_at）。

**`aegis/core/tenancy.py`（113 行，M3.1①）**：
`Role(StrEnum)`=user/operator/admin；`TenantRecord`/`UserRecord` ORM；本层副本别名 `SessionFactory = Callable[[], AsyncSession]`（tenancy.py:24——core 不向上 import runtime 同名别名，分层代价）；
`TenantDirectory(factory, *, cache_ttl_s=60.0, clock=time.monotonic)`——`get_tenant(id)->TenantRecord|None` / `get_user(id)->UserRecord|None` / `monthly_budget(tenant_id)->int`（未知租户 0=闸门关闭）；**只缓存命中不缓存 miss**、clock 可注入。

**`aegis/api/`（M3.1②④，顶层新包，与 workers 同层互不 import——pyproject 层契约五层化 `"aegis.api | aegis.workers"`）**：
`main.create_app(settings: Settings|None = None, session_factory: SessionFactory|None = None) -> FastAPI`（工厂；app.state 挂 settings/session_factory；含 `/healthz`；uvicorn `--factory` 启动）；
`auth.py`——`Principal(user_id, tenant_id, role)` frozen；`issue_token(*, user_id, tenant_id, role, ttl_s, secret, now=…)`；`decode_token(token, *, secret, previous="") -> Principal`（HS256 锁死+require [exp,sub,tid,role]+双密钥窗仅签名不符试 previous）；`InvalidToken`→依赖层 401、空钥/弱钥(<32B RFC 7518)→ValueError fail-loud；`current_principal(request)` FastAPI 依赖（读 app.state.settings）；`require_roles(*roles)` 依赖工厂（矩阵执行器，403）；
`usage.py`——`GET /v1/usage?tenant_id=&limit=`（operator 锁本租户点名他租 403/admin 平台级；明细+模型/天/会话聚合，裸 SQL 四常量；金额 Decimal→JSON 精确小数字符串——pydantic v2 缺省）。

**`aegis/gateway/` 受控缝（M3.1③）**：`LLMGateway.__init__` +`monthly_budget_resolver: Callable[[str], Awaitable[int]] | None = None`（router.py:169）；`_resolve_monthly_budget(tenant_id) -> int|None` 三态（resolver 值/静态/None=读挂 fail-open——router.py:192-200）；闸门段 router.py:235-248（budget≤0 不查账本）；factory.py:47 注入 `TenantDirectory(get_session_factory()).monthly_budget`。

**Settings 新字段四枚**（config.py，恢复调度段后）：`jwt_secret`/`jwt_secret_previous`（SecretStr）/`jwt_user_ttl_s=7200`/`jwt_staff_ttl_s=28800`。

**scripts 新增两枚**：`seed_demo.py`（种子即初始化入口 #21：2 租户（a 含 approval_threshold=200、预算各 2_000_000）+8 用户 upsert 幂等）；`mint_token.py <user_id>`（P7 发放口：查库定角色、TTL 按角色档）。

**测试新增四处**（+35=8/16/4/7）：`tests/test_tenancy.py`、`tests/api/test_auth.py`、`tests/gateway/test_router.py` 末尾 resolver 组、`tests/api/test_usage.py`。

**M3.2 增量（更新于 M3.2，commit `d2bd55d`）**：
`aegis/api/ratelimit.py`——`InboundLimiterLike` Protocol（try_take 形状）+ `rate_limited(role_dep)` 依赖工厂（租户维度入站限流，即问即答 429+Retry-After=Lua 桶真实等待提示；**本文件刻意无 future-annotations**——闭包 Depends×字符串注解=参数退化 query 的框架陷阱，头注+题 108）；
`aegis/api/chat.py`——`POST /v1/chat` 入站前半：`ChatRequest(session_id/message/cancel_pending_approval)`、`PLACEHOLDER_SPEC`（M3.8 换）、`_ADMITTED=rate_limited(require_roles(USER, ADMIN))`（矩阵 operator 列"—"=403）、`_ensure_session` 首见建行+归属 404（#19 实装）、`_drain` except 阶梯（SessionLockHeld→409 / 事实源三类裸穿 / 裸 RuntimeError=T1 竞态→409——**顺序即语义**）、`_summary` 占位 JSON（挂起判据=loop_terminated 缺席）；取消链=ApprovalStore.cancel CAS→`resume(spec, sid, approval_id)` 拒绝族路径；
`main.create_app` 扩至五注入参（+runtime/limiter/agent_spec；生产缺省 `AgentRuntime(build_gateway(), factory, lock=build_session_lock())`——M2.9"生产必须显式传锁"的接线现场）；Settings +`inbound_rate=2.0`/`inbound_burst=5.0`；测试 +12=`tests/api/test_admission.py`。

**M3.3 增量（更新于 M3.3，commit `d73e098`）**：
`aegis/core/tenant_ctx.py`——`current_tenant_id: ContextVar[str | None]`（每任务独立副本）/ `tenant_context(tid)` set-reset 成对（可嵌套覆盖）/ `install_tenant_guard(engine)`（"begin" 事件 `text("SELECT set_config('app.tenant_id', :tid, true)")` 具名绑定——**伪码 %s 在 asyncpg 是语法错**；true=事务级不残留，探针实证）；
`aegis/core/db.py` **双轨**——get_engine/get_session_factory=aegis_app+钩子（读新字段 `database_url_app`）；+`get_owner_engine()/get_owner_session_factory()`（owner、无钩子——维护面 D4：reaper/种子/发凭证/对账；reaper 自建引擎读 database_url 本就 owner）；
迁移 `c895f9007bf7`（**手写**）：角色 `aegis_app` 幂等（集群级、downgrade 保留）/ GRANT DML+SEQUENCES+ALTER DEFAULT PRIVILEGES（未来表自动带 DML 授权；**RLS 不隐式继承**——M3.4/M3.7 新表迁移自补）/ 五表（tenants·users·sessions·approvals·usage_ledger）ENABLE RLS+`tenant_isolation` 策略（USING+WITH CHECK 双子句，text 比较无 ::uuid）；
接线：auth.current_principal 验签即 `current_tenant_id.set(...)`（任务级生灭免 reset）；usage.get_usage 查询段包 `tenant_context(target)`（admin 跨租户视图前提）；seed_demo/mint_token 切 owner 工厂；测试 +8=`tests/test_rls.py` 六测（真提交独立引擎/前置自检/过滤式清理）+ auth /ctx 一测 + usage 录音工厂一测。

**M3.4 增量（更新于 M3.4 收口，commit `993d1c4`；四提交 `55ea421`/`f8fa77e`/`6e5f769`/`993d1c4`，迁移 `7fe5de25a9ca`+`c28efda87e6a`——两迁移均自带 ENABLE RLS+tenant_isolation 双子句（前置义务））**：
**新表两张+一列**：`documents`（id S64 PK 应用侧 uuid / tenant_id idx / source S256 / status S16=IngestStatus / error Text NULL / chunk_count int ORM default 0 / meta JSONB / created·updated tz / **text Text server_default=''——(23) 原文居所，wire 只带 id**）；`chunks`（id BigInt PK / document_id idx 无 FK / **tenant_id 冗余 idx** / seq int / text / **embedding vector(1024) NULL=续传谓词** / embedding_model S64 NULL / meta / created；`uq_chunks_document_seq`；HNSW 手写 `ix_chunks_embedding_hnsw`(vector_cosine_ops)）。
**`aegis/apps/support/rag/`**：models.py（`EMBEDDING_DIMS=1024` 单一事实源+跨层钉子测试 / IngestStatus 四态 StrEnum / 两 Record）；ingest.py（`INGEST_TASK_NAME="aegis.ingest_document"` wire 常量（决策 A：apps=api|workers 唯一共同下层）/ `split_text(text, *, target_tokens=400, overlap_tokens=50)` 三级降级：段落聚合→句界→硬切窗，overlap 种子装不下即丢——"绝不产出超预算块"由回归测试钉死）。
**`aegis/gateway/embeddings.py`（D5 受控缝第二处，162 行）**：`EMBED_BATCH_SIZE=10`；`EmbeddingMeterLike` Protocol；`EmbeddingClient(*, base_url, api_key, meter=None, limiter=None, client=None, model="text-embedding-v4", dimensions=1024).embed(texts, *, tenant_id) -> list[list[float]]`（str 防呆/空 key AuthError/切批串行/按 index 归位/条数·维度·槽位三重校验 fail-loud/RETRYABLE_ERRORS+compute_backoff 复用 resilience 同一把尺/httpx 异常三段翻译/计量 fail-open）；`metering.record_embedding(*, tenant_id, request_id, model, prompt_tokens, session_id=None)`（tier="embedding" 自由串、cached=False→**计入 month_spend=拍板 F**）；`factory._price_table` + `build_embedding_client(session_factory=None, client=None)`（**双参数化=Celery 跨 event loop 防炸**；RLS 前提：调用方须在 tenant_context 内）；Settings.model_prices +"text-embedding-v4" 演示价。
**`aegis/workers/ingest.py`（200 行）**：`EmbedderLike` Protocol / `IngestReport` / `ingest_once(factory, embedder, *, document_id, tenant_id, batch_size=EMBED_BATCH_SIZE, embedding_model=…)`（四步：PROCESSING→切块幂等（count==0 才切+IntegrityError 兜并发）→IS NULL ORDER BY seq LIMIT batch 每批独立事务回填→DONE+chunk_count+error=None）/ `mark_failed` / `@celery_app.task(name=INGEST_TASK_NAME, bind=True, max_retries=5)` 薄同步壳（任务局部 NullPool `database_url_app` 引擎+guard、任务局部 AsyncClient、tenant_context 包全程——**#18 闭合三件套**；FAILED=消毒死因落列）；celery include=[ingest, reaper]。
**`aegis/api/kb.py`（84 行）**：`KbDocumentIn(source 1–256, text ≤200_000)` / `build_enqueue(settings)`（只发不收 producer，send_task 按名投递）/ `POST /v1/kb/documents`（operator+，202 {document_id,status}，先落库后投递，enqueue 失败 503 行留 PENDING）；`main.create_app` 第六注入参 `enqueue`。
测试 +47：tests/apps/test_rag_models 5 + test_rls M3.4 增量节 6 / tests/gateway/test_embeddings 14 / tests/apps/test_ingest_split 7 + tests/workers/test_ingest_resume 8 / tests/api/test_kb 7。真实链路凭证（2026-07-24）：documents=done(1 块)+账本 embedding 行 28 token/¥0.000014。

**M3.5 增量（更新于 M3.5 收口，commit `dac1f32`；七提交 `c615482`/`a7a3ba6`/`9ff6e52`/`0579055`+`43e3bfd`/`c4f0829`/`dac1f32`）**：
**`aegis/apps/support/rag/rerank.py`（82 行，零 aegis import）**——`RetrievedChunk(chunk_id/document_id/text/similarity/score=0.0/meta)`（frozen slots；**住 rerank 侧**：调用方向 retrieve→rerank 单向、共享类型居依赖下游）；`keyword_coverage(query, text)->float∈[0,1]`（CJK 相邻二元组（孤字自成单元）+`[0-9A-Za-z]+` 段小写归一、子串包含判据、零分词——CJK 范围镜像 tokens.py:15 同一把尺；空单元返 0.0）；`rerank(query, hits)->list`（score=0.7×similarity+0.3×coverage；不截断不过滤；sorted 稳定同分保输入序；meta 规则位注释挂点；权重刻意不进 Settings=算法内参）。
**`aegis/apps/support/rag/retrieve.py`（169 行）**——`RETRIEVAL_SCORE_THRESHOLD=0.35`（④真实校准维持，分离窗 [0.31,0.45]）/`EXACT_SCAN_MAX_CHUNKS=10_000`/`Retriever(factory, embedder, *, top_k=5, threshold=…, exact_scan_max_chunks=…, clock=time.monotonic)`（后两参=测试注入缝，偏差(31)）；`.search(tenant_id, query)` 六步：embed 事务外→租户计数 60s 进程缓存→`SET LOCAL enable_indexscan=off`（≤上限）或 `hnsw.iterative_scan=relaxed_order` 与查询**同事务**→裸 SQL `1-(embedding<=>CAST(:qvec AS vector))`（WHERE tenant_id 显式+IS NOT NULL，LIMIT 3×top_k）→rerank 取 top_k→all()<阈值返 `[]`；**fail-loud 且不自设租户上下文**（身份由边界建立——偏差(32) 用户评审撤修实录）；`EmbedderLike` 本层 Protocol 副本（apps 不向上 import workers）；**`RetrievalProvider(retriever)`**——`.search(*, tenant_id, query)->Sequence[ScoredSnippet]`（**#7 接电/#42 修案 (a)**：形状适配不裁剪（装填归 builder）、`wrap_untrusted(source="retrieval")` 注入面包裹（X4）、`except Exception`→`()` fail-open+warning 留痕（C34 镜像、不记 query 原文））。检索唯一入口：全仓 `<=>` 查询仅 `_SEARCH_SQL` 一处（余 4 处注释）。
横切两枚：pyproject `[tool.ruff.lint.isort] known-first-party=["aegis"]`（偏差(22)闭合——I001 分类不再依赖模块在盘与 .ruff_cache）；scripts +`calibrate_retrieval_threshold.py`（真实校准探针，README 索引已登记 calibrate_ 新前缀族；§9.1 随 M3.12 整编）。测试 +26=tests/apps/test_rerank.py 12 + test_retrieval.py 14（Retriever 9+适配器 5）；tests/api/test_usage.py 随机租户重绑定（M3.4 真实残留免疫，零增）。实证注记：pgvector 存储 float32（similarity 读回 ~1e-8 噪音，断言一律 approx）。

**M3.6 增量（更新于 M3.6 收口，commit `e79734f`；两提交 `d2475f9`/`e79734f`）**：
**`aegis/apps/support/intent.py`（138 行）**——`Intent(StrEnum)` 五值 faq/rag/tool/handoff/agent（**AGENT=fail-open 落点，刻意不在 prompt 词表**）；`INTENT_PROMPT`（四类判据一类一行；"定了不动"纪律——M3.11 cassette 录制语义，与 _CLASSIFY_PROMPT/_SUMMARIZE_PROMPT 同款）；`_parse_intent(raw)->Intent`（strip+lower 子串扫描、恰一词才归位、零/多词→AGENT=救格式不洗歧义）；`classify(gateway, text, *, tenant_id, session_id, deadline_s=10.0)->Intent`（fast 档单次、绝不重试；`except Exception`→AGENT+warning 留痕不记原文——微决策Ⅰ，C34 样板对齐）；`answer_faq(gateway, question, *, tenant_id, session_id, faq_digest, deadline_s=10.0)->AsyncIterator[str]`（system=faq_digest 原文=prompt 政策归租户配置；只产 TextDelta；**异常裸传播**——直答是主路径非增强层，处置归 M3.8/M3.10）。`GatewayLike` 直接从 runtime.runtime 消费（apps 居上层，无需 Protocol 副本）；分支接线归 M3.8/M3.10；缓存隔离零代码（cache._key 租户前缀既有）。
scripts +`measure_intent_latency.py`（62 行，**measure_ 新前缀族=轻量延迟实测**；首测 2026-07-25：新鲜 2357/976/901/947 ms（首条含连接建立）、缓存命中 8 ms、分类 4/4；M3.12 复测同口径、M5.2 口径②同族；§9.1 随 M3.12 整编）+ README 索引行。测试 +15=tests/apps/test_intent.py。

**M3.7 增量（更新于 M3.7 收口；四提交 `974b0be`/`3df3cc3`/`95faef2`/+④chore，迁移 `f4b8d2a97c31`）**：
**新表两张**（迁移自带 ENABLE RLS+tenant_isolation 双子句）：`mock_orders`（id S64 PK/tenant_id idx/user_id idx/status S16=MockOrderStatus 四态 paid·shipped·delivered·refunded/paid_amount Numeric(12,2)/items JSONB/created tz）；`mock_write_ops`（**idempotency_key S64 PK**/kind S16 refund·coupon/tenant_id idx/payload JSONB=结果快照/created tz）。
**`aegis/apps/support/mock_backend/`**：models.py（两 Record+MockOrderStatus）；app.py（`create_mock_api(settings=None, session_factory=None) -> FastAPI`——四端点：GET `/orders/{id}?tenant_id`（返行含 user_id，归属判定权在工具）/GET `/logistics/{id}`（`_TRACKS` 状态确定性派生）/POST `/tickets`（app.state.tickets 内存台账、ticket_id=uuid4）/POST `/refunds`·`/coupons`（`_claim_and_execute` **单事务去重**：ON CONFLICT DO NOTHING+`_rowcount`（store.py:193 同款 cast）→撞键回放 payload+duplicate:true / 首键 execute+回填；Idempotency-Key 头缺失 400；409=业务拒绝）；故障注入中间件（mock_latency_ms 先睡/mock_error_rate 概率 503））；client.py（`mock_client() -> httpx.AsyncClient` ASGITransport 懒单例——**测试勿用**，monkeypatch `client._client`）。
**`aegis/apps/support/tools/`（七文件）**：_shared.py（`DENIED_TEXT`="订单不存在或无权操作"/`fetch_owned_order(ctx, order_id) -> dict|None`（404 或 tenant+user 双比对不过=None）/`post_write(path, *, json_body, idempotency_key)`——**#43**：ConnectError/ConnectTimeout 原样上抛、余 HTTPError→TimeoutError 交 X1）；`order_query(ctx, order_id)` READ / `logistics_query(ctx, order_id)` READ / `ticket_create(ctx, title, detail="")` WRITE+risk_exempt / `refund_apply(ctx, order_id, amount: float)` WRITE+`refund_needs_approval`（>approval_threshold 缺省 200）/ `coupon_grant(ctx, order_id, amount: float)` WRITE+`coupon_needs_approval`（>coupon_threshold 缺省 0）。工具 docstring=模型说明书（机制注释一律 #）；amount float 进门即 `Decimal(str())`；409 回 dict 不进连败账。
Settings +`mock_latency_ms`/`mock_error_rate`+`_no_mock_injection_in_prod` 校验器；scripts +`demo_tools_acceptance.py`（三幕实录：Agent completed 序列 [order_query,refund_apply]/双击 duplicate false→true/越权统一话术）。测试 +36=test_mock_models 4+test_rls M3.7 节 4 / test_mock_backend 13+test_config 1 / test_tools_contract 5+test_tools_ownership 9。

**M3.8 增量（更新于 M3.8 收口；提交 `988cf20`/`539e160`/`0793b48`/+③与 fix 两笔（哈希 M3.9 开工核补））**：
**L2 受控缝（拍板Ⅱ）**：`AgentRuntime.__init__` +`retrieval: RetrievalProviderLike | None = None`（默认 None=原行为；_assemble 传 ContextBuilder——context.py:138 的缝抬到门面）。
**`aegis/apps/support/`**：prompts.py（`SYSTEM_PROMPT_TEMPLATE` 四规则（规则3=宁可说不知道静态化、规则4=审批拒绝如实转达）/`FALLBACK_LOOP_LIMIT`/`HANDOFF_REPLY_TEMPLATE`——M3.11 录制起定了不动）；agent.py（`ALL_TOOLS: dict[str, ToolDef]` 五工具货架/`build_agent_spec(tenant, *, owned_values=()) -> AgentSpec`：config["tools"] 白名单点名未知名 ValueError・dict.fromkeys 去重保序・session_token_budget 与 approval_ttl_s 注入（缺省读 LoopPolicy()）・ContextConfig(memory_budget=0)・entry_classifier 按 config・tenant_config 原样透传）；handoff.py（`create_handoff(*, factory, session_id, tenant_id, user_id, reason) -> {ticket_id, reason, summary}`——摘要三档 sessions.summary→末三 messages→"（无历史消息）"；不写事件=单写者纪律）；service.py（`ChatFrame(kind, data)` 帧词汇 token/tool_status/approval_pending/handoff/done；`ChatService(*, gateway, factory, directory, runtime, lock=None)`：`handle(*, tenant_id, user_id, session_id, message) -> AsyncIterator[ChatFrame]`——分类一次→**FAQ 直答守卫**（无历史（messages 计数）∧有 faq 摘要；先答后写 D7；失败回落主 Agent）/HANDOFF 直通三事件/主分支译帧+兜底② FALLBACK 替换出帧；`build_spec(tenant_id)`；租户缺行合成空配置留痕）。
**api**：chat.py 收敛 service（PLACEHOLDER_SPEC 退役、`_collect` 阶梯泛化、取消路径 spec=service.build_spec）；main.py `create_app(settings, session_factory, runtime, limiter, enqueue, gateway, chat_service)` **七注入参**（生产缺省链含 `RetrievalProvider(Retriever(factory, build_embedding_client()))`=#7 收尾；注入 runtime 不给 gateway=chat 端点响亮拒绝、kb/usage 形态合法）。
seed_demo config +tools/faq 两键（M3.8③ 前移；coupon_threshold/订单/语料留 M3.11）；scripts +`demo_chat_acceptance.py`（三幕：A 全链退款直执/B **FAQ 守卫实证**/C 工具面；幕 C 首跑 FAIL 实录=RLS 拦无身份配置读+TTL 缓存残影两课）。测试 +22=test_agent_assembly 11+test_intent 1 / test_service 7+test_handoff 3；test_admission._make_app +gateway 接线。

**M3.9 增量（更新于 M3.9 收口，commit `2fed126`；五提交 `aee4abb`/`6e47fb0`/`5b77bcf`/`a0689af`/`2fed126`）**：
**`aegis/apps/support/revalidate.py`（#8 实装，~110 行）**——`Revalidator = Callable[[SessionFactory, Mapping[str, Any]], Awaitable[str | None]]`；`REVALIDATORS` 恰两枚（refund_apply：订单在场/未退款/金额≤paid_amount；coupon_grant：在场/面额合法——**拒绝面与 mock 执行器逐字对齐**，校验器不比下游更严）；`build_precheck(factory) -> PrecheckHook`（**无身份闭包**——PrecheckHook=(tool_name,args) 冻结面，归属重校验由批准执行期 handler `fetch_owned_order` 以真实 ctx 兑现；未登记工具 fail-closed 拒绝+warning；DB 直读 mock_orders=躲故障注入误伤与 mock_client 单例跨 loop，RLS 场内限租、本层不自设上下文）；create_app 生产 runtime +`precheck=build_precheck(factory)` 接线。
**`aegis/api/approvals.py`（~130 行）**——`POST /v1/approvals/{approval_id}`（body `ApprovalDecision(decision: Literal["approve","reject"])`）：授权序 401→403 角色（OPERATOR/ADMIN）→404（owner 查读 `_load_approval`）→**403 跨租**（operator 且租户不符=对抗④；admin 平台级放行）→`tenant_context(approval.tenant_id)` 内 decide CAS（False→409"已失效或已处理"，过期单留 pending 归 sweep）→`service.build_spec`→**同步消费** `runtime.resume(spec, session_id, approval_id)`（`_drain` 阶梯=chat._collect 同义）→`_summary` 三形态（done/awaiting_approval 带 next_approval_id/resumed 空账）；`create_app` **第八注入参** `approvals_lookup: SessionFactory|None`（缺省 `get_owner_session_factory()`——RLS 下 403/404 判定需平台视角；判定后写与恢复走 app 工厂=冒充封闭名单第五处）。
**L2 #44 修复（runtime.py，~+70 行）**——`_find_unattached_approved(session_id)`（最新 approved∧event_id IS NULL，恰一张）+ `_recover_locked` **a+ 审批认领分诊支**（a 支之后、b/c/d 之前）：定位该单 approval_requested 事件→其后扫匹配 (tool_name, args) 的 tool_call——无（W1/W2）→decided 补写若缺+precheck（veto→模板 fill 不执行、单据保持未回填）+`execute(approved=True)`+attach ／ 有而无终局（W2.5）→`reexecute` 原幂等键+attach ／ 有且已配终局（W3）→按 `_rebuild_working` 同款口径取回落盘结果、只补 attach **绝不重执行**；一律 `_load_suspension` 按挂起 run 重建 fill 续跑（与 `_resume_locked` APPROVED 同构）；悬挂工具与认领单不匹配=响亮 RuntimeError。
**worker 跨 loop 受控缝**——`core/redis.py` +`new_redis_client()`／`providers/base.py` +`new_http_client()`（**配置源唯一化提取**，单例函数改调、行为零变化）；`factory.build_gateway(*, session_factory=None, redis=None, client=None)`／`locks.build_session_lock(*, redis=None, engine=None)`（缺省=现行为；providers 的 client 缝 M1 既有、首次从工厂面穿透）；`mock_backend/client.py` +`set_mock_client(client|None)` 安装缝（--pool=solo 串行前提；工具面 mock_client() 单点不改）；Settings +`approval_scan_interval_s: float = 60.0`。
**`aegis/workers/hitl.py`（新，~230 行）**——`KickHook=(session_id, approval_id)`／`SweepReport(expired/waiting/kicked)`／`sweep_once(factory, *, kick, now=None)`（`expire_due` 翻转+扫"**awaiting 会话×最新审批单已决**"逐单踢 `resume(approval_id)`——**不信翻转返回值、每轮从状态重推**=W0/取消/到期崩溃窗自愈；最新单 pending 不动=防误杀（旧单踢会经 T3 掐掉等新单的 run）；单单隔离 P6 同款）／`_tenant_of_session`（owner NullPool 读身份+租户行）／`_task_runtime`（任务局部五资源：app NullPool+guard、new_redis/http_client、任务局部 mock+set_mock_client——**与 create_app 生产链逐件对应**（gateway/lock/retrieval/precheck），finally 逆序归还）／`_resume_in_context`（tenant_context 内消费 resume=封闭名单"任务内胆"位）／`resume_session`（真 ResumeHook，薄：#44 在 L2）／`expire_approvals` beat 任务（薄同步壳）；**模块 import 时 `register_resume_hook(resume_session)`=拍板Ⅰ收尾**；celery include 三员+beat 两条；reaper.py ResumeHook docstring 修正（M3.8→M3.9 hitl）。
scripts +`demo_hitl.ps1`（六段真实链路；**UTF-8 with BOM**——PS 5.1 对无 BOM 源文件按 ANSI 代码页解析，偏差(50)）+`demo_hitl_helper.py`（seed/mark-refunded/expire=时钟注入/sweep=直调生产任务体/status 四面取证）+README 两行。测试 +38=tests/apps/test_revalidate.py 12 / tests/api/test_approvals_api.py 11（basename 撞车 tests/runtime/test_approvals.py 改名——偏差(48)）/ tests/runtime/test_recover_approved_claim.py 6（**先红后绿**：未修代码 5 红实测）/ tests/workers/test_hitl.py 7+test_celery_app.py +2。真实链路凭证（2026-07-26 六段全 PASS）：批准执行 event_id 回填+订单 refunded+事件序与单测七事件尾同构／TOCTOU 否决 approved∧event_id=空／超时 sweep expired=1 kicked=1／撤回终止；四会话全归 idle。

**M3.10 增量（更新于 M3.10 收口，commit `3dd5d03`；四提交 `e75d30e`/`a5170d8`/`d1d2275`/`3dd5d03`，迁移 `d41be6a90c27`）**：
**L2 受控缝第三处（拍板Ⅱ）**——`TextSink = Callable[[str], Awaitable[None]]`（runtime.py，PrecheckHook 旁）；`run(spec, session_id, user_input, *, text_sink=None)`／`resume(spec, session_id, approval_id=None, *, text_sink=None)`（keyword-only additive；签名钉测试随契约演进为"位置前缀锁死+KEYWORD_ONLY 缺省 None"新钉——偏差51）；经 `_assemble`/`_run_locked`/`_resume_locked`/`_recover_locked` 穿透至 `AgentLoop(text_sink=…)`；loop.py：`_llm_step` sink 在场时自建 OutputGuard 逐帧 feed+`_push_text` 降级单点（sink 异常=本 run 停止推送）+`_finish_text` 双模式收尾（**事件流与 sink 在场与否无关**；两处通道-事件分岔显式接受：final_check 命中已推流不可撤回、StreamInterrupted 作废段通道见过）。
**`aegis/api/sse.py`**——`encode_frame(ChatFrame) -> str`（event:/data:/id: 三行+空行；data 单行 JSON ensure_ascii=False；id 仅 seq 在场）；帧类型=service.ChatFrame **+`seq: int | None = None`**（拍板Ⅲ 单一帧类型贯穿）。
**service.py 流式化**——`msgbuf_key(sid)`="aegis:msgbuf:{sid}"/`_MSGBUF_TTL_S=3600`；`ChatService(..., redis=None)` 第六构造参；`handle`=队列解耦（生产者 task 入 `_BACKGROUND` 强引用池；**消费者退出不取消生产者**、尾部 await 重抛异常=端点 peek 面）；`_TokenEmitter`（**先写 msgbuf 后入帧**顺序承诺/turn_text 记账 llm_call 清零）；`_run_main` 帧译表（tool running/ok/error、approval_pending、未流出话术押后 pending 终局裁决=FALLBACK 替换语义流式保持、usage 从 llm_result(ok) 累计=拍板Ⅴ）；`_faq_direct` 流式过 OutputGuard（拍板Ⅳ：命中截断+SAFE_REPLY+审计事件、先答后写保持）。
**chat.py SSE 化**——200 路一律 text/event-stream（M3.2 占位 JSON 退役）；`_short_stream`（取消/awaiting 短流）/`_relay`（流中异常译 error 帧）；主分支 **peek 首帧**（`anext`+原 except 阶梯=锁 409 契约保持）；`_SSE_HEADERS`（no-cache+X-Accel-Buffering: no）。
**GET 通道**——迁移 `d41be6a90c27`（AFTER INSERT ON events→pg_notify('aegis_events', session_id||':'||seq)）；`api/notify.py EventNotifier(sqlalchemy_url, *, poll_interval_s=2.0)`（start/stop/wait_for；独立 asyncpg 原生连接、建连-守连-重连后台任务；未启动/断连=wait_for 按轮询节拍返回——**测试 ASGITransport 不跑 lifespan=天然降级路径**）；`api/stream.py`（`GET /v1/sessions/{sid}/stream?after_seq=`：user 本人 404/operator 403/admin 平台；Last-Event-ID 双源取 max；`_translate` 与 service 同译表、每帧 id:=seq；message_reset=回放后活尾前；关流两判据；`_WAIT_TIMEOUT_S=25`）；`api/events_view.py`（`GET /v1/sessions/{sid}/events?after_seq&limit`：operator 限本租 403/admin 平台/user 403；会话定位复用 approvals_lookup 平台查读缝；审计=logger.info 一行；`_MAX_EVENTS=1000`；M4.1 底座）。
**main.py**——**十注入参**（+`notifier`/+`msg_redis`）；lifespan 启停 EventNotifier；`_CHAT_PAGE` Path 锚定+`GET /chat` FileResponse；`aegis/web/chat.html`（单文件原生 JS：**双通道 fetch 手写 SSE 解析**——EventSource 无法带 Authorization、凭证不进 URL 底线；自记 Last-Event-ID 手动重连；挂起自动换轨；断线重连=POST 中断走事件流重建+message_reset、GET 中断走游标无缝续传；sid 可编辑=重入既有会话通路（偏差56））。
pyproject +mypy override `asyncpg.*`（无 py.typed，celery 同款——偏差54）。测试 +38：tests/runtime/test_text_sink.py 6（先红后绿）/ tests/api/test_sse_frames.py 11・test_chat_sse.py 8（含 msgbuf 门控时序、直答 PII 守卫、页面路由）・test_admission 三测协议换轨 / test_stream_resume.py 5（并发两测真提交独立引擎——偏差53）・test_events_view.py 5・test_notify.py 3（真 PG LISTEN 集成）。真实链路凭证（2026-07-26 五幕全 PASS）：批准后续跑帧瞬时推达（双探针：httpx 端到端+浏览器面板复现——早于批准 HTTP 响应返回）；断线 message_reset 整条重推；curl.exe -N 裸帧。

**M3.11 增量（更新于 M3.11 收口，commit `5c1f5a1`；三提交 `d55cb8f`/`e62f139`/`5c1f5a1`；零生产代码——数据/脚本/测试面）**：
**`data/corpus/{tenant-a,tenant-b}/*.md`（各 10 篇）**——语义锚双向绑定（`tests/apps/test_seed_script.py::test_corpus_semantic_anchors` 钉：A 含「七天无理由退货」/退款 200 审批/「灵犀降噪耳机 Pro」+「24 个月」且**全库零「优惠券」**（calibrate off-topic 不可命中面）；B 含 50 元券审批且**全库零 A 字面**）；两租户各含 faq.md（M3.6 后置修订⑶ 守卫补集）。
**`scripts/seed_demo.py`（重写，M3.11 正式版）**——TENANTS config：A +`approval_ttl_s: 3600`、B +`coupon_threshold: 50`+`approval_ttl_s: 3600`（拍板 1/2）；`ORDERS` 五单（AZ-1001 168 paid u-a1 / AZ-1002 599 delivered u-a1 / AZ-2001 259 paid u-a2 / BF-5001 45 delivered u-b1 / BF-5002 88 delivered u-b2）；`seed_tenants_users(factory,*,tenants,users)` / `seed_orders(factory,*,orders)` / `seed_corpus_for_tenant(factory,embedder,*,tenant_id,corpus_dir)->(fresh,resumed,skipped)` 全部可注入（测试随机 id 驱动=I1）；摄取三分支（未变 DONE 跳过零 API／未变未完 `ingest_once` 续传／变更 upsert+删块重摄取）；身份=owner 种子面（D4）+每租户 `tenant_context` 包摄取（app 引擎与 worker 内胆同构）。**刚性注记：`stmt.excluded["items"]` 必须下标形式**——列名撞 ColumnCollection 容器协议方法（items/keys/values/get/update）时 attribute 访问拿到 bound method（偏差 57）。
**`evals/`（新目录）**——`cases/seed.jsonl` 20 条（七字段 id/kind/facet/tenant_id/user_id/query/expect/note；kind=isolation×10（facet 三面 knowledge4/order4/approval2）/out_of_kb×5/retrieval×3/normal×2；expect 词表=behavior{fallback_or_handoff,no_leak,denied,answered}+must_not_contain/must_contain/chunk_source/http_status/tool）+`README.md`（判据两纪律：判回答不判 query 复述／判据强度随语料几何定；fallback 合法形态三种含**越界声明+引导渠道**——录制实测反哺）。消费方：M3.12 兜底率分母（okb 5 条）/M4.3 行为断言/M4.4 judge/M4.5 扩集。
**`scripts/record_l3_cassettes.py`（新）**——五盘 `CASSETTE_FILES` 常量表；预算三上限写死（40 调用/100_000 token/¥2）；`BUDGET_TOKEN_LIMIT=100`（<system 估算≈160，闸门 #3 首轮预检必触发）；`PROMPT_*` 与评测集同源；`load_seed()`/`tenant_from_seed()`（**spec 从种子常量构造=录制回放 I1 定义性同源**，DB 漂移不成回放断裂面）；LogTrap 双挂点（摘要 fail-open+检索 fail-open=**脏空集不入带**）；自检全过才统一落盘+扫密。**importlib 装载纪律（偏差 60）：future-annotations 模块含 @dataclass 必须先 `sys.modules[spec.name]=module` 再 exec_module**（dataclasses 反解字符串注解查 sys.modules[cls.__module__]——M2.11 惯用法隐藏前提）。
**`tests/cassettes/l3/`（五盘）**——isolation_cross_tenant_rag / isolation_cross_user_refund / budget_token_exceeded（**80 字节空 scopes=预检零调用实物**）/ hitl_approve_resume / tool_roundtrip_order_query；README §5 补 l3/ 子目录注记、§6 登记表 L3 五行（M2.11 占位兑现）。录制凭证 `reports/m3_l3_recording.txt`（8 调用 6,695 token ¥0.006）。
**`scripts/calibrate_retrieval_threshold.py` B 检口径修订**——空集判据（M3.5 时点 B 空库）→**字面核证**（候选结构上只能是 B 块=WHERE+RLS；零 A 字面+过阈值条数如实报告）；二轮实测（A 21 块/B 10 块）：**0.35 维持**、分离窗 [0.334,0.452]、「优惠券」0.334 距阈 0.016（M4.5 留意）。
测试 +15：`tests/apps/test_seed_script.py` 6 / `tests/evals/test_seed_cases.py` 6 / `tests/apps/test_l3_cassette_smoke.py` 3（未录制时 skip 指路=资产依赖测试诚实形态；budget/tool 盘 FakeGateway 端到端回放=M4.3 踏脚石）；另 `tests/runtime/test_approvals.py` 两断言过滤式修复（M2.10 家族，零增减）。

**M3.12 增量（更新于 M3 毕业，commit `8cc58ba`；两提交 `ae3490e`/`8cc58ba`）**：
**`tests/apps/test_adversarial.py`（7 测）**——四大对抗集中对账面（00 §7.2 第 1 条 CI 承载；各对抗带对照正例或零副作用断言；行为面散点出处见文件 docstring）。
**`scripts/perf_m3.py`**——两口径实测（缓存二发全流/standard 档首块 P50/P95；预算 30 调用/¥0.50 写死）；**`scripts/fallback_rate_m3.py`**——okb 5 条兜底率（分母/信号集/Trace 三处 importlib 复用=I1；预算 15 调用/¥0.20）。两脚本 `_spend` 一律 **owner 维护面**（app 引擎在 tenant_context 外读 RLS 表=静默空集——首跑实录教训，M3.5(32) 家族第三现形）。
**`prompts.py` 规则 3 具体化**（冻结后首次修订，附五盘重录）——品牌/供应商/赠品/活动/日期/价格类事实无依据一律按「没有找到」处理；`record_l3_cassettes._FALLBACK_SIGNALS` 两轮反哺至 10 词（+越界声明族/+暂未暂无族——启发式绊线定位，语义终裁归 M4.4）。
凭证 `reports/m3_acceptance.md`（四对抗/性能两口径/兜底率三轮闭环 60→80→100 全程归因）。

**M4.1 增量（更新于 M4.1 收口，三提交 `b0bbec5`/`b7abb5a`/`0795f0c`，测试 873→894）**：
**`aegis/obs/`（新顶层包三文件，层契约第二槽 `aegis.apps | aegis.obs` 互不 import——pyproject.toml:74-80）**：
masking.py（59 行）——`mask_text(text) -> str`（逐规则替换 `***{规则名}***`）／`mask_payload(Mapping) -> dict`（递归只碰 str 叶子、返新 dict 不改入参）／`MASK_ERROR_TEXT="<mask_error>"`；模式事实源=**直接 import `guardrails.PII_RULES_V1`**（四规则自带数字边界断言，无排序依赖）；两函数**绝不抛异常**（占位顶替）。
trace.py（146 行）——TraceEvent（seq/run_id/type/created_at/payload 已脱敏/duration_ms 可空）/TraceRun（run_id/termination_reason/events）/TraceUsage（requests/prompt/completion/cached_hits/cost **Decimal→JSON 字符串**）/TraceView（trace_id≡session_id/tenant_id/run_state/runs/usage）；`TraceAssembler(factory).assemble(session: SessionRecord) -> TraceView`——**鉴权归端点**（403/404 分工需区分"不存在/他租"）、单扫描分组配耗时（tool 直读 payload.latency_ms=与投影同源；llm_result 配同 run 前一条 llm_call 的 created_at 差，pop 一次配对、重发覆盖）、账本裸 SQL 聚合**包 `tenant_context(session.tenant_id)`**（(58) 防线——admin 跨租不包=RLS 静默空账）。
**api/events_view.py 升级**——响应 `-> TraceView` 全量装配；`after_seq`/`limit`/`_MAX_EVENTS` 退役（拍板⑤）；鉴权序（owner 缝 404→operator 越界 403）与审计 logger 行保持 M3.10 形态。
**L2 契约升级（M4.1③）**——`PrecheckVeto(observation: str, detail: str | None = None)` frozen dataclass（runtime.py，PrecheckHook 旁）；`PrecheckHook = Callable[[str, Mapping], Awaitable[PrecheckVeto | None]]`（**冻结面显式升级**，str 形态退役）；`EventType` **17 类** +`PRECHECK_VETOED="precheck_vetoed"`（payload 四键 approval_id/tool_name/observation/detail；无投影；写点=runtime.py `_resume_locked` APPROVED 支与 `_recover_locked` a+ 认领支，均先落事件再以 observation 走 `_PRECHECK_VETO_TEMPLATE` 回填）；`revalidate.py`——`Revalidator` 返回 `PrecheckVeto | None`、`_stale(detail)` 收口函数（observation=_STALE_TEXT/detail/日志三面一次成型）、参数类失败 observation 具体+detail=None。
测试：+`tests/obs/`（test_masking 8/test_trace_assembler 9）；test_events_view 重写 7；test_rls +M4.1 增量节（`trace_rls_seeded`+admin 跨租账本证人，**反向实证过**）；快照 17 类；veto 面 4 文件断言升级（suspend_resume/recover_approved_claim/recover_stale_claim/revalidate +1 新）。凭证 `reports/m4_trace_sample.json`（l3 cassette 零 token 回放重建+生产链实拍）。

**M4.2 增量（更新于 M4.2 收口，四提交 `80299de`/`ba372df`/`4b33295`/`5a17bf8`，测试 894→918；依赖 +prometheus-client）**：
**`aegis/obs/metrics.py`（新，~200 行）**——`REGISTRY = CollectorRegistry()`（自有表防重复注册）；**11 族**：进程内三（`aegis_http_requests` Counter[path,method,status]／`aegis_chat_first_token_seconds` Histogram[tenant_id]（2.5 桶界=M3 阈值）／`aegis_chat_request_seconds`）+DB 派生八 Gauge（runs_terminated[tenant,reason]／llm_tokens[tenant,tier,kind]／llm_cost_yuan[tenant]／tool_invocations[tool,status]／handoffs[tenant]／cache_requests[result]／**tenant_budget_used_ratio[tenant]**（#23，budget≤0 不导出）／**documents[tenant,status]**（⑫⑱观测半））；`refresh_db_metrics(factory)`（表驱动 `_SIMPLE_FAMILIES` 七族+#23 特支——**factory 必须平台维护面 owner**（(58) 第三例）；族间隔离失败留上次值绝不抛；#23 分子=`MeteringRecorder(cast(...), {}).month_spend` **单点复用**）；`render() -> (bytes, content_type)`。
**`aegis/api/metrics_view.py`（新，~70 行）**——`GET /metrics`（刷新走 `app.state.approvals_lookup`→render；无认证=拍板 1，02 §7.1 已补行）+`RequestCounterMiddleware`（**纯 ASGI** 非 BaseHTTPMiddleware——SSE 长流零干扰；只窥 `http.response.start`；path=`scope["route"].path_format` 路由模板、未匹配归并 `"unmatched"`、异常按 500 计）。main.py：`app.add_middleware(RequestCounterMiddleware)`+`include_router(metrics_view.router)`。
**chat.py 打点**——`post_chat` 入口 `t0=time.monotonic()`；`_relay(first, rest, *, t0, tenant_id)` 签名升级：首个 `kind=="token"` 帧记 CHAT_FIRST_TOKEN_S（**首 token≠首帧**）、finally 记 CHAT_REQUEST_S（含 error 收流=防幸存者偏差）。
**M4.2③ 观察池批**——intent.py `_parse_intent` 零/多词 warning（hits/len 不记原文，㉓）；kb.py `_ADMITTED=rate_limited(_STAFF)` 挂 POST+**新端点 `GET /v1/kb/documents/{id}`**（owner 缝定位→404→operator 越界 403；返 status/chunk_count/消毒 error——⑱）；approvals.py `_ADMITTED` 同款挂 POST（(56)）；hitl.py `_SWEEP_LIMIT=100`+waiting 查询 `ORDER BY id`+`.limit`+触顶警告+`SweepReport.failed: tuple=()` 第四账+`latest is None` 警告留痕（(61)）；stream.py `_REPLAY_BATCH=500`+`_gen` 重排（`replay_done` 取代 `first_batch`：批满 continue、msgbuf 重置与终止判据等排空——(74) 分批≠截断）。

**M4.3 增量（更新于 M4.3 收口，四提交 `5240b09`/`360078a`/`ac09505`/`1126c1e`，测试 918→945）**：
**`tests/replay/`（新目录两件，零生产依赖增量）**——`expectations.json`（manifest：key=相对 tests/cassettes 的 POSIX 路径，值四键 `termination_reason` 必填+`tool_sequence`/`forbidden_output`/`required_event_types` 可选=缺省不断言）；`test_behavior_regression.py`（**装置+测试一体**，m2.6"道具不进 conftest"样式：`_load_module` importlib 装载器（复装 runtime conftest 演示工具/两录制脚本，sys.modules 先注册）／`DRIVERS: dict[str, Driver]` 注册表（`Driver=(factory, monkeypatch) -> (sid, FakeGateway)`；M2 族 `_m2_driver(key, turns, with_tools, policy)`／`_drive_long_dialog`／L3 族 `_l3_run_driver(key, tenant_id, user_id, prompt_attr, seed_order_ids, with_mock, budget_from_script)`／`_drive_hitl`=run→ApprovalStore.decide→resume）／`EXHAUSTED_EXEMPT`（token_burn+minimal_demo 带理由豁免）／`_replay`（驱动→耗尽核对→**DB 全量读**）／`_extract_tool_sequence`（tool_result/error 经 `tool_call_id` 关联 tool_call 取名，流外引用 KeyError 响亮）／`_dump_text`（C31 归一化+剔 `_MECHANICAL_KEYS={iteration,input_tokens_est,digest}`=forbidden 扫描面）。
**stream.py `_translate` +user_message 帧（M4.3③，(73)）**——GET 侧多译 `ChatFrame("user_message", {"text"}, seq=seq)`（带 seq 参与续传游标）；POST 侧刻意不发（差集双 docstring 声明）；`ChatFrame` kind 词汇表 8 种（service.py:56 括注"仅 GET 回放在场"）；chat.html `handleFrame` +case 渲染蓝气泡。
**资产与文档**——minimal_demo.json main 道 2→3 条（补工具回填终答，升级为可回放资产）；`tests/cassettes/README.md` +§7（行为回归门与 PR 纪律：完整性三向/新录盘四件事/C10 并列触发五步）+§8（断言边界四声明 ㊾㊼㉜㉗）；凭证 `reports/m4_replay_redgreen.txt`（改坏闸门 #3 恰 1 红=budget 盘 CassetteMismatch；候选① 回放世界不可达弃用实录）。

**M4.4 增量（更新于 M4.4 收口，五提交 `b5bb4ab`/`8b2e295`/`69959ae`/`3b2ebfd`/`b9ccffb`，测试 945→955）**：
**`aegis/obs/evaluation.py`（新，77 行）**——`EvalCategory`（retrieval/e2e/adversarial）+`EvalVerdict`（pass/fail/**error**=异常不算 fail）+`EvalCaseRecord`（eval_cases：id/tenant_id/**user_id**/category/question/expectation JSONB/source/enabled/created_at——**RLS 名单第十表**）+`EvalRunRecord`（eval_runs：batch_id/case_id/verdict/score/judge_model（C36 回显名）/answer_digest/judge_output/tokens×2/cost Numeric(12,6)；复合索引 (case_id, created_at)=趋势路径；无 tenant_id 不上 RLS=events 先例）。迁移 `b371c327f9ff`（ENABLE+双子句策略）。config +`eval_run_token_budget: int = 150_000`。
**评测数据面**——`evals/cases.json`（定义源，20 条：顶层字段即表列，expectation 承载 kind/facet/note 三源字段）；`scripts/seed_eval_cases.py`（`load_cases()`/`seed_cases(factory, rows) -> (inserted, updated)` 幂等 upsert，**enabled/created_at 不在更新列**）；`evals/cases/seed.jsonl` 封存保留（不再被代码读取）；`tests/evals/test_seed_cases.py` 七层 lint（+category↔kind 映射）；`scripts/fallback_rate_m3.py` 改读 cases.json（expectation.kind 筛分母）。
**`scripts/run_eval.py`（新，~470 行）**——`run_batch(cases, *, execute, judge_gateway, token_budget, fallback_signals) -> BatchReport`（可注入；预算=UsageChunk 实测循环头检查，超限 partial）；`machine_verdict(case, outcome, signals) -> str|None`（must_not_contain 一票否决→三 behavior 绊线→adv 机器 pass/e2e None 交 judge）；`judge_case(gateway, case, outcome, *, pass_verdict) -> (CaseRow, p_tok, c_tok)`（strong 档 JSON 输出，**流消费包 tenant_context**——(58) 第三例修复；非 JSON→error）；`_execute_real`（approval 面 ci_pinned／retrieval=Retriever top-5 document_id 命中／对话=record 脚本组件复用+**挂起即坐席拒单+resume 收尾**）；judge 与被评**共用唯一 sid**（`case["_sid"]`），`_row_cost(sid)` 精确对账。`JUDGE_PROMPT` 与 `docs/eval-rubrics.md` 同源（改判据两处一起改）。
**L3 增量（M4.4③）**——prompts.py +`FAQ_DIRECT_RULES`（规则 3 直答版，answer_faq system=digest+它）；service.py FAQ 分支前置 `Guardrails().check_input`（HIGH 回落 `_run_main`）；approvals.py `_summary` 零事件态 `no_op`。
**文档与凭证**——`docs/eval-rubrics.md`（**仓库内首篇 docs/**，四节：三类判据/五档锚定/同族偏差三缓解/spot-check 流程）；`reports/eval_baseline_20260803.txt`（首个完整基线 20/20，judge 判分全 5=零区分度如实归因）。

**M4.5 增量（更新于 M4.5 收口，三提交 `6a4a1c2`/`53d79c8`/`bdc55cc`+凭证，测试 955→958）**：
**数据面**——evals/cases.json 20→**40 条**（source="m4.5"；新细分类 **injection**：inj-01 泄 system 探测（禁 SYSTEM_PROMPT 专有字面）/inj-02 冒充系统（禁内部工具名字面、期望 answered）；iso-11 越权话术包装/iso-12 跨租缓存探测）；test_seed_cases **八层 lint**（词表 5 kind+inj- 前缀+总量 30–50+三类各 ≥8）。
**判据面三处演进**——`_FALLBACK_SIGNALS` **13 词冻结**（三轮+「未在知识库」「暂不」、四轮+「不支持」——此后措辞变体不再加词）；`record_long_dialog.normalized` 折叠类 `[-–—\s]`（+en/em-dash——iso-12 字符形态盲区）；`run_eval.machine_verdict` **绊线归位召回器**（e2e fallback 绊线不中→None 交 judge 终裁；adversarial 保持机器 fail——README"绊线只管召回"宣称的实现兑现）。
**prompt 面**——SYSTEM_PROMPT_TEMPLATE 规则 3 品类**二轮扩容**（+期限时效+网址公众号联系方式；"定了不动"第二次修订）+FAQ_DIRECT_RULES 同步；**五盘 l3 重录**（¥0.0063，M4.3 回放门首次真实值守 15 绿=重录后行为轨迹零漂移）。
**运营纪律**——evals/README §5 +跑批前 `seed_demo` 复位（l3 重录真实消耗 AZ-1002——nor-03 状态污染实录）。
**凭证**——`eval_baseline_20260803.txt`（稳定基线 **38/40=95%**，两条强先验编造样本 okb-07/iso-12 如实保留）+`m4_judge_spotcheck.txt`（25 条异族复评 ±1 一致率 100%，口径如实标注）。

**M4.6 增量（更新于 M4.6 收口，2026-08-03，测试 958→965，四笔 `e16aac3`①/`eae3bdf`②/`2f5e3ef`③/`934e8fc`④；本步全量 AI 直写+提交推送亦 AI 代跑=00 §2.1 单步例外第二例（M2.10 后，用户当日授权））**：
**成本实验三脚本（scripts/，零生产行为改动）**——`cost_common.py`（stdlib-only 共享底座：exp-route/exp-cache 实验租户数据面常量（tenant-a 镜像+只读订单 EXPR-1001..1008/EXPC-1001..1014——P6 拍板 tools 只点名 order_query/logistics_query）+`load_questions()`/`question_strings(section)`+`build_cache_traffic(questions, *, replay_ratio=0.3, seed=42) -> list[str]`：总长=round(n/(1−r))、复述数=总长−n **精确成立**、复述只从已流出前缀重抽、同 seed 逐条相等）；`experiment_cost_routing.py`（三组同题对照：A/A' 强制档=`replace(build_agent_spec(tenant), model_tier=...)` 直驱 `runtime.run`（**「强制指定档」旁路生产不存在**=开工核对结论，frozen replace 重跑 `__post_init__`）、B=`ChatService.handle` 进程内直驱；组间**精确 sid 清单分账**+每组账本覆盖 sanity（(58) 防线）+超预算 partial）；`experiment_cost_cache.py`（**单脚本两相位**：env `CACHE_TTL_SECONDS`+`get_settings.cache_clear()` 逐相位重装网关（build_gateway 内读全局 settings 无注入缝）；相位 D 前 SCAN+DEL `aegis:cache:v1:exp-cache:*` 冷启动；**请求级全命中自检**=`bool_and(cached)` 分组）。
**config**——+`cost_routing_token_budget: int = 600_000` +`cost_cache_token_budget: int = 600_000`（00 §8.0「预算写死在配置」+M4.4 `eval_run_token_budget` 先例；600k 经冒烟外推校准，实跑 388k/523k 双双入内）。
**数据面**——`evals/cost_questions.json`（双节：routing 80=24/32/16/8 全唯一／cache 唯一池 140=42/56/28/14；节内全唯一/节间零交集/与评测集零交集）；`tests/obs/test_cost_traffic.py` 七测 lint（文件形状 id 规则/申报分布精确钉死/零重复零交集/评测集零交集/工具题引用实验种子订单 I1/复述比例与前缀不变量/固定种子可复现）。
**凭证两件**——`reports/m4_cost_routing.txt`（**vs-strong 74.7%／vs-standard 18.9%**；三组 80/80 零 errored、¥0.3544/¥0.1106/¥0.0897；tiered=fast 105 调用 ¥0.0037+standard 68 调用 ¥0.0860——25 题被 FAQ 直答短路）+`reports/m4_cost_cache.txt`（**21.9%** @30% 复述假设；¥0.1907→¥0.1489，cached 121 调用；自检=复述 60/60 全命中/首现零误命中/关相位零命中）。**M4.6 真实调用总账 ¥0.9261**（两冒烟+两正式批+setup embedding；chat 937k+embed 9.6k token）。scripts/README「实验与压测」+3 行、evals/README +cost_questions.json 纪律条。

**M4.7 增量（更新于 M4.7 收口，2026-08-03，测试 965→989（+24），七笔 `4a06503`/`72d4eb0`/`ac872cc`/`a20033e`/`0f86b23`/`7a0392d`/`9aff73e`；全程 AI 执行=M4.6 委托延续）**：
**core**——+`loopcheck.py`（`LoopBoundGuard(what, *, hint, strict)`：跨 loop 单例共性防线（㉝）——首用绑定/同实例跨 loop 严格抛人话（mock_client）或响亮警告（get_redis/shared_client）/替身重绑定豁免）；`tokens.py` +`CJK_FIRST/CJK_LAST/CJK_RANGE`（⑳ 三处同尺单点，ingest/rerank 改消费）；`tenancy.py` 目录缓存键 `(环境身份, id)` 二元组+`_copy_tenant/_copy_user` 深拷副本（①②）；`redis.py`/`providers/base.py`/`mock_backend/client.py` 三单例接 guard。迁移 +`e5a1c7d94f02`（REVOKE alembic_version FROM aegis_app，③；链 9→**10**）。
**api**——`auth.py` +`ttl_for(role, settings)`（⑦ 单点，mint_token 改消费）；`notify.py` +heartbeat 双参数与 `_wake_all()`（(67)(68)：SELECT 1 心跳+降级/停机唤醒在途等待者）；`main.py` 注入组合声明+装配日志（⑤(76)）。
**apps**——`service.py` 重构：`_try_faq_direct`（判据+流式+写盘同锁段 ㊸㊹，回落在锁外）/`_append_direct`+`_write_direct` 分层/`_produce` 前置 `build_agent_spec`（㊵ 配置错在花钱前拦截出 error 帧）/`_run_main` 收 spec 参+兜底 try（㊻）；`prompts.py` +`FALLBACK_LOOP_LIMIT_NO_TICKET`；`handoff.py` `create_handoff` +`idempotency_key` 参改走 `post_write`（㊽）；`mock_backend/app.py` `_claim_and_execute` 泛型化 `[BodyT: (WriteOpIn, TicketIn)]`+回放读带租户过滤（㉙）+`/tickets` 幂等化 `_execute_ticket`（㊳ 同键同 ticket_id）；`intent.py` 解析入 try（㉔）；`workers/ingest.py` 壳 +`except (AuthError, BadRequestError)` 直接 FAILED（⑬）；`workers/hitl.py` `_task_runtime` 装配对应清单 docstring（(64)）；`runtime.py` a+ 认领前续租（(60)）；`loop.py` tools 轮守卫命中审计（(66)）。
**部署面（#26/#31）**——+`Dockerfile`（uv 官方 py3.13-bookworm-slim 单镜像/COPY 白名单/缺省 CMD=api `--factory`）+`.dockerignore`（.env 第一行）；compose +migrate(one-shot)/api/worker/beat 四服务（`service_completed_successfully` 先迁库后起应用；unless-stopped；宿主端口只绑 127.0.0.1）。+`scripts/experiment_kill9_ingest_linux.py`（#48 Linux 复验；原 kill9 脚本补 main 守卫成可复用件）。
**文档面（#9）**——docs/ 全量入仓 37 文件（绝对路径清零+时代注记）；CLAUDE.md 仓库主入口；+`README.md` 初稿（C43）；02 §7.1 HS256 叙事修正（④）+附A #1#2#6 回填。
**凭证三件**——`m4_container_smoke.txt`（冒烟五项+(57) 真实断连+scale：镜像级多副本 healthz 200×2）/`m4_kill9_ingest_linux.txt`（四断言：**102s 零人工自动恢复**）/仓外 backups dump（C41）。测试 +24=notify 3（A）/批一 8（B）/批二 8（C）/loopcheck 5（F）。
测试：tests/obs/test_metrics.py 9（label 族过滤式/共享 label 族 **clear+delta 式**——CI 空库红 `ba372df` 一课）；tests/api/test_metrics_endpoint.py 6（11 族在/只读/db-down 200/路由模板 label/_relay 直测两条）；③批 9=intent 1/kb 3（harness +限流桩+approvals_lookup）/approvals 1（harness +limiter 参）/hitl 3/stream_resume 1。凭证 `reports/m4_metrics_sample.txt`+`scripts/demo_metrics_acceptance.py`（README 已登记；恰 3 轮写死=拍板 2 例外）。

> **更新于 M2.5**（commit `c3eb8ce`）：+`aegis/runtime/context.py`、+2 个 test 文件；仓库根 `CLAUDE.md` 已由用户入库（`2d9b21d`）。
> **更新于 M2.6**（commit `8bec868`）：+`aegis/runtime/replay.py`、+4 个 test 文件、+`tests/cassettes/`（minimal_demo.json + README.md 重录流程）。
> **更新于 M2.7**（commit `6b7f22e`，2026-07-11）：+`aegis/runtime/loop.py`（531 行）、runtime.py 接电重写（45→162 行，run 签名未动）、+4 个 test 文件（36 测）、+4 盘对抗 cassette（`tests/cassettes/adversarial_*.json`）。
> **更新于 M2.8**（commit `553fb20`，2026-07-17）：+`aegis/runtime/guardrails.py`（564 行）、三挂点接线改 5 文件（events 15 类 / spec 9 字段 / context +entry_notice / loop 596 行 / runtime 170 行组装十步）、+3 个 test 文件（36 函数 58 测）。
> **更新于 M2.9**（commit `578b37f`，2026-07-17）：+`aegis/core/locks.py`（288 行：SessionLock 协议/Redis+PG+Failover 三实现/看门狗/工厂）、挂起-恢复接线改 5 文件（spec LoopPolicy 7 阈值 / store +SessionStateStore+attach_event（513 行）/ executor +approved（264 行）/ loop 654 行（挂起链路+resume_run+T4）/ runtime 397 行（锁+T1+resume 单入口+重建器））、+3 个 test 文件（32 函数；净增 36 测——含既有 2 处调整：DyingFactory 配额+1、K3 占位测试删除）。
> **更新于 M2.10**（commit `de39165`，2026-07-17；**本步全部代码 AI 直写——00 §2.1 单步例外**）：+`aegis/workers/`（celery_app 32 行 + reaper 157 行）、+`scripts/experiment_kill9_recovery.py`（225 行，凭证 `reports/m2_kill9_recovery.txt`）、恢复调度接线改 5 文件（config 86 行 +4 调度字段 / store 670 行 +LeaseLost+LeaseStore / events 71 行 **16 类** / executor 336 行 +reexecute / runtime 559 行 +租约伴飞+崩溃分诊+重建器 fill 泛化）、+celery≥5.5 依赖与 layers `aegis.workers`、+3 个 test 文件净增 36 测（17/7/12）。

仓库根：仓库根。生产包 `aegis/` 共 ~~28~~ ~~29~~ ~~30~~ ~~31~~ **32** 个 .py（含 6 个空 `__init__.py`——**全仓无任何 re-export，消费方一律从具体模块 import**）。

```
aegis-agent-platform/
├─ aegis/
│  ├─ __init__.py                        # 空
│  ├─ core/                              # 底座层（最下层）
│  │  ├─ __init__.py                     # 空
│  │  ├─ config.py                       # Settings 全局配置唯一事实源（pydantic-settings + lru_cache 单例）
│  │  ├─ tokens.py                       # token 启发式估算器（C25：护栏用估算、账单用实测；L1/L2 同一把尺）
│  │  ├─ redis.py                        # Redis 异步客户端进程级懒单例（快速失败三件）
│  │  ├─ db.py                           # SQLAlchemy async 引擎/会话工厂懒单例 + ORM Base
│  │  └─ locks.py                        # 会话锁原语（M2.9，ADR-005 角色5）：Redis 主+PG advisory 降级+粘滞切换+看门狗
│  ├─ gateway/                           # L1 LLM 网关（与 Agent 无关）
│  │  ├─ __init__.py                     # 空
│  │  ├─ schema.py                       # 统一协议：LLMRequest / LLMChunk 判别联合（可无损 JSON 往返）
│  │  ├─ errors.py                       # 两级异常契约：ProviderError 家族（不出网关）+ L2 可见六类
│  │  ├─ resilience.py                   # 受控重试：只在首块前、只对白名单错误、双预算
│  │  ├─ breaker.py                      # 熔断器：Redis 三键状态机（TTL 即迁移）+ 本地降级完整镜像
│  │  ├─ ratelimit.py                    # 出站限流：Lua 令牌桶 + 粘滞降级本地桶
│  │  ├─ cache.py                        # 精确缓存：租户前缀 key + 语义本体哈希 + 完整流才入库
│  │  ├─ metering.py                     # 计量：UsageRecord ORM + compute_cost 纯函数 + MeteringRecorder
│  │  ├─ router.py                       # LLMGateway 总装：档位路由/fallback/预算闸门/故障注入
│  │  ├─ factory.py                      # build_gateway()：真实依赖只在此聚合（组装在边缘）
│  │  └─ providers/
│  │     ├─ __init__.py                  # 空
│  │     ├─ base.py                      # Provider 协议 + shared_client + 状态码翻译表 + 错误消毒
│  │     ├─ openai_compat.py             # 百炼适配器（OpenAI 兼容 SSE；生产主力）
│  │     └─ anthropic.py                 # Anthropic 适配器（完整实现，桩测试验证，注册未路由）
│  ├─ runtime/                           # L2 Agent 运行时（与业务无关）
│  │  ├─ __init__.py                     # 空
│  │  ├─ spec.py                         # 注入面类型：TerminationReason/LoopPolicy/ContextConfig/AgentSpec
│  │  ├─ tools.py                        # 工具契约：ToolDef/ToolContext/@tool 装饰器/ToolRegistry
│  │  ├─ events.py                       # EventType 15 类（M2.8 +guardrail_triggered）+ AgentEvent（无时间戳=确定性回放前提）
│  │  ├─ store.py                        # 五表 ORM + EventWriter（单写者）+ 投影 + ApprovalStore（CAS）
│  │  ├─ executor.py                     # ToolExecutor 七步生命周期（五结局，不向循环抛业务异常）
│  │  ├─ context.py                      # ContextBuilder 六层预算编译 + 滚动摘要（M2.5；summary_updated 生产端；M2.8 +entry_notice）
│  │  ├─ replay.py                       # 录制回放基建（M2.6）：Cassette/FakeGateway/Recorder/normalize_events（C31）
│  │  ├─ guardrails.py                   # Guardrails v1（M2.8）：14 规则库/分类器工厂/wrap_untrusted/OutputGuard/审计 payload
│  │  ├─ loop.py                         # AgentLoop 内部驱动（M2.7）：六道闸门/_Tap 事件外流/异常矩阵（M2.8 三挂点通电）
│  │  └─ runtime.py                      # AgentRuntime 门面 + GatewayLike 协议 + 组装十步（M2.7 接电 M2.8 +防线，run 签名未动）
│  ├─ workers/                          # 非请求路径（M2.10；layers 位于 apps 与 runtime 之间）
│  │  ├─ __init__.py                     # 空
│  │  ├─ celery_app.py                   # Celery 引导：broker=Redis/无 backend/beat 恰一条 reaper（UTC 钉死）
│  │  └─ reaper.py                       # reap_once 纯 async 直测零 broker + ResumeHook 注册点 + C9 终局（T5 判赢；复盘补丁五 `b0e438b`：判死前活租约让行——_session_snapshot 四元组 +lease_alive DB 端算）
│  └─ apps/
│     └─ __init__.py                     # 空（L3 业务层，M3 起填充）
├─ tests/                                # 镜像源码分层；~~26~~ ~~28~~ ~~32~~ ~~36~~ ~~39~~ 42 个 test 文件 + 2 个 conftest + cassettes/ 资产（对账表见 §7）
├─ migrations/                           # alembic：env.py（URL 运行时覆写 + 手工 import 注册模型）+ 2 个迁移
├─ scripts/                              # 7 个演示/实验/对账脚本（见 §9.1）
├─ deploy/docker-compose.yml             # 仅基础设施两件套（pg + redis），无应用容器
├─ reports/                              # 简历数字凭证（m1_fault_injection / m2_ratelimit_retest / m2_ratelimit_degraded）
├─ .github/workflows/ci.yml              # 唯一工作流，9 步质量门（见 §9.2）
├─ pyproject.toml / uv.lock              # uv 工程；配置全文见 §2
├─ alembic.ini                           # sqlalchemy.url 是占位符，被 env.py 运行时覆写（§9.4）
├─ .env（gitignore）/ .env.example       # 密钥永不入库
└─ CLAUDE.md                             # 仓库会话入口（M4.7 起为主入口：启动序列+八条硬规则在此，docs/ 已在仓内）
```

~~注意：项目根没有 README.md、没有 Dockerfile~~ **M4.7 起两者都在**：README.md（C43 初稿，终稿 M5.5）+ Dockerfile/.dockerignore（#26 单镜像四服务，compose 见 deploy/）。

**M3 增量文件速览（M3.12 整编——拍板轻量案：本节+§6.8+§9.1 实拆更新，接口签名增量以 §0-bis 为常驻档案）**：

- `aegis/core/`：+`tenancy.py`（租户/用户 ORM+TenantDirectory）、+`tenant_ctx.py`（ContextVar+begin 钩子+install_tenant_guard）；`db.py` 双轨引擎（app/owner）；`redis.py` +new_redis_client；
- `aegis/api/`（新层，与 workers 同层互不 import）：`auth.py`／`main.py`（create_app 十注入参）／`chat.py`／`ratelimit.py`／`usage.py`／`kb.py`／`approvals.py`／`sse.py`／`stream.py`／`notify.py`／`events_view.py`；
- `aegis/apps/support/`：`intent.py`／`prompts.py`／`agent.py`／`handoff.py`／`service.py`／`revalidate.py`／`rag/`（models/ingest/embeddings 消费面/retrieve/rerank）／`tools/`（_shared+五件）／`mock_backend/`（models/app/client）；
- `aegis/workers/`：+`ingest.py`／+`hitl.py`；`aegis/gateway/`：+`embeddings.py`（D5 独立通道）；`aegis/web/chat.html`；
- 仓库根新增：`data/corpus/{tenant-a,tenant-b}/`（各 10 篇语料）、`evals/`（README+cases/seed.jsonl 20 条；M4.4 +cases.json、M4.6 +cost_questions.json）、`tests/cassettes/l3/`（五盘）；迁移 2→**10**（M4.0④b 时点 8；M4.4 +`b371c327f9ff`、M4.7 +`e5a1c7d94f02`）；scripts 13→**31**（M3.12 时 24，M4.0④b +3，M4.6 +3，M4.7 +1）（§9.1）；测试文件 42→60+（增量见 §0-bis 各节）。

---

## §2 分层与 import 契约

### 2.1 import-linter 层契约（pyproject.toml:49-60 原文）

```toml
[tool.importlinter]
root_package = "aegis"

[[tool.importlinter.contracts]]
name = "分层依赖只能向下：apps → runtime → gateway → core"
type = "layers"
layers = [
    "aegis.apps",
    "aegis.runtime",
    "aegis.gateway",
    "aegis.core",
]
```

含义：**上层可 import 下层，反向禁止**；CI 第 7 步 `uv run lint-imports` 强制。新代码写 import 前先对照本表——例如 gateway 永远不许 import runtime。

M2.4 时点的真实跨层依赖边（Grep 全仓核实）：

| 消费方 | 被消费名字 | import 位置 |
|---|---|---|
| runtime → gateway | `Tier`（spec.py:17）、`LLMChunk, LLMRequest`（runtime.py:15） | 仅 gateway.schema，**不 import 异常类与 LLMGateway 具体类**（经 GatewayLike 协议解耦） |
| runtime → core | `Base`（store.py:37）、`estimate_tokens`（executor.py:19） | |
| gateway → core | `estimate_tokens`（router.py:24）、`Base`（metering.py:27）、`get_settings/get_session_factory/get_redis`（factory.py:5-7） | |
| migrations → aegis | `aegis.gateway.metering` + `aegis.runtime.store`（env.py:9-10，**导入即注册模型**）、`get_settings`、`Base`（env.py:11-12） | 新增含 ORM 模型的模块必须同步在 env.py 加 import（§9.4） |
| 生产代码 import runtime 的地方 | **零**（L3 未存在，runtime 目前纯被测） | |

### 2.2 mypy / ruff / pytest 配置（pyproject.toml 原文要点）

```toml
[tool.ruff]
line-length = 120
target-version = "py313"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]          # pyproject.toml:32-38

[tool.mypy]
python_version = "3.13"
check_untyped_defs = true
explicit_package_bases = true                 # 允许两个 conftest.py 同名共存（M2.3 落位），pyproject.toml:40-43

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"                         # async def 测试自动识别，不用逐个加装饰器，pyproject.toml:45-47
```

- mypy 门是 **`mypy .`**（全仓含 tests，00 §10.1 #30，提交 `229ea5a`）；
- Python 版本钉 **3.13**（`requires-python = ">=3.13"`，pyproject.toml:4）；依赖锁 `uv.lock`，CI `uv sync --frozen`；
- 运行时依赖 7 个：alembic / asyncpg / httpx / pydantic / pydantic-settings / redis / sqlalchemy[asyncio]（pyproject.toml:5-13）；dev 组 6 个：import-linter / mypy / pytest / pytest-asyncio / respx / ruff（pyproject.toml:15-23）。**不引入 tiktoken**（C25）。

---

## §3 core 接口表

### 3.1 Settings 全字段表（aegis/core/config.py:8-73）

类：`class Settings(BaseSettings)`，`model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`（config.py:11-15）。**env 名规则**：无 env_prefix → env 变量名 = 字段名（大小写不敏感，惯用全大写）；dict/list 字段用 JSON 字符串覆盖。单例：`@lru_cache def get_settings() -> Settings`（config.py:70-73）——测试要干净实例直接构造 `Settings()` 绕缓存。

| 字段 | 类型 | 默认值 | env 名 | 消费方（文件:行） |
|---|---|---|---|---|
| `app_env` | `Literal["dev","staging","prod"]` | `"dev"` | `APP_ENV` | `_no_fault_injection_in_prod` 校验器（config.py:61-67） |
| `dashscope_api_key` | `SecretStr` | `SecretStr("")` | `DASHSCOPE_API_KEY` | factory.py:21（取真值必须 `.get_secret_value()`） |
| `dashscope_base_url` | `str` | `"https://dashscope.aliyuncs.com/compatible-mode/v1"` | `DASHSCOPE_BASE_URL` | factory.py:21 |
| `anthropic_api_key` | `SecretStr` | `SecretStr("")` | `ANTHROPIC_API_KEY` | factory.py:22 |
| `anthropic_base_url` | `str` | `"https://api.anthropic.com"` | `ANTHROPIC_BASE_URL` | factory.py:22 |
| `database_url` | `str` | `"postgresql+asyncpg://aegis:aegis@localhost:5432/aegis"` | `DATABASE_URL` | db.py:26、migrations/env.py:17 |
| `redis_url` | `str` | `"redis://localhost:6379/0"` | `REDIS_URL` | redis.py:16 |
| `model_routes` | `dict[str, list[str]]` | 三档（**2026-07-17 模型池重构**，commit `90060c9`——幻影 glm5.2 移除+充值解锁便宜优先）：fast=[qwen-flash,qwen-turbo] / standard=[qwen-plus,qwen-turbo] / strong=[qwen3.7-max,qwen-plus]（~~07-16：fast=standard=[qwen3.7-plus,glm5.2] / strong=[qwen3.7-max,glm5.2]~~；~~M1 原版 fast=[qwen-flash,qwen-turbo,qwen-plus] / standard=[qwen-plus,deepseek-v3] / strong=[qwen-max,deepseek-v3]~~），均 `bailian:` 前缀；**百炼请求全池 `enable_thinking:false`**（openai_compat `_build_payload`，commit `61e89d7`——思考流饿死首块计时器+计费虚高，00 §2.2 C1 补注/§10.1 #41） | `MODEL_ROUTES`（JSON） | factory.py:27 → `parse_routes` |
| `provider_rate` | `float` | `Field(default=8.0, gt=0)` | `PROVIDER_RATE` | factory.py:31-37 → GatewayLimits |
| `provider_burst` | `float` | `Field(default=16.0, gt=0)` | `PROVIDER_BURST` | 同上 |
| `tenant_rate` | `float` | `Field(default=5.0, gt=0)` | `TENANT_RATE` | 同上 |
| `tenant_burst` | `float` | `Field(default=10.0, gt=0)` | `TENANT_BURST` | 同上 |
| `limiter_max_wait` | `float` | `10.0` | `LIMITER_MAX_WAIT` | 同上（→ GatewayLimits.max_wait） |
| `replica_count` | `int` | `Field(default=1, ge=1)` | `REPLICA_COUNT` | factory.py:29 → RateLimiter(replicas=)：降级本地配额=全局/副本数 |
| `cache_ttl_seconds` | `int` | `300`（0=关缓存） | `CACHE_TTL_SECONDS` | factory.py:30 |
| `model_prices` | `dict[str, list[float]]` | 5 模型价目（元/千 token，[输入,输出]，config.py:48-54，演示值） | `MODEL_PRICES`（JSON） | factory.py:41-44（float→`Decimal(str(p))`） |
| `tenant_monthly_token_budget` | `int` | `0`（0=关闭） | `TENANT_MONTHLY_TOKEN_BUDGET` | factory.py:45 → LLMGateway 月度闸门；**M3.1 读路径切 tenants 表（00 §10.1 #13）** |
| `request_token_budget` | `int` | `0`（0=关闭） | `REQUEST_TOKEN_BUDGET` | factory.py:46 → LLMGateway 单请求闸门（三级预算 L1 级） |
| `fault_injection_rate` | `float` | `0.0` | `FAULT_INJECTION_RATE` | factory.py:38；prod>0 启动即炸（config.py:61-67） |
| `fault_injection_targets` | `list[str]` | `[]`（形如 `["bailian:qwen-plus"]`） | `FAULT_INJECTION_TARGETS`（JSON） | factory.py:39 |
| `fault_injection_mode` | `Literal["error","hang","midstream"]` | `"error"` | `FAULT_INJECTION_MODE` | factory.py:40 |

⚠️ `.env` 以**相对路径**加载（config.py:12）——相对 cwd 解析，从非仓库根跑脚本时 .env 不生效（与记忆中"脚本落盘锚定项目根"同族坑）。

### 3.2 tokens.py 估算算法（aegis/core/tokens.py:11-17 全文）

```python
def estimate_tokens(text: str) -> int:
    """纯启发式，零分词依赖（tiktoken 是 OpenAI 词表，对 Qwen 中文系统性偏差）。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return cjk + (other + 3) // 4
```

口径（tokens.py:1-8 docstring）：CJK ≈ 1 token/字、其余 ≈ 4 字符/token（向上取整）；CJK 判定**仅 U+4E00–U+9FFF 基本区**（扩展区/假名/韩文按 4 字符/token）；±15% 余量由预算数字消化；真实计费以供应商 usage 回填 usage_ledger 为准；**M2.5 ContextBuilder 六层预算必须复用本估算器（L1/L2 同一把尺）**。消费方：router.py:24（estimate_request_tokens）、executor.py:19（结果预算裁剪）。

### 3.3 redis.py 快速失败参数（aegis/core/redis.py:12-26）

`def get_redis() -> aioredis.Redis`——进程级懒单例（模块级 `_client`，redis.py:9）。构造参数字面量：`decode_responses=True` / `socket_connect_timeout=1.0` / `socket_timeout=2.0` / `retry=Retry(NoBackoff(), 1)`。理由：redis-py 8 默认 retries=10+指数抖动退避一次失败拖 ~3s，与各消费方自带降级是重复兜底（00 §2.2 复盘补丁二）。

### 3.4-bis locks.py（288 行）——会话锁原语（M2.9 新增，commit `578b37f`；节号避让既有 3.4）

```python
class SessionLockHeld(RuntimeError)                                   # 锁被占；M3.2 映射 409
def new_owner_token() -> str                                          # uuid4().hex——释放/续期的身份凭证
class SessionLock(Protocol):                                          # 三方法结构化协议
    async def acquire(session_id, owner_token, *, ttl_s=30.0) -> bool
    async def extend(session_id, owner_token, *, ttl_s=30.0) -> bool
    async def release(session_id, owner_token) -> bool
class RedisSessionLock:                                               # SET NX / Lua CAD 释放 / Lua 比对续期
    def __init__(redis)                                               # 必须 decode_responses=True（CAD bytes 陷阱）
@dataclass class HeldSessionLock: session_id / owner_token / lost: asyncio.Event
@asynccontextmanager hold_session_lock(lock, session_id, *, ttl_s=30.0,
    renew_interval_s=10.0, sleep=asyncio.sleep)                       # 唯一推荐持锁形态；看门狗失败 lost 置位即停（D13）
class PgAdvisorySessionLock:                                          # C4 三件套：session 级/专用 AUTOCOMMIT 连接/hashtext 服务端
    def __init__(engine)                                              # release 异常路径 conn.invalidate() 防带锁归池
class FailoverSessionLock:                                            # 粘滞切换+5s 顺路探针（ratelimit 同构）；_granted 路由
    def __init__(primary, fallback, *, probe_interval_s=5.0)          # 占用 False≠故障不降级；双灭异常上抛
def build_session_lock() -> SessionLock                               # 生产组装（M3.2）；测试禁用——单例跨 event loop 炸
```

**消费方**：runtime.run/resume（`_maybe_lock`：lock=None 无锁直通——2026-07-17 拍板）；M2.10 恢复调度；M3.2 会话互斥 409；M5.4 真停容器复验。锁失效物理兜底=(session_id,seq) 唯一约束（store.py:97）。

### 3.4 db.py 引擎与会话工厂（aegis/core/db.py）

- `class Base(DeclarativeBase)`（db.py:14-15）——全仓 ORM 公共基类，alembic 靠其 metadata 发现表；
- `def get_engine() -> AsyncEngine`（db.py:22-31）：`create_async_engine(database_url, pool_size=5, max_overflow=10, pool_pre_ping=True)`；
- `def get_session_factory() -> async_sessionmaker[AsyncSession]`（db.py:34-39）：`async_sessionmaker(get_engine(), expire_on_commit=False)`（async 下访问过期属性会隐式 IO，禁）；
- 两者均手动 global 懒单例（与 redis.py、providers/base.shared_client 同族三例；口径：值用 lru_cache、资源用手动 global）。

---

## §4 gateway 契约面（L2/L3 消费视角）

### 4.1 schema.py 类型全表（aegis/gateway/schema.py）

类型别名（schema.py:14-15）：`Tier = Literal["fast", "standard", "strong"]`、`Role = Literal["system", "user", "assistant", "tool"]`。

**LLMRequest**（schema.py:45-60）：

| 字段 | 类型 | 默认/约束 | 要点 |
|---|---|---|---|
| `tier` | `Tier` | 必填 | 只声明档位，**永远不写模型名** |
| `messages` | `list[Message]` | 必填，`Field(min_length=1)` | |
| `tools` | `list[ToolSpec]` | `[]` | |
| `temperature` | `float \| None` | `None` | None=供应商默认 |
| `max_tokens` | `int \| None` | `None` | |
| `tenant_id` | `str` | 必填；`min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"` | 字符集收紧保护 Redis key 租户前缀 |
| `session_id` | `str \| None` | `None` | 进 usage_ledger 对账 |
| `request_id` | `str` | `default_factory=lambda: uuid4().hex` | |
| `deadline_s` | `float \| None` | `None`，`gt=0` | **首块预算**：只约束首块前空转；首块后由块间空闲超时守护，整流不设上限（C1） |

配套模型：`ToolSpec{name, description, parameters: dict}`（schema.py:18-23，parameters 是 JSON Schema，网关不解释）；`ToolCall{id, name, arguments_json}`（schema.py:26-35，arguments_json 保持原始字符串**可能不是合法 JSON**，解析归 L2）；`Message{role, content="", tool_calls=[], tool_call_id=None}`（schema.py:38-42）。

**LLMChunk 判别联合**（schema.py:63-95）——四种块与全字段：

| 块 | 判别值 `type` | 其余字段 |
|---|---|---|
| `TextDelta` | `"text_delta"` | `text: str` |
| `ToolCallChunk` | `"tool_call"` | `tool_call: ToolCall`（v1 工具调用轮整体交付，不做增量解析） |
| `UsageChunk` | `"usage"` | `model: str`、`prompt_tokens: int`、`completion_tokens: int`、`cached: bool = False`（缓存回放盖章，计量器据此零成本记账） |
| `StopChunk` | `"stop"` | `reason: Literal["end_turn", "tool_calls", "max_tokens"]` |

```python
LLMChunk = Annotated[TextDelta | ToolCallChunk | UsageChunk | StopChunk, Field(discriminator="type")]
chunk_adapter: TypeAdapter[LLMChunk]; chunk_list_adapter: TypeAdapter[list[LLMChunk]]   # schema.py:89-95
```

两条 L2 可依赖的不变量：① 所有模型**可无损 JSON 往返**（schema.py:6，M2.6 cassette 直接依赖）；② chunk 顺序恒为 **`TextDelta* → ToolCallChunk* → UsageChunk → StopChunk`**（openai_compat.py:7-8 / anthropic.py:4，两适配器共同承诺）。

### 4.2 六类异常继承树（aegis/gateway/errors.py 原样）

```
Exception
└── GatewayError                    (errors.py:8)
    ├── ProviderError               (errors.py:12)  __init__(provider, message)；永不穿出网关
    │   ├── RateLimitedError        (errors.py:20)  __init__(provider, message, retry_after=None)
    │   ├── ProviderTimeoutError    (errors.py:28)  请求可能已在上游执行（重复计费风险）
    │   ├── ProviderServerError     (errors.py:32)  502/503/504，可重试
    │   ├── BadRequestError         (errors.py:36)  4xx（除 429/401/403），重试无意义
    │   └── AuthError               (errors.py:40)  401/403，该修配置
    ├── GatewayOverloadedError      (errors.py:44)  ┐ 本地池排队超时：不记熔断账/不重试/不换路
    ├── GatewayExhausted            (errors.py:52)  │ 重试+fallback 用尽（首块前），可整体降级
    ├── BudgetExceeded              (errors.py:64)  ├ L2 可见"六类"（00 §2.2 C6）
    ├── TenantQuotaExceeded         (errors.py:68)  │ 租户配额尽，换供应商无解
    ├── GatewayRejected             (errors.py:72)  │ 确定性拒绝，**不降级**→终止原因 gateway_rejected
    └── GatewayStreamInterrupted    (errors.py:82)  ┘ 流级（首块后），死因在 __cause__，恢复语义入口
```

L2 消费口径：请求级·可降级 = Exhausted/Budget/TenantQuota/Overloaded；请求级·不降级 = Rejected（bug 信号，不走兜底话术）；流级 = StreamInterrupted（"半截 llm_call"作废重发的捕获入口）。**ProviderError 家族永不出网关**（errors.py:60）。

### 4.3 公开入口与协议

**L2 眼中的网关**（aegis/runtime/runtime.py:20-30）：

```python
class GatewayLike(Protocol):
    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...
```

注意是 `def` 不是 `async def`（async 生成器方法的类型是"调用后返回 AsyncGenerator"）。真网关侧对应 `async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]`（router.py:190）——结构等价，兼容性由 tests/runtime/test_runtime.py:23 的永不执行内层函数交给 mypy 静态锁定。

**router.py 公开面**：

| 名字 | 签名/形状 | 行号 |
|---|---|---|
| `LLMGateway.__init__` | keyword-only：`providers: dict[str, Provider], routes: dict[str, list[Candidate]], breaker: BreakerLike, limiter: LimiterLike, cache: CacheLike \| None = None, meter: MeterLike \| None = None, monthly_token_budget: int = 0, request_token_budget: int = 0, limits: GatewayLimits \| None = None, retry_policy: RetryPolicy \| None = None, fault_rate: float = 0.0, fault_targets: frozenset[str] = frozenset(), fault_mode: FaultMode = "error"` | router.py:158-188 |
| `Candidate` | `@dataclass(frozen=True)`：`provider: str; model: str` | router.py:79-82 |
| `parse_routes(raw, known_providers) -> dict[str, list[Candidate]]` | 启动即校验：`provider:model` 形式、provider 已知、链非空、**三档必须齐全**（以 schema.Tier 为事实源） | router.py:85-103 |
| `estimate_request_tokens(req) -> int` | messages 全文 + 工具名/说明/parameters JSON；只估 prompt 侧 | router.py:106-113 |
| `GatewayLimits` | frozen dataclass：`provider_rate=8.0, provider_burst=16.0, tenant_rate=5.0, tenant_burst=10.0, max_wait=10.0` | router.py:116-122 |
| `FaultInjector(inner, rate, *, mode="error", hang_s=120.0)` | 自身满足 Provider 协议；error=首块前抛 5xx / hang=挂起等首块超时切 / midstream=首块后断流 | router.py:125-155 |
| 四个依赖协议 | `BreakerLike`（allow→str/on_success/on_failure/release_probe）、`LimiterLike`（wait_take）、`CacheLike`（get/put）、`MeterLike`（record/month_spend） | router.py:51-76 |
| `build_gateway() -> LLMGateway` | 真实依赖聚合；注册 provider 名恰为 `"bailian"` 与 `"anthropic"`；retry_policy 未显式传（全默认） | factory.py:18-47 |

**complete 装配顺序**（router.py:190-342 源码核实）：

```
缓存查询（命中→回放+盖 cached 章+记账 provider="cache"，零配额消耗）
→ 租户月度预算闸门（month_spend ≥ budget → BudgetExceeded；账本读挂 fail-open 放行+告警）
→ 单请求预算闸门（estimate_request_tokens > budget → BudgetExceeded；0=关闭）
→ 租户限流（候选环外一次，scope=f"tenant:{tenant_id}"，失败→TenantQuotaExceeded）
→ for cand in candidates:
    deadline 剩余 < min_attempt_budget → budget_out 停止换路
    → breaker.allow（deny→跳过计 transient；probe→单次尝试 _PROBE_POLICY）
    → 供应商限流（scope=f"provider:{provider}"；排不上跳过，probe 令牌归还）
    → [FaultInjector 包装：fault_rate>0 且 f"{provider}:{model}" ∈ targets]
    → complete_with_retry(target, req, model, policy, deadline=deadline)
终局：budget_out → GatewayExhausted("…首块预算…耗尽")；
     rejections>0 且 transients==0 → GatewayRejected；否则 GatewayExhausted("…所有候选均不可用")
```

异常三待遇（router.py:310-332）：`_BREAKER_COUNTED = (ProviderServerError, ProviderTimeoutError)` 记熔断账再换路；429 换路不记账（probe 时归还令牌）；Auth/BadRequest 换路不记账计 rejections。**红线一**：任一异常发生在已 yielded 之后 → `GatewayStreamInterrupted(f"流中断于 {provider}:{model}") from e`。计量失败走 `_safe_record` 吞掉（router.py:344-351）。

### 4.4 口径常量表（改动=改口径，先过 00 §2.2）

| 类别 | 常量 | 值 | 出处 |
|---|---|---|---|
| 三段超时（C1） | httpx connect / read / write / pool | 5.0 / **30.0（块间空闲）** / 10.0 / 5.0 | base.py:46 |
| | 首块超时 `first_chunk_timeout` | **25.0** | resilience.py:41 |
| | `min_attempt_budget`（deadline 剩余低于此不开新尝试） | 8.0 | resilience.py:42 |
| | httpx 池上限 | max_connections=100, max_keepalive=20 | base.py:47 |
| 重试（RetryPolicy 默认） | max_attempts / base_backoff / max_backoff / total_timeout | 3 / 0.5 / 8.0 / 60.0 | resilience.py:34-42 |
| | 重试白名单 | `(RateLimitedError, ProviderTimeoutError, ProviderServerError)` | resilience.py:27 |
| | 退避算法 | Retry-After 优先（封顶 max_backoff）；否则 `_uniform(0, min(base*2^(n-1), max))` 满抖动 | resilience.py:45-50 |
| 熔断（CircuitBreaker 默认） | failure_threshold / open_seconds / probe_ttl / fail_window | 5 / 30 / 120 / 120 | breaker.py:40-51 |
| | Redis key | `aegis:cb:{provider}:open` / `:fails` / `:probe`（TTL 即状态迁移；探测互斥 SET NX） | breaker.py:60-62 |
| | 计账规则 | 只有 5xx/超时算熔断失败；429/Auth/BadRequest 不算 | breaker.py:8-9 |
| 限流（令牌桶） | 桶 key | `aegis:rl:{scope}`，scope=`tenant:{id}` / `provider:{name}` | ratelimit.py:100、router.py:247/272 |
| | 桶算法 | 新桶满桶开局；Redis TIME 时钟；NTP 回拨不负补给；桶 TTL=`min(ceil(cap/rate)+60, 86400)`；wait 须 tostring | ratelimit.py:35-67 |
| | 降级 | 本地桶配额=全局/replicas；粘滞 + `probe_interval=5.0s` 顺路探针；恢复时 `_local.clear()` | ratelimit.py:70-115 |
| 缓存 | key 规则 | `aegis:cache:v1:{tenant_id}:{sha256(canonical_json(exclude={request_id,session_id,tenant_id,deadline_s}))}` | cache.py:38-42 |
| | 入库标准 | StopChunk 收尾 **且** ≥1 个 TextDelta/ToolCallChunk；脏数据读到即删按 miss | cache.py:44-60 |
| | 默认 TTL | 300s（Settings.cache_ttl_seconds；0=关闭） | config.py:46 |
| 路由 | `_PROBE_POLICY` | `RetryPolicy(max_attempts=1)` | router.py:43 |
| 计量 | 成本 | `Numeric(12,6)`/Decimal；cached=0 元；模型不在价目表记 0 + logger.warning | metering.py:48/57-74 |
| | month_spend | DB 端 `date_trunc('month', now())`；**排除 cached 行** | metering.py:113-125 |
| 适配器 | Anthropic `DEFAULT_MAX_TOKENS` | 4096（max_tokens 缺省时用） | anthropic.py:38 |
| | 终止哨兵 | openai_compat 须见 `[DONE]`、anthropic 须见 `message_stop`，否则抛 ProviderServerError"流被截断" | openai_compat.py:129-132、anthropic.py:130-131 |
| | httpx 异常翻译 | PoolTimeout→GatewayOverloaded；TimeoutException→ProviderTimeout；TransportError→ProviderServer | openai_compat.py:121-127、anthropic.py:123-128 |
| | 错误消毒 | `sanitize_error_text`：截断 200 + `sk-***` 打码，所有上游错误文本进异常前必过 | base.py:52-62 |
| 测试接缝 | 模块级可替换名 | resilience：`_sleep`/`_uniform`；router：`_random`/`_hang_sleep`；ratelimit：`_sleep` | resilience.py:30-31、router.py:46-47、ratelimit.py:24 |

已知边角（引用时留意）：① 上游缺 usage 时 openai_compat 收尾合成 `UsageChunk(prompt_tokens=0, completion_tokens=0)`（openai_compat.py:144）——账本里 0 token 行可能是"上游没报"；② `BreakerLike.allow` 协议返回类型写 `str`（router.py:52），实现返回 `Decision = Literal["allow","probe","deny"]`（breaker.py:24）——假件返回任意字符串 mypy 不拦；③ `GatewayOverloadedError` 不被候选环 except 捕获、直接穿出——probe 令牌在该路径不归还（等 probe_ttl 自愈，未在注释明示的已知取舍）；④ anthropic 是"注册未路由"状态：默认 model_routes 全走 bailian，给它配路由前必须先配 ANTHROPIC_API_KEY，否则该候选恒 AuthError 计 rejection。

---

## §5 runtime 全接口（本文最重的一节）

（**更新于 M2.5/M2.6/M2.8**，commit `553fb20`）`aegis/runtime/` ~~6~~ ~~7~~ ~~8~~ **9** 个实文件 + 空 `__init__.py`；除 executor.py 外均有 `from __future__ import annotations`。包内互引：spec←tools.ToolDef；store←events；executor←events+tools；runtime←events.AgentEvent+spec.AgentSpec+**guardrails（Classifier/Guardrails/build_classifier——M2.8 组装）**；**context←events.EventType + spec.ContextConfig + store（EventRecord/MessageRecord/SessionFactory）+ executor.EventSink**（另引 gateway.schema.Message、core.tokens——层内向下合法）；**loop←guardrails（七名字）**；**guardrails←gateway.schema（运行时）+ runtime.GatewayLike（仅 TYPE_CHECKING——loop 顶层引 guardrails，真 import runtime 成环）**。executor 与 context 均**不 import** EventWriter——经 `EventSink` 结构化协议消费其形状。

### 5.1 spec.py（~~158~~ ~~163~~ 168 行）——注入面四类型（M2.8：AgentSpec **9 字段**——+`owned_values`（C23）+`entry_classifier`（默认关）；M2.9：LoopPolicy **7 阈值**——+`approval_ttl_s: float = 3600.0`（P1 方案 A：审批单 expires_at 生成依据，租户级策略 M3.1 经配置注入））

**`TerminationReason(StrEnum)`**（spec.py:21-37）——8 成员，值进 loop_terminated 事件 payload 与回放断言，**改值=破坏重放**（值快照测试钉死）：

```python
COMPLETED = "completed"                      # 0 正常完成
MAX_ITERATIONS = "max_iterations"            # 闸门1
STEP_TIMEOUT = "step_timeout"                # 闸门2
TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"  # 闸门3
REPEATED_CALLS = "repeated_calls"            # 闸门4
PROTOCOL_VIOLATION = "protocol_violation"    # 闸门5
CANCELLED = "cancelled"                      # 闸门6 取消/HITL 拒绝或超时
GATEWAY_REJECTED = "gateway_rejected"        # 七类之外：L1 确定性拒绝，不走兜底话术（C6）
```

**`TERMINATION_GATES`**（spec.py:40-43）：`frozenset(TerminationReason) - {COMPLETED, GATEWAY_REJECTED}`——恰 6 个闸门（测试钉死 len==6，00 §2.2 术语口径）。

**`LoopPolicy`**（spec.py:48-80，`@dataclass(frozen=True, slots=True)`）：

| 字段 | 类型 | 默认 | `__post_init__` 校验（spec.py:68-80） |
|---|---|---|---|
| `max_iterations` | `int` | `10` | <1 抛 ValueError |
| `llm_step_timeout_s` | `float` | `90.0` | ≤0 抛（= 传给网关的 deadline，嵌套约束靠传播不靠算术——C1） |
| `tool_step_timeout_s` | `float` | `30.0` | ≤0 抛（循环级默认上限，单工具更严取更严） |
| `session_token_budget` | `int` | `50_000` | <1 抛（生产值 M3.1 由租户配置注入；计数用估算器——C25） |
| `repeat_call_limit` | `int` | `3` | <1 抛 |
| `protocol_retry_limit` | `int` | `2` | <0 抛（**0 合法**） |

只承载闸门 1–5 阈值；闸门 6 由外部信号与审批单 expires_at 触发（M2.9）。frozen：一次 run 内不许改，要变换新实例。

**`ContextConfig`**（spec.py:83-118，frozen+slots）——六层上下文预算（03 §3），单位 token：

| 字段 | 默认 | 校验 |
|---|---|---|
| `system_budget` | `1_500` | <1 抛（不许 0） |
| `memory_budget` | `1_000` | <0 抛（0=显式关闭该层；M2 只有注入接口，实现随 M3 RAG） |
| `history_budget` | `4_000` | <0 抛 |
| `retrieval_budget` | `3_000` | <0 抛（同 memory，M3 接） |
| `tool_results_budget` | `3_000` | <0 抛 |
| `output_reserve` | `4_000` | <1 抛（不许 0） |

属性 `input_total -> int`（spec.py:109-118）：输入侧五层合计（不含 output_reserve），默认 **12_500**——M2.5 编译器与 M2.7 对账用。

**`SubAgentPolicy(StrEnum)`**（spec.py:121-127）：唯一成员 `DISABLED = "disabled"`；v1 恒 DISABLED（ADR-002 v2 预留位，测试钉死 len==1）。

**`AgentSpec`**（spec.py:130-157，frozen+slots）：

| 字段 | 类型 | 默认 |
|---|---|---|
| `system_prompt` | `str` | **必填** |
| `tools` | `tuple[ToolDef, ...]` | `()`（tuple 不是 list：注入面冻结） |
| `policy` | `LoopPolicy` | `LoopPolicy()` |
| `context_config` | `ContextConfig` | `ContextConfig()` |
| `model_tier` | `Tier` | `"standard"` |
| `sub_agent_policy` | `SubAgentPolicy` | `SubAgentPolicy.DISABLED` |
| `tenant_config` | `Mapping[str, Any]` | `field(default_factory=dict)`（对运行时**不透明**，只透传 risk_policy 等，解释权在 L3） |

`__post_init__`（spec.py:149-157）三校验：system_prompt.strip() 空 → ValueError；`model_tier not in get_args(Tier)` → ValueError（拦 L3 配置裸字符串）；工具名重复 → ValueError（含排序后重名清单）。

### 5.2 events.py（~~68~~ ~~69~~ 71 行）——~~14~~ ~~15~~ **16** 类事件 + AgentEvent（M2.8 +`GUARDRAIL_TRIGGERED`；M2.10 +`RECOVERY_ABANDONED`（C9 审计三键 recovery_count/recovery_limit/last_lease_owner，无投影，T5 赢家写入））

`SCHEMA_VERSION = 1`（events.py:16-18）：重放器按版本路由解析器；重构 payload 时版本 +1 并保留旧解析器。

**`EventType(StrEnum)`**（events.py:21-38）——**14** 成员（C8 于 2026-07-09 增 summary_updated；快照测试钉死）：

```
user_message / assistant_message / llm_call / llm_result /
tool_call / tool_result / tool_error /
approval_requested / approval_decided / approval_cancelled / approval_expired /
summary_updated / loop_terminated / handoff
```

**`AgentEvent`**（events.py:41-68，frozen+slots）：字段 `id: str`、`session_id: str`、`run_id: str`、`seq: int`、`type: EventType`、`payload: Mapping[str, Any]`（前六个必填）、`schema_version: int = SCHEMA_VERSION`。`__post_init__`：三个 id 非空；`seq >= 1`（单写者从 1 起）；`schema_version >= 1`。

契约（events.py:3-6、43-48）：事件即事实源（先写事件再继续，恢复=重放重建）；AgentEvent 是"已落盘事实"的镜像；**不带时间戳**（墙钟由 DB 赋值，C31 确定性回放前提）；payload 存原文（X4）；粒度到"步"，逐 token 是 M3.10 通道问题。

### 5.3 store.py（~~477~~ ~~513~~ 670 行）——五表 + 单写者 + 投影 + 三 CAS 原语族（M2.9 +attach_event/SessionStateStore（T1–T4）；**M2.10 +`LeaseLost`（终态围栏，同 EventWriteFenced 语义）+`default_lease_owner()`（host:pid）+`LeaseStore` 五方法**——`acquire`（running 前置 + 无租约/过期/NULL/同 owner 重入四条件，gen+1）/`renew`（打空即围栏 C2 协议二）/`release`（清双列+recovery_count 归零）/`steal_expired`（gen+1 且 count+1，未超限前置）/`clear_lease`（C9 赢家清扫，无 CAS——判定权在 T5 transition，偏差 #7）/`list_expired`（NULL 幽灵 nullsfirst）；时钟全 DB 钟 func.now()、now 可注入；**全部 SET 不碰 run_state**；T5 已随 reaper 接电） |

**枚举三件**（存字符串列 + 代码层快照守护，**不用 PG ENUM**，store.py:5-7）：

- `RunState`（store.py:41-47）：`idle / running / awaiting_approval / failed`（failed 进入路径随 M2.10——C9）；
- `InvocationStatus`（store.py:50-55）：`running / succeeded / failed`（write-ahead 落盘时 running）；
- `ApprovalStatus`（store.py:58-65）：`pending / approved / rejected / cancelled / expired`（五态，翻转全走 CAS——C11）。

**ORM 五模型**（列级 DDL 细节见 §6；此处仅列形状要点）：

| 模型 | 表 | 行号 | 要点 |
|---|---|---|---|
| `SessionRecord` | sessions | store.py:68-89 | `Index("ix_sessions_reaper", "run_state", "lease_expires_at")`；lease_generation（C2 围栏）/recovery_count（C9）/summary（M2.5 写入） |
| `EventRecord` | events | store.py:92-109 | `UniqueConstraint("session_id","seq", name="uq_events_session_seq")`；id 应用侧 uuid（幂等键须先于副作用存在） |
| `MessageRecord` | messages | store.py:112-123 | event_id unique=投影防重；role 仅 user/assistant（代码约定） |
| `ToolInvocationRecord` | tool_invocations | store.py:126-142 | event_id = tool_call 事件 id = 幂等键；result_digest 存摘要，原文在 events.payload（X4） |
| `ApprovalRecord` | approvals | store.py:145-165 | **不挂 tool_invocation 外键**（审批③先于 write-ahead④，审批的是参数快照；event_id 执行后回填）；`Index("ix_approvals_expiry","status","expires_at")` |

**类型别名与常量**：`SessionFactory = Callable[[], AsyncSession]`（store.py:168-170，按形状声明，测试故障注入工厂由此进）；`_RETRY_BACKOFF_S = (0.1, 0.2, 0.4)`（store.py:171-173，内部，3 次重试无抖动——单写者无雷群）。

**异常三件**（均继承 `RuntimeError`）：

| 异常 | 定义 | 语义 | 抛出点 |
|---|---|---|---|
| `EventStoreUnavailable` | store.py:176-177 | PG 瞬态故障重试耗尽——事实源不可用=服务不可用（02 §5），终止本次 run | store.py:368-371 |
| `EventWriteFenced` | store.py:180-183 | 围栏信号（C2）：(session_id, seq) 被别的写者占用；**终态，零退避零重试**，loop 应自毁 | store.py:363-365 |
| `ProjectionError` | store.py:185-188 | 投影派生失败（缺字段/被引用行不在）——bug 信号裸抛；发生在 append 事务内，**连事件一起回滚（事实与投影同生共死）** | store.py:232-233 / 260-261 / 283-284 |

**`EventWriter`**（store.py:287-387）——**单写者：一个 run 一个实例，创建前提是已持会话锁（M2.9 接电，唯一约束兜底）**：

```python
def __init__(self, factory: SessionFactory, session_id: str, run_id: str, next_seq: int, *,
             sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
             id_factory: Callable[[], str] | None = None) -> None      # store.py:294-309；id 缺省 uuid4().hex
@property session_id -> str    # store.py:311-313
@property run_id -> str        # store.py:315-317
@classmethod
async def open(cls, factory, session_id, run_id, *, sleep=..., id_factory=...) -> EventWriter  # store.py:319-336
async def append(self, event_type: EventType, payload: Mapping[str, Any]) -> AgentEvent        # store.py:338-382
```

- `open`：读流尾 `coalesce(max(seq), 0)`，`next_seq = max_seq + 1`——恢复场景新 run 天然接续旧流 seq；
- `append` 三岔口（store.py:343-374）：① 正常：同一事务内 `s.add(record)` + `_apply_projections`（**投影同事务**），成功后 `_next_seq += 1`；② `IntegrityError` → 查 `_already_written(event_id)`：行已在=**幽灵写入**（上次实际成功、commit ack 丢了）当成功；否则抛 `EventWriteFenced`；③ `(OperationalError, InterfaceError)` 白名单 → 按 `_RETRY_BACKOFF_S` 退避，耗尽抛 `EventStoreUnavailable`（ProgrammingError 等 bug 信号裸抛）；
- 返回同 event_id/seq/`dict(payload)` 构造的 AgentEvent，schema_version 走默认；**append 返回即 durably committed**（write-ahead 前置由此成立）。

**投影 payload 契约**（每个投影函数的必填键——从源码提取；写事件方必须给足，缺键=ProjectionError 掀翻整个事务）：

| 事件类型 | 投影函数（行号） | **必填 payload 键** | 可选键 | 投影行为 |
|---|---|---|---|---|
| `user_message` | `_project_user_message`（store.py:207-208） | `content` | `token_usage` | 插 MessageRecord(role="user") |
| `assistant_message` | `_project_assistant_message`（store.py:211-212） | `content` | `token_usage` | 插 MessageRecord(role="assistant") |
| `tool_call` | `_project_tool_call`（store.py:215-223) | `tool_name`、`args` | — | 开 ToolInvocationRecord 行（status 默认 running） |
| `tool_result` | `_project_tool_result`（store.py:236-243） | `tool_call_id` | `digest`、`latency_ms`、`retry_count`（缺省 0） | 按 event_id==tool_call_id UPDATE 为 succeeded + finished_at=now()；rowcount≠1 → ProjectionError |
| `tool_error` | `_project_tool_error`（store.py:246-253） | `tool_call_id`、`error` | `latency_ms`、`retry_count` | 同上翻 failed |
| `summary_updated` | `_project_summary`（store.py:256-261） | `summary` | — | UPDATE SessionRecord.summary；会话行不存在 → ProjectionError |
| 其余 8 类 | 无投影（`_PROJECTORS` 查不到=合法 no-op，store.py:264-273） | — | — | 审批类不在此列**不是遗漏**——approvals 是独立状态机不是投影 |

`_apply_projections`（store.py:276-284）：投影是事件的**纯函数**（只读 record，不读时钟/外部状态——回放可重建）；KeyError 转 ProjectionError 并点名缺失字段。

**`ApprovalStore`**（store.py:390-476）——审批状态机原语层，**全部翻转 CAS：条件进 WHERE、输赢看 rowcount**；事件写入与 run_state 置位**不在此层**（归 M2.9"先取会话锁再恢复"单入口）：

```python
def __init__(self, factory: SessionFactory) -> None                                    # store.py:398-399
async def create(*, approval_id: str, session_id: str, tenant_id: str, tool_name: str,
                 args: Mapping[str, Any], expires_at: datetime) -> None                 # store.py:401-423 开单，status 默认 pending
async def decide(self, approval_id: str, *, approved: bool, operator_id: str) -> bool   # store.py:425-442
async def cancel(self, approval_id: str) -> bool                                        # store.py:444-456
async def expire_due(self, *, now: datetime | None = None) -> list[str]                 # store.py:458-476
```

- `decide`：WHERE `status==pending AND expires_at > func.now()`——**C7 fail-closed，过期单拒绝翻转，归宿只有 reaper**；DB 时钟与 expires_at 同源；返回 `rowcount == 1`；
- `cancel`：只查 pending，**不查过期**（撤回已到期未清扫的单无害）；
- `expire_due`：批量翻 expired + `.returning(id)` 返回单号列表；`now` 可注入（C7 可注入时钟），缺省 `func.now()`；reaper 调度随 M3.9。

### 5.4 tools.py（190 行）——工具契约与注册

**`SideEffect(StrEnum)`**（tools.py:21-25）：`READ = "read"` / `WRITE = "write"`（X2：恢复期"仅读可重发"由此机器判定）。

**`ToolRegistrationError(ValueError)`**（tools.py:32-33）：一切注册期防呆在 import 时统一为此异常。

**`ToolContext`**（tools.py:36-54，frozen+slots）：五个 `str` 字段全必填——`tenant_id / user_id / session_id / run_id / tool_call_id`；任一 falsy → ValueError。全部 LLM 不可控；`tool_call_id` = write-ahead 的 tool_call 事件 id = **幂等键**透传下游（M3.7 退款服务按键去重）；id 三层模型：trace_id ≡ session_id，run_id 每次循环新生成（X5）。

**`RiskPolicy`**（tools.py:57-59）：`Callable[[Any, Mapping[str, Any]], bool]`——`(已校验参数, 租户配置) -> 是否需要 HITL 审批`。

**`ToolDef`**（tools.py:62-103，frozen+slots）：

| 字段 | 类型 | 默认 |
|---|---|---|
| `name` / `description` / `handler` | `str` / `str` / `Callable[..., Awaitable[Any]]` | 必填 |
| `side_effect` | `SideEffect` | **必填（刻意无默认：读写必须显式声明）** |
| `parameters_schema` | `Mapping[str, Any]` | `field(default_factory=dict)` |
| `args_model` | `type[BaseModel] \| None` | `None`（与 parameters_schema 同源生成） |
| `risk_policy` | `RiskPolicy \| None` | `None` |
| `risk_exempt` | `bool` | `False`（C15 豁免开关，留档可审计） |
| `timeout_s` | `float \| None` | `None`（=继承 LoopPolicy.tool_step_timeout_s） |
| `retries` | `int` | `0` |

`__post_init__` 八校验按序（tools.py:84-103）：① name 须匹配 `_TOOL_NAME_RE = ^[a-zA-Z0-9_-]{1,64}$`（tools.py:28-29，OpenAI tool schema 硬约束）；② description 非空；③ timeout_s>0 或 None；④ retries≥0；⑤ **写工具 retries>0 直接拒绝**（写禁自动重试，03 §4）；⑥ C15-a：risk_exempt 仅对写工具；⑦ C15-b：risk_exempt 与 risk_policy 互斥；⑧ C15-c：写工具无 risk_policy 且未豁免 → 拒绝注册（报错含"C15"字样）。

**`tool` 装饰器工厂**（tools.py:126-162）：

```python
def tool(*, side_effect: SideEffect, risk_policy: RiskPolicy | None = None, risk_exempt: bool = False,
         timeout_s: float | None = None, retries: int = 0, name: str | None = None,
         ) -> Callable[[Callable[..., Awaitable[Any]]], ToolDef]:
```

行为：`tool_name = name or fn.__name__`；`description = inspect.getdoc(fn) or ""`（docstring 即说明书）；`parameters_schema = model.model_json_schema()` 与 `args_model = model` **同源**；**装饰后模块级名字指向 ToolDef 而非函数**（函数在 `.handler`）；ToolDef 构造期 ValueError 被包装为 ToolRegistrationError（tools.py:158-160）。

`_build_args_model(fn, tool_name)`（tools.py:106-123，内部）规则（全部抛 ToolRegistrationError）：首参必须是 `ctx` 且注解**恰为** `ToolContext`（用 `get_type_hints` 解析——全仓 future annotations 下注解是字符串，必须解析回真类型）；不支持 `*args/**kwargs`；除 ctx 外每参必须有注解；无默认值→pydantic 必填；模型名 `f"{tool_name}_args"`，`ConfigDict(extra="forbid")`（幻觉参数响亮拒绝）。

**`ToolRegistry`**（tools.py:165-190）：

```python
def __init__(self, tools: Iterable[ToolDef] = ()) -> None
def add(self, t: ToolDef) -> None          # 重名 → ToolRegistrationError
def get(self, name: str) -> ToolDef | None # 查不到返回 None 不抛错（幻觉工具名是常态，处置归 M2.7 闸门#5）
def specs(self) -> tuple[ToolDef, ...]     # dict 插入序 → 工具顺序进 LLMRequest（回放确定性一环）
```

不做自动发现——注入是唯一入口（生产喂真工具、回放喂演示工具集）。

### 5.5 executor.py（~~262~~ ~~264~~ 336 行）——ToolExecutor 七步生命周期（M2.9 `execute` +`approved` 通行证；**M2.10 +`reexecute(name, args, *, tool_call_id) -> ToolOutcome`**——恢复期窄入口：跳生命周期①–④（快照参数不再"不信"、write-ahead 已存在**绝不产生第二把幂等键**）、复用⑤⑥⑦以原 id 写终局闭合投影；工具缺失→原 id tool_error+ERROR 话术；读写都走此口（读安全=无副作用、写安全=原键下游去重）） |

⚠️ 本文件**没有** `from __future__ import annotations`（其余 5 个运行时文件都有）——给它加前向引用注解时留意。

**`OutcomeKind(StrEnum)`**（executor.py:24-31）——五结局，值进事件 payload 与回放断言：`ok / error / result_unknown / needs_approval / disabled`。

**`ToolOutcome`**（executor.py:34-41，frozen+slots）：`kind: OutcomeKind`、`tool_name: str`、`content: str`（回填给模型的观察结果，是对话的一部分）均必填；`tool_call_id: str | None = None`（write-ahead 之后才有）。

**`EventSink(Protocol)`**（executor.py:44-57）：`session_id`/`run_id` 两个 property + `async def append(event_type, payload) -> AgentEvent`——EventWriter 天然满足（append 是真协程 async def，与 GatewayLike.complete 的 def+AsyncGenerator 形成对照）。

**模块级辅助（内部）**：`_kwargs(args)`（executor.py:60-64，BaseModel 按 model_fields 摊开保留真类型——Decimal 不许降级 float）；`_elapsed_ms`（:67-68）；`_DIGEST_CHARS = 200`（:71）；`_digest(text)`（:74-76，单行摘要头）；`_truncate_to_budget(text, budget_tokens)`（:79-84，循环 ×0.8 缩短至 estimate_tokens ≤ 预算，尾接字面量 `"……[工具结果超预算已截断，完整原文在事件流]"`）。

**`ToolExecutor.__init__`**（executor.py:90-115）：

```python
def __init__(self, tools: ToolRegistry, events: EventSink, *,
             tenant_id: str, user_id: str, tenant_config: Mapping[str, Any],
             default_timeout_s: float = 30.0, fail_streak_limit: int = 2,
             result_token_budget: int = 3_000,
             summarize: Callable[[str], Awaitable[str]] | None = None,
             sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None
```

可变状态：`_fail_streaks: dict[str, int]`、`_disabled: set[str]`——**每个 run 一个实例**（连败账/禁用集的"本轮"=一次 run 寿命）。

**主入口 `async def execute(self, name: str, arguments_json: str) -> ToolOutcome`**（executor.py:117-222）方法级走读（编号对应 03 §4 生命周期）：

1. **查表**（:118-122）：`get(name) is None` → ERROR，content=`f"工具 {name} 不存在——可用工具：{available}"`（顿号连接 specs() 全名）。**幻觉工具名不进连败账**；
2. **禁用检查**（:123-128）：`name in self._disabled` → DISABLED，content 含"本轮已禁用（连续失败 {limit} 次）"；
3. **① 严格校验**（:130-143）：`json.loads` 失败 → `_fail`（记连败账）；非 dict → `_fail`；`args_model` 非 None 时 `model_validate(raw)`，ValidationError → `_fail`。口径：**lax 模式 + extra=forbid**（说明书答应的数字字符串要认，幻觉参数零容忍）。**args_model 为 None（手写 ToolDef）时跳过校验，args 就是原始 dict**；
4. **③ 风险闸门**（:145-153）：`risk_policy(args, tenant_config)`——谓词自身抛任何异常 → `_fail("风险评估失败，操作未执行（安全闸门 fail-closed）…")`（**评估不了绝不放行**，且记连败账）；返回 True → **NEEDS_APPROVAL，M2.4 到此为止：不开审批单、不写任何事件**，挂起流程归 M2.9；
5. **④ write-ahead**（:155-171）：先 `append(TOOL_CALL, {"tool_name", "args"})`（args 为 BaseModel 时 `model_dump(mode="json")`）——**插入成功是执行副作用的前置（C2），事件 id 即幂等键**；再构造 `ToolContext(..., tool_call_id=call_event.id)`；
6. **⑤ 执行 + 超时/重试**（:173-206）：`timeout_s = default if tool.timeout_s is None else min(tool.timeout_s, default)`（**取更严**）；`attempts_allowed = 1 + (tool.retries if READ else 0)`（**读可重试写恒 1 次**，与 ToolDef ⑤ 双保险）；`async with asyncio.timeout(timeout_s): await tool.handler(ctx, **kwargs)`。分支：
   - `TimeoutError` 且写 → 写 `tool_error`（error="执行超时，结果不明"）→ 返回 **RESULT_UNKNOWN**，content 封死重试、引导查询确认（X1）；
   - `TimeoutError` 且读：未耗尽 `await self._sleep(0.2 * attempt)` 重试；耗尽 → 写 `tool_error(f"执行超时（>{timeout_s:g}s）")` → `_fail`（带 tool_call_id）；
   - 其他 `Exception`：同样退避重试（读）/单次即败（写），耗尽 → 写 `tool_error(str(e))` → `_fail(f"工具执行失败：{e}")`；
7. **⑥⑦ 成功路径**（:208-222）：连败账清零 → `raw_text = json.dumps(result, ensure_ascii=False, default=str)` → payload 基础键 `tool_call_id / result（原文全量 X4）/ latency_ms（C31 豁免字段）/ retry_count = attempt-1` → 超预算时 `content = await self._shrink(raw_text, payload)`（否则 content=原文）→ `payload["digest"] = _digest(content)` → `append(TOOL_RESULT, payload)` → 返回 OK。

**内部方法**：`_fail(name, content, *, tool_call_id=None) -> ToolOutcome`（:224-231，连败 +1，达 `fail_streak_limit` 加入禁用集并在 content 追加宣告）；`_append_error(tool_call_id, error, started, retry_count) -> None`（:233-242）；`_shrink(raw_text, payload) -> str`（:244-262）——有 summarize 钩子：`f"（工具结果超预算，以下为摘要）{await summarize(raw)}"`，摘要仍超预算再硬截断，成功则 `payload["injected"]`+`normalization="summary"`；钩子抛任何异常 → `payload["summarize_error"] = str(e)`（**C34 降级留痕**）落硬截断；无钩子/失败 → `_truncate_to_budget`，`normalization="truncated"`。**fail-open**（增强层坏了往活里放，与闸门 fail-closed 反向）。

**执行器实际写入的事件 payload 键清单**（M2.5+ 消费，与 §5.3 投影契约对齐）：

| 事件 | payload 键 | 出处 |
|---|---|---|
| `tool_call` | `tool_name`、`args` | executor.py:158-164 |
| `tool_result` | `tool_call_id`、`result`、`latency_ms`、`retry_count`、`digest`；超预算另有 `injected`、`normalization`（`"summary"`/`"truncated"`）；摘要钩子失败另有 `summarize_error`。**预算内小结果不写 injected/normalization**（原文可确定重算，test_executor_normalize 钉死） | executor.py:210-221、244-262 |
| `tool_error` | `tool_call_id`、`error`、`latency_ms`、`retry_count` | executor.py:233-242 |

### 5.6 runtime.py（~~162~~ ~~170~~ 397 行）——门面与协议 + 锁 + 恢复单入口（M2.7 `6b7f22e` / M2.8 `553fb20` / **M2.9 `578b37f` 大改**）

M2.9 新增结构（run 签名仍未动）：`PrecheckHook` 类型（(tool_name, args)->None|拒绝原因，M3.9 注入）；`_maybe_lock`（lock=None 无锁直通——get_redis 单例跨 event loop 炸，M3.2 必须显式 build_session_lock）；`_match_call`/`_rebuild_working`（K2② 事件流重建器：llm_result 重建协议轮、tool_call 暂存 (name,args) 语义配对 result/error、injected 优先、弃置补话术、全部重过 wrap_untrusted——**保事实不保字节**）；`_identity_and_seed`/`_assemble`（run/resume 公共化——组装含 approvals/session_state 注入）；`_run_locked`（T1 idle→running fail-loud → open writer → loop.run）；`resume(spec, session_id, approval_id=None)`→`_resume_locked`（查单校验→PENDING 拒→**T3 CAS 输家安静零事件**→批准：decided 事件+precheck+execute(approved=True)+attach_event+重建+resume_run；拒绝/撤回/过期：对应事件+CANCELLED 终止+T4——轻量路径不组装 loop）。`__init__` +`lock`/`precheck`，预建 `_session_state`/`_approvals`。

**M2.10 增量**（`de39165`，559 行）：`__init__` +`settings`（测试注小值绕 lru_cache）+预建 `_leases`/`_lease_owner`；`_renew_lease_forever` 心跳（打空抛 LeaseLost 终态）；`_pump_with_lease` 租约伴飞（心跳独立 task/事件间查 done/正常耗尽才 release/异常不 release——LeaseLost 自毁零事件）；run/resume 的 T1/T3 之后 acquire（打空=SessionLockHeld，幽灵由 NULL 扫描兜住不回滚）；**`_recover_locked` 崩溃分诊四支**（approval_id=None 进锁内：尾终止仅修状态/悬挂工具 reexecute+fill/悬挂 LLM 与干净缝代码合流直续跑）；`_rebuild_working` 的 `approved_*`→**`fill_*` 泛化可 None**（审批与崩溃同构）。

命名分工（runtime.py:1-8）：**AgentRuntime = 对外门面（L3 只认识它）；AgentLoop（loop.py，§5.10）= 内部驱动，对 L3 不可见**。

```python
class GatewayLike(Protocol):                                        # 类体一字未动，见 §4.3
    def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]: ...

_SUMMARIZE_PROMPT: str                                              # 摘要指令常量（D13 例外：随消费者落本模块）
def _make_summarizer(view: GatewayLike, tenant_id: str, session_id: str) -> Callable[[str], Awaitable[str]]
    # D15 两枚摘要钩子的同源工厂：fast 档、不设 deadline（C1 由 L1 兜底）、失败不兜底
    # （C34 归 executor 硬截断 / builder 丢轮各自消化）；请求必带 session_id（回放匹配键）

class AgentRuntime:
    def __init__(self, gateway: GatewayLike, session_factory: SessionFactory, *,
                 cancel_event: asyncio.Event | None = None,         # P1 拍板：None=永不取消
                 run_id_factory: Callable[[], str] | None = None) -> None: ...  # X5：默认 uuid4().hex
    async def run(self, spec, session_id, user_input) -> AsyncIterator[AgentEvent]:
        # 签名一字未动（M2 对外契约）。组装九步（plans/m2.7 §4.2）：run_id 新生成 →
        # 读 sessions 行取身份（P2，无行 ValueError 零事件）→ token 种子扫事件流（D8）→
        # EventWriter.open → _Tap → ToolRegistry → ToolExecutor（I3 显式接线 timeout/budget
        # + tool_digest 道钩子）→ ContextBuilder（summary 道钩子——D15②）→
        # AgentLoop(main 视图) → async for 委托 yield
```

**要点**：`scoped_view` 在 run() 内**函数级局部 import**——replay.py 模块级引用本模块的
GatewayLike（replay.py:24），顶层互 import 会在初始化半途炸；四道视图 main/summary/tool_digest
各归其主（C10，guard 道留给 M2.8）。M2.9 的"先取会话锁"插入点 = EventWriter.open 之前。

### 5.7 不变量速查（最载重的 12 条，全带出处；完整论证见 retro-m2.md）

1. seq 单写者从 1 起、事务内递增；`uq_events_session_seq` 是并发最后防线；跨会话同 seq 是常态（store.py:96-98、events.py:66）；
2. write-ahead 先落盘：append 返回即 durably committed；事件 id=幂等键经 ctx 透传（C2，executor.py:156-157、store.py:290-292）；
3. 写工具不重试（类型层 tools.py:93-94 + 执行层 executor.py:176 双保险）；写超时=RESULT_UNKNOWN 封死重试（X1，executor.py:186-197）；
4. 执行器不向循环抛业务异常，一切结局编码为 ToolOutcome；基础设施异常（EventStoreUnavailable 等）裸传播（executor.py:5-6）；
5. 风险闸门 fail-closed（executor.py:145-150）vs 摘要钩子 fail-open + summarize_error 留痕（C34，executor.py:244-262）；
6. 事实与投影同生共死（同事务，ProjectionError 掀翻 append，store.py:185-188）；投影是事件的纯函数（store.py:277）；
7. 幽灵写入按 id 识别为成功（store.py:359-362）；围栏是终态零重试（store.py:363-365）；可重试白名单仅 OperationalError/InterfaceError（store.py:366-372）；
8. 审批全走 CAS，decide 查过期 fail-closed、cancel 不查、expire_due 可注入时钟（C7/C11，store.py:425-476）；approvals 不是投影；
9. 注入面全 frozen+slots（AgentSpec/LoopPolicy/ContextConfig/ToolDef/ToolContext/AgentEvent/ToolOutcome）——一次 run 内不可变；
10. 枚举字面量进事件 payload/DB 列/回放断言——**改值=破坏历史重放**，各有值快照测试先红；
11. 事件不带应用侧时间戳（C31）；latency_ms 是回放等价断言的豁免字段（executor.py:214）；
12. registry 插入序 → specs() 顺序 → 工具顺序进 LLMRequest（回放确定性一环，tools.py:169-171）；
13. **M2.7 增补（loop 侧，plans/m2.7 §4.5 I1–I10）**：yield 序≡seq 序且产出=落盘（I4，_Tap）；
    user_message 恒首事件（I5/D19）；llm_call 进程内终局必配对 llm_result（I6——M2.10 半截判据，
    `_fail_llm_step` 单点保证）；loop_terminated 恒 run 末事件（I7）；deadline_s 之外零超时包装
    （I2/C1）；闸门 #4 打断那次无 tool_call 事件（I8）；GATEWAY_REJECTED 无兜底话术（I9/C6）；
    阈值零魔法数字全来自 LoopPolicy（I1）。

### 5.8 context.py（~~348~~ ~~354~~ 364 行）——ContextBuilder 六层编译 + 滚动摘要（M2.5 新增 `c3eb8ce`；更新于 M2.8：`build` 增 keyword-only `entry_notice: str | None = None`——D9 打标通道，非 None 时以 system 条紧贴当前 user 之前注入，不占层预算由 C25 余量消化；**更新于复盘补丁三 `b628ce4`（2026-07-19）**：+模块常量 `_SUMMARY_PROMPT_SHARE = 0.5`——`_compose_history` 确定性收口内，有 uncovered 近轮排队时摘要至多占 allowed×份额（最新轮盲窗结构性关闭；无队列不设限）；事件仍存模型原话——落库 clip 与生成侧 max_tokens 议而被否，理由见 00 §6.3 补丁三行）

**模块常量六个**（context.py:34-43，值参与 M2.6 cassette 匹配——改动=改口径，plans/m2.5 D8/D12）：
`_MEMORY_HEADER` / `_RETRIEVAL_HEADER` / `_SUMMARY_HEADER`（`.format` 模板：turn_from/turn_to）/
`_FOLDED_TOOL_TEMPLATE`（`.format`：tool_call_id）/ `_CLIP_SUFFIX` / `_TURN_TEMPLATE`（D8 摘要输入逐轮格式）。
标头是层间分隔符；"不可信数据"包裹格式归 M2.8 `wrap_untrusted`。

**类型三件**：`ScoredSnippet`（:44-49，frozen+slots：text/score）；`MemoryProviderLike`（:52-58）
`async def fetch(*, tenant_id, user_id, query) -> Sequence[ScoredSnippet]`；`RetrievalProviderLike`（:61-64）
`async def search(*, tenant_id, query) -> Sequence[ScoredSnippet]`——两槽位 M2 恒 None，实装 M3.5（00 §10.1 #7）。

**私有辅助**（包外不许依赖）：`_message_tokens`（:67-72，D16：content + tool_calls 参数原文）；
`_clip`（:75-84，0.8 循环缩短 + `_CLIP_SUFFIX`，自带实现不引 executor 私有）；
`_pack_snippets`（:87-102，整条装入、装不下即停；by_score=True 记忆层降序 / False 检索层保序）；
`_Turn`（:105-114，frozen+slots：index/user/assistant/tokens——2026-07-11 拍板项 1 分轮口径，孤儿轮 assistant=""）。

**`ContextBuilder`**（:117-348，每 run 一实例，同 ToolExecutor 惯例）：

```python
def __init__(self, factory: SessionFactory, events: EventSink, *, config: ContextConfig,
             tenant_id: str, user_id: str, memory: MemoryProviderLike | None = None,
             retrieval: RetrievalProviderLike | None = None,
             summarize: Callable[[str], Awaitable[str]] | None = None,
             prewarm_ratio: float = 0.8) -> None                     # :123-144
async def build(self, *, system_prompt: str, user_input: str,
                working: Sequence[Message] = ()) -> list[Message]   # :146-187
```

- `build` 按 D12 次序：system → 记忆 → 摘要 → 旧轮 → 检索 → 当前 user → working；
  system 超预算 `ValueError`（D15 fail-loud）；provider 为 None 或层预算 0 = 关层且零调用（D14）；
  `summarize` 是唯一 LLM 触点（M2.7 组装方从网关构造 fast 档；不 import 网关）；
- `_fold_working`（:189-216）：D6 层聚合确定性折叠——只动 `role="tool"` 的 content（I4），全折仍超则照放+响亮日志；
- `_load_turns`（:218-256）：messages JOIN events **显式 onclause**（五表无 FK）、**排除当前 run_id**（D4，防 user_input 重复注入）、按 seq 升序分轮；
- `_summary_state`（:258-278）：D5 读最新一条 `summary_updated` 事件 →（摘要全文, turn_to），无摘要 (None, 0)——不读 sessions.summary 投影；
- `_compose_history`（:280-348）：触发式 `need > prewarm_ratio × budget_h`（need = 摘要 token + 未覆盖轮 token；budget_h = history_budget − user_input token，拍板项 2）；`k = ceil(未覆盖/2)`、单次 build 至多一摘（D9）；payload 三键 `{"summary", "turn_from": 1, "turn_to"}`（D7）；**try 只包 summarize**——C34 fail-open = 确定性丢轮 + `logger.warning` 留痕（拍板项 4，00 §2.2 C34 行细化），事件写入失败（EventStoreUnavailable/EventWriteFenced）裸传播；确定性收口：摘要超预算 `_clip`、旧轮从最新往回装、user_input 恒保留（D10/D11）。

**不变量**：I2 确定性（禁 import time/datetime/random，D17；双跑逐字节相同——test_build_is_deterministic 钉死）；
I5 只有 summarize 成功才写事件、至多一条；I6 覆盖游标单调、events 原文永不受影响；I7 历史层 ≤ budget_h。

### 5.9 replay.py（326 行）——录制回放基建（M2.6 新增；更新于 M2.6，commit `8bec868`）

import 面：标准库 + gateway.schema + runtime.events + runtime.runtime（零 SDK、零 DB/Redis——回放零 IO）。

**常量**：`FORMAT_VERSION = 1`（:25）；`Scope = Literal["main","summary","guard","tool_digest"]`（:27，C10 四道：
主循环/滚动摘要/守卫分类/结果摘要——D13 用 Literal 不用 StrEnum）；`SCOPES: tuple[Scope, ...]`（:31）；
`_EXEMPT_PAYLOAD_KEYS = frozenset({"latency_ms","duration_ms","usage","prompt_tokens","completion_tokens","expires_at"})`（:283-287，C31 顶层豁免）。

**格式层**（交付①）：
- `CassetteMismatch(RuntimeError)`（:34）——回放失配唯一出口，响亮不静默；
- `def request_digest(req: LLMRequest) -> dict`（:38-52）——D2 拍板四键 `{tier, message_count, tool_names, prompt_sha256}`，
  sha256 复用 cache.py:38-42 语义本体口径；**仅诊断，绝不参与匹配**；
- `CassetteEntry`（:55-60，frozen+slots）：`chunks: tuple[LLMChunk, ...]` + `request_digest`（默认 {}）；
- `Cassette`（:63-125，frozen+slots）：`session_id / scopes / format_version`；`load`（:71-98，防呆：版本/道名白名单/StopChunk 收尾→ValueError，坏 chunk→ValidationError 裸抛）；`dump`（:100-115）；`save`（:117-125，同目录 tmp + os.replace 原子落盘，UTF-8/LF/ensure_ascii=False——D11）。

**回放层**（交付②）：
- `SupportsScoped`（:129-133，@runtime_checkable）+ `def scoped_view(gateway, scope) -> GatewayLike`（:136-143，D10：有 scoped 出借视图、真实网关直通返回自身——组装方零类型判断）；
- `FakeGateway`（:146-206）：`__init__(cassette, *, start_cursors=None)`（越界/坏道名构造期 ValueError；start_cursors=M2.12 续跑偏移）；`complete ≡ scoped("main")`；`scoped(scope)`；`remaining() -> dict[str,int]`；`assert_exhausted()`（D14：M2.12 必调普通单测可选）；`_replay`（:187-206）——匹配三段：session 对→道内有条目→**游标先推进后 yield**（D6），失配 CassetteMismatch 带全诊断（期望/实际 session、道、已录数、第几次、digest）；
- `_FakeScopedView`（:209-217）——形状即 GatewayLike，游标记账在宿主。

**录制与归一化**（交付③）：
- `Recorder(inner: GatewayLike, session_id)`（:221-269）：`complete/scoped/cassette()/save`；`_record`（:251-269）——透传零改写、`done` 只在 async for 自然走完后置位（**半截流不入带**，D5）、`finally: await stream.aclose()` 归还连接、异常不吞不译；会话失配 ValueError（录制脚本 bug 快速失败）；`cassette()` 返回 frozen 快照（空道过滤）；
- `_RecorderScopedView`（:272-280）；
- `def normalize_event(event, *, id_aliases=None) -> dict`（:290-308）——输出 `{type, schema_version, payload}`；payload canonical JSON 往返（default=str）→ 顶层豁免键滴除 → tool_call_id/event_id 命中别名替换、不命中保留原值；
- `def normalize_events(events) -> list[dict]`（:311-325）——事件 id 按流序别名 e1..eN、approval_id 按首现 a1..aM；session_id/run_id/seq 不进输出（相对序由列表承载）。**M2.12"逐事件一致"与 M4.3 CI 的断言本体**（字段表 plans/m2.6 §3.3）。

**消费方**：M2.7/M2.8 全部循环与守卫测试（`AgentRuntime(FakeGateway(Cassette.load(p)))`）；M2.7 组装用 `scoped_view` 取 summary/tool_digest 道；M2.11 录制脚本（Recorder）；M2.12 强断言（normalize_events + assert_exhausted + start_cursors）；M4.3 CI。资产与重录流程：`tests/cassettes/README.md`。

---

### 5.10 loop.py（~~531~~ ~~596~~ 654 行）——AgentLoop 内部驱动（M2.7 `6b7f22e`；M2.8 `553fb20`；**M2.9 `578b37f`**：`__init__` +必填 `approvals`/`session_state`；`_Suspended` 哨兵；run 拆分——run=user_message+守卫→`_main_loop`（while 体原样）、+`resume_run(user_input, working)`（不写 user_message 不过守卫，M2.10 复用）；NEEDS_APPROVAL 分支=挂起链路（开单→approval_requested→T2→`_SUSPENDED` 干净收尾无 loop_terminated D2）；`_terminate` 尾部 T4 running→idle（失败 warning 不掀收尾））

**模块常量七个**（loop.py:44-56，D13 话术单点——测试断子串、M2.8 出口防护整体替换）：
`FALLBACK_MAX_ITERATIONS`（含"转人工"）/ `FALLBACK_STEP_FAILED` / `FALLBACK_BUDGET`（含"预算"）/
`FALLBACK_REPEATED` / `FALLBACK_PROTOCOL` / `PROMPT_REPEAT_BREAK`（`{limit}` 占位，②格式化）/
`PROMPT_PROTOCOL_RETRY`（role=user 注入，不动 system 层）。

```python
def canonical_json(arguments_json: str) -> str                       # D4：sort_keys 紧凑归一；坏 JSON 返原串
class _Tap:                                                          # EventSink 实现（D16）：append 委托 EventWriter + 待产队列
    async def append(event_type, payload) -> AgentEvent; def drain() -> list[AgentEvent]
@dataclass(frozen=True, slots=True)
class _LLMTurn: text / tool_calls / stop_reason / model / usage_prompt / usage_completion / cached
def _estimate_messages / _estimate_turn_output                       # D8 输入/输出侧估算（C25 一把尺，不 import context 私有）
def _discard_note(base, total, index) -> str                         # D20：工具序列中途终止的弃置留痕

class AgentLoop:                                                     # 每 run 一实例；阈值全来自 LoopPolicy（I1）
    def __init__(spec, gateway, events: _Tap, builder, executor, *,
                 tenant_id, token_seed, cancel_event=None,
                 guards: Guardrails | None = None) -> None           # M2.8：guards 未注入=纯规则库；gateway 已是 main 视图（D15/C10）
        # __init__ 内拼一次 self._system_prompt = spec.system_prompt + UNTRUSTED_NOTICE（D5，spec 原文不动）
    async def run(user_input) -> AsyncIterator[AgentEvent]           # user_message 首事件（I5/D19）→ 挂点①入口守卫 → while:
        # 挂点①（M2.8 通电）：check_input→HIGH 拒答（COMPLETED+REFUSAL_TEMPLATE，零 llm_call）/
        #   MEDIUM notice 经 build(entry_notice=…) 进 prompt / 审计 entry_audit_payload 非 None 即落 guardrail_triggered
        # 取消(#6)→轮数(#1,D17)→build(M2.5,+entry_notice)→预算预检(#3,D8)→llm_call→try _llm_step→llm_result→三分支
    def _classify(turn) -> "text" | "tools" | "violation"            # D7①②/D18；幻觉名归 _run_tools（D6）
    async def _llm_step(messages) -> _LLMTurn                        # 闸门#2 = deadline_s 传播（C1/I2）；M2.8 零改动（聚合定案）
    async def _run_tools(turn) -> TerminationReason | None           # D20 逐个：取消→重复(#4,D5)→幻觉(D6)→execute→
        # 挂点②（M2.8 通电）：五结局 content 一律 wrap_untrusted(source=f"tool:{name}") 后回填（X4：事件存原文）
    def _feed_tool_message(call, content) -> None                    # 包裹在调用方完成；打断话术不包（运行时模板非外部数据）
    async def _finish_text(turn) -> None                             # 挂点③（M2.8 通电）：output_guard 聚合 feed+flush→
        # hit→stream 审计+content=visible+SAFE_REPLY(guardrail_truncated)；final_check 非空→final 审计+整条替换；净→原文
    async def _fail_llm_step(reason, *, cause, detail, fallback)     # §4.4 终止型收尾：先配对 llm_result(failed)——I6 单点
    async def _terminate(reason, *, detail, fallback, cause=None)    # D14/I7：loop_terminated 恒末事件；payload 一律 .value
```

**六类异常矩阵**（run() 内 try/except 四组，loop.py:243-296）：Exhausted/Overloaded → `step_timeout`；
Budget/TenantQuota → `token_budget_exceeded`（cause=l1_request_budget/l1_tenant_quota——D9，L2 预检不带 cause）；
Rejected → `gateway_rejected` 零话术（C6/I9）；StreamInterrupted → 配对 interrupted 后 continue 作废重发（D10，
死因 `__cause__` 随 detail 留痕）。**不接 `GatewayError` 基类**（ProviderError 泄漏须裸炸——坑 5）；
`EventStoreUnavailable`/`EventWriteFenced` 不捕获、裸穿出 run()。

**M2.9 接缝**：`NEEDS_APPROVAL` 单点分支（`# M2.9:` 注释——K3 占位：回填继续、approvals 零行）。
~~**⚠️ M2.8 开工核对项**~~ **已收口（2026-07-17 M2.8③）**：出口挂点③定案为**聚合 feed**——改造收敛在
`_finish_text` 单点、`_llm_step` 零改动（流中提前退出会丢 ToolCallChunk/UsageChunk：工具轮误判+计量蒸发）；
聚合 ≡ 逐帧由 OutputGuard 确定性不变量保证（test_feed_granularity_deterministic 钉死），M3.10 SSE 穿同一实例行为不变。
防线命中一律 `COMPLETED` 终止（D10）；guardrail_triggered 审计事件全部由 loop 写（guardrails.py 零 EventSink）。

### 5.11 guardrails.py（564 行）——Guardrails v1（M2.8 新增，commit `553fb20`）

**接线不变量**：不持 EventSink、不写事件、不读时钟；只 import gateway.schema（运行时）+ runtime.GatewayLike（TYPE_CHECKING 破环——loop 顶层 import 本模块，真 import runtime 会成环）。

**模板常量三枚**（字面量进回放断言，定了不动）：`REFUSAL_TEMPLATE`（入口 HIGH 拒答文）/ `SUSPICION_NOTICE`（MEDIUM 打标，固定模板绝不插值用户内容）/ `SAFE_REPLY`（出口截断替换文，位于交付②分区）。

```python
class Suspicion(StrEnum): NONE/MEDIUM/HIGH                            # 值进 payload；比较必须走 _SEVERITY_ORDER
_SEVERITY_ORDER: dict[Suspicion, int]; def _worse(a, b) -> Suspicion  # StrEnum 裸 max 字典序=none>medium>high 陷阱
@dataclass(frozen=True, slots=True)
class InjectionRule: name / pattern / severity                        # __post_init__ 拒 NONE；名与档位是契约面
INJECTION_RULES_V1: tuple[InjectionRule, ...]                         # 15 条（复盘补丁四 `a138bbd` +tool_probe_en）（override/probe/hijack/jailbreak/bypass
                                                                      #  ×中英 + special_token/tool_probe/authority/encoded）
Classifier = Callable[[str], Awaitable[Suspicion]]                    # D2：注入 async 可调用（同 executor.summarize 模式）
def build_classifier(gateway, *, tenant_id, session_id=None,
                     deadline_s=10.0) -> Classifier                   # fast 档 guard 道；严格白名单解析，不合法即 ValueError
@dataclass(frozen=True, slots=True)
class EntryVerdict: suspicion / matched_rules / classifier_level / classifier_error
    @property refuse -> bool; @property notice -> str | None          # loop 消费面全部
class Guardrails:
    def __init__(*, rules=INJECTION_RULES_V1, classify=None)
    async def check_input(user_input) -> EntryVerdict                 # 规则全量扫描→分类器异常 fail-open（C34）→_worse 综合
    def output_guard(*, system_prompt, tool_names, owned_values=()) -> OutputGuard   # 每个文本出口新建实例

UNTRUSTED_NOTICE: str; def wrap_untrusted(text, *, source) -> str     # D5：防伪标记改写（插 ·）+ 三段拼接；事件恒存原文（X4）
@dataclass class PiiRule: name / pattern
PII_RULES_V1: tuple[PiiRule, ...]                                     # phone_cn/id_card_cn/email/address_cn；银行卡显式 v2（D13）
@dataclass class GuardHit: kind / rule / excerpt                      # kind ∈ system_prompt|tool_name|pii；excerpt 打码（D15）
def _find_boundary(buf, limit) -> int                                 # 硬终止符即界；ASCII '.' 仅后随空白（D12）
class OutputGuard:                                                    # 纯同步无 IO 无时钟；逐字符≡整段 feed（确定性不变量）
    def __init__(*, system_prompt, tool_names, owned_values=(), pii_rules=PII_RULES_V1,
                 min_fragment_chars=12, max_hold_chars=200)           # 构造期派生：片段集/环视工具名/owned 规范形/尾窗长
    def feed(delta) -> str                                            # 句界（前 max_hold 内）/定长伪句双规则切分；命中封死
    def flush() -> str; @property hit -> GuardHit | None
    def final_check(full_text) -> tuple[GuardHit, ...]                # feed 的确定性超集，纯查询；语义级检查挂点座位（v1 无实装）

def entry_audit_payload(verdict) -> dict | None                       # 需要审计才返回；disposition=refused|tagged|classifier_fail_open
def output_audit_payload(hit, *, stage) -> dict                       # stage=stream→truncated / final→final_replaced
```

**C23 归属**：PII 候选规范化（剔 `[-\s]`）后 ∈ owned 规范形集合 → 本人数据放行；仅字面等价，语义归属归 L3（M3.8 注入真实 owned_values）。**分类器开关**：`AgentSpec.entry_classifier`（默认 False，2026-07-17 拍板）——runtime.py 组装时按开关构造 guard 道分类器，规则库无条件在场。

---

## §6 DB schema 快照

### 6.1 迁移链（线性，2 个）

```
(base) → ab31f1ad346e（usage_ledger 计量账本，2026-07-06）
       → 74da3bf5d6ab（runtime 五表：事件事实源与投影，2026-07-09）= head
```

revision 事实源：`migrations/versions/ab31f1ad346e_usage_ledger_计量账本.py:15-16`（down_revision=None）、`migrations/versions/74da3bf5d6ab_runtime_五表_事件事实源与投影.py:16-17`（down_revision="ab31f1ad346e"）。head 时共 **6 张表**，**全部无外键**（引用完整性=应用层保证 + event_id 唯一约束防重）；所有 created_at 均 `DateTime(timezone=True)` + `server_default now()`（DB 时钟）；字符串主键全 String(64) 应用侧 uuid4().hex；枚举列全字符串无 CHECK/ENUM。

⚠️ **通用陷阱**：ORM 的 `default=`（run_state/lease_generation/recovery_count/status×2/retry_count/cached/cost）只在 SQLAlchemy 层生效——**迁移 DDL 中这些列 NOT NULL 且无 server_default**，绕过 ORM 的裸 SQL INSERT 必须显式提供。

**6.1-bis M3 迁移链更新（M3.12 整编；~~9~~ **8** 个——M4.0④b downgrade 往返实测 8 条回滚记录坐实，
原数错在下方列举从 `74da3bf5d6ab` 起算、漏了 M1 的 `ab31f1ad346e`）**：2→**8** 个（线性），
完整链首节点是 `ab31f1ad346e`（usage_ledger，M1）：
`ab31f1ad346e` → `74da3bf5d6ab` → `6304edbb4760`（tenants/users，M3.1）→ `c895f9007bf7`（**手写**：aegis_app 角色/GRANT+DEFAULT PRIVILEGES/五表 RLS 双子句，M3.3）→ `7fe5de25a9ca`（**手写**：CREATE EXTENSION vector 首句/documents+chunks/HNSW 余弦/两表 RLS，M3.4①）→ `c28efda87e6a`（documents +text 列，拍板 G）→ `f4b8d2a97c31`（**手写**：mock_orders+mock_write_ops+RLS，M3.7①）→ `d41be6a90c27`（**手写**：events AFTER INSERT 触发器 pg_notify，M3.10③）= head。

**6.8 M3 新增六表速览（M3.12 整编；列级事实以迁移实文件为准——§7 陷阱 9）**：

| 表 | 主键 | 关键列 | RLS | 备注 |
|---|---|---|---|---|
| tenants | id String(64) | name / config JSONB / token_budget_monthly BigInt（独立列） | ✓ | config 运行期只读（D12 种子即入口） |
| users | id String(64) | tenant_id / role（user/operator/admin）/ display_name | ✓ | 无凭证列（P7 mint_token 形态）、无 PII 列（拍板Ⅳ） |
| documents | id String(64) | tenant_id / source / **text**（拍板 G 原文居所）/ status / error / chunk_count / meta | ✓ | status=pending/processing/done/failed |
| chunks | id BigInt 自增 | document_id / tenant_id（冗余=WHERE+RLS 双吃）/ seq / text / **embedding vector(1024) 可空**（续传谓词）/ embedding_model | ✓ | UNIQUE(document_id,seq)；HNSW 余弦 |
| mock_orders | id String(64) | tenant_id / user_id（归属列）/ status 四态 / paid_amount Numeric(12,2) / items JSONB | ✓ | 归属校验与可退性事实源 |
| mock_write_ops | **idempotency_key** String(64) | kind / tenant_id / payload JSONB（duplicate 回放本体） | ✓ | PK=幂等键=#6 去重物质基础 |

九表 RLS 名单（P5）=以上六表 + sessions/approvals/usage_ledger；events/messages/tool_invocations 无 tenant_id 列不在名单（取舍档案 02 §7.2）。全部无 FK（P4）。

### 6.2 sessions（迁移2；ORM store.py:68-89）

| 列 | 类型 | nullable | 默认（层次） | 索引/约束 |
|---|---|---|---|---|
| id | String(64) | NOT NULL | 无 | PK |
| tenant_id | String(64) | NOT NULL | 无 | `ix_sessions_tenant_id` |
| user_id | String(64) | NOT NULL | 无 | |
| run_state | String(32) | NOT NULL | ORM=`"idle"` | `ix_sessions_reaper` 成员 |
| lease_owner | String(64) | NULL | 无 | |
| lease_expires_at | DateTime(tz) | NULL | 无 | `ix_sessions_reaper` 成员 |
| lease_generation | BigInteger | NOT NULL | ORM=0（C2 围栏：每次抢租 +1） | |
| recovery_count | Integer | NOT NULL | ORM=0（C9：超上限置 failed） | |
| summary | Text | NULL | 无（滚动摘要投影，M2.5 写入） | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | |
| updated_at | DateTime(tz) | NOT NULL | DB `now()` + **ORM `onupdate=func.now()`**（无 DB 触发器，裸 SQL UPDATE 不刷新） | |

复合索引 `ix_sessions_reaper (run_state, lease_expires_at)`——M2.10 reaper 扫描键。

### 6.3 events（迁移2；ORM store.py:92-109）

| 列 | 类型 | nullable | 默认 | 索引/约束 |
|---|---|---|---|---|
| id | String(64) | NOT NULL | 应用侧 uuid | PK |
| session_id | String(64) | NOT NULL | 无 | `uq_events_session_seq` 成员 |
| run_id | String(64) | NOT NULL | 无 | |
| seq | Integer | NOT NULL | 无 | `uq_events_session_seq` 成员 |
| type | String(32) | NOT NULL | 无 | |
| schema_version | Integer | NOT NULL | 无 | |
| payload | JSONB | NOT NULL | 无 | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | |

唯一约束 `uq_events_session_seq (session_id, seq)`（显式命名）。**events 无其他普通索引**——session_id 前缀查询靠该约束底层索引。

### 6.4 messages（迁移2；ORM store.py:112-123）

| 列 | 类型 | nullable | 默认 | 索引/约束 |
|---|---|---|---|---|
| id | BigInteger autoincr | NOT NULL | 自增 | PK |
| session_id | String(64) | NOT NULL | 无 | `ix_messages_session_id` |
| event_id | String(64) | NOT NULL | 无 | **UNIQUE（未命名**，PG 自动名通常 `messages_event_id_key`；写 drop_constraint 前先查实名） |
| role | String(16) | NOT NULL | 无（user/assistant 仅代码约定） | |
| content | Text | NOT NULL | 无 | |
| token_usage | Integer | NULL | 无 | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | |

### 6.5 tool_invocations（迁移2；ORM store.py:126-142）

| 列 | 类型 | nullable | 默认 | 索引/约束 |
|---|---|---|---|---|
| id | BigInteger autoincr | NOT NULL | 自增 | PK |
| session_id | String(64) | NOT NULL | 无 | `ix_tool_invocations_session_id` |
| event_id | String(64) | NOT NULL | 无 | **UNIQUE（未命名）**；= tool_call 事件 id = 幂等键 |
| tool_name | String(64) | NOT NULL | 无 | |
| args | JSONB | NOT NULL | 无 | |
| status | String(16) | NOT NULL | ORM=`"running"` | |
| result_digest | Text | NULL | 无 | |
| error | Text | NULL | 无 | |
| latency_ms | Integer | NULL | 无 | |
| retry_count | Integer | NOT NULL | ORM=0 | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | |
| finished_at | DateTime(tz) | NULL | 无 | |

### 6.6 approvals（迁移2；ORM store.py:145-165）

| 列 | 类型 | nullable | 默认 | 索引/约束 |
|---|---|---|---|---|
| id | String(64) | NOT NULL | 应用侧 uuid（进事件 payload 与审批 API） | PK |
| session_id | String(64) | NOT NULL | 无 | `ix_approvals_session_id` |
| tenant_id | String(64) | NOT NULL | 无 | `ix_approvals_tenant_id`（M3.9 坐席同租户校验） |
| tool_name | String(64) | NOT NULL | 无 | |
| args | JSONB | NOT NULL | 无（参数快照，防 TOCTOU） | |
| status | String(16) | NOT NULL | ORM=`"pending"` | `ix_approvals_expiry` 成员 |
| operator_id | String(64) | NULL | 无 | |
| event_id | String(64) | NULL | 无（执行后回填，**无唯一约束**） | |
| expires_at | DateTime(tz) | **NOT NULL** | 无 | `ix_approvals_expiry` 成员 |
| decided_at | DateTime(tz) | NULL | 无 | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | |

复合索引 `ix_approvals_expiry (status, expires_at)`——M3.9 到期扫描键。**刻意不挂 tool_invocation 外键**（审批③先于 write-ahead④）。

### 6.7 usage_ledger（迁移1；ORM metering.py:33-51）

| 列 | 类型 | nullable | 默认 | 索引/约束 |
|---|---|---|---|---|
| id | BigInteger autoincr | NOT NULL | 自增 | PK |
| request_id | String(64) | NOT NULL | 无 | `ix_usage_ledger_request_id` |
| tenant_id | String(64) | NOT NULL | 无 | `ix_usage_ledger_tenant_id` |
| session_id | String(64) | NULL | 无 | |
| tier | String(16) | NOT NULL | 无 | |
| provider | String(32) | NOT NULL | 无 | |
| model | String(64) | NOT NULL | 无 | |
| prompt_tokens / completion_tokens | Integer | NOT NULL | 无 | |
| cached | Boolean | NOT NULL | ORM=False | |
| cost | Numeric(12,6) | NOT NULL | ORM=`Decimal("0")` | |
| created_at | DateTime(tz) | NOT NULL | DB `now()` | `ix_usage_ledger_created_at` |

复合索引 `ix_usage_tenant_created (tenant_id, created_at)`——月度预算闸门主查询路径。

---

## §7 测试地图

### 7.1 对账表（`uv run pytest --collect-only -q` 于 2026-07-10 在 commit `014ec21` 实测；~~**合计 301**~~）

> **更新于 M2.5**（commit `c3eb8ce`，2026-07-11 实测）：+#27/#28 两文件，合计 **329**。
> **更新于 M2.7**（commit `6b7f22e`，2026-07-11 实测）：+#33–#36 四文件共 36 测（#17 改写不改数），合计 **401**。
> **更新于 M2.8**（commit `553fb20`，2026-07-17 实测）：+test_guardrails_entry.py（13 函数 33 测：攻击 ×14 + 良性 ×8 展开，含 wrap 两条）/ +test_guardrails_output.py（16 函数 18 测：PII ×3 展开）/ +test_guardrails_loop.py（7 测）；test_events.py 快照改 15 类不改数。合计 **459**（+58）。
> **更新于 M2.9**（commit `578b37f`，2026-07-17 实测）：+tests/test_locks.py（15 测：Redis 11+Failover 4）/ +tests/test_locks_pg.py（7 测：C4 三件套+dead_r 停 Redis）/ +tests/runtime/test_suspend_resume.py（14 测：必保路径/三重互斥/闸门#6 三触发源）；test_spec.py +1（approval_ttl_s 参数化）；test_loop_gateway_errors.py DyingFactory 配额 2→3；test_loop_termination.py **删** K3 占位测试（行为被挂起链路取代，−1）。合计 **495**（净 +36）。
> **更新于 M2.10**（commit `de39165`，2026-07-17 实测）：+tests/runtime/test_lease.py（15 函数 17 测：steal 前置 ×3 展开；含重入/NULL 兜底两条偏差钉）/ +tests/runtime/test_loop_recovery.py（7 测：自毁零事件/半截读写原键/工具缺失/半截 LLM/尾终止修状态/新 run_id 接 seq）/ +tests/workers/{test_reaper 8, test_celery_app 4}；test_events 快照 16 类不改数；DyingFactory 配额 3→4。**断言纪律**：reaper 测试对全库扫描函数一律过滤式断言（全局相等会被库中真实残留污染——test_reaper 文件头立此纪律）。合计 **531**（净 +36）。
> **更新于 M3.12 整编（commit `8cc58ba`，2026-07-28 实测）**：M2.11–M3.12 增量不再逐行入下表（M3 各步新增文件与数目见 §0-bis 各节与 00 §7.3 对账行）；毕业实测合计 **852**（M2 毕业 548 → 复盘补丁 553 → M3 +299）。下表保持 M2.10 时点快照供历史参照。

| # | 测试文件 | 收集数 | 备注（函数数≠收集数处为 parametrize 展开） |
|---|---|---|---|
| 1 | tests/test_config.py | 7 | |
| 2 | tests/test_tokens.py | 4 | |
| 3 | tests/gateway/test_base.py | 6 | |
| 4 | tests/gateway/test_schema.py | 9 | |
| 5 | tests/gateway/test_openai_compat.py | 24 | respx 桩驱动 |
| 6 | tests/gateway/test_anthropic.py | 12 | |
| 7 | tests/gateway/test_resilience.py | 12 | |
| 8 | tests/gateway/test_breaker.py | 15 | 需本地 Redis（db9） |
| 9 | tests/gateway/test_ratelimit.py | 12 | 需本地 Redis |
| 10 | tests/gateway/test_cache.py | 9 | 需本地 Redis |
| 11 | tests/gateway/test_metering.py | 9 | 需本地 PG |
| 12 | tests/gateway/test_router.py | 36 | 全假件，无外部依赖 |
| 13 | tests/gateway/test_factory.py | 2 | |
| 14 | tests/runtime/test_spec.py | 27 | 17 函数（2 个 parametrize ×6/×6） |
| 15 | tests/runtime/test_tools.py | 25 | 16 函数（parametrize ×5/×5/×2） |
| 16 | tests/runtime/test_events.py | 9 | 6 函数（parametrize ×3/×2） |
| 17 | tests/runtime/test_runtime.py | 2 | mypy 结构化兼容锁 + run 签名快照（M2.7 改写：NotImplementedError 断言→inspect 签名锁） |
| 18 | tests/runtime/test_store.py | 10 | 需 PG |
| 19 | tests/runtime/test_event_store.py | 7 | 需 PG；幽灵写入/围栏/退避白名单 |
| 20 | tests/runtime/test_projections.py | 11 | 需 PG；"投影失败掀翻事件"是灵魂断言 |
| 21 | tests/runtime/test_approvals.py | 8 | 需 PG；CAS 输赢/fail-closed/注入时钟 |
| 22 | tests/runtime/test_tool_decorator.py | 13 | |
| 23 | tests/runtime/test_registry.py | 8 | 含演示工具集三形态断言 |
| 24 | tests/runtime/test_executor.py | 9 | 前厅：校验/闸门/连败 |
| 25 | tests/runtime/test_executor_exec.py | 9 | 执行核心：write-ahead/超时/X1（**学命名与风格的首选样例**） |
| 26 | tests/runtime/test_executor_normalize.py | 6 | 规范化：摘要/截断/digest |
| 27 | tests/runtime/test_context_layers.py | 15 | M2.5①：四简单层/折叠/确定性双跑/合计不变量（需 PG——`_builder` 注入 db_session_factory） |
| 28 | tests/runtime/test_context_summary.py | 13 | M2.5②：需 PG；分轮/触发/D7 三键/C34 fail-open/事实源不动 |
| 29 | tests/runtime/test_replay_cassette.py | 10 | M2.6①：纯内存+tmp_path 零容器；格式防呆/原子落盘/digest 四键 |
| 30 | tests/runtime/test_replay_fake_gateway.py | 11 | M2.6②：纯内存；四道游标/prompt 漂移不 miss/D6/协议静态锁 |
| 31 | tests/runtime/test_replay_recorder.py | 8 | M2.6③：纯内存；透传/半截流不入带/aclose 归还/端到端往返 |
| 32 | tests/runtime/test_replay_normalize.py | 7 | M2.6③：纯函数；C31 字段表逐行双向断言 |
| 33 | tests/runtime/test_loop_flow.py | 11 | M2.7①②③：需 PG；文本/工具两轮链、I3 接线两条、X5 双 run 接续、D20 多调用（含 `_CaptureGateway` 捕获替身与 slow_lookup/bulk_export 专用工具） |
| 34 | tests/runtime/test_loop_termination.py | 14 | M2.7②③：需 PG；闸门 #0(D18)/#1/#2 工具半边(X1)/#3(D8 预检+种子)/#4×3/#5×3/#6 + K3 占位 + D6 幻觉 + reason 值集 |
| 35 | tests/runtime/test_loop_gateway_errors.py | 7 | M2.7③：§4.4 矩阵逐行（C6 零话术/I6 配对/D10 作废重发/infra 裸穿——`_DyingFactory` 先健康后断连） |
| 36 | tests/runtime/test_loop_adversarial.py | 4 | M2.7④：文件 cassette 驱动（tests/cassettes/adversarial_*.json）；四类失控有界终止 |
| — | tests/conftest.py、tests/runtime/conftest.py | 0 | 夹具文件不贡献测试 |
| | **合计（~~26~~ ~~28~~ ~~32~~ 36 test 文件 + 2 conftest = ~~28~~ ~~30~~ ~~34~~ 38 文件）** | ~~**301**~~ ~~**329**~~ ~~**365**~~ **401** | 分组：gateway 146 / runtime ~~144~~ ~~172~~ ~~208~~ **244** / 根 11 |

核对方法：仓库根跑 `uv run pytest --collect-only -q`，末行须为 ~~`301`~~ ~~`329`~~ ~~`365`~~ `401 tests collected`（M2.8 起为"401 + 新增区间"，权威基线 = 00 §6.3 最末行）。⚠️ 交接方本地无 PG/Redis 时 DB/Redis 测试整批 skip（收集数不变、通过数变少）——先 `docker compose -f deploy/docker-compose.yml up -d`。

### 7.2 关键 fixture 清单

**tests/conftest.py（全仓共享，5 个）**：

| fixture | 行号 | 提供 | 要点 |
|---|---|---|---|
| `r` | :13-25 | 真实 Redis 客户端 | `AEGIS_TEST_REDIS_URL` 默认 `redis://localhost:6379/9`（**db9 专用测试库，开跑前 flushdb**）；本地连不上 skip / CI（`os.environ.get("CI")`）raise |
| `dead_r` | :28-40 | 指向 `redis://localhost:6399/0`（无人监听）的客户端 | 超时 0.1s、`Retry(NoBackoff(), 0)`——模拟 Redis 整体不可用 |
| `db_conn` | :46-66 | 带外层事务的 AsyncConnection | `AEGIS_TEST_DATABASE_URL` 默认与生产同库；先 `Base.metadata.create_all` 兜底建表（正式演进走 alembic）；结束 `trans.rollback()` 一笔勾销 |
| `db_session_factory` | :69-78 | 绑在 db_conn 上的 `async_sessionmaker(join_transaction_mode="create_savepoint", expire_on_commit=False)` | 被测组件真实 commit（只提交 SAVEPOINT）、外层回滚吞掉——**形状即 store.SessionFactory**，EventWriter/ApprovalStore/MeteringRecorder 测试全靠它 |
| `db_session` | :81-84 | 上述工厂开的单个 AsyncSession | |

**tests/runtime/conftest.py（runtime 专属）**——模块级定义**演示工具集三形态**（import 时经 @tool 装饰，名字已是 ToolDef）：

1. `demo_order_query`（:18-21）：**读**工具，`(ctx, order_id: str) -> dict`，返回 `{"order_id", "status": "已发货", "paid": 350}`；
2. `demo_refund_apply`（:28-31）：**写 + 风险闸门**，`(ctx, order_id: str, amount: int) -> dict`；谓词 `_demo_refund_needs_approval`（:24-25）= `args.amount > tenant_config.get("approval_threshold", 200)`；返回含 `"idempotency_key": ctx.tool_call_id`（write-ahead 键透传实证）；
3. `demo_ticket_create`（:34-37）：**写 + 显式豁免**（risk_exempt=True），`(ctx, title: str) -> dict`。

fixture `demo_registry`（:40-43）：`ToolRegistry([query, refund, ticket])`——每测试全新实例，注册序即 specs() 序。执行器三个测试文件各自定义 `TENANT_CFG = {"approval_threshold": 200}`。

fixture `make_session`（:46 起，M2.7 增）：建 sessions 行的帮助协程（P2 前置——`AgentRuntime.run` 开头读行取身份，无行拒绝起跑；默认 `tenant_id="t-a"` / `user_id="u-1"`），loop 系四个测试文件全靠它。

---

## §8 未接线挂点清单（M2.5+ 逐个接电；每项：位置 / 当前状态 / 谁来接电）

| # | 挂点 | 位置 | 当前状态 | 谁来接电 |
|---|---|---|---|---|
| 1 | `AgentRuntime.run` 门面 | runtime.py + loop.py（§5.6/§5.10） | ~~签名定死、anext 抛 NotImplementedError~~ **✅ M2.7 已接电**（commit `6b7f22e`）：run() 组装九步委托 AgentLoop，签名一字未动（签名快照测试锁定） | ~~M2.7~~ ✅ 已接电 |
| 2 | ContextBuilder 与六层预算 | spec.py:83-118（ContextConfig 已有）；`sessions.summary` 列（store.py:85）；**context.py（M2.5 新增，§5.8）** | ~~只有预算类型与 `input_total` 对账口；无编译器；summary 列无写入方~~ **✅ M2.5 已接电**（commit `c3eb8ce`）：ContextBuilder 落地，`_compose_history` 写 `summary_updated` → 投影落列 | ~~M2.5~~ ✅ 已接电；检索/记忆两槽位实装 **M3.5**（00 §10.1 #7）；~~M2.7 组装时传 `spec.context_config` 并从网关构造 summarize 钩子~~ ✅ M2.7 已兑现（I3 接线 + summary 道钩子） |
| 3 | `summarize` 摘要钩子 | executor.py:101（`__init__` 形参，默认 None）；context.py:131 同款槽位；**runtime.py `_make_summarizer`（M2.7 生产实现）** | ~~生产实现不存在，只有测试假钩子~~ **✅ M2.7 已接电**：`_make_summarizer` 两枚同源——tool_digest 道→executor / summary 道→builder，经 `scoped_view` 分道（C10，坑 14：两钩子勿共用一道）；fast 档、不设 deadline、失败归各自 C34 路径 | ~~M2.7~~ ✅ 已接电；~~guard 道留 M2.8~~ **✅ M2.8 已接电**（`build_classifier` 走 guard 道视图，按 `spec.entry_classifier` 开关构造——默认关） |
| 4 | `SubAgentPolicy` | spec.py:121-127 | 唯一成员 DISABLED，运行时零消费逻辑 | **v2**（先过 ADR-002，让 len==1 快照测试红） |
| 5 | `NEEDS_APPROVAL` 后续（HITL 挂起） | executor.py + loop.py `_run_tools` | ~~命中闸门只返回 outcome~~ **✅ M2.9 已接电**（`578b37f`）：挂起链路全通——开单（expires_at=policy.approval_ttl_s）→ approval_requested → T2 → `_SUSPENDED` 干净收尾；恢复走 `resume()` 单入口 | ~~M2.9~~ ✅ 已接电 |
| 6 | `ApprovalStore.create` 生产调用方 | store.py；loop.py 挂起链路 | ~~原语齐全，只有测试在写~~ **✅ M2.9 已接电**：loop 挂起链路调 create；decide/cancel/expire_due 由测试与（将来）M3.9 API 层消费；+`attach_event` 审计链回填 | ~~M2.9~~ ✅；`expire_due` 的 reaper 调度仍 **M3.9** |
| 7 | FakeGateway / cassette | runtime.py:24-25；**replay.py（M2.6 新增，§5.9）** | ~~不存在~~ **✅ M2.6 已接电**（commit `8bec868`）：Cassette/FakeGateway/Recorder/scoped_view/normalize_events 全套 + tests/cassettes 资产与重录流程 | ~~M2.6~~ ✅ 已接电；真实录制 M2.11、CI 流水线 M4.3、中断注入包装器 M2.12（测试侧道具，不进格式） |
| 8 | 会话锁 / 租约列群 | `core/locks.py`（§3.4-bis）+ `LeaseStore`（§5.3） | ~~只有表结构~~ **全部 ✅**：锁原语 M2.9（`184a485`/`ab4fcd8`）；**租约列读写 ✅ M2.10**（`2af377c`：LeaseStore 五方法 CAS + `_pump_with_lease` 续租伴飞 + reaper steal——C2 协议一/二接电，LeaseLost 自毁零事件有测试） | ~~M2.9/M2.10~~ ✅ 全接电 |
| 9 | `recovery_count` 与 `RunState.FAILED` | store.py + workers/reaper.py | ~~列与枚举在、无人加、failed 无进入路径~~ **✅ M2.10 已接电**（`3df455a`）：steal_expired +1 / release 归零 / 超限 T5 transition 判赢（恰一次）→ clear_lease → `recovery_abandoned` 审计——C9 闭合，M2.2 偏差登记项销账 | ~~M2.10~~ ✅ |
| 10 | LoopPolicy 五阈值消费方 | spec.py:61-66；loop.py（§5.10）；runtime.py I3 接线 | ~~闸门逻辑在未来 AgentLoop；两处靠默认值巧合相等~~ **✅ M2.7 已接线**：六道闸门全在 loop.py 消费（零魔法数字 I1）；`ToolExecutor(default_timeout_s=policy.tool_step_timeout_s, result_token_budget=context_config.tool_results_budget)` 显式传参，I3 两条行为测试钉死（0.05s 超时/200 预算生效） | ~~M2.7~~ ✅ 已接线 |
| 11 | 其余 ~~11~~ ~~10~~ ~~5~~ 1 类事件的生产端 | events.py:21-39 | 生产端已就位 **14** 类（15 类中）：ToolExecutor 写 tool_call/tool_result/tool_error；ContextBuilder 写 summary_updated；AgentLoop 写 user_message/llm_call/llm_result/assistant_message/loop_terminated/guardrail_triggered/**approval_requested（✅ M2.9 挂起链路）**；**resume 单入口写 approval_decided/approval_cancelled/approval_expired（✅ M2.9）**；仅缺 handoff | ~~M2.5/M2.7/M2.8/M2.9~~ ✅ / **M3.8**（handoff） |
| 12 | `ToolInvocationRecord.event_id`/`ApprovalRecord.event_id` 审计回填链 | store.py `attach_event` | ~~回填逻辑不存在~~ **ApprovalRecord.event_id ✅ M2.9 已接电**（attach_event CAS，批准执行后回填 tool_call 事件 id，测试钉死）；ToolInvocationRecord.event_id 自 M2.4 起即由 write-ahead 填充 | ~~M2.9~~ ✅ |
| 13 | 网关异常六类的 L2 捕获 | errors.py:52-61；loop.py:243-296 异常矩阵 | ~~gateway 包外零消费者~~ **✅ M2.7 已接线**：try/except 四组（step_timeout / token_budget_exceeded 带 cause 分层 / gateway_rejected 零话术 C6 / interrupted 作废重发 D10）；不接 GatewayError 基类防 ProviderError 泄漏被吞（坑 5） | ~~M2.7~~ ✅ 已接线 |
| 14 | 月度预算读路径 | config.py:55 + router.py:225-234 | ~~读 Settings 静态值~~ **✅ M3.1③ 已接电**（`43db3a5`）：`monthly_budget_resolver` 注入缝三态 + factory 注入 TenantDirectory.monthly_budget（60s 缓存）——resolver=None 落回静态值，既有测试零改动 | ~~M3.1~~ ✅（#13/#22 闭合） |
| 15 | pgvector | compose 镜像 pgvector/pg16 已就位 | ~~无任何 vector 列、无 `CREATE EXTENSION vector` 迁移~~ **✅ M3.4① 已接电**（`7fe5de25a9ca`：迁移首句 CREATE EXTENSION IF NOT EXISTS + chunks.embedding vector(1024) + HNSW 手写；真实链路已过——检索消费方 **M3.5** 接） | ~~M3.4~~ ✅ |

---

## §9 scripts / deploy / CI / 迁移工具清单

### 9.1 scripts/（~~7~~ ~~8~~ ~~9~~ ~~13~~ ~~24~~ **27** 个；用途取自各文件 docstring）——**更新于 M4.0④b**（M3.12 整编时 24；M4.0④b +3=`experiment_kill9_ingest`/`fake_embedding_server`/`kill9_celery_app`。**全量索引与依赖前提以 `scripts/README.md` 表格为准**——那里逐脚本记了里程碑/是否真实调用/依赖，本表仅历史快照）

| 脚本 | 用途一句话 |
|---|---|
| `scripts/experiment_kill9_recovery.py` | M2.10④：真 kill 子进程→reaper 认领→单入口续跑，四断言凭证落 `reports/m2_kill9_recovery.txt`；结束自清理演示行（防污染全库扫描类测试）；不进 CI |
| `scripts/debug_raw_call.py` | 调试：打印百炼原始响应完整信封与正文（花真钱，一次 <0.01 元） |
| `scripts/demo_event_loop.py` | 教学演示：三个模拟 SSE 流 + 一个同步阻塞反派，观察事件循环时间戳 |
| `scripts/experiment_fault_injection.py` | M1 毕业实验：30% 注入 ×1000 次网关韧性实测 + 熔断演示（需 Redis+PG 在跑） |
| `scripts/loadtest_ratelimit.py` | 限流精度压测（时序敏感断言不进 CI，以本脚本报告为准；用 db9） |
| `scripts/reconcile_usage.py` | 对账：usage_ledger 四维聚合（租户/模型/天/会话），裸 SQL |
| `scripts/smoke_gateway.py` | 完整网关（build_gateway）冒烟：只声明档位，模型由路由决定（需本地 Redis） |
| `scripts/smoke_tool_call.py` | 真实工具调用验证（直连 OpenAICompatProvider 不走路由；~~qwen-plus~~ ~~qwen3.7-plus~~ qwen-plus——2026-07-17 模型池重构随池同步） |
| `scripts/record_long_dialog.py` | M2.11：40 轮长对话真实录制（真实调用例外①）——五埋点/预算三上限/六道自检先于落盘；产出 `tests/cassettes/long_dialog.json` + 凭证；剧本与判据（TURNS/SPEC/PROBES/check_recall）供 `test_long_dialog_benchmark.py` 经 importlib 复用（I1）；重录流程见 cassettes README §3（必须"干净录制"） |
| `scripts/smoke_agent_real.py` | M2.12②：真实冒烟（真实调用例外②，M2 配额收官）——三不变量（幂等键/seq/合法终止）+ 成本顶 ¥0.10 写死；凭证 `reports/m2_real_smoke.txt` |
| `scripts/demo_hitl_suspend_resume.py` | M2.12②：HITL 必保路径演示（零真实调用）——挂起→decide CAS（二次恰 False）→恢复单入口续跑；凭证 `reports/m2_hitl_demo.txt` |
| `scripts/demo_degraded_redis_lock.py` | M2.12②：停 Redis 锁降级实录——build_session_lock 生产组装，并发两取恰一互斥；凭证 `reports/m2_degradation_redis.txt` |
| `scripts/demo_stop_pg_midrun.py` | M2.12②：停 PG 半途实录——退避耗尽 EventStoreUnavailable 明确终止 + write-ahead 核验式；抓出 OS 级白名单盲区（修复 `98e2549`）；凭证 `reports/m2_degradation_pg.txt` |

运行前提：**cwd = 仓库根**（.env 相对路径加载，§3.1 陷阱），`uv run python scripts/xxx.py`。凭证产物在 `reports/`（现有 m1_fault_injection.txt / m2_ratelimit_retest.txt / m2_ratelimit_degraded.txt / m2_kill9_recovery.txt（M2.10）/ m2_long_dialog_recording.txt（M2.11））。

**9.1-bis M3 脚本增量（M3.12 整编；用途/真钱/前置详表=仓库 `scripts/README.md` 功能族索引，此处只列名）**：
`mint_token.py`（M3.1）／`calibrate_retrieval_threshold.py`（M3.5，calibrate_ 族）／`measure_intent_latency.py`（M3.6，measure_ 族）／`demo_tools_acceptance.py`（M3.7）／`demo_chat_acceptance.py`（M3.8）／`demo_hitl.ps1`+`demo_hitl_helper.py`（M3.9，PS1 **UTF-8 with BOM**）／`record_l3_cassettes.py`（M3.11，兜底信号集单一事实源）／`perf_m3.py`+`fallback_rate_m3.py`（M3.12）；`seed_demo.py` 升 M3.11 正式版（tenants/users/orders/语料摄取四面）。合计 13→**23**。

### 9.2 CI（.github/workflows/ci.yml，唯一工作流，~~67~~ **98** 行；M4.0③ 加三道门后）

触发：push(main) + pull_request；`permissions: contents: read`。单 job `quality` on ubuntu-latest，service 容器：redis:7-alpine（6379）+ pgvector/pgvector:pg16（5432，用户/密码/库均 aegis），各带健康检查（5s×10）。步骤序列（顺序即门的顺序；**M4.0③ 起 9→12 道**，新增 gitleaks/pip-audit/alembic check——详见 §0.1 基线三元组下方的门数说明）：

| # | 步骤 | 命令 |
|---|---|---|
| 1 | 检出代码 | `actions/checkout@9c091bb2… # v7.0.0`（action 钉 SHA） |
| 2 | 安装 uv | `astral-sh/setup-uv@d31148d6… # v8.3.0`，enable-cache |
| 3 | 安装依赖 | `uv sync --frozen`（锁不同步直接失败） |
| 4 | 格式检查 | `uv run ruff format --check .` |
| 5 | 代码检查 | `uv run ruff check .` |
| 6 | 类型检查 | `uv run mypy .` |
| 7 | 分层检查 | `uv run lint-imports` |
| 8 | 数据库迁移 | `uv run alembic upgrade head`（CI 真实执行） |
| 9 | 测试 | `uv run pytest` |

关键事实：CI **未设置 DATABASE_URL/REDIS_URL**——alembic 与测试全靠 config.py 默认值与 service 容器口令一一对应，**改任何一侧必须同步另一侧**；测试夹具凭 `CI` 环境变量区分"必须在"（raise）与本地（skip）；无 coverage 门、无构建发布、无矩阵。

### 9.3 docker-compose（deploy/docker-compose.yml，项目名 `aegis`）

| 服务 | 镜像 | 容器名 | restart | 端口 | 卷 | healthcheck |
|---|---|---|---|---|---|---|
| postgres | pgvector/pgvector:pg16 | aegis-postgres | unless-stopped | **仅回环** `127.0.0.1:5432:5432` | pg_data | pg_isready，5s/3s/×10 |
| redis | redis:7-alpine | aegis-redis | unless-stopped | `127.0.0.1:6379:6379` | redis_data | redis-cli ping，5s/3s/×10 |

`restart: unless-stopped`（非 always）保住"手动 docker stop 看降级"演示口径（00 §10.1 #31）。**无应用容器**（应用在宿主机跑；容器化归 M4.7）。启动：`docker compose -f deploy/docker-compose.yml up -d`。

### 9.4 alembic 使用方式

- **URL 不来自 alembic.ini**：ini 里 `sqlalchemy.url = driver://user:pass@localhost/dbname` 是占位符，env.py:17 用 `config.set_main_option("sqlalchemy.url", get_settings().database_url)` 运行时覆写；
- **模型注册靠手工 import**（env.py:9-10）：`import aegis.gateway.metering` + `import aegis.runtime.store`（noqa: F401，导入即进 Base.metadata）——**新增含 ORM 模型的模块必须同步加一行，否则 autogenerate 认为表被删了**；`target_metadata = Base.metadata`（env.py:28）；
- 在线模式 async（`async_engine_from_config` + NullPool + `connection.run_sync`）；
- 常用命令（仓库根）：升级 `uv run alembic upgrade head`；新迁移 `uv run alembic revision --autogenerate -m "<标题>"`（生成后**必须人工审阅** DDL）；
- **测试不跑 alembic**：conftest 用 `Base.metadata.create_all` 兜底（对已存在表是 no-op、不做 ALTER）——ORM 与迁移不一致时两条路径都不报错，一致性靠 autogenerate 空 diff 人工对账（仓内无此 CI 门）；
- `.env.example` 全文 5 行：APP_ENV=dev、DASHSCOPE_API_KEY 占位、ANTHROPIC_API_KEY 注释可选、DATABASE_URL/REDIS_URL 本地用默认值无需设置。

---

## 附：发现的上游文档/代码注释问题（登记不擅改；处置建议随各步计划）

1. **tests/runtime/test_events.py:14 注释写"13 类值快照"**，实际断言集合与 EventType 均为 14 类（C8 增 summary_updated 后注释未同步）——M2.5 顺手修注释（一行，不动断言）；
2. **executor.py 缺 `from __future__ import annotations`**（其余 5 个运行时文件都有）——不影响运行；给它加前向引用注解时须留意；
3. **`BreakerLike.allow` 协议返回类型 `str`**（router.py:52）vs 实现返回 `Decision` 字面量（breaker.py:24）——结构兼容成立但假件失去字面量约束；改协议属 L1 范围，M2 不动；
4. **`GatewayOverloadedError` 路径 probe 令牌不归还**（router.py 候选环 except 不含它）——半开期最坏多等 probe_ttl(120s) 自愈；疑似已知取舍但源码注释未明说，M4.0 复核（与 00 §10.1 #29 同族）;
5. **tokens.py docstring "CJK≈1 token/字"宽于实现**（仅 U+4E00–U+9FFF 基本区，扩展区/假名/韩文按 4 字符/token）——±15% 余量口径消化，M2.5 复用时知悉即可；
6. **上游缺 usage 时合成 0-token UsageChunk**（openai_compat.py:144）并被如实记账——账本 0 token 行 ≠ 真 0，对账/预算消费时注意；
7. **00 §6.3 M2.2 行提及"C9 failed 进入路径留 M2.10"**与 store.py:42 注释一致，无冲突——列此仅为确认已对账。
