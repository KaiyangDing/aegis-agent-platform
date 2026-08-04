# 15 分钟 Demo 分镜（M5.4 交付①）

> 排练实况：2026-08-04 完整跑 4 遍全绿（含首遍原型），逐段计时见文末登记表。
> 操作列 = `scripts/demo_m5_highlights.py` 子命令 + 原生 docker/curl——观众看到的就是可复跑命令。
> 主线预算 15 min（含 1 min 缓冲）；机器时间实测 <1 min，时长吃在讲稿，超时预案压高光3。

**前置（开演前完成，不占主线）**：compose 真实上游栈在跑（`deploy/docker-compose.yml`，api×3+nginx）；
`.env` 带 key；`uv run python scripts/demo_m5_highlights.py prep`（订单复位 + 5 枚角色 token 落
`.demo_tokens.json`，gitignore）。

## 排片总表（00 §9.1 四高光 + M5.3 布景）

| 段 | 内容 | 预算 |
|---|---|---|
| 开场 | 架构一页 + 3 副本布景 | 1.5 min |
| 高光1 | 故障注入：30% 照答 + 熔断毫秒拒 | 3.5 min |
| 高光2 | 断点续跑全弧：挂起→kill 副本→断连批准→事实面闭环 | 4 min |
| 高光3 | 多租户隔离四连 | 3 min |
| 高光4 | trace 还原 + 回放门（#27 正式高光） | 2 min |
| 缓冲 | 提问/超时余量 | 1 min |

## 开场（1.5 min）

| 操作 | 预期画面 | 讲稿一句话 | 失败预案 |
|---|---|---|---|
| 展示 README 架构图（mermaid） | 三层 L3→L2→L1 + 横切 | 「LLM 是 CPU，Aegis 是操作系统：网关管供应商，运行时管确定性，业务层管客服」 | 图挂了→口述三层 |
| `docker compose -f deploy/docker-compose.yml ps` | migrate 完成退出；api×3 **无宿主端口**、nginx 127.0.0.1:8080 唯一入口、pg/redis/worker/beat 全 Up | 「api 无状态才敢 ×3：状态全在 PG/Redis，这是后面 kill 副本的底气」 | 副本不齐→`docker compose -f deploy/docker-compose.yml up -d --scale api=3` |
| `curl -s http://127.0.0.1:8080/healthz` | `200` | 「入口只有 nginx 一个」 | 非 200→查 `docker logs aegis-nginx-1` |

## 高光1 · 故障注入与熔断（3.5 min）

| 操作 | 预期画面 | 讲稿一句话 | 失败预案 |
|---|---|---|---|
| `uv run python scripts/demo_m5_highlights.py h1` | ① 30% 注入 3 连发全部照常回答（1–3s/次）② 100% 注入单候选：熔断打开后拒绝 **1–5ms**（GatewayExhausted）③ 结尾自动清熔断键 | 「同一套重试+档内 fallback 消化了 30% 的上游故障；候选被打死时熔断毫秒级拒绝——不烧上游预算也不拖用户延迟」 | 30% 段偶现失败行→讲稿预答"0.3^重试次数 的小概率，重跑即可（幂等）" |
| （讲稿预答 C5/D9，不敲命令） | — | 「容灾实录里熔断**全程不开**是预期：熔断按 provider 记账，档内 fallback 成功即清零失败计数——这暴露 provider 粒度对单模型坏死的钝感，v1 显式接受，v2 细化到 provider:model」（凭证 `reports/m5_failover_qwen_tier.txt`） | — |

⚠️ 纪律：h1 直连网关但与容器**共用同一 Redis**，段尾清键由脚本保证；中途 Ctrl-C 则手动清
（`aegis:cb:bailian*`），否则高光2 真实流量被熔断误拒。

## 高光2 · 断点续跑全弧（4 min）

| 操作 | 预期画面 | 讲稿一句话 | 失败预案 |
|---|---|---|---|
| `uv run python scripts/demo_m5_highlights.py h2` | ① 退款 300>阈值 200 → `approval_pending`，用户侧即断连 ② `docker kill aegis-api-3` ③ 幸存副本上 decide、**3s 读超时主动断连** ④ 事实面 kill 后 ~5s 落地：`approval_decided/tool_result/loop_terminated` + 订单 `refunded` ⑤ 用户 GET /stream 回放整段含 done 帧 | 「审批状态在 PG 不在进程里：kill 掉一个副本、再拔掉批准那条连接，事实面照样闭环——run 的生死跟连接的生死解耦，这就是 crash-only」 | ① decide 快速完整返回（答案命中精确缓存，续跑快于 3s 窗）→讲稿转"续跑快过人手拔线"；要强制断连剧情就把金额改 310 绕开缓存 ② 150s 未落地→beat 60s 对账扫描兜底，`uv run python scripts/demo_hitl_helper.py status <sid>` 四面取证 |
| `docker start aegis-api-3` | 副本回归 3/3 | 「手动 kill 不触发 unless-stopped 自启——Docker 的语义：手工停的容器不替你做主重启」 | `docker ps` 核对 |

## 高光3 · 多租户隔离四连（3 min；超时压缩至 90s）

| 操作 | 预期画面 | 讲稿一句话 | 失败预案 |
|---|---|---|---|
| `uv run python scripts/demo_m5_highlights.py h3` | ① B 租坐席裁 A 租**真单**=403 ② 跨用户回放**真会话**=404 ③ user 查 trace=403（三拒零 LLM）④ B 租户问"灵犀降噪耳机 Pro 保修"：走自家语料兜底、自报"云杉生鲜超市"家门，A 的保修条款一字未现 | 「两种拒绝哲学：staff 面越界**点名 403**、user 面**隐身 404** 不泄露存在性；第④连是检索不可见+缓存不命中——缓存键含租户语境，B 永远吃不到 A 的缓存」 | 超时→只看三拒（<5s，零 LLM），第④连转答疑素材 |

## 高光4 · trace 还原与回放门（2 min）

| 操作 | 预期画面 | 讲稿一句话 | 失败预案 |
|---|---|---|---|
| `uv run python scripts/demo_m5_highlights.py h4` | ① 坐席 trace API 还原高光2 会话：runs=2、events≈11–15，每步耗时/工具参数可见、展示层脱敏 ② `tests/replay` **15 passed**（约 5s） | 「同一条事件流三用：断点续跑的物质基础、坐席排障的 trace、CI 里的零 token 回放门——录制昨天的事故现场，今天确定性重放做事件序列等价性断言」 | pytest 环境慢→开演前先跑一遍留屏 |

## 彩排清单（不进 15 分钟主线，跑一次留凭证）

**#14 会话锁降级复验**（00 §10.1 "M5.4 演示复验"）——2026-08-04 已复验 ✅：

```
docker stop aegis-redis && uv run python scripts/demo_degraded_redis_lock.py && docker start aegis-redis
```

实录：前置确认 Redis 不可达（TimeoutError，redis client 重试回溯属预期画面）→ 并发两协程
恰一个获锁（PG advisory 承接互斥）→ 赢家释放/输家重取/再释放全 True →
凭证 `reports/m2_degradation_redis.txt`；栈复活后 healthz=200。
停 PG 线为可选项不复跑（#15 归位 M2.12/M4.0，实况为准）。

## 排练计时登记（00 §9.2 "实测 ≤15 分钟"的凭证；机器时间，不含讲稿）

| 遍次（2026-08-04） | 预备 | 高光1 | 高光2 | 高光3 | 高光4 | 合计 |
|---|---|---|---|---|---|---|
| 第 2 遍（排练器） | 6.4s（共享） | 10.4s | 10.3s | 7.8s | 6.5s | 35.0s |
| 第 3 遍（排练器） | 同上 | 10.1s | 4.6s | 4.8s | 6.6s | 26.2s |
| 第 4 遍（`demo_m5_highlights.py all`，正式形态） | 7.3s | 10.0s | 10.4s | 19.6s | 6.5s | 53.9s |

判定：四遍全绿（第 1 遍原型暴露计量配对缺陷后修正）；机器时间 <1 min，主线 15 min
预算全部留给讲稿与画面停留——**实测 ≤15 分钟成立**（高光3 时长随 LLM 答复长度浮动 5–20s，
已含在预算内）。

## 排练期发现与修正（凭证不掺假的留痕）

1. **(58) 家族第三例**：裸网关驱动缺 `tenant_context` 配对 → 计量被 usage_ledger RLS
   静默拒收（fail-open 空账）。首遍排练暴露后，`experiment_breaker_recovery.py` /
   `experiment_qwen_tier_failover.py` 同病同治，**两实验已重跑出真账版报告**
   （首跑曾分别记 ¥0.0000 / ledger=[]，报告内已注记）。
2. `docker kill` 的副本不会被 unless-stopped 自启（Docker 对手动停止的语义）——
   高光2 收尾必须手动 `docker start`，分镜已列。
3. 精确缓存可使续跑快于 3s 断连窗（第 3 遍实测）——断连剧情的退化路径已写进失败预案。
