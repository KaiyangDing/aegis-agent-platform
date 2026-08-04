# M2 复盘（定稿）：从注入面到毕业实验的自研运行时全程

> **定稿基线**：tag `m2-runtime`（commit `98e2549`，2026-07-17），**548 测试**全绿，L2 生产代码
> 实测 **4371 行**。**范围**：M2.1–M2.13 全程（含两枚缺陷修复提交与模型池 v3 事件）。
> **凭据分层**：M2.1–M2.7 章节（§2 前七行、§4.1–4.4、§5 前六节）经对着 `6b7f22e` 源码逐条 Read
> 核实（一轮对抗性证伪 55/60 CONFIRMED、0 证伪、5 处精修并入）——**该部分正文一字未动**，其行号锚
> 为 `6b7f22e` 时点值，M2.8+ 改造使部分行号漂移（如 `_llm_step` 现约 loop.py:425-475）——语义断言经
> 毕业时点复核仍成立，精确行号查 08 或直接 Read；M2.8–M2.13 新章节（§2 后六行、§4.5、§5 后五节、
> §6 九/十、§7 更新）以毕业时点源码为准（定稿会话中全部文件已逐一 Read）。
> **读法**：08 答"接口长什么样"，本文答"为什么长这样、一次 run 怎么跑、边界在哪"；速查图册见
> atlas.md（图组/闸门总表/数字卡）。面试前把 §4（旅程）和 §6（哲学）读到能脱稿。
> **配套**：接口快照 08；步骤对账 00 §6.3；面试题库 interview-questions.md 第 12–74 题；
> 框架对照 compare-langchain-m1 / compare-langgraph-m2；M0/M1 姊妹篇 retro-m0-m1.md。

---

## 1. 全景地图（代码 ↔ 职责 ↔ 测试）

```
aegis/runtime/                              # L2：与业务无关，服务任意 L3（"模型是租来的，Harness 才是自己的"）
├── spec.py       (168 行)  M2.1  注入面四类型（毕业时 AgentSpec 9 字段：M2.8 +owned_values/entry_classifier）
├── events.py     ( 71 行)  M2.1  16 类事件 + AgentEvent（无时间戳=确定性回放前提，seq 是逻辑时钟；
│                                  C8 +summary_updated、M2.8 +guardrail_triggered、M2.10 +recovery_abandoned）
├── store.py      (673 行)  M2.2+ 五表 ORM + 单写者 EventWriter + 审批 CAS + M2.9 SessionStateStore(T1-T5)
│                                  + M2.10 LeaseStore（CAS 租约/围栏 generation）；退避白名单 M2.12 +OSError
├── tools.py      (190 行)  M2.3  工具契约与注册：@tool/ToolDef/ToolContext/ToolRegistry（防呆 import 时爆炸）
├── executor.py   (336 行)  M2.4+ 七步生命周期五结局 + M2.10 reexecute 窄入口（原幂等键重执行）
├── context.py    (354 行)  M2.5  ContextBuilder 六层预算编译 + 滚动摘要（summary_updated 生产端）
├── replay.py     (325 行)  M2.6  Cassette/FakeGateway(start_cursors)/Recorder/normalize_events（C31）
├── guardrails.py (576 行)  M2.8  三挂点防线：15 条规则库+分类器(fail-open)/wrap_untrusted/OutputGuard(C23)
│                                  （15 条=M2.8 的 14 + 复盘补丁四 tool_probe_en `a138bbd`）
├── loop.py       (654 行)  M2.7+ 六道闸门/_Tap 外流/异常矩阵 + M2.8 挂点接线 + M2.9 挂起链路/resume_run
├── runtime.py    (559 行)  M2.7+ 门面+组装 + M2.9 恢复单入口/重建器 + M2.10 租约伴飞/崩溃分诊四支
└── __init__.py   (  0 行)        空——全仓无 re-export
     core/tokens.py (17 行, M2.0)   L1/L2 同一把估算尺（C25）
     core/locks.py  (288 行, M2.9)  会话锁：Redis 主(CAD/看门狗) + PG advisory 降级 + 粘滞切换
     workers/       (189 行, M2.10) celery 引导 + reaper（租约扫描/CAS 抢租/ResumeHook/C9 终局判定在 T5）
```

**测试分布**：全仓 **548**（毕业时点；M2.7 时点 401、runtime 分组 244 的逐文件账见上版与 08 §7）。
毕业期新增大件：guardrails 三文件 58、suspend_resume/locks 系 36、lease/loop_recovery 系 36、
`test_long_dialog_benchmark` 8（判据经 importlib 复用录制脚本）、`test_recovery_replay` 8（三形态等价）、
event_store OS 白名单回归 1。测试目录镜像源码分层。

一句话地图：**events 是唯一事实源，其余全是它的投影或消费者**；spec 定义"注入什么"，
store 定义"事实怎么落"，tools/executor 定义"工具世界的边界"，context 定义"每轮 prompt 怎么编译"，
replay 定义"怎么在零真实调用下回放"，loop/runtime 把这一切编排成一条有界收敛的事件流。

---

## 2. 逐步交付账（M2.1 → M2.7，关键决策 + 提交）

| 步 | 一句话 | 关键决策（面试锚点） | 提交 |
|---|---|---|---|
| **M2.1** 核心抽象 | 注入面四类型 + 14 类事件枚举 + 门面/协议 | 校验强度按信任边界分档（受信配置 frozen dataclass，不背 pydantic）；`TERMINATION_GATES` 用全集减法派生恰 6 个；`GatewayLike.complete` 声明成 `def` 非 `async def` | `75f29c1` `fe8b3e4` `6d02897` |
| **M2.2** EventStream 底座 | 五表迁移 + 单写者 + 投影同事务 + 审批 CAS | write-ahead 幂等键（`events.id` 用应用侧 uuid 而非自增，因幂等键须先于副作用存在）；投影与事件同生共死（ProjectionError 掀翻 append 事务）；围栏三协议（幽灵写入按 id 识别为成功/围栏终态零重试/瞬态白名单退避 3 次）；审批全 CAS（decide 查过期 fail-closed、cancel 不查、expire_due 可注入时钟） | `4f60fa1` `02173df` `5bfe39f` `4cef2a1` |
| **M2.3** 工具注册 | @tool 装饰器 + ToolRegistry + 演示工具集 | 身份走 ctx 注入、业务参数走 schema（越权第一道防线在类型签名上）；C15 三层防呆（写工具必须"有闸门或签字画押豁免"，读工具不许豁免）；schema 与 args_model 同源于函数签名；get 返 None vs add 重名抛错（机制 vs 政策） | `a44c78e` `270d938` |
| **M2.4** ToolExecutor | 七步生命周期 + 五结局 | 世界分界（业务结局编码成 ToolOutcome，基础设施故障裸传播）；write-ahead 先落盘、事件 id 经 ctx 透传当幂等键；写超时=RESULT_UNKNOWN 封死重试（X1）；风险闸门 fail-closed vs 摘要钩子 fail-open（C34 反向） | `d9a8a73` `8cc635e` `014ec21` |
| **M2.5** ContextBuilder | 六层预算编译 + 滚动摘要 | prompt 是编译不是拼接（六层各带预算，超预算各有确定性收缩）；滚动摘要必须写 `summary_updated` 事件而非只 UPDATE 投影（不可确定重算的必须落事件）；try 只包 summarize 一行（增强层 fail-open，事实源/围栏裸传播）；"异步预热"落成同步 await + 0.8 触发阈值（保 seq 可复现） | `61695a3` `f9b0902` `3fde910` `c3eb8ce` |
| **M2.6** 录制回放 | Cassette/FakeGateway/Recorder/normalize | 匹配键 `(session_id, scope, 道内序号)` 非 prompt 哈希；四道独立游标（C10）；游标先推进后 yield（D6）；半截流绝不入带（D5，done 标志在 async for 自然结束后）；C31 归一化划"行为等价"边界 | `70907f9` `3f772c0` `8bec868` |
| **M2.7** AgentLoop 总装 | 六道闸门 + 异常矩阵 + 组装九步 | _Tap 双写让 yield 序≡seq 序（I4）；六道闸门阈值零魔法数字全来自 LoopPolicy（I1）；闸门#2"LLM 90s"仅 `deadline_s` 传播不包 asyncio.timeout（C1）；六类异常压成四组 except、故意不接 GatewayError 基类；I3 显式接线关掉"默认值巧合相等"挂点 | `cce29f0` `311283a` `a7c0e62` `6b7f22e` |

| **M2.8** Guardrails | 三挂点防线：入口 14 条规则库+可选分类器 / wrap_untrusted / 出口状态机 | 规则库无条件底座、分类器增强层只抬不压（StrEnum 裸 max 字典序陷阱→显式序表）；OutputGuard"逐字符 feed≡整段 feed"不变量（聚合接线与 M3.10 流式同行为）；C23 owned_values 规范化字面等价放行本人 PII；防线命中一律 COMPLETED（防线≠第七道闸门 D10）；entry_classifier 默认关（会话中拍板：不让既有测试陪跑 guard 道） | `66b5d22` `9e8efe6` `553fb20` |
| **M2.9** HITL 挂起-恢复 | core/locks.py + 挂起链路 + 恢复单入口 + T1-T4 状态机 | 锁三实现（CAD 释放/看门狗 lost 即停不切后端/PG advisory 三件套/粘滞切换且"占用≠故障"）；挂起=干净收尾无 loop_terminated（_SUSPENDED 哨兵 D2）；"审批回调只做 decide CAS"、恢复统一走单入口；事件流重建 working**保事实不保字节**（K2②：(name,args) 语义配对、弃置补话术）；三重互斥 decide×锁×transition | `184a485` `ab4fcd8` `578b37f` |
| **M2.10** 恢复调度 | LeaseStore + 租约伴飞 + reaper + kill -9 实录（AI 直写例外步） | 租约 CAS 同 owner 重入/NULL 幽灵兜底；LeaseLost 自毁零事件（新 owner 已接续 seq，再写必撞约束）；reexecute 凭**原事件 id** 重执行；崩溃分诊四支（尾终止仅修状态/悬挂工具 fill/悬挂 LLM 与干净缝代码合流）；C9 终局判定权在 T5 transition（lease 侧 CAS 因 NULL 兜底可重入而废弃）；两课：过滤式断言（空间）+时序无关断言（时间） | `2af377c` `7dccdbf` `3df455a` `de39165` `16e84bf` |
| **M2.11** 长对话基准 | 40 轮真实录制 cassette + 回放 8 测试 + 基准会话集登记表 | **六跑迭代 ≈¥0.55 揪出六项缺陷全被六道自检拦在落盘前**：摘要 prompt 枚举窄丢会员号/C34 fail-open=回放分歧源（"干净录制">"成功运行"）/文三路→文大路采样变异（埋点避真实命名家族）/19点→19:00 格式归一（顺书写吸引子）/幻影 glm5.2（入池三验纪律）/思考模型饿死首块（全池 enable_thinking:false）；判据经 importlib 单一事实源（I1）；例外①消耗 | `8a2d4de` `3679e7f`（先行 `90060c9` `61e89d7`） |
| **M2.12** 毕业实验 | 中断-恢复等价强断言 + 真实冒烟 + HITL 演示 + 降级两实录 + LangGraph 对照 | 等价判据=C31+半截步折叠+剔 run 簿记键 {iteration,input_tokens_est}；确定性中断=monkeypatch EventWriter.append（无缝版 CrashSink）；冒烟只断三不变量 ¥0.001004（例外②收官）；**停 PG 实录抓出 OS 级白名单盲区**（注入测语义、实录测形状——修复 `98e2549` 回归测试先红后绿） | `d0857de` `d4abb40` `98e2549` |
| **M2.13** 毕业四件 | 00 七项对账全勾 + tag + atlas 骨架 + 记忆毕业版 | 图册增量维护纪律启动（#40：M3.12/M4.8 增量、M5.5 终稿） | tag `m2-runtime` |

**提交纪律**：每步小步单主题、message 写"为什么"、生产代码用户亲手敲入（M2.10 全步与 M2.11 剧本加固两处
特许例外均登记在案）、测试 AI 直写；M2.5② 曾误删 future import（③补回），M2.4①/M2.7④ 各错报一次预告
收集数，M2.11 第二笔提交 message 与首笔重复——教训均见记忆档案与各计划偏差块。

---

## 3. 接口对齐表（谁消费谁的什么、协议缝在哪）

> #35 明确要求。缝的类型分四种：**结构化 Protocol**（只认形状不认具体类）/ **frozen dataclass 注入**
> （一次 run 内不可变）/ **StrEnum 值契约**（值进事件与回放，改值=破坏历史）/ **纯函数/类型别名**。

| 契约 | 生产者 | 消费者 | 缝的类型 | 出处 |
|---|---|---|---|---|
| **AgentSpec** | L3（M2 由测试构造，M3.2 归 API 层） | `AgentRuntime.run` 拆包接线；`AgentLoop` 读 system_prompt/model_tier/tools | frozen+slots 注入面 | spec.py:130-158 |
| **LoopPolicy** | L3 经 `AgentSpec.policy` | `AgentLoop` 六道闸门阈值唯一来源；llm_step_timeout_s→deadline_s；tool_step_timeout_s→executor（I3） | frozen dataclass + __post_init__ 防呆 | spec.py:48-80 |
| **ContextConfig** | L3 经 `AgentSpec.context_config` | `ContextBuilder` 六层预算；executor result_token_budget；loop max_tokens=output_reserve（D3） | frozen dataclass；input_total 只读属性 | spec.py:83-118 |
| **ToolDef** | `@tool` 从签名+docstring 生成，或直接构造 | `AgentSpec.tools`；`ToolExecutor` 经 registry.get 取说明书；`AgentLoop` 转 ToolSpec 喂 LLMRequest | frozen+slots + 注册期防呆 | tools.py:62-103 |
| **ToolContext** | `ToolExecutor` 在 write-ahead 后注入（tool_call_id=落盘事件 id） | 工具 handler 实现（身份 LLM 不可控） | frozen+slots（越权防线在类型签名上） | tools.py:36-54 |
| **ToolOutcome** | `ToolExecutor.execute` 唯一返回类型（异常只留给基础设施） | `AgentLoop._run_tools` 按 kind 分支、content 回填模型 | frozen+slots 值对象；OutcomeKind 五结局 | executor.py:34-41 |
| **AgentEvent** | `EventWriter.append` 返回（已 durably committed 的镜像） | `_Tap.drain`→loop yield→runtime yield 给 L3；`normalize_events` 做 C31 断言 | frozen+slots；**不带时间戳** | events.py:41-69 |
| **EventWriter** | `EventWriter.open` 读流尾接续 seq，在 run() 构造 | `_Tap` 唯一具体包裹 | 具体类（单写者，一 run 一实例） | store.py:287-387 |
| **EventSink** | executor.py 定义 Protocol | `ToolExecutor`/`ContextBuilder` 只依赖形状、**不 import EventWriter**；`_Tap` 也满足此形状 | **结构化 Protocol**（async def append） | executor.py:44-57 |
| **ApprovalStore** | 以 SessionFactory 构造，原语齐全 | M2 仅测试写；生产消费方 M2.9 接电，reaper M3.9 | 具体类；翻转全走 CAS | store.py:390-476 |
| **GatewayLike** | runtime.py 定义 Protocol | `AgentRuntime`/`AgentLoop`（收 `scoped_view(g,'main')`）/ `_make_summarizer` | **结构化 Protocol**（`def complete`→AsyncGenerator） | runtime.py:30-40 |
| **SessionFactory** | 生产=core.db；测试=db_session_factory fixture（SAVEPOINT 事务） | EventWriter/ApprovalStore/ContextBuilder/AgentRuntime 四处 | 按形状声明的类型别名 `Callable[[],AsyncSession]` | store.py:168-170 |
| **Memory/RetrievalProviderLike** | M3.5 RAG 实装（M2 恒 None） | `ContextBuilder` 记忆/检索层 | async Protocol；None 或预算 0 = 关层且零调用 | context.py:52-64 |
| **Cassette / FakeGateway** | Cassette.load / 测试构造 | `FakeGateway(cassette)` 回放；M2.7+ 循环测试 `AgentRuntime(FakeGateway(...))` | frozen+slots / 结构化（GatewayLike+SupportsScoped 双协议） | replay.py:65-207 |
| **Recorder / normalize_events**（M2.11/12 接电） | replay.py（M2.6 预铺） | 录制脚本把 Recorder 当 gateway 传入（runtime 内部 scoped_view 自动分道）；`test_recovery_replay` 以 normalize_events 为等价断言本体（M2.12 侧加折叠+剔簿记预处理，不改 C31 本体） | 具体类 / 纯函数 | replay.py:221-325 |
| **SessionLock**（M2.9） | core/locks.py 三实现 + `build_session_lock()`（仅生产组装） | `AgentRuntime(lock=…)`（M2 测试恒 None 直通——get_redis 单例跨 event loop 定案）；M3.2 API 层必须显式注入 | **结构化 Protocol**（acquire/extend/release + owner_token） | locks.py:45-52 |
| **SessionStateStore / RunState**（M2.9/10） | store.py | T1（run 起跑 idle→running）/T2（挂起→awaiting）/T3（恢复→running）/T4（终止→idle）在 loop/runtime；**T5（→failed）判定权在 reaper 经 transition** | 具体类；全部翻转走 CAS，输家安静 | store.py:496-530 |
| **LeaseStore**（M2.10） | store.py | runtime 租约伴飞（acquire/renew/release，同 owner 重入）；reaper 扫描 steal（generation+1 围栏） | 具体类；CAS+NULL 幽灵兜底 | store.py:532-660 |
| **Guardrails / Classifier / OutputGuard**（M2.8） | guardrails.py（`build_classifier` 由组装方从 guard 道构造） | loop 三挂点：check_input（run 头）/wrap_untrusted（五结局回填+重建器）/output_guard（_finish_text 单点） | 门面类 + Callable 形态分类器（不持网关句柄） | guardrails.py:180-291 |
| **PrecheckHook / ResumeHook** | runtime.py / workers | 批准后前置校验（M3.9 注入，M2 恒 None=全通过）；reaper 恢复钩子（未注册只抢租不续跑——C9 兜底自洽） | Callable 别名挂点 | runtime.py:60-62 |

**四条解耦要点（复述用）**：
1. **EventSink vs EventWriter**：executor.py 与 context.py 的 import 表都**没有 EventWriter**（Grep 核实），只 import
   `EventSink` 这个结构化 Protocol。理由有二——① 可替换（生产喂真 writer、测试喂 fake sink）；② `_Tap`（loop.py:80-108）
   也满足 EventSink 形状，它 tee 每条 append 进待产队列让 run() 在固定点外流，而 executor/builder 对这层拦截毫不知情。
2. **GatewayLike 为何 `def` 不 `async def`**：async 生成器方法的类型是"调用即同步返回一个 AsyncGenerator"——消费方
   call 后不 await，直接 async-for（loop.py:384 `stream = self._gateway.complete(request)` 无 await）。与 `EventSink.append`
   的真 `async def`（await 一次拿一个值）刻意成对照，executor.py:44-49 docstring 明写这组对比。
3. **循环依赖两处破环**：loop↔runtime 用 `if TYPE_CHECKING` import（loop.py:46-48，只为类型注解要 GatewayLike）；
   runtime↔replay 用 run() 内**函数级局部 import** `from ...replay import scoped_view`（runtime.py:99，因 replay.py:24
   模块级反向引用 GatewayLike，顶层互 import 会在初始化半途炸）。
4. **组装在边缘**：`AgentRuntime.run` 是唯一聚合真实依赖处，在此用 `scoped_view` 把网关切成 main/summary/tool_digest
   三道注入 loop/builder/executor（runtime.py:92-162）；同一个 AgentRuntime 生产注入真网关+真工具，回放注入
   FakeGateway+演示工具，业务代码一行不改——"换武器不换枪手"。

---

## 4. 一次 run 的完整旅程（数据流 + 事件流双轨）—— 复盘的中心篇

### 4.1 组装九步（`AgentRuntime.run`，runtime.py:92-162）

```
① 延迟 import scoped_view 破 replay↔runtime 环          runtime.py:99
② run_id = run_id_factory()（默认 uuid4().hex，X5）      runtime.py:101   每次 run 新生成
③ 开事务读 sessions 行取 tenant_id/user_id（P2）         runtime.py:102-110  无行→ValueError 且零事件落盘
④ 同事务读历史 llm_call/llm_result 的 payload            runtime.py:111-122  一次查全，不新增查询面
⑤ token_seed = Σ(input_tokens_est + output_tokens_est)   runtime.py:125    D8：会话级预算种子从事件流重建
⑥ EventWriter.open 读流尾定 next_seq + _Tap(writer) 包裹  runtime.py:128-130  单写者，loop/executor/builder 共用同一 tap
⑦ ToolExecutor 组装 + I3 显式接线                        runtime.py:131-141  default_timeout_s=policy.tool_step_timeout_s、
                                                                            result_token_budget=context_config.tool_results_budget、
                                                                            summarize=scoped_view(gw,'tool_digest') 道
⑧ ContextBuilder 组装（summarize=scoped_view(gw,'summary')道）runtime.py:142-150  D15② 漏接则滚动摘要永不触发
⑨ AgentLoop(scoped_view(gw,'main'), ...) 并 async for 委托 yield  runtime.py:151-162  门面只组装+委托，编排全在 loop
```

> **关键精修（面试别答错）**：D8 的 token 重建发生在**门面组装阶段（runtime.py:111-125）**，`AgentLoop` 只接收算好的
> `token_seed` 当 `_tokens_used` 起点（loop.py:175）；闸门#3（loop.py:222-233）只做"发请求前 `_tokens_used+input_est>budget`
> 的预检"。**重建在门面、预检在循环——两处别混。** M2.9 的"先取会话锁"插入点在 `EventWriter.open` 之前（runtime.py:128）。

### 4.2 主循环每轮的关卡顺序（`AgentLoop.run`，顺序即语义）

```
user_message 首事件（loop.py:184，I5/D19）→ while True:
  #6 取消（LLM 前）    cancel_event.is_set() → _terminate(CANCELLED, fallback=None) 无道歉文   loop.py:191
  #1 最大轮数          iteration >= max_iterations → MAX_ITERATIONS；否则 iteration += 1        loop.py:202-211
  build 组装上下文     messages = builder.build(..., working=self._turns)；input_est 随后算    loop.py:214-219
  #3 会话预算预检      tokens_used + input_est > session_token_budget → TOKEN_BUDGET_EXCEEDED   loop.py:222-233  ← 调用前查，不打半截请求
  发 llm_call 事件     append(LLM_CALL,{iteration,tier,input_tokens_est}) → drain 外流         loop.py:235
  #2 _llm_step        构 LLMRequest（deadline_s=llm_step_timeout_s，max_tokens=output_reserve）loop.py:244,371-379
     └ 异常四组 except（见 §5-loop）                                                          loop.py:245-296
  发 llm_result(ok)    tokens_used += input_est + output_est                                    loop.py:298-315
  _classify 三分支    tool_calls 但无 tools→violation(D7②) / 有 tools→tools / text→text / 空→violation(D7①)  loop.py:355-363
    ├ violation:  violations+=1；>protocol_retry_limit→PROTOCOL_VIOLATION；否则注入纠错 user 消息 continue  loop.py:320-333
    ├ text:       violations 清零 → _finish_text（发 assistant_message）→ COMPLETED → return    loop.py:335-345
    └ tools:      append assistant(tool_calls) 进 _turns → _run_tools → 非 None 则 return       loop.py:347-353
        └ _run_tools 每 call 前：#6 取消检查点（loop.py:428）→ #4 重复（loop.py:437-455）→
          #5 幻觉名记违规（loop.py:459-467）→ executor.execute → 五结局 _feed_tool_message 回填 continue  loop.py:469-478
```

### 4.3 事件流两轨对照（seq 落盘 vs messages 装配）

**文本直答 run**（"你好"→模型直接回答）：

| seq | 事件 | payload 关键键 | 数据流备注 |
|---|---|---|---|
| 1 | `user_message` | content | 恒首事件（I5/D19），投影 messages(role=user)；append 后立即 drain |
| 2 | `llm_call` | iteration=1, tier, input_tokens_est | build 已装配 messages 并算出 input_est；**无投影** |
| 3 | `llm_result` | status=ok, text, tool_calls=[], stop_reason=end_turn, usage, output_tokens_est, latency_ms | latency_ms 是 C31 回放豁免字段；随后 tokens_used += input+output |
| 4 | `assistant_message` | content, token_usage(=usage_completion) | _classify→text→_finish_text；投影 messages(role=assistant) |
| 5 | `loop_terminated` | reason=**completed**, iteration, detail | 末事件（I7）；text 分支 fallback=None 故无额外话术；payload 一律 `.value` |

**工具 run**（模型要求调 `demo_order_query` 读工具 → 回填 → 再答）：

| seq | 事件 | payload 关键键 | 数据流备注 |
|---|---|---|---|
| 1 | `user_message` | content | 同上 |
| 2 | `llm_call` | iteration=1 | 第一轮 build（working 空） |
| 3 | `llm_result` | status=ok, tool_calls=[{id:call-1,name,arguments_json}], stop_reason=tool_calls | _classify→tools；随后 append `Message(role=assistant,tool_calls)` 进 `_turns`（**内存工作序列，非事件**——故本轮无 assistant_message 事件） |
| 4 | `tool_call` | tool_name, args | **write-ahead**：事实先落盘、是执行副作用的前置（C2）；发生在 handler 运行**之前**；`call_event.id`=幂等键经 `ToolContext.tool_call_id` 透传（赋值在 executor.py:170）；投影 tool_invocations（status=running 是**列默认值** store.py:136，投影器本身不 set status） |
| 5 | `tool_result` | tool_call_id(=call_event.id), result(全量原文 X4), latency_ms, retry_count, digest | 成功后连败账清零；outcome 返回 loop 后 `_feed_tool_message` 用**模型侧 call.id**（非事件 id）配对 role=tool 进 _turns（loop.py:487，坑 6）；投影翻 succeeded+result_digest |
| 6 | `llm_call` | iteration=2 | 本轮 build 的 working 已含 assistant(tool_calls)+role=tool 观察 |
| 7 | `llm_result` | status=ok, text="订单已发货。", stop_reason=end_turn | _classify→text |
| 8 | `assistant_message` | content, token_usage | _finish_text |
| 9 | `loop_terminated` | reason=completed, iteration=2 | 末事件 |

### 4.4 双轨闭环的七个对照点（面试必答）

1. **数据流先于事件流**：`build`（装配 messages）在 `llm_call` 事件之前（loop.py:214 vs 235），故 `llm_call.input_tokens_est`
   是"将要发出的 messages"的估算，落进 payload 供**下次 run** 的 D8 重建——数据流产物喂养事件流，事件流反哺下一次预算起点。
2. **working 跨轮累积回填工具观察**：`_turns` 是本 run 工作消息序列；tool 分支先 append assistant(tool_calls)，执行后每个
   工具 `_feed_tool_message` append role=tool，下一轮 `build(working=_turns)` 因此看见工具观察。
3. **旧 run 历史来自投影而非内存**：`_load_turns` 以 seq 序 JOIN messages↔events 且 `run_id != 当前 run`（D4，防本轮
   user_message 重复注入）。
4. **两种 id 严禁混用**：进 prompt 的工具观察用**模型侧 ToolCall.id**（对话协议字段）；`tool_result` 事件的 tool_call_id 用
   **write-ahead 事件 id**（幂等键出境去重）。坑 6，test lf-7 分别断死。
5. **seq 单调落盘**：所有事件经共享 `_Tap`→`EventWriter.append`，返回即 durably committed；seq 由 open 读 `max(seq)+1`
   播种、本 run 单调 +1、同会话跨 run 接续；`(session_id,seq)` 唯一约束是并发写最后防线，冲突→EventWriteFenced 自毁。
6. **_Tap 保证 yield 序≡seq 序（I4）**：append 既委托 writer 落盘又排 `_pending` FIFO 队列，run() 在固定 drain 点取走外流；
   append 序≡seq 赋值序≡队列序 ⇒ yield 序≡seq 序；三方共用同一 _Tap ⇒ 产出集合=落盘集合逐条不漏（test lf-2）。
7. **drain 时机差异**：build 内滚动摘要发的 `summary_updated` 与随后的 `llm_call` 一并 drain；executor 发的
   `tool_call`/`tool_result` 由 run() 在 `_run_tools` 返回后 drain——事件在 append 瞬间就已落盘，drain 只决定何时 yield。

### 4.5 三条支线旅程（M2.9/M2.10 接电后，与 §4.3 主线并列的事实轨）

**挂起→批准→恢复**（形态 C，`test_approval_flow_event_shape_snapshot` 钉死的 11 事件）：

```
run:    user_message → llm_call → llm_result(tool_calls) → [executor 前厅命中 risk_policy，
        无 write-ahead 无 tool_call 事件] → approval_requested{approval_id,tool,args,expires_at}
        → T2 running→awaiting_approval → run 干净返回（无 loop_terminated=进程可下线）
坐席:   ApprovalStore.decide CAS（查 pending 且未过期，C7；二次 decide 恰返 False）
resume: T3 awaiting→running → approval_decided → executor.execute(approved=True) 通行证
        → tool_call/tool_result（此刻才 write-ahead，audit 链 attach_event 回填 approval.event_id）
        → resume_run（working 从旧 run 事件重建，fill 配对批准结果）→ llm_call/llm_result
        → assistant_message → loop_terminated(completed) → T4 → idle
```

**崩溃恢复四支分诊**（`resume(approval_id=None)` → `_recover_locked`，M2.10）：
a) 尾事件已是 loop_terminated——上个 run 其实收了尾只是 T4 没翻：仅修状态零新事件；
b) 悬挂 tool_call（有 write-ahead 无终局）——`reexecute` 凭**原事件 id** 重执行（恰一把幂等键，
   下游按键去重：已执行返原结果、未执行正常执行），结果经 fill 配对进重建序列续跑；
c) 悬挂 llm_call（I6：无任何 llm_result 配对=真崩溃）——作废重发：不补旧事件，续跑自然产生
   新 llm_call（显式接受重生成文本不同）；d) 干净缝——直接续跑。c/d 在代码上合流（"作废"就是无为）。

**重建器 `_rebuild_working` 的口径——保事实不保字节**：llm_result(ok) 工具轮→assistant(tool_calls)
协议消息；tool_result 内容优先取 injected（X4 收缩留痕正为此刻）否则 dumps(result) 与 executor 同参
逐字节一致；未配对调用弃置补话术（防悬空 tool_calls 被上游 400）；打断/纠错话术无事件**不重建**；
全部 tool 消息重过 wrap_untrusted（与挂起前 loop 行为一致）。副产品：恢复段 prompt 与原始 run 不同
（孤儿轮注入），est 簿记漂移——这正是 M2.12 等价断言要剔 `input_tokens_est` 的根因。

---

## 5. 逐模块深挖（职责 / 关键决策 / 边界）

### spec.py —— 注入面四类型（M2.1）
- **校验强度按信任边界分档**（面试题 12 判据）：LoopPolicy/ContextConfig/AgentSpec 是 L3 **受信**代码注入的配置，用
  frozen dataclass + `__post_init__` 范围防呆即够，顺带拿到 frozen 的回放不可变性；只有 LLM 生成的**不可信**工具参数才需
  pydantic 严校验+强制转换+extra=forbid+可导出 schema（M2.4）。一句话："受信配置只拦手滑，不可信输入才配重装甲。"
- **`TERMINATION_GATES` 用全集减法**：`frozenset(TerminationReason) - {COMPLETED, GATEWAY_REJECTED}` 恰 6 个（spec.py:40-43），
  测试钉死 `len==6`。新增终止原因自动并入闸门集合（除非显式排除），手列六个会静默漂移。`gateway_rejected` 是七类之外的
  第 8 类——它是 L1 确定性拒绝（配置/协议 bug 信号），不触发兜底话术，故被显式减掉。
- **frozen 让实例能安全当默认值**：`AgentSpec.policy=LoopPolicy()` 共享单个 frozen 默认实例无别名污染；而 `tenant_config`
  是真 dict 必须 `field(default_factory=dict)`——可变默认参数陷阱的正反两面。
- **model_tier 复用 L1 的 Tier 字面量 + `get_args` 运行时防线**：Literal 只防静态，L3 会从租户配置读裸字符串塞进来，
  `__post_init__` 做 `model_tier not in get_args(Tier)` 兜底（spec.py:152）。
- 灵魂断言：`test_termination_reason_values_are_stable`（8 值整体快照=回放 ABI）、`test_context_config_allows_zero_optional_layers`
  （首尾层不可 0、中间四层可显式关闭的非对称契约）。

### events.py + store.py —— 事件事实源子系统（M2.1 枚举 + M2.2）
- **事件不带时间戳、seq 从 1 起——共享一个前提：确定性回放**。墙钟由 DB `server_default now()` 赋值，运行时逻辑一概不读；
  定序责任交给 seq 这个**逻辑时钟**。同一串事件无论何时/何机重放，重建状态字节一致。代价：跨副本/后台任务写事件 seq 不可
  复现会击穿"逐事件一致"CI 断言——这正是 M2.5 把摘要预热做成同步 await 的根因。
- **append 三岔口，`event_id` 在循环外固定做分诊依据**（面试题 17）：撞 `(session_id,seq)` 唯一约束的 IntegrityError 时查
  `_already_written(event_id)`——查得到=我上次实际 commit 成功只是 ack 丢了（**幽灵写入**）当成功；查不到=同一 seq 被别人
  （不同 id）占了、会话所有权旁落（**围栏**）抛 `EventWriteFenced` 让 loop 自毁。可重试白名单仅 `OperationalError/InterfaceError`
  退避 `(0.1,0.2,0.4)` 三次耗尽抛 `EventStoreUnavailable`；`ProgrammingError` 等 bug 信号裸抛。三类失败=三种世界态、三种机制。
- **投影与事件同一 PG 事务派生，失败连事件一起回滚**（本步灵魂断言 `test_projection_failure_rolls_back_event_too`）：
  messages/tool_invocations/summary 是 events 的只读投影，事件落了投影没跟上=事实源与读模型永久错位、且对回放不可见。
  投影是事件的**确定性 dispatch**（只读 record、不读时钟/随机）——**注意**：投影**行**含 DB 墙钟（`finished_at=func.now()`），
  严格说不逐字节可复现；但回放事实源是 events 不是投影表，I2 断言目标是 events，故不破坏确定性。`_PROJECTORS` 恰 6 条，
  审批四类**刻意不在此**（approvals 是独立状态机不是投影）。
- **审批全 CAS**（面试题 20/20b）：`decide` 的 WHERE 查 `status=pending AND expires_at>now()`（C7 fail-closed，过期单哪怕坐席
  点批准也拒翻、归 reaper）；`cancel` 不查过期（撤回已过期未清扫的 pending 无害）；`expire_due` 可注入时钟。竞态由 PG 行锁 +
  READ COMMITTED 谓词重查解决、赢家恰一个、输家 rowcount=0 绝不覆盖。
- **枚举存 String 列 + StrEnum 快照守护，不用 PG 原生 ENUM**（面试题 18 同族）：事件溯源 schema 频繁演进（C8 就临时加了
  summary_updated），加值只想改代码不想跑 `ALTER TYPE`（PG 加 enum 不可回滚、删值几乎做不到）。代价=放弃 DB CHECK，改由
  四个 `*_values_are_stable` 快照测试兜底。与"五表全无外键、引用完整性交给应用层 + event_id 唯一约束"同一套哲学。

### tools.py —— 工具契约与注册（M2.1 雏形 + M2.3）
- **身份走 ctx 注入、业务参数走 schema——越权第一道防线在类型签名上**：LLM 只能提供业务参数，`tenant_id/user_id/session_id/
  run_id/tool_call_id` 五身份字段由运行时注入 ToolContext、模型连它们的存在都不知道。`@tool` 强制首参名为 `ctx` 且注解
  **恰为**（identity 判等，子类不认）ToolContext，并从导出 schema 剔除。
- **C15 三层防呆**（面试题 16b）：写工具必须"有 risk_policy 或 risk_exempt"，二者互斥，读工具不许豁免；违者**注册期爆炸**。
  为什么不用 `lambda a,c: False` 假闸门？——假闸门把"我确认低危"伪装成"这里有风险判断"，抹掉审计意图；`risk_exempt=True`
  是留档可查的签字画押。合法形态恰三种：读 / 写+闸门 / 写+豁免（对应演示工具集三形态）。
- **写工具 retries 恒 0，两层双保险**：类型层 `__post_init__` 拒绝 `WRITE 且 retries>0`（且刻意排在 C15 之前，报"写禁重试"
  而非被 C15 抢报"缺闸门"）；执行层 `attempts_allowed = 1 + (retries if READ else 0)`。写幂等靠 write-ahead 键透传，不靠"再试一次"。
- **注解即事实源**：`parameters_schema`（给 LLM）与 `args_model`（给执行器 model_validate）同源于 `_build_args_model`，
  `model.model_json_schema()` 与 `model` 是同一 `create_model` 的两面，永不漂移；`extra="forbid"` 让幻觉参数响亮拒绝。
- **get 返 None vs add 重名抛错**（面试题 24）：get 查不到是运行期常态（模型幻觉工具名，处置政策归 M2.7 闸门#5）——机制不越权
  替政策决定；add 重名是配置期事故（dispatch 无法唯一路由）——启动即炸。机制 vs 政策、常态 vs 事故。

### executor.py —— ToolExecutor 七步生命周期（M2.4）
- **世界分界**（面试题 25，用户自己问出的满分题）：工具的一切业务结局编码成五种 ToolOutcome 回填模型（它看得懂错误文本能
  自我修正）；但 `append` 抛 `EventStoreUnavailable/EventWriteFenced` 是**事实源没了**，必须裸穿透执行器由循环处置。
  三个 append 点（write-ahead 前 / tool_result 后 / tool_error 后）全不被 try 兜——① write-ahead 炸=副作用没发生"死得干净"；
  ② tool_result 炸=工具已执行但结果没落盘、留下孤儿 tool_call"死得可愈"；③ 绝不能捕获后继续=在残缺事件流上带伤跑，回放永远
  重建不出真实状态。
- **写超时=RESULT_UNKNOWN 而非 ERROR**（X1，面试题 26）：写超时的本质是"不确定"（请求已发、响应没回，副作用可能已生效）。
  若回填 ERROR 模型会自发重试，而每次调用 write-ahead 生成**新的 tool_call 事件 id=新幂等键**，下游按键去重当场失效、同一笔
  退款执行两次。分类边界="超时=结果不明、异常=已知失败"：只有 WRITE+超时走 RESULT_UNKNOWN。
- **超时取更严 `min(工具自报, 循环级默认)`**：工具自以为有 99s 也不能饿死 loop 时间预算。
- **风险闸门 fail-closed vs 摘要钩子 fail-open**（面试题 27，C34 分野）：判据是"挡的是危险还是花钱/质量"。风险评估器崩了=评估
  不了绝不放行（ERROR+未执行）；摘要钩子（LLM 产物）崩了 fail-open 退化硬截断但**留痕** `summarize_error`。口诀："安全闸门坏了
  往死里关，增强层坏了往活里放。"
- **预算内小结果不记 injected**（面试题 28）：判据与 C8 加 summary_updated 同一条公理——可确定重算的产物不留痕，不可重算的必须
  留痕。预算内 content=序列化原文（`payload['result']` 已有全量 X4，重算即得）；超预算走 _shrink 才写 `injected/normalization`。

### context.py —— ContextBuilder 六层编译 + 滚动摘要（M2.5）
- **prompt 是编译出来的不是拼出来的**：上下文是 Agent 第一大账单（M1 实测输入 1.29 亿 token）。build 按 D12 固定次序装配
  system→记忆→[摘要→旧轮]→检索→当前 user→working，每层从 ContextConfig 拿独立预算、越界各有确定性收缩、**不做跨层借调**
  （借调破坏 I2 逐字节可复现）。system 超预算直接 `ValueError`（D15 fail-loud，固定层无合法降级）。
- **滚动摘要必须写 `summary_updated` 事件**（面试题 30）：摘要是 LLM 产物不可确定重算，投影必须是事件的纯函数才能回放重建。
  先 append 事件，`_project_summary` 同事务派生 `sessions.summary`；读取侧对称——`_summary_state` 直接读最新 summary_updated
  **事件**（不读投影），杜绝"投影滞后窗口"的推理负担。
- **try 只包 summarize 一行**（面试题 34）：summarize raise（fast 档 LLM 挂）fail-open——捕获+logger.warning+确定性丢最老轮；但
  紧随的 `append` 刻意在 try 之外——`EventStoreUnavailable`/`EventWriteFenced` 裸传播。吞掉它们会让本轮 prompt 引用一条**不存在
  于事件流**的摘要，回放重建不出、I2 作废。fail-open 只兜"LLM 不好使"，不兜"事实源/围栏"。
- **"异步预热"落成同步 await + 0.8 阈值**（面试题 31）：后台任务写事件时机不确定→seq 不可复现→击穿"逐事件一致"CI 强断言。
  "预热"语义靠触发式提前做保住：`need > 0.8×budget_h` 就摘（撑爆前一步压缩），fast 档低延迟弥补同步代价，真后台化 v2。
- **当前 user_input 恒保留**：`budget_h = history_budget − tokens(user_input)`，user_input 份额先扣走保证原文进 prompt；
  若它自身超 history_budget 则历史层清空+响亮日志，user 原文照放不截断（D11：截断用户输入=篡改输入）。
- **压缩丢的信息都找得回**（面试题 32）：被摘要吸收的轮/被折叠的工具结果（`_fold_working` 带 tool_call_id 可回溯）/被确定性
  丢弃的旧轮，全躺在 messages 投影与事件流里——prompt 是 events 的**有损投影**，events 是无损事实源。

### replay.py —— 录制回放基建（M2.6）
- **匹配键排除 prompt 哈希**（面试题 35）：L2 每步 prompt 都在动（滚动摘要/上下文重组/工具注入），prompt 哈希方案下"改一个字"
  全量 miss、回放退化成"改一处全部重录"。改成 `(session_id, scope, 道内序号)`——第 k 次 main 调用永远回放 main 道第 k 条。
  `request_digest` 里虽算了 prompt_sha256 但**仅供失配诊断绝不参与匹配**。补三道机器守卫：session 对不上/道内越界（多一次调用=
  行为漂移）→ 响亮 `CassetteMismatch`。
- **四道独立游标**（C10，面试题 36）：一次 run 有四种调用源（main/summary/guard/tool_digest），混成一条账则"中间插进一次摘要"
  挤占主循环序号、后面全错位。四道各推各的；`scoped(scope)` 出借的窄视图共享宿主游标账本（`complete ≡ scoped('main')`）。
- **游标先推进后 yield**（D6）：消费方常取首块就 break，若"yield 完才推进"则半途挂断不算数、下次重复吐同条=静默错配温床。
  在 yield 前就 +1，与真网关"调用即计费"语义一致。
- **半截流绝不入带**（D5，面试题 39）：把事故录成基线是回放体系头号腐蚀源。Recorder 用 `done` 标志——只有 async for **自然
  走完**才置 True，`GeneratorExit`（消费方早关）和中途异常都到不了那行；`finally` 里仅当 done 才 append，无条件 `aclose()`
  归还连接；异常不吞不译不重试原样穿出。与 ExactCache"完整流才入库"同哲学。
- **C31 归一化划"行为等价"边界**（面试题 37）：参与比较=type+schema_version+payload 其余键；豁免=payload **顶层**的墙钟/usage
  六键（递归会误伤 result 内层同名业务字段）；引用类 id 按流序别名 e1..eN、approval_id 首现 a1..aM（比结构不比具体 uuid）；
  流外引用 id 保留原值不别名（让 bug 响亮失败）。

### loop.py + runtime.py —— AgentLoop 总装（M2.7）
- **_Tap 双写 + 固定点 drain**（面试题问 "_Tap 为什么必须存在"）：事件来自 loop/executor/builder 三源共用同一 _Tap，loop 无法在
  executor 内部 yield。_Tap.append 一边委托真 writer 落盘（拿带 seq 的 AgentEvent）、一边排待产 deque；run() 只在固定检查点
  drain。落盘先于入队、FIFO 出队 ⇒ yield 序≡seq 序、产出=落盘（I4）。代价=每个终止分支手写 `drain+yield+return`（约十处）。
- **六道闸门阈值零魔法数字全来自 LoopPolicy**（I1）：#1 max_iterations / #2 llm_step_timeout_s(=deadline_s) / #3
  session_token_budget / #4 repeat_call_limit / #5 protocol_retry_limit / #6 cancel。闸门是"调用前查"哲学（预算/轮数在发起
  昂贵调用前查，不打注定超预算的半截请求）。
- **闸门#2 只是 `deadline_s` 一行赋值，不包 asyncio.timeout**（C1，面试题 40）：靠 deadline 传播 + L1 三段超时（connect 5s/首块
  25s/块间空闲 30s）守护挂起形态。本地再计时是人肉算术，会误杀"块间健康但整流长"的合法慢流、且在重试/换路中途粗暴掐断。
  触发面=捕获 `GatewayExhausted`。
- **六类异常压成四组 except、故意不接 GatewayError 基类**（面试题 43/44）：`(Exhausted,Overloaded)→step_timeout`；
  `(Budget,TenantQuota)→token_budget_exceeded`；`Rejected→gateway_rejected`（fallback=None 零兜底话术，C6/I9——全候选确定性拒绝
  =自家配置/协议 bug，发"请稍后再试"=把 bug 藏进客服话术）；`StreamInterrupted→配对 interrupted 后 continue 作废重发`（D10，
  M1"半截不换路"在 L2 的镜像）。**绝不 `except GatewayError` 基类**——ProviderError 泄漏是 bug 信号必须裸炸；
  `EventStoreUnavailable/EventWriteFenced` 同样裸穿出 run()。
- **canonical_json 归一化 + 坏 JSON 原样返回**（D4，面试题 41）：闸门#4 的键=`(工具名, canonical_json(参数))`，先 loads 再
  `dumps(sort_keys, 紧凑, ensure_ascii=False)` 把键序/空白抖动归一；坏 JSON 以原串为规范形（网关本就不解析坏参数）。字符串
  直比而非取哈希——判定等价且失配时可读可调试。"打断不清零"（==limit 只喂话术不执行、streak 不重置，下次同键自增至 >limit
  终止），"打断那次无 tool_call 事件"（I8，==limit 不调 executor.execute）。
- **I3 显式接线**关掉"默认值巧合相等"挂点：`ToolExecutor(default_timeout_s=policy.tool_step_timeout_s,
  result_token_budget=context_config.tool_results_budget)`——此前 30.0/3000 靠巧合相等，M2.7 显式传参、两条行为测试钉死。

> **关键精修（面试别答错）**：
> - **三级预算共用 `token_budget_exceeded`，分层靠 `payload.cause` 三态**：cause **缺席**=L2 会话级预检（loop.py 刻意不带
>   cause）/ `l1_request_budget`=L1 单请求闸门 / `l1_tenant_quota`=L1 租户配额（D9）。"缺席"本身是一态。
> - **`_fail_llm_step` 是【终止型失败】配对 `llm_result(failed)` 的单点**（loop.py:496-511）；正常 ok（loop.py:298）与半截
>   interrupted（loop.py:286）各在分支内独立配对。I6"进程内不留孤儿 llm_call"由这三处**共同**维系——供 M2.10 reaper 判半截
>   （"有 call 无 result"才是真崩溃，作废重发）。**进程内流中断与进程死亡是同一语义的两个触发面。**

### guardrails.py —— 三挂点防线（M2.8）
- **规则库是无条件底座、分类器是增强层，综合裁决只抬不压**：`max(规则档, 分类器档)`——防"分类器说没事"
  洗白规则命中；分类器输出严格白名单解析（"High."/"高"一律 ValueError→fail-open 降级仅规则库+留痕），
  宽容解析只会把不可靠输出洗成可靠裁决。**StrEnum 裸 max 字典序陷阱**："n">"m">"h" 会得出 none 最严的
  荒谬序——所有档位比较走显式 `_SEVERITY_ORDER` 表（测试钉死）。
- **OutputGuard 的核心不变量：逐字符 feed ≡ 整段 feed**（切分只依赖缓冲内容不依赖增量边界：句界+
  定长伪句双规则，尾窗抓跨句拼出）——M2.7 聚合接线（`_finish_text` 单点）与 M3.10 真流式共享同一行为
  的前提。命中即终态封死；已放行前缀不可撤回——守卫的保证是**止损不是零泄漏**，终局 final_check 兜底。
- **C23 owned_values**：出口 PII 区分"本人数据 vs 他人泄漏"——候选串剔 `[-\s]` 规范化后与允许清单
  字面等价才放行；wrap_untrusted 对数据内伪造的开始/结束标记做确定性改写（插 `·`），防"数据自带假
  结束标记越狱回指令"。**防线命中一律 COMPLETED**（D10：防线不是第七道闸门——拒答是平台的正常回答）。

### core/locks.py —— 会话锁三实现（M2.9）
- **owner token 是身份凭证**：裸 DEL 会误删他人锁（A 过期后 B 获取，A 迟到的 release 删掉 B）——释放/
  续期必须 Lua CAD/比对（GET 比对与 DEL 原子）。看门狗续期失败 `lost.set()` 即停：**不重试不切后端**
  （D13：跨后端互斥不可证），兜底交给 (session_id,seq) 唯一约束物理防线。
- **PG advisory 降级三件套**（评审 C4 修正）：session 级锁（xact 级首事务提交即释放，撑不住跨事务 run）
  / 专用 AUTOCOMMIT 连接持有显式释放、异常路径 invalidate 物理销毁（带锁归池=锁寄生池中连接）/
  `hashtext` 服务端稳定哈希（Python hash() 每进程随机盐，两副本对同会话算出不同键）。
- **粘滞切换与"占用≠故障"**：降级期 5s 顺路探针自愈（与限流器/熔断半开同构范式）；锁被占返回 False
  是常规结果**绝不触发降级**；持锁中途后端固定。M2.12 真容器实录：停 Redis 后并发两取恰一成功。

### store.py 增量 —— 状态机与租约（M2.9/M2.10）
- **run_state 五翻转全 CAS**：T1 起跑 idle→running（失败=会话在挂起/运行中，fail-loud）；T2 挂起；
  T3 恢复先回 running（四种审批结局统一，CAS 输家=并发双击第二击→安静零事件）；T4 终止归 idle；
  **T5 →failed 的判定权在 reaper 经 transition**——lease 侧 mark_failed 因 WHERE 含 NULL 兜底**可重入**
  （首跑测试抓出双 reaper 双赢双审计），状态机 CAS 才天然恰一次。
- **租约与锁是两个东西**（面试题 58）：锁防"两个活人同时干活"（毫秒级互斥、TTL 自动消失）；租约防
  "死人占着位置没人知道"（分钟级心跳、死后留尸检线索 owner/generation/过期时刻供 reaper 认领）。
  同 owner 重入支撑 steal→resume 交接；release 清 recovery_count=干净收尾自证非毒会话。
- **退避白名单的形状课**（M2.12 补）：`(OperationalError, InterfaceError)` 只覆盖 SQLAlchemy 包装后的
  dbapi.Error——asyncpg **池建连期**的 OS 级错误（ConnectionRefused 等）未经包装裸穿，真容器停库
  实录才暴露；修复纳入 OSError（builtin ConnectionError/TimeoutError 皆其子类，CancelledError 属
  BaseException 不受波及）。

### runtime.py 增量 —— 恢复单入口与租约伴飞（M2.9/M2.10）
- **"先取会话锁再恢复"单入口**：审批四结局（批准→执行通行证+续跑；拒绝/撤回/超时→对应事件+
  CANCELLED 轻量路径不组装 loop）与崩溃分诊（approval_id=None）共用一个 `resume`——计划内恢复与
  灾难恢复同路径（03:161 的兑现）。
- **租约伴飞 `_pump_with_lease`**：心跳独立 task、事件间检查其死活；**LeaseLost 自毁零事件**——新
  owner 已在接续 seq，再写任何事件（含 loop_terminated）必撞唯一约束；异常路径不 release（所有权已
  旁落，围栏终态）。已知边界：finally 段 `await renew` 只 suppress CancelledError，心跳先死时次生异常
  会顶掉 in-flight 原始异常（plans/m2.12 偏差 #7，M4.0 候选）。

### M2.11/M2.12 —— 把承诺变凭证的两步（资产不是代码，是可出示性）
- **六跑录制史诗的分类学**（每种失败模式恰现形一次，全被"六道自检先于落盘"拦截）：①摘要 prompt
  枚举窄→枚举外事实（会员号/型号）被合法丢弃——修=埋点框成"诉求/结论"语义+复述强化；②录制期
  C34 fail-open=回放分歧源——触发判定确定性⇒回放必复现触发点而 FakeGateway 不会失败⇒summary 道
  错位消费，**"干净录制"是比"成功运行"严格更强的要求**（logging.Handler 捕告警作第六道判据）；
  ③纯 CJK 专名采样变异（文三路→文大路：真实路名族先验提供"合理邻居"）——埋点避开真实世界命名
  家族，字母数字串六跑零变异；④时间格式归一（19点→19:00 无视复述指令）——顺着模型书写吸引子埋；
  ⑤幻影候选（glm5.2 未实测入池 404，fallback 断链两天静默）——**入池三验**：存在性/思考默认态/
  关思考参数接受性；⑥思考流饿死首块计时器（reasoning_content 不产 chunk，25s 卡解析后首块）——
  全池 enable_thinking:false，活性信号方案留给关不掉思考的模型（00 #41）。
- **等价断言的三段预处理**（M2.12 交付①）：C31 归一化（id 别名/墙钟 usage 豁免）+ 半截步折叠
  （孤儿 llm_call=中断物理痕迹，不折叠则 LLM 中断形态数学上不可能一致）+ 剔 run 簿记键
  （iteration 单 run 重计、input_tokens_est 随重建 prompt 漂移）。比较器自身两枚自证：防恒真
  （双跑裸 C31 即等）与防放水（篡改必响亮点名首个分歧索引）。中断注入=monkeypatch
  `EventWriter.append` 计数抛 SimulatedCrash——AgentRuntime 无 writer 注入缝，monkeypatch 以零生产
  改动达成 CrashSink 同一计数语义（全部事件漏斗过同一 writer 实例）。

---

## 6. 横切哲学十条（M2 版=八条 + 毕业期补两条；每条带代码可指 + 与 M1 网关的对照）

1. **事件即事实源：状态是事件的投影，恢复=重放而非读快照**。events 是唯一事实源，messages/tool_invocations/summary 全是它
   同事务派生的投影且是纯函数；token 种子从事件流 SUM 重建不加新列（runtime.py:111-125）；摘要游标只读最新 summary_updated
   事件不读投影（context.py:258-278）；恢复 `open` 读流尾 `max(seq)+1` 天然接续。**vs M1**：网关是无状态笨管道，状态散在 Redis、
   每次请求彼此独立；M2 一次 run 的全部状态是"这条会话至今发生过什么"的函数。
2. **write-ahead + 幂等键透传才是真幂等**（面试题 16）。副作用执行前 tool_call 事件必须先 durably committed，其 id 经
   `ToolContext.tool_call_id` 透传下游当幂等键；正因幂等键须先于副作用存在，`events.id` 用应用侧 uuid 而非自增（自增要等 INSERT
   返回才有）。"裸 order_id 做键"错在粒度——同一订单两次不同意图会被误判重复吞掉第二次；每次调用一个独立事件 id 才是正确去重
   粒度。**vs M1**：网关的"幂等"是"无副作用故可重放"（LLM 补全重试代价只是重复计费），所以网关能自动重试而写工具 retries 恒 0。
3. **单写者 + (session_id,seq) 唯一约束 + 围栏——三道防线守并发写**。第一防线单写者（一 run 一 EventWriter，前提已持会话锁）；
   第二防线 DB 物理约束（唯一约束在锁失效时兜底）；第三防线围栏（撞约束且非幽灵写入→EventWriteFenced 自毁）。**vs M1**：网关的
   并发协调是"多副本抢共享资源"（SET NX 探测令牌 / Lua 令牌桶）；M2 是"单写者独占一个会话"，用关系库唯一约束 + 乐观围栏代替
   分布式锁——不抢锁，谁先写进 seq 谁赢，输家撞约束后自毁。
4. **六道终止闸门，阈值零魔法数字全来自 LoopPolicy**（I1）。每处循环终止必是七类 TerminationReason 之一，阈值只读 spec.policy、
   模块内无字面量数字；闸门是"调用前查"（预算/轮数在发起昂贵调用前查）。**vs M1**：网关闸门阈值来自全局 config 单例（平台级
   进程级恒定）；M2 阈值来自 per-AgentSpec 的 LoopPolicy（L3 按租户注入的会话级策略）——运行时对"客服"一无所知。
5. **辅助 LLM 失败 fail-open，安全闸门失败 fail-closed**（C34 分野）。挡"危险"就 fail-closed（评估不了绝不放行），挡"省钱/质量"
   就 fail-open（坏了往活里放但必须结构化留痕）。**vs M1**：这是 M1"安全 fail-closed / 成本 fail-open"的延伸，但 M2 引入网关层
   不存在的第三类主体——"辅助 LLM"（摘要/守卫），判据落在"它是增强还是把关"；且因其产物不可确定重算，M2 给 fail-open 追加了
   "留痕"硬约束（回放资产），网关成本闸门 fail-open 只需告警、无回放包袱。
6. **确定性回放：无应用侧时间戳、normalize 豁免墙钟、回放匹配键非哈希**。凡进入回放等价比较的产物必须可确定重算；不可确定的量
   （墙钟/供应商 usage/模型输出指纹）要么不落进逻辑、要么比较时豁免。**vs M1**：网关的可序列化统一协议（LLMChunk 判别联合无损
   JSON 往返）是 M2 回放的直接地基——但网关自己从不回放（每次调用真钱真流量，"作用域"对真网关无意义，故 scoped_view 对真网关
   直通）。是 M2 才把"确定性"提升为一等公民，把网关埋下的可序列化能力兑现成录制回放。
7. **结构化协议解耦 + 组装在边缘：同一运行时换武器不换枪手**。模块间依赖只认形状（Protocol/Callable 别名），真实依赖聚合集中在
   唯一边缘装配点 `AgentRuntime.run`。协议细节埋伏笔：`complete` 是 `def` 不是 `async def`。**vs M1**：网关的"组装在边缘"落在
   factory.py（收敛副作用初始化）；M2 沿用同一哲学但服务于"可替换性/回放"——生产注入真网关+真工具，回放注入 FakeGateway+演示
   工具，业务代码一行不改。网关的 Protocol 解耦供应商差异，运行时的 Protocol 解耦真实/回放两个世界。
8. **话术单点 + 口径常量版本化：改值=破坏历史重放**。凡进落盘事件/DB 列/回放断言的字符串/枚举值都收敛到单点常量，值一旦发布
   即冻结、演进走版本号（`SCHEMA_VERSION`/`FORMAT_VERSION` +1 保留旧解析器）。话术是 loop.py 模块级常量（D13，M2.8 出口防护单点
   替换）；参与 cassette 匹配的 context.py 六个常量与 `_SUMMARIZE_PROMPT` 是回放基线的一部分。**vs M1**：网关 cache key 带 schema
   版本前缀 v1 是同源哲学，但代价量级不同——网关常量改了只让缓存 miss、300 秒自愈；M2 常量改了让历史事件**永久**无法一致重放
   （回放是审计资产、不折旧），所以 M2 把"冻结"从工程习惯升级成硬红线。
9. **断言钉语义承诺，不钉环境巧合**（毕业期两课合流）。空间课：全库扫描类断言必须过滤式（M2.10 试跑残留
   6 红）；时间课：不钉在途事件的竞态命运只钉"终止收尾类事件缺席"（M2.10 CI 首推抓出）；环境课：测试不依赖
   库内既有状态（M2.11 回放复用录制 session_id 撞键——CI 绿本机红=环境依赖测试的定义，修=重绑定随机会话）。
   **vs M1**：M1 的对应物是"时序断言不进 CI"；M2 把它推广成三维——空间/时间/环境，断言只许锚在系统自己
   承诺过的语义上。
10. **注入测语义分支，实录测形状边界——两类测试互补不可互替**（毕业实验的元收获）。注入测试回答"给我这类
   异常我会怎么做"（M2.2 的退避用例），真容器实录回答"真实故障到底抛什么类型"（停 PG 抓出 OS 级错误
   未经 SQLAlchemy 包装裸穿白名单——注入的 OperationalError 永远测不到这个形状）；同理六跑录制的每一项
   缺陷（幻影模型/思考饿死/摘要变异）都只有真实调用能暴露。**vs M1**：M1 毕业实验（30% 注入 1000 次）
   已经是这条哲学的第一次实践——M2 把它说破：注入器本身也是被测物形状的假设，形状假设要靠实录周期性校准。

---

## 7. 已知边界与取舍（"它有什么不足"的标准答案，主动讲比被问强）

**M2 特有取舍**：
1. **五表全无外键**：引用完整性交给应用层 + event_id 唯一约束；跨表一致性成为单写者纪律的责任（换 schema 演进自由）；
   将来事件与读模型分库，投影同事务的原子保证要靠 outbox/CDC 另补。
2. **投影行含 DB 墙钟**（`finished_at/created_at=func.now()`）故投影表不逐字节可复现——但回放事实源是 events 不是投影表，不影响
   I2；投影表是审计/读优化。
3. **枚举放弃 DB 层 CHECK/ENUM**，改由快照测试守护（拿 DB 强一致换演进成本低）。
4. **确定性回放牺牲了"异步预热"**：滚动摘要落成 build() 内同步 await（真后台化留 v2），换取 seq 可复现。
5. **闸门#2 的超时不在本地兜**：靠 deadline 传播——好处是不误杀合法慢流，代价是"块间健康但整流很长"没有本地硬上限（信任 L1
   三段超时守护）。
6. **`GatewayOverloadedError` 路径在网关侧不归还 probe 令牌**（M1 遗留，08 §附 4，M4.0 复核）——与 M2 无关但会浮到 loop 的
   step_timeout 触发面。

**挂点接电对账（M2.1–M2.7 留缝 → 毕业时全部按期接电，仅 M3 缝仍开）**：
| 挂点 | 毕业时状态 |
|---|---|
| `NEEDS_APPROVAL` HITL 挂起 | ✅ M2.9：开单→approval_requested→T2→干净挂起（K3 占位测试删除，行为被取代） |
| `ApprovalStore` 生产调用方 + 会话锁 + 租约 | ✅ M2.9 锁/挂起链路 + M2.10 续租伴飞/reaper（审批到期扫描调度仍归 M3.9） |
| `recovery_count` / `RunState.FAILED` | ✅ M2.10：C9 超限置 failed+审计，判定权在 T5 transition |
| Guardrails 三挂点 | ✅ M2.8：出口③按预警定案为聚合 `_finish_text` 单发（OutputGuard 确定性不变量保证与 M3.10 逐帧同行为——⚠️ 预期兑现） |
| ContextBuilder 记忆/检索两槽位 | ⬜ **M3.5** RAG（恒 None，接口在） |
| 幂等键下游去重 | ⬜ **M3.7** 退款服务闭环（M2 透传+kill9/恢复测试已用假下游自证键唯一） |
| handoff 事件生产端 | ⬜ **M3.8**（16 类中唯一零生产者） |
| PrecheckHook 批准后前置校验 | ⬜ **M3.9**（M2 恒 None=全通过） |

**毕业期新增边界**（详表见 atlas"已知边界汇总"，此处只列面试必讲三条）：
思考型模型首块饥饿盲区（现处置=全池关思考；关不掉思考的模型入池需活性信号——00 #41，连着讲
"入池三验"纪律）；`_pump_with_lease` finally 段次生异常可顶掉原始异常（plans/m2.12 偏差 #7，M4.0）；
恢复"保事实不保字节"的可见代价——恢复段 prompt 与原始 run 不同（孤儿轮注入、est 漂移），这是
M2.12 等价断言剔簿记键的根因，也是"逐事件一致"的诚实边界：一致的是**行为轨迹**不是字节流。

**08-code-map 行号漂移处置（定稿注记）**：草稿登记的 8 处漂移未逐条追校——M2.8+ 的改造使其中数处
（话术常量/NEEDS_APPROVAL 分支等）行号再次变化，逐条校正是追着尾巴跑。定稿处置：08 已于 M2.11–M2.13
期间按维护规则更新基线三元组与结构性内容（§0.1/§3.1/§9.1），**行号一律以"最新 08 + 直接 Read"为准**；
本文 M2.1–M2.7 章节行号保留 `6b7f22e` 时点值并已在头部声明。

---

## 8. M2 面试连环炮速查（按被问概率排序；深化 interview-questions 第 12–45 题）

1. **一次 run 怎么跑？** → §4 双轨旅程（组装九步 + 闸门顺序 + 两条事件流 + 七个对照点）。
2. **write-ahead + 幂等键为什么才是真幂等？裸 order_id 做键为什么错？** → 哲学 #2 + executor.py:158-171。
3. **崩溃恢复由谁调度？** → 三件分开答：租约续租（M2.10）/ reaper 抢租（M2.10）/ 锁单入口"先取会话锁再恢复"（M2.9）；判半截
   靠 I6 配对（有 call 无 result=真崩溃）。
4. **上下文压缩丢信息怎么办？** → 面试题 32：prompt 是 events 的有损投影、events 是无损事实源；摘要/折叠/丢弃三种都能回溯。
5. **投影为什么必须同事务？失败为什么连事件回滚？** → §5-store + 面试题 19。
6. **审批 CAS：decide 查过期、cancel 不查——为什么相反？** → §5-store + 面试题 20/20b（保险柜类比）。
7. **风险闸门 fail-closed、摘要钩子 fail-open——两个"坏了"为什么方向相反？** → 哲学 #5 + 面试题 27。
8. **闸门#2"90s"为什么只是 deadline 一行、不包 asyncio.timeout？** → §5-loop + 面试题 40（C1）。
9. **回放匹配键为什么不是 prompt 哈希？四道游标防什么？** → §5-replay + 面试题 35/36。
10. **`GatewayLike.complete` 为什么声明 `def` 不 `async def`？** → §3 解耦点 2 + 面试题 13（已深答）。
11. **校验强度为什么分档（frozen dataclass vs pydantic）？** → §5-spec + 面试题 12（信任边界）。
12. **三级预算为什么共用一个终止原因？cause 怎么分层？** → §5-loop 精修（cause 三态，缺席=L2）+ 面试题 44。
13. **锁和租约为什么是两个东西？** → §5-store 增量 + 面试题 58（当下排他 vs 身后移交，故障面独立）。
14. **HITL 挂起时进程凭什么可以下线？恢复怎么保证不重复退款？** → §4.5 支线一 + 哲学 #2（write-ahead
    键 + reexecute 原键 + 下游按键去重三件套）。
15. **"中断-恢复逐事件一致"怎么变成 CI 断言的？裸 diff 为什么不行？** → §5-M2.12 + 面试题 70
    （三段预处理各自的数学必要性 + 比较器双自证）。
16. **LangGraph 有 interrupt/checkpoint，你们为什么还自研？** → compare-langgraph-m2 §3/§4（重放节点 vs
    重建事实；快照可恢复但不可审计回放）——面试最深一问的完整弹药。
17. **长对话基准录了六次才成，这说明系统不行吗？** → 反着讲：六项互不重复的真实缺陷各现形一次、全被
    落盘前自检拦截、每次迭代 <¥0.2——这恰是"自检先于落盘"与"注入/实录互补"（哲学 #10）的价值实证；
    分类学见 §5-M2.11 + 面试题 63–69。
18. **真实冒烟为什么只断不变量？** → 面试题 71（回放测行为/评测测质量/冒烟测不变量，三套判据各管一段）。
19. **它有什么不足？** → §7 逐条主动讲，每条带"为什么接受 + 升级路径"；atlas"已知边界汇总"是速查版。

---

> **定稿于 2026-07-17（M2 毕业当日，同会话完成 M2.11→M2.13 全程后落笔——上下文最热时定稿，
> 较原计划"新会话首件事"提前，经用户指示）。** M2.1–M2.7 主体沿用 2026-07-16 对抗核验版
> （`6b7f22e`，55/60 CONFIRMED、0 证伪）一字未动；M2.8–M2.13 章节以毕业基线 `98e2549`
> （tag `m2-runtime`，548 测试）为准，定稿会话中相关源码全部逐一 Read。与设计文档冲突处以
> 代码 + 00 §2.2 为准。姊妹篇：retro-m0-m1 / compare-langchain-m1 / compare-langgraph-m2 / atlas。
