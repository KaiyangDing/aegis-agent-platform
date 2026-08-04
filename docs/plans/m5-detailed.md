# M5 · 交付收口 详细计划（M5.0–M5.6，接口级）

> **写作基线**：M2.4 毕业（commit `014ec21`，301 测试全绿）· 撰写 2026-07-10 Fable 5 交接工程。
> **实际落地偏差**：（毕业时回填；本块为差异权威，随步追加）
>
> **M5.0 开工走查实况（2026-08-03/04；基线 B=989/`m4-governance`；全程 AI 执行=M4.6 委托延续，
> 六项拍板 P1-P6 全按建议：10/30/60 三档／200 tok 响应写死／LangGraph 技能栏行以 #33 凭证为前提
> ／M5.3 顺手验优雅停机／spike 落仓外（若做）／容灾对象改档内）**：
> §0 十五项：**14 项过、1 项过期修正**——⑴ **§0-8 作废**：standard 实为
> `["bailian:qwen-plus","bailian:qwen-turbo"]`（模型池 v3，M2.11 起；deepseek/glm 两版容灾对象
> 均随 #28 作废）→ **P6 拍板：容灾实录=档内 fallback（qwen-plus→qwen-turbo），凭证名
> `m5_failover_qwen_tier.txt`**，00 §9.1/§9.2/§10.2 三处过期字样已修，§4-M5.4 交付③ 的
> deepseek 专用步骤按对象替换执行（断言 20/20==qwen-turbo）。
> ⑵ **§0-4 帧词汇过期**：实况 **8 种帧**（M4.3 起 +user_message/message_reset/handoff）——
> sse_client 按 8 帧词汇写，SSEFrame 注释随实况。⑶ **附录 P7' 裁决：采 D1**
> （LatencyModelProvider 挂 Provider 层；00 §9.1 M5.2 行"FakeGateway 注入"措辞属规划期笔误
> ——FakeGateway 是回放件不适合无剧本压测，实装以 D1 为准，本块即登记不再改 00 行文）。
> ⑷ **附录 P8' 顺序解耦确认**：M5.3 的 nginx/compose 改造先落地、口径① 实验后执行
> （交付编号不变）。⑸ **#33 spike 未做**：弹性窗保持归用户排期，§4-M5.0-B 任务卡不执行，
> 05 技能栏 LangGraph 行**暂不写**（P3 前提=凭证在，C18 逐词诚实）。⑹ 0-7 breaker
> threshold=5/open=30/probe_ttl=120 实核无漂移；0-13 locust 确未安装；0-9 README 初稿在
> （M5.5 只做终稿）。
>
> **M5.1–M5.4 落地实况（2026-08-03/04，随步追加；提交对账表 M5.6 建于 00 §9）**：
> M5.1–M5.3 无新增计划面偏差（D1/P8' 已在 M5.0 块预登记；口径①报告以 21,600ms 注入基线
> 立账=OutputGuard 对无边界合成文本整段 flush 的实测形态，报告§口径段自带）。**M5.4 实况七条**：
> ⑴ 交付③ 按 P6 对象执行，脚本名 `experiment_qwen_tier_failover.py`（§8 表 M5.4 行 deepseek
> 文件名随对象替换）；⑵ **(58) 家族第三例**：两补录实验首跑均空账——裸网关驱动缺
> `tenant_context` 配对，计量被 usage_ledger RLS 静默拒收（fail-open）；demo 排练首遍暴露，
> 两脚本补配对**重跑出真账版**（breaker 三轮 32.5/31.7/32.3s、¥0.0001；failover 20/20+
> ledger 20 行、¥0.0003），报告内注记首跑空账史，failover 增设"空账即断言失败不出报告"；
> ⑶ 计划外新增 `scripts/demo_m5_highlights.py`（分镜"操作"列的可复跑驱动器，prep/h1–h4/all
> 子命令；段间状态 `.demo_tokens.json`/`.demo_state.json` 入 gitignore——短时 JWT 不入库）；
> ⑷ 高光2 全弧实测形态=挂起→`docker kill` 副本→幸存副本 decide **3s 读超时断连**→事实面
> kill 后 ~5s 落地（events 三事件+订单 refunded）→用户 GET /stream 回放闭环——(57) approvals
> 断连余账清账；两枚实测行为差入分镜失败预案（手动 kill 不触发 unless-stopped 自启／精确缓存
> 可使续跑快于 3s 断连窗）；⑸ #14 复验 ✅（2026-08-04 停 Redis 容器实跑，凭证行入
> demo-script.md 彩排清单，`m2_degradation_redis.txt` 刷新）；⑹ (72)(77) 连带清账随本步提交
> （stream 译表按 run_id 分段清零+见证测试；chat.html POST 失败自动 resubscribe——M4.2 移位单
> 末两条，00 §10.1-bis 已翻 ✅）；⑺ 排练 4 遍全绿、逐段计时登记 demo-script.md（机器时间
> <1min，"实测 ≤15 分钟"判定成立）。
>
> **消费方式**：先读 00 §9 全章（步骤行是权威范围）+ §10.2 + 本文件全文，强制执行 §0 核对清单。
> M5 距写作时点隔着 M2.5–M4.8 共 31 步（9+13+9，00 §6.1/§7.1/§8.1 实数）——本文件是五份计划中「未来最远」的一份，
> 【开工核对】密度最高：任何一处与实况对不上，先停下修订本计划，再动手。
> 信任序：实际代码 > 00 §2.2 > 本计划 > 02/03/04 叙述（plans/README.md §2）。

---

## §0 开工核对清单（M5.0 第一件事，逐项核对后才许进 M5.1）

在仓库根（本 repo） 执行。任何一项 ✗ → 报给用户并修订本计划。

| # | 核对项 | 核对方法 | 本计划假设 |
|---|---|---|---|
| 0-1 | M4 已毕业：tag `m4-governance` 存在，00 §8 标 ✅ | `git tag` / 读 00 §8 | M4.8 六项全勾（00 §13） |
| 0-2 | pytest 收集数基线 **B**（M4.8 毕业登记值） | `uv run pytest -q` 与 00 §6.3 式对账表核对 | 写作时点 301；M5 全程以 **B** 为基线记账 |
| 0-3 | 应用容器化产物（§10.1 #26，M4.7 交付，**M5.3 硬依赖**）：Dockerfile、api/worker/beat 编排文件名、api 服务名与容器内端口、alembic 迁移执行顺序、restart 策略（#31） | `ls deploy/`；读 compose 文件 | 存在且 `docker compose up` 可起全栈。**缺失 = M5.3 阻塞**，回 M4.7 补 |
| 0-4 | `POST /v1/chat` 请求体字段形状 + SSE 五帧实际字段（M3.10 落地实况；02 §9 只定义了帧类型） | Read `aegis/api/` 路由源码 | 帧类型 = token/tool_status/approval_pending/done/error（ADR-007:15）；done 帧含 trace_id+usage |
| 0-5 | 压测用户的 JWT 获取方式（M3.1 信任根 #17 落地实况：签发脚本/测试密钥） | Read M3.1 交付物 + m3-detailed.md 偏差登记 | 存在开发环境签发办法，locust 可从环境变量拿 token |
| 0-6 | FakeGateway（M2.6）实际形态与 M3 API 的网关装配点 | Read `aegis/runtime/`（M2.6 产物）与 api 组装代码 | 本计划把压测替身挂在 **Provider 层**（§3 D1）——若 M2.6/M3 已有更顺的替身挂点，以实况为准并回填偏差 |
| 0-7 | `CircuitBreaker` 默认参数仍为 threshold=5 / **open_seconds=30** / probe_ttl=120（breaker.py:41-51） | Read `aegis/gateway/breaker.py` | M5.4 熔断恢复实验的预期值依赖 open_seconds |
| 0-8 | `model_routes` standard 档仍为 `["bailian:qwen-plus", "bailian:deepseek-v3"]`（config.py:36） | Read `aegis/core/config.py` | M5.4 容灾实录依赖此候选链 |
| 0-9 | docs 已迁入仓库（M4.7 #9）：`docs/` 在 repo 内、README 初稿是否存在（评审 C43 处置实况） | `ls docs/ README.md` | 存在 README 初稿；缺则 M5.5 职责从「终稿」扩为「初稿+终稿」并登记偏差 |
| 0-10 | §10.2 表实况：M4.5 评测数/通过率、M4.6 两组降本数字的凭证文件名与状态 | 读 00 §10.2 + `ls reports/` | M4 三行已 ✅ 待回填；仍 ⬜ 的行按 00 §11 第 4 条走砍法同步 |
| 0-11 | LangGraph spike（#33）完成状态 | 读 00 §10.1 #33 + spike 工程是否存在 | 未完成则按本文件 §4-M5.0-B 任务卡在弹性窗执行 |
| 0-12 | `reports/` 既有凭证在位：`m1_fault_injection.txt`、`m2_ratelimit_degraded.txt`、`m2_ratelimit_retest.txt` + M4 新增凭证 | `ls reports/` | M5.5 回填的读数来源 |
| 0-13 | locust 尚未安装（写作时点 dev 组无 locust——pyproject.toml:15-23）；M4 期间未被引入 | 读 pyproject.toml | M5.1 首个动作是 `uv add --dev locust` |
| 0-14 | CI workflow 对 `scripts/`、`deploy/` 的触碰面（M4.3 回归流水线形态） | 读 `.github/workflows/` | M5 新增脚本/配置不得让 CI 门（含 mypy .）变红 |
| 0-15 | 05 模板与 06 §5 当前文本（M4.7 迁入后可能有路径变化） | 读 `docs/05-...md`、`docs/06-...md` §5 | M5.5 逐词校对基线（#28） |

---

## §1 目标与定位

- **本步做什么**（00 §9.1，7 步）：压测两组口径出数字、水平扩展演示、15 分钟 demo 脚本、
  README 终稿与简历回填、tag `v1.0`。M5 不再新增平台能力（唯一例外：压测替身
  `LatencyModelProvider`，测试基建性质——§3.2 D1，与 00 措辞的冲突见附录 P7'）——
  它把 M0–M4 的能力**变成可展示、可背书、逐词可对账的交付物**。
  简历项目的「最后一公里」：面试官看到的一切在本里程碑定稿。
- **面试叙事位置**：05 §2 第 4 拍「结果：量化指标 + 15 分钟可复现 demo」全部产自 M5；
  §10.2 七个占位符中 3 个在本里程碑产出（M5.2 ×1 + M5.4 ×2），全部七个在 M5.5 回填。
- **真实调用口径**（由 00 §9.1 行文导出，00 无独立声明——见文末问题清单 P6'）：
  仅 M5.2 口径②（50–100 次）与 M5.4 demo/两项补录产生真实调用，预算上限写死进脚本；
  M5.2 口径① 全程零真实调用（延迟模型替身）；CI 恒零真实调用（全局纪律）。
- **规模**：S+M+L+M+M+M+S（00 §9.1）；参照系 M ≈ 2–3 次交付。

---

## §2 契约事实源

### 2.1 本步消费的既有接口（签名已 Read 源码核实，M2.4 时点）

| 接口 | 签名/事实 | 出处 |
|---|---|---|
| 网关组装入口 | `def build_gateway() -> LLMGateway:` | factory.py:18 |
| Provider 协议 | `name: str` + `def complete(self, req: LLMRequest, model: str) -> AsyncGenerator[LLMChunk]: ...` | providers/base.py:21-28 |
| 流式四块 | `TextDelta(type,text)` / `ToolCallChunk` / `UsageChunk(type,model,prompt_tokens,completion_tokens,cached)` / `StopChunk(type,reason)` | schema.py:66-92 |
| 故障注入器 | `FaultInjector.__init__(self, inner: Provider, rate: float, *, mode: FaultMode = "error", hang_s: float = 120.0)`；mode ∈ error/hang/midstream | router.py:125-155、router.py:48 |
| 网关注入参数 | `LLMGateway(..., fault_rate: float = 0.0, fault_targets: frozenset[str] = frozenset(), fault_mode: FaultMode = "error")` | router.py:158-188 |
| 熔断器 | `CircuitBreaker(redis, *, failure_threshold: int = 5, open_seconds: int = 30, probe_ttl: int = 120, fail_window: int = 120)`；三键 `aegis:cb:{p}:open/fails/probe` | breaker.py:40-62 |
| 熔断记账粒度 | `on_success/on_failure(cand.provider)`——**provider 粒度**；成功即清零失败计数 | router.py:301、router.py:311 |
| 配置面 | `model_routes`（standard=`["bailian:qwen-plus","bailian:deepseek-v3"]`）、`fault_injection_rate/targets/mode`、`cache_ttl_seconds`、`provider_rate=8.0` 等限流参数、`replica_count`、prod 禁注入校验器 | config.py:33-67 |
| LLMRequest | `tier/messages/tenant_id(pattern ^[A-Za-z0-9_-]+$)/session_id/max_tokens/deadline_s` | schema.py:45-60 |
| SSE 双通道帧协议 | POST 五帧 + GET 重订阅通道 after_seq；Nginx 两坑 | ADR-007:12-19、ADR-007:26-27 |
| 实验脚本先例 | 口径写死进 docstring、`os.environ` 在 import aegis 前放宽限流、`ROOT = Path(__file__).resolve().parent.parent` 锚定落盘、报告 `write_text(encoding="utf-8")`、熔断键清场 | scripts/experiment_fault_injection.py:20-27、40、46、109、143、196 |
| 预热稳态先例 | 牺牲 scope 首发排除故障检测延迟、首发耗时单独上报 | scripts/loadtest_ratelimit.py:48-54；00 §2.2 复盘补丁二行 |
| 基础设施 compose | pg/redis `restart: unless-stopped`、端口只绑 127.0.0.1 | deploy/docker-compose.yml:7、15、29 |
| M3/M4 交付面 | `POST /v1/chat`、`GET /v1/sessions/{id}/stream?after_seq=N`、`GET /v1/sessions/{id}/events`（trace API，M4.1）、`POST /v1/approvals/{id}`、`/metrics` | 02 §9（形状以实装为准，§0-4） |

### 2.2 本步提供的交付物（M5 是终点，消费者 = 面试现场与简历）

| 交付物 | 消费者 |
|---|---|
| `reports/m5_loadtest_overhead.txt`（口径①）、`reports/m5_real_first_token.txt`（口径②） | §10.2「本地压测 P99 首 token」；README 数字表 |
| `reports/m5_breaker_recovery.txt`、`reports/m5_deepseek_failover.txt` | §10.2 末两行；05 简历网关 bullet |
| `deploy/nginx.conf` + compose nginx 服务 | M5.3 演示；demo 开场 |
| `scripts/loadtest/`（locust SSE client）、`scripts/experiment_*.py` ×3 | 压测与补录的可复现入口 |
| `docs/demo-script.md`（分镜） | 面试 demo；00 §9.2 验收 |
| README 终稿 + 架构图；05 简历定稿（占位符清零 + #34 调序 + #27/#28 校对） | 简历投递 |
| tag `v1.0` + 记忆归档（完结版） | 项目关账 |

---

## §3 设计决策与口径

### 3.1 已裁决口径（出处即裁决，本步不许重开）

| 口径 | 内容 | 出处 |
|---|---|---|
| 压测两组分开 | ① 平台开销与并发容量（延迟模型替身，零 token）；② 真实首 token 分布（小样本 50–100 次，**不做高并发：费用与厂商限流约束**——理由声明必须原样进报告） | 00 §9.1 M5.2；04 M5 |
| 延迟模型参数**写死** | 首 token **800ms** + **20 tok/s**。不许调参：该模型与 C1 超时语义耦合（20 tok/s 下 1800+ token 长回答是「健康」的——块间隔 50ms ≪ 空闲超时 30s、首 token 0.8s ≪ 首块超时 25s），改参数连带超时语义的面试解释 | 00 §9.1 M5.2；评审 C1 验证者补充；base.py:37-40 |
| 预热后稳态计时 | 冷启动/故障检测延迟排除在稳态窗外、单独上报 | 00 §2.2 复盘补丁二行 |
| 档位数 | ≥3 个并发档位 | 00 §9.2 |
| Nginx 两坑 | `proxy_buffering off` + 调大 `proxy_read_timeout`（默认 60s 掐长回复） | ADR-007:26-27 |
| demo 高光 | 故障注入（熔断+fallback）/ 断点续跑（HITL/kill -9）/ 多租户隔离 + **replay 调试升为高光**（#27 的 00 措辞比评审 C33「备选」更强，以 00 为准）；实测 ≤15 分钟 | 00 §9.1 M5.4；§10.1 #27 |
| M5.4 两项补录 | 熔断恢复闭合时间（04 M1 验收未尽项，**无条件补**）+ qwen-plus↔deepseek-v3 容灾实录（无凭证则**改 05 表述**，不许留字面） | §10.1 #10；§10.2 末行 |
| 会话锁降级复验 | PG advisory lock 降级在 M5.4 **演示复验**（00 M5.4 行文没写，挂在 §10.1 #14——只读 §9.1 会漏） | §10.1 #14 |
| 简历数字纪律 | 没实测不写数字；口径限定语随数字走（「本地压测（模拟上游延迟）下 P99 …」）；简历与交付物逐词对得上；被砍项三处同步删除 | 00 §2.2；00 §11 第 4 条；05 头部 |
| 简历调序 | 应用岗版：运行时/业务层 bullet 前置，网关 infra 数字降为支撑证据；90 秒叙事线同步调序 | §10.1 #34 |
| DeepSeek 表述口径 | 「模型级容灾实测（qwen-plus↔deepseek-v3，同平台异族）；平台级容灾由 Anthropic 适配器（桩测试）证明架构能力」——不许拔高为「多供应商实测」 | 06 §5（06:73-75）；§10.1 #28 |
| 演示/压测一律走容器 | 本地 solo 池只是调试便利，生产形态以容器为准 | 06 §4（06:42-45） |
| 测试纪律 | 时序敏感断言不进 CI——压测/演示数字全部走脚本+报告落盘 | 00 §2.2 测试纪律行 |

### 3.2 本计划替未来定下的决策（蓝图未覆盖、有唯一合理答案）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 压测口径① 的上游替身命名 **`LatencyModelProvider`**，落 `aegis/gateway/providers/latency_model.py`，实现 Provider 协议（base.py:21-28），由 `build_gateway()` 按新 Settings 开关 `loadtest_upstream: bool = False` 装配，prod 环境校验器拒绝（与 `_no_fault_injection_in_prod` 同哲学，config.py:61-67） | 挂 Provider 层让**整个平台栈为真**（限流/熔断/缓存/计量/运行时/SSE 全在被测路径上），只有上游是假的——这正是「平台自身开销」口径要的测量面；与 FaultInjector 同一挂法（router.py:125），组装逻辑零新概念。M2.6 的 FakeGateway 是 L2 回放件、匹配键=会话+轮次，不适合无剧本压测流量（§0-6 开工时确认）。**注意**：00 §9.1 M5.2 行与 04 M5 原文点名的机制是「FakeGateway 注入固定延迟模型」——本决策推翻该点名，属计划层与 00 的口径冲突，已登记附录 P7' 报用户裁决 |
| D2 | 口径② 测量点 = **直连 `build_gateway()` 的 `complete()` 首块**（复用 M1.13 脚本模式），不过 HTTP/SSE | 口径② 的目的是「上游为真时的首 token 分布」，用来给口径① 的 800ms 假设提供现实参照；若过全栈会把平台开销混进上游分布，两组口径就不再正交。报告须声明测量点 |
| D3 | locust 以 **dev 依赖**引入（`uv add --dev locust`）；locustfile **不 import aegis 包** | 压测客户端不是产品代码不进主依赖；locust 基于 gevent monkey-patch，与 aegis 的 asyncio 代码同进程互相污染（见 §7 T2） |
| D4 | SSE 帧解析器做成**纯函数**放 `scripts/loadtest/sse_client.py`；pyproject `[tool.pytest.ini_options]` 加 `pythonpath = ["."]` 使 `tests/loadtest/` 可 import 它 | 解析器是 **scripts/ 侧**唯一值得进 CI 的逻辑（纯函数、无时序、无网络；生产包内另有 LatencyModelProvider 测试——§5）；pytest ≥7 原生支持 pythonpath ini 项，不引入打包动作 |
| D5 | 压测会话形态：**每虚拟用户一个会话、串行发消息**；每条消息 prompt 带 uuid 唯一化；压测环境 `CACHE_TTL_SECONDS=0` | 同会话并发第二条消息会 409（会话互斥，02 §2③）误报错误率；重复 prompt 会命中精确缓存把「平台开销」测成缓存延迟（双重保险：唯一化+关缓存） |
| D6 | 稳态窗实现：locustfile 在 `test_start` 后 30 秒调 `runner.stats.reset_all()`，报告只取 reset 后窗口；首 30 秒单独记为预热段 | 兑现复盘补丁二稳态口径；比事后裁剪 CSV 简单且不易错 |
| D7 | 压测环境限流放宽并**写进报告口径**（如 `PROVIDER_RATE=200/TENANT_RATE=200`，学 experiment_fault_injection.py:24-27 先例） | 默认 provider_rate=8 QPS（config.py:40）测的是限流墙不是平台开销；放宽值属于口径的一部分，不声明就是被质疑点 |
| D8 | 熔断恢复闭合时间**定义**：起点 = 上游恢复时刻（脚本切换到无注入网关），终点 = 首次探针成功、`open`/`fails` 键清零后请求正常放行；预期 ≈ open TTL 剩余 + 一次探针延迟，上界 open_seconds=30s + 探针耗时 | 04 M1 验收原文只说「上游恢复后 X 秒内自动闭合」没定义端点；此定义可复现、且直接验证设计值（TTL 即状态迁移，breaker.py:3-6） |
| D9 | deepseek 容灾实录同场**预写 C5 预期行为**：熔断 provider 粒度 + 同 provider fallback → 每次 qwen-plus 失败记 `bailian` 一账、deepseek-v3 成功即清零（router.py:301/311）→ **熔断全程不打开是预期行为**，demo 稿预答「为什么熔断没开」 | 评审 C5 对 M5.4 的附加要求（review:121）；不预写则现场解释不清 |
| D10 | demo 四高光排片与计时预算见 §4-M5.4（合计 14 分钟 + 1 分钟缓冲）；#14 会话锁降级复验放**彩排清单**（不占 15 分钟主线），凭证一行进 demo 报告 | 00 §9.2 只约束「≤15 分钟跑通全部高光」；复验是验证义务不是展示高光 |
| D11 | nginx 监听 `127.0.0.1:8080`；upstream 走 Docker 内嵌 DNS（服务名 `api`）；`--scale api=3` 之后 nginx 需 reload（见 §7 T5） | 端口只绑回环是既有安全口径（deploy/docker-compose.yml:13-15）；8080 避开可能被 api 占用的 8000 |
| D12 | 报告文件命名 `reports/m5_*.txt`，UTF-8、锚定项目根（`Path(__file__)` 模式） | 与 m1/m2 凭证命名连续；记忆档案「脚本落盘锚定项目根」教训 |
| D13 | LangGraph spike 笔记落 `docs/notes/langgraph-spike-notes.md`（M4.7 后 docs 在 repo 内，走提交） | 笔记是「熟悉 LangGraph」的凭证，必须在可指认的位置 |

### 3.3 【用户拍板】项（开工时议，每项附建议）

| # | 议题 | 建议与理由 |
|---|---|---|
| P1 | 口径① 并发档位取哪三档 | 建议 **10 / 30 / 60 并发用户**。理由：单请求持流 ≈ 0.8s + 200tok/20tok/s = 10.8s，计入 locustfile `wait_time` 均值 2s 后每用户周期 ≈ 12.8s，60 并发 ≈ 4.7 req/s 稳态到达率（不含 wait_time 的上界 ≈ 5.5），本地 3 副本 + PG/Redis 单实例下预计可见开销拐点又不至于全线超时；若 60 档错误率 <1% 可加测 100 档（加档不违反「≥3」） |
| P2 | 口径① 每响应 token 数 | 建议**写死 200 token/响应**（对话典型长度，单请求 10.8s）。响应长度是吞吐口径的自由参数，必须定死并写进报告口径，否则数字可被质疑 |
| P3 | 简历是否加 LangGraph 框架素养条目 | 建议加在**技能栏一行**（「熟悉 LangGraph：迷你复刻 spike + 与自研运行时的对照文档」），不进项目 bullet——项目 bullet 是自研叙事，混入框架条目稀释主线；表述以 #33 凭证（spike + 笔记）背书，逐词诚实（C18 纪律） |
| P4 | M5.3 是否顺手验证优雅停机（`uvicorn --timeout-graceful-shutdown` + compose `stop_grace_period`，与 kill -9 演示同场） | 建议**做**（约半小时）：评审 C35 建议（review:393），但 00 无追踪行（见文末 P1'）——用户点头即做并在 00 §10.1 补登记，不点头则只保留 M2.0 已落档的 crash-only 文档声明 |
| P5 | spike 工程落点 | 建议**独立 uv 工程 仓外 `langgraph-spike\`（repo 外独立工程）**（不进 aegis 仓库）：langchain 系依赖进 uv.lock 会污染主工程 CI 门与依赖审计（PyCharm×uv 教训的反向应用）；简历可另给 spike 仓库链接。备选：仓库内 `spike/` 目录 + 排除出 mypy/CI（配置成本更高） |

---

## §4 实施蓝图（按步切分；生产代码用户敲，本节只给签名与算法步骤）

### M5.0 开工走查 + 占位符清点（S，1 次交付，纯走查无代码）

**A. 走查与清点**（交付物 = 一份差异表，报给用户）：

1. 执行 §0 全部 15 项核对；
2. 重读 04 M5 节、**05 全文**、ADR-007、00 §9 + §10.2（00 §12 M5 必读行）；
3. **§10.2 逐项核对表**——七行逐行核对并输出三列结论（占位符 | 凭证实况 | M5 动作）：

| 占位符（00 §10.2） | 凭证应在 | 核对方法 | 若缺失 |
|---|---|---|---|
| 故障注入成功率 X% + P99 代价 X s | `reports/m1_fault_injection.txt` | 打开文件读数与 00 §5.2 对照 | 不可能缺（M1 已 ✅）；缺=历史损坏，停下报告 |
| 档位路由降本 X% | M4.6 实验① 报告 | `ls reports/` + 读口径段 | 回 M4.6 补或按 00 §11 砍法从简历删 |
| 精确缓存降本 X% | M4.6 实验② 报告 | 同上 | 同上 |
| 本地压测 P99 首 token X s | **本里程碑 M5.2 产出** | — | M5.2 必做项 |
| 评测用例数 + 通过率基线 | M4.5 报告 | 读数 | 回 M4 补或砍法同步 |
| 熔断恢复 X 秒闭合 | **本里程碑 M5.4 产出** | — | 无条件补（#10） |
| Qwen↔DeepSeek 容灾实测 | **本里程碑 M5.4 产出** | — | 补录失败 → M5.5 改 05 表述 |

4. **#33 spike 完成情况核对**：已完成 → 核对笔记与复刻工程在位、简历表述素材齐；未完成 → 走 B。
5. 给 M5 全景图（步骤地图 + 契约走查 + 首步预告），用户确认后进 M5.1（00 §2.1 第 6 条）。

**B. LangGraph spike 任务卡**（#33，1–2 天，弹性窗执行；落点见 P5）：

- **复刻范围**（demo 场景子集，刻意最小）：单租户版「订单查询 + 退款审批」——
  ① `create_react_agent` 装配 2 个工具（`get_order` 读 / `apply_refund` 写）；
  ② 写工具用 `interrupt` 做审批挂起，恢复走 `Command(resume=...)`；
  ③ checkpointer 用 `PostgresSaver`（连本地 aegis-postgres 容器），验证进程重启后续跑；
  ④ 跑通一条「查订单→退款→挂起→批准→完成」端到端对话即止——**不做**多租户/RAG/SSE/评测（越界即偏离 spike 目的）。
- **源码阅读笔记清单**（每项 = 现象 + 源码位置 + 与 aegis 对照一句话，落 D13 文件）：
  1. `@tool` 装饰器如何从签名/docstring 生成 schema——对照 `aegis/runtime/tools.py` 的同源三消费者设计；
  2. `ToolNode` 的错误处理与并行执行语义——对照 ToolExecutor 五结局契约（executor.py:24-31 口径）；
  3. `interrupt` 的挂起/恢复机制（checkpoint 边界、重放语义）——对照 aegis「先取会话锁再恢复」单入口；
  4. `PostgresSaver` 的 checkpoint 表结构与写入时机——对照 events 事件溯源（快照 vs 事件流，M2 面试考点）。
- **产出**：spike 工程可运行 + 笔记文件 + 简历表述素材（P3）。compare-langgraph-m2.md（#32）是 M2.12 产物，spike 笔记与它互补不重复——笔记记「跑起来才知道的行为」。

### M5.1 locust SSE client 自写（M，约 2 次交付）

**新建**：`scripts/loadtest/sse_client.py`、`scripts/loadtest/locustfile.py`、`tests/loadtest/test_sse_client.py`（AI 直写）。
**修改**：`pyproject.toml`（dev 加 locust；pytest 加 `pythonpath = ["."]`——D4）。

**交付① `sse_client.py`——SSE 帧解析（纯函数，唯一进 CI 的部分）**：

```python
@dataclass(frozen=True, slots=True)
class SSEFrame:
    event: str            # token/tool_status/approval_pending/done/error（ADR-007:15，实际帧名以 §0-4 为准）
    data: str             # 多个 data: 行按 SSE 规范以 "\n" 连接
    id: str | None = None # 对应事件流 seq——GET 通道续传用（ADR-007:28-29）

def iter_sse_frames(chunks: Iterable[bytes]) -> Iterator[SSEFrame]: ...
```

算法（SSE 规范子集，够用即止）：
1. 维护 `bytes` 缓冲，按 `\n\n`（兼容 `\r\n\r\n`）切帧，尾部半帧留在缓冲；
2. 帧内逐行解析：`event:`/`data:`/`id:` 前缀（冒号后一个可选空格）；`:` 开头为注释行、空字段名行忽略；
3. 多个 `data:` 行以 `\n` 连接；帧内无任何字段 → 丢弃；
4. **不做** JSON 解析——data 载荷的解释归调用方（帧字段形状 §0-4 开工核对）。

关键不变量：解析器不吞异常、不做 IO、不认识 locust——纯 bytes 进 frame 出（这是它可测的原因）。

**交付② `locustfile.py`——虚拟用户与指标采集**：

```python
class AegisChatUser(HttpUser):
    wait_time = between(1.0, 3.0)
    def on_start(self) -> None: ...   # 从环境变量拿 JWT 与 base 配置；开本用户专属会话（D5）
    @task
    def chat_turn(self) -> None: ...
```

`chat_turn` 编号步骤：
1. 组包：唯一 prompt（`uuid4().hex` 拼入文本，防缓存命中——D5）；请求体形状按 §0-4 实况；
2. `t0 = time.perf_counter()`；`self.client.post("/v1/chat", json=..., headers=..., stream=True, name="chat")`；
3. HTTP 状态 ≠200 → fire 失败事件，本轮结束；
4. `resp.iter_content(chunk_size=1024)` 喂 `iter_sse_frames`（**不许用 `iter_lines`**——§7 T3）；
5. 收到**第一个 token 帧** → `ttft_ms = (perf_counter()-t0)*1000`，`events.request.fire(request_type="SSE", name="chat_first_token", response_time=ttft_ms, response_length=0, exception=None, context={}, response=None)`（locust ≥2 统一事件签名，**落笔前读 `.venv/Lib/site-packages/locust/` 核实字段**——§7 T1）；
6. 持续消费至 `done` 帧（正常）或 `error` 帧/连接中断（fire exception）；
7. 结束 fire `name="chat_total"` 总耗时事件；
8. 会话生命周期：done 后同会话串行下一轮（wait_time 间隔）；收到 409 视为脚本 bug（D5 应已排除）单独计数上报。
9. 稳态窗钩子：`@events.test_start` 注册 30s 后 `runner.stats.reset_all()` 的 greenlet（D6）。

**指标采集口径**（写进文件头 docstring，报告照抄）：TTFT = POST 发出到首个 token 帧；
平台开销 = TTFT − 800ms（注入的固定首 token 延迟）；错误 = HTTP 非 200 / error 帧 / done 前断流三类分开计数。

**交付③ 解析器测试**（AI 直写，见 §5）。

### M5.2 压测两组口径（L，约 4 次交付）

**交付① `LatencyModelProvider`（生产代码，用户敲；D1）**：

新建 `aegis/gateway/providers/latency_model.py`：

```python
class LatencyModelProvider:
    """压测口径① 的固定延迟上游：首 token 800ms + 20 tok/s（00 §9.1 M5.2，参数不许改——§3.1）。"""
    name: str
    def __init__(self, name: str = "latency-model", *, first_token_s: float = 0.8,
                 tokens_per_s: float = 20.0, response_tokens: int = 200) -> None: ...
    async def complete(self, req: LLMRequest, model: str) -> AsyncGenerator[LLMChunk]: ...
```

`complete` 算法：① `await asyncio.sleep(first_token_s)`；② 循环 `response_tokens` 次：
`yield TextDelta(text="测")` 后 `await asyncio.sleep(1.0 / tokens_per_s)`；
③ `yield UsageChunk(model=model, prompt_tokens=<estimate_tokens(拼接输入)>, completion_tokens=response_tokens)`；
④ `yield StopChunk(reason="end_turn")`。（块类型：schema.py:66-92。）
不变量：不抛业务异常、不读网络——它是「永远健康的上游」，平台开销以外的一切耗时为零。

**修改**：`aegis/core/config.py` 加 `loadtest_upstream: bool = False`、`loadtest_response_tokens: int = 200`（P2 拍板值），
校验器 prod 禁开（config.py:61-67 同款）；`aegis/gateway/factory.py` 按开关装配（挂法与 FaultInjector 并列，形态以 §0-6 实况为准）。

**交付② 口径① 实验**（零真实调用）：

| 口径项 | 值（报告照抄） |
|---|---|
| 上游 | LatencyModelProvider：首 token 800ms + 20 tok/s + 200 tok/响应（P2） |
| 部署形态 | 容器全栈（06 §4 承诺）：`--scale api=3` + nginx。**执行顺序注意**：nginx.conf 与 compose 改造（api 去 container_name/宿主端口——T6 前置）是 **M5.3 交付物**，口径① 实验的**实际执行**排在 M5.3 落地之后（交付顺序与实验执行顺序解耦，见附录 P8'）；若想在 M5.3 前先单副本跑通，档位表加「副本数」列且不 `--scale` |
| 环境覆盖 | `LOADTEST_UPSTREAM=1`、`CACHE_TTL_SECONDS=0`、限流放宽（D7，具体值进报告）、预算闸门关闭（`TENANT_MONTHLY_TOKEN_BUDGET=0` 默认即关） |
| 负载 | locust headless：`-u <档位> -r 5 -t 120s`，三档位（P1）各跑一轮；前 30s 预热不计（D6） |
| 报表 | 见下模板 |

报告 `reports/m5_loadtest_overhead.txt` 模板（每档位一行）：

```
== 口径①：平台开销与并发容量（模拟上游：首 token 800ms + 20 tok/s + 200 tok/响应）==
环境：3×api 副本（容器）+ nginx + PG/Redis 单实例；缓存关；限流 PROVIDER_RATE=... ；预热 30s 后稳态 90s 计窗
档位 | 完成请求 | 吞吐 req/s | 错误率(HTTP/error帧/断流) | TTFT P50/P99 (ms) | 平台开销 P50/P99 = TTFT−800 (ms)
10   | ...
30   | ...
60   | ...
简历读数 = 最高「错误率 <1%」档位的 TTFT P99（口径限定语见 §4-M5.5）
```

**交付③ 口径② 实验**（真实调用，预算写死）：

新建 `scripts/experiment_real_latency.py`（模式照抄 experiment_fault_injection.py：环境覆盖在 import aegis 前、ROOT 锚定、UTF-8 落盘）：
- N=100 次（下限 50）、standard 档、串行（并发 1）、prompt 唯一化、缓存关、注入关；
- 每次记 `complete()` 首块耗时（D2：网关直连，测量点写进报告）；
- 输出首 token 分布 P50/P90/P99 + 直方图（文本桶即可）+ **理由声明原文**：「不做高并发：费用与厂商限流约束（04 M5）」；
- 预算护栏：`max_tokens=64`、脚本内写死 `BUDGET_CEILING_CNY = 1.0`，用 usage_ledger 圈定本次租户核对（ledger_check 模式，experiment_fault_injection.py:148-168）；
- 报告尾注：与口径① 的 800ms 假设对照一句话（「实测 P50 = X ms，模拟参数 800ms 属真实量级/偏保守」——以实测为准措辞）。
- 落盘 `reports/m5_real_first_token.txt`。

**交付④**：两份报告口径互检（两组数字不许出现在同一张表里混排——04 M5「两组口径分开呈现」）+ 深挖题登记。

### M5.3 水平扩展演示（M，约 2 次交付；**硬依赖 M4.7 #26，§0-3 未过不许开工**）

**新建**：`deploy/nginx.conf`；**修改**：M4.7 的应用 compose 文件（加 nginx 服务；api 服务去掉 `container_name` 与宿主端口发布——§7 T6）。

nginx 配置样例（ADR-007 两坑是核心，其余为 SSE 常识配置。**样例即口径基准、允许照抄**——对 plans/README §3「不给整段实现」的显式豁免，理由：两坑指令必须逐字精确，且 nginx 配置无「签名级骨架」可言）：

```nginx
upstream aegis_api {
    server api:8000;            # Docker 内嵌 DNS；--scale 后需 nginx reload（§7 T5）
}
server {
    listen 80;
    location / {
        proxy_pass http://aegis_api;
        proxy_http_version 1.1;
        proxy_set_header Connection "";      # 复用上游 keep-alive
        proxy_buffering off;                 # ADR-007 坑一：不关则 token 攒批，流式失效
        proxy_cache off;
        proxy_read_timeout 3600s;            # ADR-007 坑二：默认 60s 掐断长回复
        gzip off;                            # 压缩缓冲同样破坏逐帧送达
    }
}
```

compose 增补（形态随 M4.7 实况调整）：

```yaml
nginx:
  image: nginx:1.27-alpine
  ports: ["127.0.0.1:8080:80"]        # 只绑回环，既有安全口径
  volumes: ["./nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
  depends_on: [api]
```

演示脚本步骤（进 demo-script.md 开场段）：
1. `docker compose up -d --scale api=3`；`docker compose ps` 展示 3 副本；
2. curl 经 8080 发一条 chat，确认流式逐帧（肉眼可见 token 陆续到达）；
3. 断线重连：中断 curl，`GET /v1/sessions/{id}/stream?after_seq=N` 续收（跨副本命中不同实例也能续——PG LISTEN/NOTIFY + after_seq，00 §2.2 C22 行）；
4. （P4 拍板后）优雅停机顺手验证：`docker compose stop api`（观察 `stop_grace_period` 内在途流收尾）对照 `docker kill`（crash-only 路径，与 M5.4 kill -9 同场素材）。

验证点：3 副本轮询可从响应头/日志辨认；SSE 在 nginx 后不攒批、长回复不被 60s 掐断。

### M5.4 15 分钟 demo 脚本 + 两项凭证补录（M，约 3 次交付）

**交付① `docs/demo-script.md` 分镜**。每段四列：操作（含完整命令）/ 预期画面 / 讲稿一句话 / 失败预案。计时预算：

| 段 | 内容 | 预算 |
|---|---|---|
| 开场 | 架构一页（README 图）+ `docker compose ps`（3 副本 + nginx，M5.3 成果即布景） | 1.5 min |
| 高光1 故障注入 | 开 30% 注入（error 模式）现场发问题→照常回答；切 100% 注入单候选→熔断打开毫秒级拒绝（M1.13 phase_b 复用）；**C5 预答**（D9）：同 provider fallback 下熔断为何不开 | 3.5 min |
| 高光2 断点续跑 | 退款 300 元（>200 阈值）→ `approval_pending` 挂起 → curl 批准 → 前置校验重跑 → 续跑完成；同场 `docker kill` 一个 api 副本 → reaper 抢租恢复 → 重订阅通道续收 | 4 min |
| 高光3 多租户隔离 | 四大对抗快打（00 §7.2）：跨租户检索不可见 / B 侧缓存不命中 / 水平越权拒绝 / 跨租户审批 403 | 3 min |
| 高光4 replay 调试 | 取高光2 的 trace_id → trace API 逐步还原输入输出 → 回放模式确定性重跑同一会话 → diff 事件序列（复用 M2.12 等价性断言）——#27 正式高光 | 2 min |
| 缓冲 | 提问/超时余量 | 1 min |

排练纪律：完整跑 ≥2 遍并**实测计时逐段登记**（00 §9.2 验收「实测 ≤15 分钟」不是估算）；
超时预案写死在分镜里（优先压缩高光3 至 90 秒——评审 C33 的「深挖型面试官替换」思路反向使用）。
**彩排清单**（不进 15 分钟主线，跑一次留凭证行）：停 Redis → 会话互斥降级 PG advisory lock 复验（#14，00 §10.1 明写「M5.4 演示复验」）；停 PG → 事件写入退避后终止（**可选项，不进 §6 硬验收**：#15 归位 M2.12/紧张时 M4.0，00 未要求 M5 复跑——「已验」以 M2.12/M4.0 实况为准）。

**交付② 熔断恢复闭合时间实测**（#10，无条件补）——新建 `scripts/experiment_breaker_recovery.py`：

1. 清场三键（`aegis:cb:bailian:*`，先例 experiment_fault_injection.py:46/109）；
2. `gw_bad`：单候选路由 + `fault_rate=1.0`（零真实调用），连发直至 `open` 键出现，记 `t_open`；
3. **立即**切 `gw_good`（同一 Redis/breaker、注入关）——此刻即「上游恢复」，记 `t_recover`；
4. 每 0.5s 发一次真实短请求（`max_tokens=16`，预算写死 `BUDGET_CEILING_CNY = 0.5`）：open 期得 deny/换路失败属预期；
5. 首次成功且 `open`/`fails` 键消失 → 记 `t_closed`；**闭合时间 = t_closed − t_recover**（D8 定义，写进报告）；
6. 复跑 3 轮取全部值（TTL 相位不同，闭合时间在 (探针耗时, 30s+探针耗时] 区间浮动是预期——报告写区间与主导因子「open TTL 30s 设计值」）；
7. 落盘 `reports/m5_breaker_recovery.txt`，清场退出。

**交付③ deepseek 容灾切换实录**（§10.2 末行）——新建 `scripts/experiment_deepseek_failover.py`：

1. standard 档（候选链 `["bailian:qwen-plus","bailian:deepseek-v3"]`，config.py:36）；
2. `FAULT_INJECTION_RATE=1.0`、`FAULT_INJECTION_TARGETS=["bailian:qwen-plus"]`（**provider:model 格式**，config.py:58 注释）、缓存关；
3. N=20 次真实调用，逐次记录 `UsageChunk.model`；断言 20/20 == `deepseek-v3`；
4. ledger 圈定核对：本实验租户的 20 行 `model=deepseek-v3`（计费路径同样切换成功）；
5. 报告含 D9 预期行为段（熔断不开的机理）+ 花费（预估 <¥0.1，预算护栏写死）；
6. 落盘 `reports/m5_deepseek_failover.txt`。**若 deepseek-v3 调用失败**（模型下线/欠费等）：不硬凑——登记实况，M5.5 按 §10.2 说明改 05 表述（「DeepSeek 为配置候选」措辞）。

### M5.5 README 终稿 + 架构图 + 简历回填（M，约 3 次交付）

**交付① README 终稿**（repo 根 `README.md`，基于 M4.7 初稿——§0-9）。结构：

1. 一句话定位 + 七类工程问题（05 §2 口径）；2. 架构图；3. 高光能力表（每行：能力 | 一句话 | 凭证文件）；
4. Quickstart（compose up → 迁移 → 种子 → chat 一条）；5. **数字表（每个数字带口径限定语 + `reports/` 凭证链接）**；
6. demo 入口（docs/demo-script.md）；7. 文档地图（docs/ + ADR 索引）；8. AI 协作声明一段（05 §4 立场：不隐瞒、化被动为主动）。

架构图要点（mermaid，README 内嵌、无构建链）：三层 L3→L2→L1 单向依赖 + 横切（obs/安全/交付）；
L2 中事件溯源标出「断点续跑 / replay / 审计三合一」（#27 的视觉呼应）；数据面 PG（事实源）/Redis（六角色一句话）。

**交付② 简历回填**（改 `docs/05-resume-and-interview.md`）。回填规则表——**数字一律现场从凭证文件读，不许抄本表**：

| 占位符（05:11-25） | 凭证 | 回填模板（口径限定语随数字走） |
|---|---|---|
| 成功率 X% + P99 X s | `reports/m1_fault_injection.txt` | 「故障注入实验（30% 上游失败）下端到端成功率 _%（P99 _ s）」——口径已在句内 |
| 熔断恢复闭合 X s | `reports/m5_breaker_recovery.txt` | 「熔断恢复闭合 ≤_ s（open TTL 主导，实测 _ 轮区间 _–_ s）」或取最大值单数字+凭证注 |
| 评测 X 条用例、通过率基线 X% | M4.5 报告（§0-10 实名） | 「_ 条用例、通过率基线 _%」 |
| 档位路由降本 X% / 缓存降本 X% | M4.6 两报告 | 「档位路由降本 _%、缓存降本 _%（含实验口径）」——「含实验口径」四字保留 |
| 本地压测 P99 首 token X s | `reports/m5_loadtest_overhead.txt` | 「**本地压测（模拟上游延迟）下** P99 首 token _ s」——限定语原文出自 00 §9.1 M5.5，逐字保留 |
| Qwen/DeepSeek 实测 | `reports/m5_deepseek_failover.txt` | 有凭证：保留「Qwen/DeepSeek 实测」+ 可加「（qwen-plus↔deepseek-v3 容灾切换实录）」；无凭证：改「Qwen 实测，DeepSeek 为配置候选」并同步 06 §5 |

**#34 应用岗调序**（结构性变更，照抄现文即错；调序方案已内联如下——出处「素材包 H9」为交接期工作件、未落档，以内联结论为准）：bullet 顺序改为
**① 自研 Agent 运行时（含事件溯源/replay——#27 借调序自然进前三）② 业务层 ③ 治理 ④ 自研 LLM 网关**（infra 数字降为支撑证据，句式从「自研网关：…」调为佐证语气）；
90 秒叙事线（05 §2）第 3 拍「亮点抓手」默认改挑事件溯源/replay 展开；
**精简版校验**：取前三 bullet 各一行后，replay 字样必须仍在（#27 的验收点）。

**#28 逐词校对 checklist**：①「统一多供应商抽象」仅指协议层能力（保留「Anthropic 适配器桩测试就绪」限定）；
②「实测」二字只跟有凭证的名词；③ 与 06 §5 口径句（06:73-75）逐词对照；④ 被砍项三处同步（00 步骤标注 / §10.2 / 05 模板——00 §11 第 4 条）。
（P3 拍板后）技能栏加 LangGraph 一行。

**交付③**：00 §10.2 状态列翻转为「✅ 已回填」+ 05 头部版本号与「回填完成」注记。

### M5.6 终验收（S，1 次交付）

1. 00 §9.2 四项逐项对账（见 §6）；
2. 简历与交付物**逐词对照**：05 模板每个名词短语在 repo 里找到对应物（代码/报告/文档），找不到的当场删或改；
3. 00 §13 六项毕业清单走完：验收对账 / 报告落盘 / CI 全绿 + **tag `v1.0`** 推送 / 记忆归档 / 00 更新（§9 标 ✅、§10.1 #10/#27/#28/#33/#34 翻转、§10.2 清零）/ 开新会话（项目完结，「新会话」= 面试准备模式）；
4. **记忆归档（项目完结版）要点**：`aegis-agent-platform.md` 重写为——状态行（v1.0 已交付 + 最终测试数 + tag 链）；最终数字表指针（README §5 + reports/ 清单，不复制数字）；面试准备入口（05 全文 + interview-questions.md 全部题目状态 + 各 retro/compare 文档）；v2 边界一段（00 §10.3，防止面试前复习时误述范围）；协作教训精选保留；`MEMORY.md` 索引行同步改为完结态。

---

## §5 测试蓝图（AI 直写；命名与风格学 tests/runtime/test_executor_exec.py——中文单句 docstring、断言直给、辅助函数下划线前缀）

M5 唯一进 CI 的新逻辑是 SSE 帧解析器（D4）与 LatencyModelProvider（生产包内代码必须有测试）。
压测/演示/补录脚本一律**不进 CI**（时序敏感——00 §2.2 测试纪律行），凭证以 reports/ 为准。

**新建 `tests/loadtest/test_sse_client.py`**（纯函数测试，无 fixture 依赖，无 DB/Redis）：

| 测试函数 | 断言要点 |
|---|---|
| `test_single_frame_event_and_data` | 一帧 `event: token\ndata: {...}\n\n` → SSEFrame(event="token", data 原文) |
| `test_multiline_data_joined` | 两个 `data:` 行 → 以 `\n` 连接（SSE 规范） |
| `test_frame_split_across_chunks` | 帧从中间被 chunk 边界切开 → 缓冲拼接后仍解析出完整帧（核心场景：iter_content 任意切割） |
| `test_trailing_partial_frame_not_emitted` | 尾部半帧不产出（无 `\n\n` 不算帧） |
| `test_crlf_tolerated` | `\r\n\r\n` 分帧同样成立 |
| `test_comment_line_ignored` | `: keep-alive` 注释行不产字段、不产帧 |
| `test_id_field_captured` | `id: 42` → frame.id == "42"（续传依赖） |
| `test_colon_space_optional` | `data:x` 与 `data: x` 等价 |
| `test_multiple_frames_in_one_chunk` | 单 chunk 含两帧 → 依序产出两帧 |

**新建 `tests/gateway/test_latency_model.py`**（M5.2 交付①随行；async 测试走 pyproject `asyncio_mode="auto"`）：

| 测试函数 | 断言要点 |
|---|---|
| `test_chunk_sequence_shape` | 产出序列 = N 个 TextDelta + 1 个 UsageChunk + 1 个 StopChunk（完整流形状，缓存完整性守卫兼容） |
| `test_usage_reports_response_tokens` | `completion_tokens == response_tokens`、`model` 回显入参 |
| `test_prod_forbids_loadtest_upstream` | `Settings(app_env="prod", loadtest_upstream=True)` 构造即 ValueError（与 config.py:61-67 同款断言风格，学 tests/test_config.py） |
| `test_timing_params_default` | 默认 first_token_s=0.8 / tokens_per_s=20.0（**钉死口径参数**——被改动=简历口径漂移，测试是护栏）；不测真实耗时（时序不进 CI），sleep 经注入桩记录（`_sleep_recorder` 模式，test_executor_exec.py:26-30） |

fixture：全部复用现有根 conftest；无新增 DB fixture。sleep 注入若需改 `__init__` 加 `sleep=asyncio.sleep` 参数（ToolExecutor 先例）。

**预期新增测试数：13–16**（解析器 9〔上表实列〕+ latency 4–5 + 机动 ≤2，机动可不用）。M5.3–M5.6 新增 0。
收集数账本：M5.1 后 = B + 9；M5.2 交付① 后 = B + 13~16（含机动）；此后不变。**逐项点名后再报数**（M2.4 错报教训，00 §6.3 偏差登记①）。

---

## §6 验收对账清单（对应 00 §9.2 + §13）

- [ ] **demo 实测 ≤15 分钟**跑通全部高光（含 replay 第四高光——#27）：以排练计时记录为凭，逐段时长登记进 demo-script.md 尾部；
- [ ] **压测报告 ≥3 并发档位、两组口径分开**：`m5_loadtest_overhead.txt`（档位表齐 + 预热稳态口径注记 + 限流放宽值声明）与 `m5_real_first_token.txt`（N、测量点、不做高并发理由声明）各自独立成文；
- [ ] **两项凭证补录完成**：`m5_breaker_recovery.txt`（≥3 轮 + D8 定义注记）、`m5_deepseek_failover.txt`（20/20 model 断言 + ledger 核对 + C5 预期行为段）——或 deepseek 失败时 05 表述已同步修改；
- [ ] **§10.2 清零**：七行全部 ✅ 已回填，简历无残留 X；口径限定语逐条在位（§4-M5.5 表）；
- [ ] 彩排清单 #14 会话锁降级复验凭证行在 demo 报告内（停 PG 复跑为可选项，做了则加一行，不作硬验收——§4-M5.4 彩排清单）；
- [ ] pytest 收集数 = B + 本里程碑新增（§5 账本），CI 全绿；
- [ ] 00 §13 六项全勾：tag `v1.0` 已推送、记忆完结版归档、00 §9 标 ✅ + §10.1 #10/#27/#28/#33/#34 翻转。

---

## §7 陷阱与常见错误（症状 → 原因 → 正解）

**T1 · 凭记忆写 locust API**：`events.request_success.fire(...)` 报 AttributeError 或静默无指标 → locust 2.x 把 request_success/request_failure 合并为统一 `events.request`，字段名也换代（response_time/response_length/exception/context）→ 落笔前 Read `.venv/Lib/site-packages/locust/event.py` 与 `env.py` 核实事件与字段；这是本计划无法预核的少数接口（locust 尚未安装，§0-13）。

**T2 · locustfile 里 import aegis**：locust 启动即卡死/协程怪异报错 → locust 用 gevent monkey-patch 全局 socket/ssl，aegis 的 asyncio+httpx 代码在补丁环境下行为不可预期 → locustfile 只用 requests/纯 Python（D3）；需要复用的逻辑（帧解析）放 sse_client.py 且保持零 aegis 依赖。

**T3 · 用 `iter_lines` 收 SSE**：TTFT 虚高且成簇（多帧同时「到达」）→ requests 的 iter_lines 有内部缓冲，且按行切割吞掉空行分帧信息 → `iter_content(chunk_size=1024)` 拿原始 bytes 交给 `iter_sse_frames` 自己切帧（§4-M5.1 步骤 4）。

**T4 · 压测数字被平台自己的闸门污染**：错误率虚高/吞吐封顶在 8 req/s → 默认 `provider_rate=8.0`（config.py:40）与租户限流在压测流量下先于「容量」触顶；或重复 prompt 命中精确缓存把 TTFT 测成 <50ms → 限流放宽 + 值进报告口径（D7）；prompt 唯一化 + `CACHE_TTL_SECONDS=0`（D5）。

**T5 · `--scale api=3` 后流量只打一个副本**：三副本 CPU 一高两低 → nginx 在启动时解析 upstream 域名并缓存，scale 发生在 nginx 起后则新副本不在解析结果里 → 先 scale 后起 nginx，或 scale 后 `docker compose exec nginx nginx -s reload`；demo 里把顺序写死进命令步骤。

**T6 · scale 时端口冲突/容器名冲突**：`--scale api=3` 报 `port is already allocated` 或 container_name 冲突 → api 服务写了宿主端口发布或 `container_name` → api 只暴露容器网络端口，宿主入口唯一走 nginx `127.0.0.1:8080`（§4-M5.3）；这要求改 M4.7 的 compose——属 M5.3 范围内修改，不是重构。

**T7 · SSE 在 nginx 后「不流了」**：curl 直连 api 逐帧、经 8080 一次性吐全文 → `proxy_buffering` 默认 on（ADR-007 坑一）；或开了 gzip → 配置样例三行（buffering/cache/gzip）缺一不可；验证方法写进演示步骤（肉眼看 token 节奏）。

**T8 · 长回复 60 秒整被掐**：压测/演示中恰好 ~60s 处连接断开、错误归因混乱 → nginx `proxy_read_timeout` 默认 60s（ADR-007 坑二）→ 调大到 3600s；注意该超时是「两次读之间」的空闲超时，与 L1 块间空闲 30s（base.py:38-39）语义同族——面试可对答。

**T9 · 熔断恢复实验测出「假 30s」或熔断不开**：闭合时间恒等于 open_seconds 却无探针成功记录，或 fails 永远到不了 5 → 前者：恢复探测请求间隔太大/预算不足以完成探针调用；后者：容灾实验的同 provider 成功清零了 fails（D9 机理），或上一轮实验残留键 → 严格按 §4-M5.4 交付② 步骤：清场 → 双网关共享 breaker → 0.5s 轮询；容灾实验与熔断实验**分开跑、各自清场**。

**T10 · `fault_injection_targets` 写成 provider 名**：注入不生效、20 次全走 qwen-plus → 目标格式是 `provider:model`（config.py:58 注释：`["bailian:qwen-plus"]`）→ 照抄 experiment_fault_injection.py:22 的格式。

**T11 · PowerShell 落盘乱码/UTF-16 凭证**：报告文件 git diff 显示二进制或中文乱码 → 中文 Windows 管道 GBK 解码 + Tee-Object 默认 UTF-16（06 §4 第三坑）→ 报告一律由 Python 脚本 `write_text(encoding="utf-8")` 落盘（先例 experiment_fault_injection.py:196）；必须用 shell 重定向时 `Out-File -Encoding utf8`；脚本内路径用 `Path(__file__)` 锚定项目根（记忆档案教训——PyCharm cwd=脚本目录会把 reports/ 写歪）。

**T12 · 压测跑在裸 uvicorn --reload 上**：数字异常好/异常差且不可复现 → 违反「演示/压测一律走容器」（06 §4）——reload 监听器、单副本、无 nginx 都不是交付形态 → 口径① 一律容器全栈；报告环境行写死部署形态。

**T13 · 口径混写**：报告或简历把口径① 的 P99 与口径② 的分布放同一句/同一表 → 两组口径分开是 04 M5 原文要求，混写=「数字是评测集凑的」质疑入口 → 两文件两段落，简历只取口径① 数字且带「模拟上游延迟」限定语。

**T14 · 照抄 05 现文回填**：直接在现有 bullet 顺序上填数字 → 05 §1 当前顺序**不是终稿**（#34 调序 + #27 前三 bullet 是 M5.5 的结构性义务，方案已内联 §4-M5.5）→ 先调序再回填，最后跑精简版校验（前三 bullet 各一行仍含 replay）。

**T15 · 弱模型高发四连**：① 凭记忆发明接口（如给 LLMGateway 编一个不存在的 `set_fault_rate()` 运行时开关——注入参数是构造期的，router.py:172-174；要切换就构造两个网关）；② 越步（M5.1 顺手把 M5.2 的 Provider 也写了——每次交付只给一步，00 §2.1 第 5 条）；③ 顺手重构（觉得 factory 组装「不优雅」想改——M5 零重构窗口，v1.0 前动核心组装是自杀）；④ 收集数未逐项点名就报总数（M2.4 错报 12 实为 11 的教训）。另：**交付正文必须放在回合最末、所有工具调用之后**（2026-07-09 生产代码整段蒸发事故——记忆档案）。

**T16 · 改延迟模型参数「让数字好看」**：把 800ms 改小让 P99 漂亮 → 参数是 00 §9.1 写死的口径且与 C1 超时语义耦合（§3.1）→ 参数硬编码默认值 + 测试钉死（§5 `test_timing_params_default`）；数字不好看就如实报——「没实测不写数字」的孪生纪律是「实测了就写实测的」。

---

## §8 指令块模板（仓库根（本 repo）；顺序 = 00 §2.1 第 3 条，逐条给用户执行）

**通用模板**（每次交付后；`<...>` 按步替换）：

```powershell
uv run ruff format .
# 预期：N files left unchanged（若有 reformatted，重跑一次确认收敛）
uv run ruff check .
# 预期：All checks passed!
uv run pytest -q
# 预期：<B+累计新增> passed（收集数账本见 §5；与预告逐项点名核对后才报）
uv run mypy .
# 预期：Success: no issues found in <N> source files
uv run lint-imports
# 预期：Contracts: 1 kept, 0 broken
git add <本步指定文件，逐个列出，不用 git add .>
git commit -m "<类型(范围): 主题>" -m "<为什么：一句话动机>"
git push
# 预期：远端 CI 全绿（含 M4.3 回放回归门）
```

**各步专用差异**：

| 步 | add 清单（预期） | 附加命令与预期 |
|---|---|---|
| M5.1 | `pyproject.toml uv.lock scripts/loadtest/ tests/loadtest/` | 前置 `uv add --dev locust`（预期 lock 更新、Resolved N packages）；pytest 收集数 **B → B+9**；commit 例：`feat(loadtest): 自写 locust SSE client（帧解析纯函数+虚拟用户）` -m `SSE 压测无现成客户端；TTFT 指标须自采` |
| M5.2① | `aegis/core/config.py aegis/gateway/factory.py aegis/gateway/providers/latency_model.py tests/gateway/test_latency_model.py` | 收集数 **→ B+13~16**（§5 账本）；生产文件用户敲完落盘后再走本块 |
| M5.2②③ | `scripts/experiment_real_latency.py reports/m5_loadtest_overhead.txt reports/m5_real_first_token.txt` | **前置：M5.3 nginx/compose 改造已落地（否则 8080 不存在、`--scale` 踩 T6——附录 P8'）**；实验前起容器栈：`docker compose -f deploy/<M4.7 文件名> up -d --scale api=3`；locust：`uv run locust -f scripts/loadtest/locustfile.py --headless -u <档位> -r 5 -t 120s -H http://127.0.0.1:8080`（预期 CSV/终端表 + 报告脚本落盘）；收集数不变 |
| M5.3 | `deploy/nginx.conf deploy/<compose 文件>` | `docker compose ... up -d --scale api=3 && docker compose ... ps`（预期 api ×3 + nginx Up）；SSE 验证 curl 一条（预期逐帧）；收集数不变 |
| M5.4 | `scripts/experiment_breaker_recovery.py scripts/experiment_deepseek_failover.py docs/demo-script.md reports/m5_breaker_recovery.txt reports/m5_deepseek_failover.txt` | 两实验各自跑（预期报告含区间、20/20 断言）；demo 排练计时登记；收集数不变 |
| M5.5 | `README.md docs/05-resume-and-interview.md docs/00-master-plan.md` | 纯文档步；pytest 照跑护栏（收集数不变） |
| M5.6 | `docs/00-master-plan.md docs/plans/m5-detailed.md`（偏差回填） | `git tag v1.0 && git push origin v1.0`（预期远端 tag 可见）；记忆文件更新（AI 直接维护，不走 git——docs 内文件除外） |

---

## §9 完成后动作（M5.6 当天）

1. **00 更新**：§9 全章标 ✅ + 实际交付对账表（步 → 提交，学 §5.1 格式）；§3 总览 M5 行 ✅ + tag `v1.0`；§10.1 #10/#27/#28/#33/#34（及 P4 若做则补登记的优雅停机行）状态翻转；§10.2 七行全 ✅；
2. **本文件头部回填「实际落地偏差」**（无偏差也写「无偏差」——plans/README.md §4）；
3. **深挖题登记** `docs/interview-questions.md`（照该文件既有节式追加 `## M5 压测与交付（日期 出题）`，编号接续不重排）。建议题目：① 为什么 locust SSE client 要自写、TTFT 怎么采；② 「平台开销」怎么从端到端延迟里剥出来（800ms 模型的作用）；③ 为什么真实调用不做高并发；④ Nginx 对 SSE 的两个坑及其超时语义与 L1 块间空闲超时的同构关系；⑤ 熔断恢复闭合时间由什么主导、怎么测的；⑥ 同 provider fallback 下熔断为什么不开、这暴露了什么粒度问题（C5→v2 provider:model）；⑦ demo 的 replay 段在演示什么本质能力；
4. **记忆归档完结版**（要点见 §4-M5.6 第 4 条）+ `MEMORY.md` 索引行更新；
5. 项目完结：后续新会话即面试准备模式（通读 05 + 全部 ADR + interview-questions 自测——00 §12 通用行）。

---

## 附：发现的上游文档问题（撰写本计划时核对发现，勿擅改上游，逐条报用户裁决）

| # | 问题 | 影响 | 建议处置 |
|---|---|---|---|
| P1' | 评审 C35「优雅停机在 M5.3 演示中顺手验证一次」（review:393）在 00 §10.1 无追踪行 | 只读 00 会漏；本计划以 §3.3-P4 拍板项承接 | 拍板后在 00 §10.1 补一行 |
| P2' | 00 M5.4 行文未提 #14（会话锁 PG advisory 降级「M5.4 演示复验」在 §10.1 有、§9.1 行没有） | 同类漏项风险（与 M4.7 容器化漏项同构） | 本计划已并入彩排清单；00 可在 M5.4 行补括注 |
| P3' | 「locust SSE client 自写（**1 天**）」的天数标注在 00 §9.1 M5.1 行与 04:161 同源并存，且与同一 00 行的规模 **M**（≈2–3 次交付）粒度不一致——冲突在 00 行内部，「以 00 为准」无法裁决 | 排期预期差 | 建议 00 删「1 天」或加注「1 天 ≈ 2 次交付的墙钟估计」，处置报用户 |
| P4' | 05 模板无 LangGraph/框架素养条目，但 #33 声称支撑「熟悉 LangGraph」简历表述——落点（技能栏/项目 bullet）无文档裁决 | M5.5 回填时无所依 | §3.3-P3 拍板后同步 05 |
| P5' | 评审 C43 处置为「M4.7 迁 docs 时自然解决，措辞改 README 初稿」，但 00 M4.7 行未显式写 README 初稿 | M5.5「终稿」可能落空为从零写 | §0-9 开工核对兜底；若 M4.7 计划文件已含则此条自动关闭 |
| P6' | 00 §9 无 M5 真实调用口径声明行（§7.0/§8.0 均有对应段） | 弱模型可能在压测里烧真钱 | 本计划 §1 已导出口径；建议 00 §9 补一句 |
| P7' | 00 §9.1 M5.2 行与 04 M5 原文点名「**FakeGateway** 注入固定延迟模型」，但 M2.6 FakeGateway 是 L2 回放件（匹配键=会话+轮次），不适合无剧本压测流量——本计划 §3.2 D1 改挂 Provider 层（LatencyModelProvider），属计划层推翻 00 步骤行点名机制的口径冲突（plans/README §2） | 只读 00 会按 FakeGateway 实施；D1 新增 `aegis/` 生产代码，须对 §1「不新增平台能力」显式豁免（§1 已加限定） | 建议 00 §9.1 M5.2 行措辞改「延迟模型替身（Provider 层）」，报用户裁决后修 00 |
| P8' | 00 §9.1 步骤顺序 M5.2（压测）先于 M5.3（nginx/compose 改造），但口径① 实验的容器全栈形态（nginx 8080 入口、api 去 container_name/宿主端口）依赖 M5.3 交付物——依赖倒置 | 按指令块原样在 M5.3 前执行口径① 时 8080 不存在、`--scale api=3` 踩 T6 冲突 | 本计划已在 §4-M5.2 交付② 与 §8 注明「实验实际执行排在 M5.3 落地之后」（交付顺序与实验执行顺序解耦）；建议 00 在 M5.2 行补括注 |
