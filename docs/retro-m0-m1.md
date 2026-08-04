# M0/M1 复盘：从空仓库到 150 测试的 LLM 网关

> **基线**：commit `f176b1e`（2026-07-07，M2.0 收尾时点），150 测试全绿。
> **读法**：这不是设计文档的重抄——02/04 讲"打算做什么"，本文对着真实代码讲"实际做成了什么、
> 每个决策为什么、边界在哪"。面试前把 §3（旅程）和 §5（哲学）读到能脱稿。
> **配套**：架构见 02；步骤对账见 00 §4/§5/§6.3；面试题索引见 05 §3。

---

## 1. 全景地图（代码 ↔ 职责 ↔ 测试）

```
aegis/
├── core/                    # 与网关无关的底座
│   ├── config.py    (77 行) # 全局配置唯一事实源：SecretStr / 启动即炸 / lru_cache 单例
│   ├── db.py        (39 行) # SQLAlchemy async 引擎+会话工厂（三处连接池之三）
│   ├── redis.py     (17 行) # Redis 客户端懒单例
│   └── tokens.py    (17 行) # token 估算器（M2.0 新增，M2.5 复用）
└── gateway/                 # L1：与 Agent 无关，服务任意上层
    ├── schema.py            # 统一协议：LLMRequest / LLMChunk 判别联合（可序列化=回放的地基）
    ├── errors.py            # 两级异常：ProviderError 家族（内部）/ Gateway 六类（对 L2 契约）
    ├── providers/
    │   ├── base.py          # Provider 协议 / 共享 httpx 客户端(三段超时) / 错误翻译表 / 消毒
    │   ├── openai_compat.py # 百炼适配器：SSE 解析、[DONE] 哨兵、tool-call 增量组装
    │   └── anthropic.py     # Anthropic 适配器（完整实现、桩测试；差异点即统一协议的存在理由）
    ├── resilience.py        # 受控重试：首块窗口 + 双闸超时 + 指数退避满抖动 + 双重预算
    ├── breaker.py           # 熔断：Redis 三键状态机（TTL 即迁移）+ SET NX 探测互斥 + 本地降级
    ├── ratelimit.py         # 出站限流：Lua 令牌桶（Redis TIME 时钟）+ 本地降级桶
    ├── cache.py             # 精确缓存：租户前缀 key + 语义本体哈希 + 完整性守卫 + 自愈
    ├── metering.py          # 计量：usage_ledger ORM + Decimal 成本 + 月度聚合读路径
    ├── router.py            # 总装：档位路由 / fallback / 故障注入 / deadline / 六类契约终局
    └── factory.py           # 组装在边缘：真实依赖只在这里聚合
```

**测试分布（150 = 133 M1 + 17 M2.0）**：router 36 / openai_compat 24 / resilience 12 /
anthropic 12 / breaker 11 / schema·ratelimit·metering·cache 各 9 / config 7 / base 6 /
tokens 4 / factory 2。测试目录镜像源码分层（§2.2 测试纪律）。

---

## 2. M0 底座：五个提交里的工程态度

| 交付 | 关键决策与为什么 |
|---|---|
| uv 工程 | `pyproject.toml` + `uv.lock` **入库**——可复现构建是交付物的一部分；CI 用 `uv sync --frozen`，锁不同步直接失败 |
| 分环境配置 | pydantic-settings：环境变量 > .env > 默认值；密钥一律 `SecretStr`（repr/日志自动打码）；**默认空 key 是刻意的**——CI 与零真实调用的测试无需配密钥 |
| docker-compose | pgvector/pg16 + redis7；**端口只绑 127.0.0.1**（不写时 Docker 默认 0.0.0.0，公共 Wi-Fi 同网段可直连你的 Redis——它是网关的整个状态平面）；健康检查 + 数据卷 |
| GitHub Actions | 六道门按序：ruff → mypy(aegis) → **import-linter** → **alembic upgrade head（CI 真跑迁移）** → pytest；PG/Redis service containers；**action 钉完整 SHA**（tag 可被上游重指恶意提交）；`permissions: contents: read` 最小权限；dependabot 开启 |
| import-linter | layers 契约 `apps → runtime → gateway → core` 写进 pyproject，**CI 强制单向依赖**——"三层不互相渗透"不是口号是红灯 |

M0 的面试一句话：**工程底座的每一项都在回答"错误配置/坏依赖/反向 import 应该在哪一刻被发现"——答案永远是"越早越好、启动时炸好过凌晨三点炸"。**

---

## 3. 一次请求的完整旅程（router.py::complete 的装配顺序）

```
LLMRequest
  ↓ ① 路由防御          candidates 缺档 → 立刻 GatewayExhausted（不消耗任何配额）
  ↓ ② deadline 换算      deadline_s → 绝对单调钟（只管"首块前"，M2.0/C1）
  ↓ ③ 精确缓存（最外圈）  命中 → 盖 cached 章回放 + 记零成本账 → 结束
  ↓ ④ 月度预算闸门        fail-open：账本读挂了放行并告警（成本护栏≠安全边界）
  ↓ ⑤ 单请求预算闸门      估算 token > 预算 → BudgetExceeded（确定性纯函数，M2.0/C25）
  ↓ ⑥ 租户出站限流        候选环外——换供应商换不掉租户身份；耗尽 → TenantQuotaExceeded
  ↓ ⑦ 沿候选链循环：
  |    deadline 预检（剩余 < min_attempt_budget → 停止换路）
  |    → 熔断闸门 allow/probe/deny（deny 连限流队都不排——秒拒的意义）
  |    → 供应商限流 wait_take（排不上队 → 换下一站，probe 令牌必须归还）
  |    → [故障注入器 error/hang/midstream]
  |    → 受控重试 complete_with_retry（见 §4-resilience）
  |    → 适配器真实调用
  ↓ ⑧ 成功收尾            on_success 清熔断账 → 完整流入缓存 → 计量记账（失败只告警）
  ↓ ⑨ 失败终局三段        budget_out → "首块预算耗尽"
                          全员确定性拒绝 → GatewayRejected（bug 信号，不降级）
                          其余 → GatewayExhausted from last_error
```

**顺序即设计**（面试深挖点）：
- 缓存在一切闸门之前——命中=零上游成本，不该消耗配额、不该问预算；
- 两个预算闸门在限流之前——被拒的请求不该占配额；
- 租户限流在候选环外、供应商限流在环内——**两种配额跟着两种身份走**；
- 熔断在供应商限流之前——deny 的供应商连队都不排。

**异常三待遇**（候选环内的分类学）：5xx/超时 → 记熔断账再换路；429 → 换路**不记账**
（上游活着只是挤，限流是配额信号不是健康信号）；Auth/BadRequest → 换路不记账
（本家配置问题，别家未必过不去）+ 计入 rejections 供终局判定。

**两条红线**：半截不换路（有 chunk 流出后任何失败 → `GatewayStreamInterrupted`，死因在
`__cause__`，绝不重放）；租户配额环外（见上）。

---

## 4. 逐模块深挖（职责 / 关键决策 / 边界）

### schema.py —— 统一协议
- **判别联合**：`LLMChunk = TextDelta | ToolCallChunk | UsageChunk | StopChunk`，按 `type`
  字段自动还原子类型；**全部可无损 JSON 往返**——这是 M2 录制回放的直接依赖；
- **网关是笨管道**：`ToolCall.arguments_json` 保持模型输出的原始字符串（可能不是合法 JSON）——
  怎么处理坏参数是 L2 的业务决策，传输层不越权；
- `tenant_id` 字符集收紧（`^[A-Za-z0-9_-]+$`）：空串/冒号/通配符会破坏 Redis key 租户前缀与
  SCAN 运维——纵深防御在类型层就开始；
- `deadline_s`（M2.0）：只约束首块前；**加字段先想缓存键**——已进 cache 的 exclude 集合。

### providers/base.py —— 适配器公共契约
- `Provider` 协议返回 **AsyncGenerator**（不是 AsyncIterator）：显式承诺 `aclose()`，
  上层 `aclosing` 链式关闭依赖它——消费者挂断时连接立刻归还池子，不等 GC；
- **三段超时**（M2.0/C1 重构）：connect 5s / read 30s（流式下 read 作用于每次 socket 读，
  语义=**块间空闲超时**，不限整流时长）/ 首块 25s 在重试层把守；
- `raise_for_status` 一张翻译表全适配器共用（防两份表漂移）：429→RateLimited（读
  Retry-After，**支持秒数与 HTTP-date 双格式**，解析失败退化 None 走指数退避）、
  408→Timeout、401/403→Auth、**501→BadRequest（未实现≠上游故障）**、5xx→ServerError；
- `sanitize_error_text`：上游错误体**在源头消毒**（截断+key 打码）——401 体惯例回显 key 片段，
  异常文本会进日志与 `__cause__` 链，是展示层 masker 罩不住的旁路。

### providers/openai_compat.py —— 百炼适配器（M1 实现量最大单项）
- **对外不变量**：chunk 顺序恒为 `TextDelta* → ToolCallChunk* → Usage → Stop`，
  文本逐块流式、工具调用轮整体交付——消费方可依赖此顺序（两个适配器同一承诺）；
- **[DONE] 哨兵见证**：没亲眼见到终止哨兵的流是截断不是成功——否则残缺回答会被熔断销账、
  被缓存 300 秒（审计高危 #2 的修复）；
- **tool-call 增量组装**：流式碎片按 `index` 归槽（id/name/arguments 分片到达），
  收尾统一合成；个别方言不发 id → `call_{idx}` 兜底；
- **流内错误事件**：上游用 200 流告诉你它坏了（`event.error`）——绝不静默跳过；
- `httpx.PoolTimeout` 单独翻译成 `GatewayOverloadedError`——本地连接池排队超时是**我们自己
  过载**，三个"不"：不记熔断账（供应商无辜）、不重试（加剧争抢）、不换路（共用一个池）。

### providers/anthropic.py —— 第二适配器（桩测试）
- 完整实现、桩测试驱动（respx 假响应），暂无真实 key——**平台级容灾由它证明架构能力**，
  简历表述已按此口径对齐（06 §5）；
- 差异点即统一协议的存在理由：`max_tokens` 强制必填（缺省补 4096）、stop_reason 词表不同、
  tool 结果消息结构不同——这些都被抹平在适配器内。

### resilience.py —— 受控重试
- **三条铁律**：只重试无业务副作用的操作（LLM 补全可重复，代价只是重复计费）；
  只在**首块之前**重试（`anext` 安全窗口——首块后重试=重复输出）；退避=指数+**满抖动**
  （无抖动的同步重试会让所有客户端一起冲撞刚恢复的上游——惊群）；
- **Retry-After 优先**于指数退避（服务端说等 3 秒就等 3 秒，不套抖动）；
- **双闸取小**（M2.0/C1）：首块等待 = min(first_chunk_timeout 25s, deadline 剩余)；
  挂起被切断后翻译成 `ProviderTimeoutError`——与 5xx 走**同一条**重试/记账/换路流水线，零新分支；
- **预算耗尽裸抛真实死因**：total_timeout 或 deadline 不够时 `raise`（原始异常 e）——
  预算耗尽不是新故障，不造新异常、不冤枉供应商；
- 测试接缝：`_sleep`/`_uniform` 模块级可替换——单测记录退避序列且不真睡。

### breaker.py —— 熔断器
- **三键状态机，TTL 即迁移，无后台任务**：`open`（存在即打开，TTL 过期自动进入半开机会）/
  `fails`（连续失败计数，自带窗口 TTL 120s）/ `probe`（半开探测令牌）；
- **SET NX 抢探测令牌**：全集群只放一个探针——多副本同时探测会对刚恢复的上游打突发流量；
  `probe_ttl=120 ≥ 读超时`：探针飞行中令牌过期会放出第二个并发探针（参数间的隐性耦合，
  评审 C1 曾借此定位超时语义问题）；
- **为什么不需要 Lua**：INCR 自身原子、重复 SET open 幂等、探测互斥靠 SET NX——
  需要"读-改-写捆绑"的是限流器（对比记忆点）；
- `release_probe` **无 owner-token 校验（已知取舍）**：极端时序可能误删他人新令牌，
  代价只是多放一个探针、可自愈——owner CAD 在此属过度设计（对比会话锁：那里必须有，
  因为误删锁的代价是互斥破裂）；
- 降级：Redis 挂 → 本地计数 fail-open（单机自保，放弃"全集群唯一探针"承诺，恢复自动切回）。

### ratelimit.py —— 出站限流
- **为什么必须 Lua**：取令牌是"读桶→按时间补给→扣减→写回"序列，没有单条 Redis 命令能表达
  补给逻辑，两副本交错执行会超发——Lua 在 Redis 单线程内整体执行=自定义原子命令；
- **时钟用 `redis.call('TIME')`**（服务器钟）：各副本本地钟会漂移；`math.max(0, elapsed)`
  防 NTP 回拨负补给；EXPIRE 封顶 86400 防 rate 误配极小值时溢出；
- **RESP 陷阱**：协议把浮点截断为整数，"还需等待秒数"必须 `tostring` 返回；
- `wait_take`：短暂排队比直接失败体验好——按脚本返回的 wait 提示睡，max_wait 预算内循环；
- 降级：本地桶**配额=全局/副本数**（牺牲精度保总量）——`_LocalBucket` 就是 Lua 算法的
  Python 直译，两份对照着读。

### cache.py —— 精确缓存
- **key 三原则**：tenant_id 明文前缀（跨租户绝不共享+可按租户 SCAN 清理）；只哈希**语义本体**
  （request_id/session_id/deadline_s 排除——混入则永不命中且静默烧钱）；canonical JSON
  （sort_keys，字段顺序不产生不同 key）；
- key 带 **schema 版本前缀（v1）**：chunk 结构升级后旧缓存天然全体 miss，不会"新代码解析旧数据"；
- **完整性守卫**：以 Stop 收尾**且**含实质内容才入库——半截/失败/空洞流绝不入库
  （缓存事故=可重放的事故）；
- **自愈**：读到解析不了的条目当场删除、按 miss 处理；缓存任何故障（读/写）都只告警不拖垮主链路。

### metering.py —— 计量与预算
- **钱用 Decimal**（Numeric(12,6)），永远不用 float——浮点误差在账本里是事故不是笑话；
- `created_at` 用**数据库时钟**（server_default）：多副本时钟漂移，账本认一个报时员——
  月度闸门的 `date_trunc('month', now())` 同理，"账本认谁的钟，预算就认谁的钟"；
- 价目表缺新模型：**计费不崩溃但必须在日志里喊**——静默记零是财务事故；
- 缓存命中也记账（provider="cache"，cost=0）——命中率统计的分母在这；
- 记账员自己开会话自己提交（独立工作单元，不搭请求事务）；记账失败绝不拖垮请求
  （"为了发票烧掉货物是荒唐的"），缺口由对账脚本暴露；
- **已知边界**：`month_spend` 每次全月 SUM（有复合索引但行数月内线性涨）——评审 C39 已登记
  M3.1 优化（Redis 计数器或短缓存）。

### router.py —— 总装（见 §3 旅程）
- 补充：**FaultInjector 自己实现 Provider 协议**——重试/熔断对它一视同仁，不知道故障是演的；
  三模式 error/hang/midstream（M2.0/C1 补齐挂起与断流盲区）；
- `parse_routes` 启动即校验 + **齐档校验**（以 `schema.Tier` 为单一事实源）——环境变量整体
  覆盖路由表时最容易漏档，启动时炸好过凌晨三点 KeyError；
- fast 档候选链末位升档 qwen-plus（配置里就能看到"fallback 矩阵不做能力断崖、fast 可升档"）。

### core/ —— 底座四件
- config：`lru_cache` 单例（值缓存）vs db/redis/httpx 的手动 global 懒单例（资源）——
  **"值用 lru_cache，资源手动 global"** 是 §2.2 口径；prod 禁故障注入在 model_validator
  里启动即炸；
- db：pool_size=5 + max_overflow=10 显式写出（背压刹车）；`pool_pre_ping` 挡数据库重启后的
  半死连接；`expire_on_commit=False`——async 下访问过期属性会隐式 IO；
- tokens：CJK≈1 token/字、其余≈4 字符/token，**护栏用估算、账单用实测**（±15% 容差自带余量）。

---

## 5. 横切哲学七条（面试的"底层操作系统"，每条都有代码可指）

1. **失败哲学分野**：安全闸门 fail-closed；成本闸门 fail-open（月度预算读挂→放行告警）；
   缓存与计量**绝不拖垮请求**（隔离+自愈+对账兜底）。判定口诀：这个闸门挡的是"危险"还是"花钱"？
2. **半截不换路**：首块是分水岭——首块前世界可以重来（重试/换路），首块后只能诚实中断
   （`GatewayStreamInterrupted` + `__cause__`）。M2 的"半截 llm_call 作废重发"是它的镜像。
3. **重试的前提是无副作用，不是"错误幂等"**：LLM 补全可重复（代价=重复计费，所以有双重预算）；
   写工具绝不自动重试（M2 铁律，M2.0/X1 连模型诱导重试都要防）。
4. **429 不进熔断账**：限流是配额信号不是健康信号。异常分类学：谁的错、能不能重试、
   记不记账——三个维度正交。
5. **测试纪律**：CI 测逻辑状态迁移（怎么跑都一个结论），演示脚本测真实时间量（数字落 reports/
   当凭证）。时序敏感断言进 CI = 腐蚀"红=有 bug"的信号契约。
6. **配置错误启动时炸**：parse_routes 齐档校验 / gt=0 防呆 / prod 禁注入——
   "在启动时炸，不在凌晨的流量里炸"。
7. **口径与凭证**：没实测不写数字，每个数字有凭证文件与口径说明（§6）；
   估算与实测分家（tokens.py 的存在理由）。

---

## 6. 数字与凭证（简历第一批，全部可复现）

| 指标 | 实测 | 口径 | 凭证 |
|---|---|---|---|
| 端到端成功率 | **100%**（1000/1000） | 仅主供应商注入 30% 失败、重试≤3、1 层同档 fallback、缓存关、并发 10、限流放宽 20 QPS | `reports/m1_fault_injection.txt` |
| 延迟 | P50 0.98s / P95 1.89s / **P99 2.42s** | 同上 | 同上 |
| fallback | 22 次 qwen-flash→turbo | 理论 0.3³×1000=27，同量级 | 同上 |
| 熔断零穿透 | closed 294–1161ms → 第 5 次触发打开 → **1.0–1.3ms** | 100% 注入单候选；毫秒级失败=连重试层都没进 | 同上 |
| 限流精度 | 误差 **0.76%**（521/525） | rate=50/s、capacity=25、20 协程×10s、Redis TIME 时钟、按 HTTP 调用计数 | `reports/m2_ratelimit_retest.txt` |
| 账本对账 | 1000 次 vs 1000 行一致；token 27758；成本 **¥0.0079** | 四维聚合：租户/会话/模型/天 | 实验报告 + `scripts/reconcile_usage.py` |

未尽项（诚实清单）：熔断**恢复闭合时间**无实测（TTL 30s 是设计值）→ M5.4 补测（§10.1 #10）。

---

## 7. 已知边界与取舍（"它有什么不足"的标准答案，背熟——主动讲比被问到强）

1. 出站限流按 **HTTP 调用**计数，重试第 2/3 次尝试暂不过闸（§10.1 #11 冻结，v2 升"按尝试"）；
2. 熔断 **provider 粒度**：同供应商多模型共享失败计数（02 §4 已档：保护的是平台级配额与连接层；
   误伤再细化为 provider:model）；评审 C5 指出它与同 provider fallback 的组合张力——M5.4 演示时验证；
3. `release_probe` 无 owner 校验（代价=极端时序多放一个探针，自愈）；
4. 降级形态承诺弱化并有日志声明：限流精度（配额/副本数）、熔断"全集群唯一探针"失效、
   reaper 随 broker 停摆（02 §5/ADR-005 已档）；
5. `month_spend` 热路径全月 SUM → M3.1 优化（§10.1 #22）；
6. Anthropic 适配器无真实 key，平台级容灾是"架构能力证明"而非实测（06 §5 口径，§10.1 #28 校对表述）；
7. 单实例 Redis/PG，无哨兵无备份实操（ADR-005/02 §5 备份口径：文档声明+种子可重建）。

---

## 8. M0/M1 面试连环炮速查（按被问概率排序）

1. 供应商挂了怎么办？→ §3 旅程 + 重试三铁律 + 熔断三键 + fallback 矩阵，数字见 §6；
2. 上游挂死 120 秒（连上不吐字）呢？→ 三段超时两阶段模型（§4-base/resilience，M2.0/C1）；
3. 为什么"重试幂等错误"是错误说法？→ 哲学 #3；
4. 429 为什么特殊？→ 哲学 #4 + Retry-After 双格式；
5. 熔断半开怎么防惊群？→ SET NX 探测令牌 + probe_ttl≥读超时 + 429 探测归还令牌；
6. 限流为什么必须 Lua？时钟怎么办？→ §4-ratelimit（读-改-写原子性 + Redis TIME + NTP 回拨）；
7. 缓存怎么保证不跨租户/不缓存垃圾？→ key 三原则 + 完整性守卫 + v1 版本前缀；
8. 多副本部署行为一致吗？→ 状态全在 Redis（限流/熔断/缓存）+ 降级语义逐项写实；
9. 成本怎么算的？→ Decimal + 数据库时钟 + 价目表告警 + 对账脚本；三级预算闸门位置（§3 ④⑤ + M2 会话级）；
10. 跨供应商差异怎么抹平？→ 统一协议判别联合 + chunk 顺序不变量 + [DONE] 哨兵 + tool-call 按 index 组装；
11. 它有什么不足？→ §7 逐条主动讲，每条带"为什么接受+升级路径"。

---

> 复盘产出于 M2.0 与 M2.1 之间；M2 毕业后建议增补"M2 复盘"姊妹篇。
> 文中所有断言以 `f176b1e` 代码为准，与设计文档冲突处以代码+00 §2.2 为准。
