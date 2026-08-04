# Aegis — 多租户客服 Agent 平台

> **"LLM 是 CPU，Aegis 是操作系统。"**（ADR-001）
> 一个证明"造平台"而非"用平台"的工程项目：不依赖 Agent 框架，自研运行时解决
> 循环失控、工具不可信、上下文爆炸、上游故障、并发与成本、不可观测、不安全七类工程问题。

## 三层架构

```
L1 gateway   LLM 网关（与 Agent 无关）：统一协议 / 档位路由+fallback / 熔断限流 / 精确缓存 / 计量预算
L2 runtime   Agent 运行时（与业务无关）：事件溯源事实源 / 六道终止闸门 / 上下文预算编译 /
             工具七步生命周期 / HITL 挂起恢复 / 崩溃租约恢复 / 确定性录制回放 / 护栏
L3 apps      客服业务：多租户(JWT+RLS 四层隔离) / RAG 摄取检索 / 意图分诊 / 业务工具 /
             审批闭环 / SSE 双通道
横切 obs     治理：trace API / Prometheus 指标 / 零 token 回放回归门 / 离线评测(LLM-as-judge) / 成本实验
```

依赖方向严格单向（import-linter 在 CI 强制）：`api|workers → apps|obs → runtime → gateway → core`。

## 快速启动（Windows 本地开发形态）

```powershell
docker compose -f deploy/docker-compose.yml up -d   # PG16+pgvector / Redis7（端口只绑 127.0.0.1）
uv sync                                             # Python 3.13 + uv（绝不用 pip 装包）
Copy-Item .env.example .env                         # 按需填 DASHSCOPE_API_KEY / JWT_SECRET
uv run alembic upgrade head
uv run python scripts/seed_demo.py                  # 两租户演示种子（含语料真实摄取，<¥0.02）
uv run python scripts/mint_token.py u-a1            # 签发演示 JWT
uv run uvicorn aegis.api.main:create_app --factory  # http://127.0.0.1:8000/chat 演示页
```

测试与质量门（CI 十二道，全程零真实 LLM 调用）：

```powershell
uv run pytest -q          # 全量测试
uv run mypy . ; uv run ruff check . ; uv run lint-imports
```

## 文档索引（`docs/`，M4.7 迁入——文档变更走提交）

| 入口 | 内容 |
|---|---|
| [docs/00-master-plan.md](docs/00-master-plan.md) | **执行主文档**：M0→M5 步骤计划 / 全局口径表 / 横切清单 / 交付对账 |
| [docs/02-architecture.md](docs/02-architecture.md) | 三层架构 / 表结构 / 安全矩阵 / 降级清单 |
| [docs/03-agent-runtime-design.md](docs/03-agent-runtime-design.md) | L2 运行时详设（循环/上下文/工具/事件/回放契约） |
| [docs/08-code-map.md](docs/08-code-map.md) | 代码地图与接口事实源快照 |
| [docs/adr/](docs/adr/) | 7 篇架构决策记录 |
| [docs/atlas.md](docs/atlas.md) | 全景复习图册（图/闸门总表/数字凭证卡/已知边界） |
| [docs/eval-rubrics.md](docs/eval-rubrics.md) | 离线评测判据（三类用例/五档锚定/spot-check 流程） |
| [reports/](reports/) | 简历数字凭证（每个对外数字都有实测凭证与口径说明） |

## 实测数字一览（口径与凭证见 `reports/` 对应文件，绝不写无凭证数字）

- 故障注入 30%×1000 次成功率 **100%**（P99 2.42s）；限流精度误差 **0.76%**
- 评测集 40 用例稳定基线 **38/40=95%**（两条已知失败有名有姓；judge spot-check ±1 一致率 100%）
- 档位路由降本 **vs-strong 74.7% / vs-standard 18.9%**（双基线；80 条全唯一集）
- 精确缓存降本 **21.9%**（30% 复述假设显式声明；请求级全命中自检 60/60）
- kill -9 崩溃恢复 / 停 Redis / 停 PG 降级实录各有四断言凭证

> 本 README 为 M4.7 初稿（C43）；架构图与终稿归 M5.5。
