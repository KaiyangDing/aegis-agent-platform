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

## 实验与压测（数字凭证的产地）

| 脚本 | 用途 | 诞生 | 真钱 | 前置 |
|---|---|---|---|---|
| `experiment_fault_injection.py` | 30% 注入 ×1000 韧性实测 + 熔断演示（M1 毕业实验） | M1 | 否（打桩） | PG/Redis |
| `loadtest_ratelimit.py` | 限流精度压测（时序断言不进 CI，以本脚本报告为准） | M1 | 否 | Redis（db9） |
| `record_long_dialog.py` | 40 轮长对话真实录制（M2 真实调用例外①）；六道自检先于落盘 | M2.11 | **是**（预算写死） | 全套 + `.env` key |

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
