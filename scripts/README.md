# scripts/ 索引（按功能族分组；文件不搬家，命名前缀即分类）

> 维护约定：新脚本入列时在此登记一行；前缀选自下表既有族（新族先想清楚它是什么工种）。
> 通用前提：**在仓库根执行**（`.env` 相对 cwd 加载——08 §3.1 陷阱）；`uv run python scripts/<名>.py`。
> 「真钱」列 = 是否发生真实 API 调用（红线口径见 00 各里程碑章首）。

## 种子与凭证（日常最常用）

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `seed_demo.py` | 两租户+8 用户种子（upsert 幂等；#21 种子即初始化入口，改配置=改本文件重跑） | M3.1① | 否 | PG + `alembic upgrade head` |
| `mint_token.py <user_id>` | 签发演示 JWT（查库定角色，TTL 按角色档——P7 无登录端点形态） | M3.1② | 否 | PG + 种子 + `.env` JWT_SECRET |

## 冒烟（改完链路先跑它）

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `smoke_gateway.py` | 完整网关冒烟（build_gateway，档位路由决定模型） | M1 | **是**（<0.01 元） | Redis + `.env` key |
| `smoke_tool_call.py` | 真实工具调用（直连适配器不走路由） | M1 | **是**（<0.01 元） | `.env` key |
| `smoke_agent_real.py` | Agent 全链路真实冒烟：三不变量+成本顶 ¥0.10 写死（M2 真实调用例外②） | M2.12 | **是** | PG/Redis + `.env` key |

## 演示实录（毕业实验与降级凭证，产物进 reports/）

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `demo_hitl_suspend_resume.py` | HITL 挂起→decide CAS→恢复续跑（零真实调用） | M2.12 | 否 | PG/Redis |
| `demo_degraded_redis_lock.py` | 停 Redis 锁降级实录：并发恰一互斥 | M2.12 | 否 | PG（Redis 手动停） |
| `demo_stop_pg_midrun.py` | 停 PG 半途实录：退避耗尽明确终止 + write-ahead 核验 | M2.12 | 否 | PG（中途手动停） |
| `experiment_kill9_recovery.py` | kill -9 → reaper 认领 → 续跑，四断言凭证；结束自清理演示行 | M2.10 | 否 | PG/Redis |
| `experiment_kill9_ingest.py` | **摄取链路** kill -9 四断言（#48 的"配置改了≠行为验证了"）：崩溃现场 PROCESSING+部分回填 / 消息不丢仍在 unacked / 越过 visibility_timeout 后 restore→重新消费至 DONE / 账本重复 ≤1 批。**实测发现**：Windows 上 celery 恒无 event loop（`should_use_eventloop` 排除本平台，与 pool 无关）→ unacked **永不自动重投**，故本脚本手动触发 restore，自动那一环挂 M4.7 Linux 复验 | M4.0④b | 否（假 embedding 服务顶替上游） | PG/Redis + 迁移 + `fake_embedding_server.py` 在跑 |
| `fake_embedding_server.py` | 确定性假 embedding 端点（`DASHSCOPE_BASE_URL` 指向它即可，生产代码零改动）：同文本恒同向量、协议面按 `EmbeddingClient._post_once` 逐条对齐、`FAKE_EMBED_DELAY_S` 给 kill 留窗口、每批调用落跨进程账本 | M4.0④b | 否（**它就是零真实调用的实现手段**） | 无（独立进程） |
| `kill9_celery_app.py` | kill -9 实录专用 Celery app：复用生产 app 与全部生产任务体，只把 `visibility_timeout` 由默认 3600s 调到 60s（实验时间尺度，同 M2.9/M2.10 注入时钟手法） | M4.0④b | 否 | 由实录脚本自动拉起 |
| `demo_tools_acceptance.py` | 工具五件真实链路三幕：Agent 查单退款 / 双击去重(#6) / 对抗③统一话术；演示订单 upsert 自带+自清理 | M3.7④ | **是**（<¥0.01，单次 Agent run） | PG/Redis + 迁移 + 种子 + `.env` key |
| `demo_chat_acceptance.py` | 完整客服链路三幕（生产装配原件 create_app）：租户 A 查单退款直执 / **FAQ 守卫实证**（首问直答·跟进问进主 Agent）/ 租户工具面白名单 | M3.8③ | **是**（<¥0.02，≈5 次调用） | PG/Redis + 迁移 + **M3.8③ 版种子** + `.env` key |
| `demo_hitl.ps1` | **HITL 业务闭环六段**（M3.9 验收面，走 HTTP API+curl.exe）：挂起提示 / 对抗④ 403 / 批准→#8 重跑→执行→续跑（重复决策 409）/ **TOCTOU 否决实证**（批准落锤前订单被退→不执行）/ 超时（时钟注入+生产对账任务体）/ 撤回；会话随机后缀防残留 | M3.9⑤ | **是**（<¥0.05，≈8–12 次调用） | PG/Redis + 迁移 + 种子 + **uvicorn 在跑** + `.env` key |
| `demo_hitl_helper.py` | demo_hitl.ps1 证据面帮手：seed（订单复位 paid）/ mark-refunded（TOCTOU 制造）/ expire（时钟注入）/ sweep（直调生产 expire_approvals 任务体）/ status（会话·审批·事件·订单四面取证，owner 视角） | M3.9⑤ | 否（sweep 的踢恢复走终止路径零 LLM） | PG/Redis + 迁移 + 种子 |

## 实验与压测（数字凭证的产地）

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `experiment_fault_injection.py` | 30% 注入 ×1000 韧性实测 + 熔断演示（M1 毕业实验） | M1 | 否（打桩） | PG/Redis |
| `loadtest_ratelimit.py` | 限流精度压测（时序断言不进 CI，以本脚本报告为准） | M1 | 否 | Redis（db9） |
| `record_long_dialog.py` | 40 轮长对话真实录制（M2 真实调用例外①）；六道自检先于落盘 | M2.11 | **是**（预算写死） | 全套 + `.env` key |
| `record_l3_cassettes.py` | L3 行为五盘 cassette 录制（隔离×2/预算触发/HITL 批准续跑/工具正例；自检先于落盘、五盘全过才统一落盘；产物 `tests/cassettes/l3/` + `reports/m3_l3_recording.txt`——M4.3 CI 回归输入） | M3.11③ | **是**（预算写死 40 调用/10 万 token/¥2，实跑 <¥0.10） | 全套 + 种子 + 语料已摄取 + `.env` key |
| `calibrate_retrieval_threshold.py` | 检索阈值真实语料校准（§3.5 留白定值；首测 0.35 维持、分离窗 [0.31,0.45]；M3.11 语料扩容后复跑复核。新前缀族 calibrate_=数值留白定值工种） | M3.5④ | **是**（<¥0.001，查询清单钉死上限） | PG + 语料已摄取 + `.env` key |
| `measure_intent_latency.py` | 意图分类延迟实测（四类探针+缓存命中重复问；首测新鲜 901–2357 ms/命中 8 ms/4-4 全中；M3.12 复测同口径。新前缀族 measure_=轻量延迟实测工种，M3.12 性能口径/M5.2 口径②扩展位） | M3.6② | **是**（<¥0.001，探针清单钉死上限） | PG/Redis + 种子 + `.env` key |
| `perf_m3.py` | M3 性能两口径实测（00 §7.2 第 2 条）：缓存命中二连发 <50ms（3 组中位）/未命中首 token standard 档 20 样本 P50/P95 <2.5s；超设计值=修正记录不改口径；产出进 reports/m3_acceptance.md | M3.12② | **是**（≤26 调用 <¥0.05，上限 30/¥0.50 写死） | PG/Redis + 种子 + `.env` key |
| `fallback_rate_m3.py` | 知识库外兜底触发率实测（00 §7.2 第 4 条）：分母=seed.jsonl okb 5 条（I1）、主 Agent 生产装配直驱+真实检索；判定=兜底信号集（record 脚本同源）∨ ticket_create；≥95%，未触发逐条归因全文 | M3.12② | **是**（≈5–10 调用 <¥0.02，上限 15/¥0.20 写死） | PG/Redis + 迁移 + 种子 + 语料已摄取 + `.env` key |

## 对账与调试

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `reconcile_usage.py` | usage_ledger 四维聚合对账（裸 SQL） | M1 | 否 | PG |
| `debug_raw_call.py` | 打印百炼原始响应完整信封（调适配器用） | M1 | **是**（<0.01 元） | `.env` key |
| `demo_event_loop.py` | 事件循环教学演示（与业务无关） | M0 | 否 | 无 |

## 为什么不按里程碑分目录（2026-07-24 定案）

里程碑是**出生日期**不是**工种**——M5 要找对账脚本时不该先回忆它生于 M1。功能族分类
（本表）+ 各脚本 docstring 里的里程碑锚点 + 08 §9.1 快照表，三处已覆盖"何时生/干什么/怎么用"。
文件搬家的代价：docs/00/08/plans/retro 与 reports 凭证里的路径引用全体失效、命令肌肉记忆作废。
若 M4/M5 后数量超 ~25，再按**功能**建子目录（demo/ experiments/ …），随 M5.3 整编做——绝不按里程碑。
