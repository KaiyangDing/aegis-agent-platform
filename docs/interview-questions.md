# 面试深挖题 · 自测题库（全里程碑）

> **用途**（协作规约 2026-07-09 修订）：模块收尾的深挖题不再当场问答，集中存此，
> 用户开发完毕后统一自测——**先自己答，AI 补充与批改**。答完标 ✅ 并在题后记一行要点。
> M0/M1 的题产自复盘（retro-m0-m1.md），自带答案指针；M2 起的题随交付出题。
> 配套复习索引见 05 §3（问题 → 答案位置表）；本文件是"待自测清单"，两者互补不重复。

## M0/M1 网关（源自 retro-m0-m1.md §8，按被问概率排序）

1. ⬜ 供应商挂了怎么办？→ retro §3 旅程 + 重试三铁律 + 熔断三键 + fallback 矩阵，数字见 retro §6
2. ⬜ 上游挂死 120 秒（连上不吐字）呢？→ 三段超时两阶段模型（retro §4-base/resilience，M2.0/C1）
3. ⬜ 为什么"重试幂等错误"是错误说法？→ retro 哲学 #3
4. ⬜ 429 为什么特殊？→ retro 哲学 #4 + Retry-After 双格式
5. ⬜ 熔断半开怎么防惊群？→ SET NX 探测令牌 + probe_ttl 推导 + 429 探测归还令牌
6. ⬜ 限流为什么必须 Lua？时钟怎么办？→ retro §4-ratelimit（读-改-写原子性 + Redis TIME + NTP 回拨）
7. ⬜ 缓存怎么保证不跨租户/不缓存垃圾？→ key 三原则 + 完整性守卫 + v1 版本前缀
8. ⬜ 多副本部署行为一致吗？→ 状态全在 Redis + 降级语义逐项写实（M1.12/复盘补丁二）
9. ⬜ 成本怎么算的？→ Decimal + 数据库时钟 + 价目表告警 + 对账脚本；三级预算闸门位置
10. ⬜ 跨供应商差异怎么抹平？→ 统一协议判别联合 + chunk 顺序不变量 + [DONE] 哨兵 + tool-call 按 index 组装
11. ⬜ 它有什么不足？→ retro §7 逐条主动讲，每条带"为什么接受 + 升级路径"

## M2.1 核心抽象（2026-07-08 出题）

12. ⬜ `LoopPolicy`/`AgentSpec` 用 frozen dataclass，而 M2.4 的工具参数要用 pydantic 严校验——
    两处校验强度为什么不一样？判断标准是什么？
13. ✅ `GatewayLike` 协议里 `complete` 为什么声明成 `def` 而不是 `async def`？写错会发生什么？
    （2026-07-09 对话已深答：async 生成器函数不是协程函数、协议描述调用方视角——自测时复述即可）
14. ⬜ `TERMINATION_GATES` 为什么用"全集减法"而不是手列六个成员？`gateway_rejected` 为什么不算闸门？
15. ⬜ `AgentEvent` 为什么不带时间戳？`seq` 为什么必填且从 1 起？（提示：两个答案共享同一个前提）
16. ⬜ write-ahead 幂等键（`tool_call_id`）为什么放在 `ToolContext` 里交给工具实现，
    而不是让 ToolExecutor 自己拿着？

## M2.3 工具注册（2026-07-09 出题）

16b. ✅ `side_effect` 为什么用 StrEnum 不用裸 str？`args_model` 与 `parameters_schema` 为什么
     同时存在、谁是母版？`risk_exempt` 解决什么死角（提示：假闸门 lambda False 为什么更糟）？
     （2026-07-09 对话已深答——自测时复述"必填且必对 / 母版与导出物 / 签字画押的豁免"三个短语）
22. ✅ `@tool` 的三步脱糖是什么（装饰器工厂 → register → ToolDef 覆盖名字）？为什么防呆能
    "import 时爆炸"？为什么不做自动发现/全局注册表（对比 Flask `@app.route` 的隐式全局状态）？
    （2026-07-09 对话已深答——复述"装饰器不是注释，是 import 时立刻执行的函数调用"）
23. ✅ 供货时刻表：schema/tenant_config/业务参数/tool_call_id/ctx 各由谁在何时注入？
    handler 汇合的两路参数是什么、汇合点为什么是安全边界？
    （2026-07-09 对话已深答——复述 T0–T3 四时刻与"越接近副作用的注入越晚越受控"）
24. ⬜ `registry.get` 查不到返回 None，`registry.add` 重名却抛异常——同是"查无此物"，
    为什么处置相反？（提示：机制 vs 政策、运行期常态 vs 配置期事故）

## M2.4 ToolExecutor（2026-07-10 出题）

25. ✅ 执行器里 `_events.append` 抛异常怎么办？三个调用点（write-ahead 前 / tool_result 后 /
    tool_error 后）的"死后现场"分别是什么、各被什么机制接住？为什么绝不能捕获后继续对话？
    （2026-07-10 对话已深答，用户自己问出的满分题——复述"副作用前死得干净、副作用后死得可愈、
    禁止带伤继续跑"三段 + Fenced 时连成功结果都作废的角落）
26. ⬜ X1：写工具超时为什么回填"结果未知、禁止重试"而不是普通报错？模型自发重试会破坏什么？
    超时=不明、异常=已知失败——这条分类边界为什么这么划？
27. ⬜ 同一个执行器里，风险闸门崩溃 fail-closed、摘要钩子崩溃 fail-open——两个"坏了"为什么
    方向相反？各自的判据是什么（C34 分野）？
28. ⬜ tool_result 的 payload 里，什么时候记 `injected`、什么时候不记？判据是哪条公理
    （提示：与 C8 加 summary_updated 是同一条）？
29. ✅ `summarize: Callable[[str], Awaitable[str]] | None` 这个座位将来坐的是谁？为什么注入
    "文本→文本"的窄能力而不是整个 gateway？（2026-07-10 对话已深答——复述"单能力用 Callable、
    多能力才配协议 + 总装闭包 make_result_summarizer"）

## M2.2 EventStream 底座（2026-07-09 出题）

17. ⬜ `(session_id, seq)` 唯一约束和会话锁是什么关系——为什么要两道防线？
    撞了 `IntegrityError` 之后，怎么区分"幽灵写入"和"围栏信号"？分诊依据是什么？
18. ⬜ `events.id` 为什么用应用侧 uuid，`messages.id` 却用自增 bigint？给出判断三问。
19. ⬜ 投影为什么必须与事件同一个事务？投影派生失败为什么要连事件一起回滚？
    如果事件与读模型分库，这个保证要靠什么补（一句话即可）？
20. ⬜ 审批翻转为什么不能 SELECT 再 UPDATE？`decide` 的 WHERE 为什么查过期而 `cancel` 不查？
    坐席对过期单点批准，系统行为是什么、依据哪条口径？
20b. ✅ CAS 的竞态"是数据库解决的还是代码解决的"？精确说出分界（原子性 vs 正确性），
     并讲出 PG 行锁 + READ COMMITTED 谓词重查的机制、乐观 vs 悲观（FOR UPDATE）的选型理由。
     （2026-07-09 对话已深答——自测时复述"保险柜类比"即可）
21. ⬜ PG 挂了事件写不进去怎么办？为什么退避重试 3 次就放弃而不是无限重试？
    哪些异常进重试白名单、哪些裸抛，划分标准是什么？
21b. ✅ 为什么写路径异常处理精细而读路径裸抛？（写失败后世界三态、只有写入现场能分诊；
     读失败后世界一态、重跑恒安全，异常归口到 loop 边界；读加重试=重复兜底——复盘补丁二同病。
     2026-07-09 对话已深答，用户自己发现的问题——自测时复述"能行动处处理、不能行动处透传"）

## M2.5 ContextBuilder（2026-07-11 出题）

30. ⬜ 滚动摘要为什么必须写 `summary_updated` 事件、而不能只 UPDATE `sessions.summary` 投影？
    （C8：摘要是 LLM 产物不可确定重算——投影必须是事件的纯函数才能回放重建；
    对照 M2.4：预算内工具结果不记 injected，因为可确定重算——同一条公理的正反两面）
31. ⬜ 03 原文写"压缩异步预热、不阻塞当前请求"，最终为什么落成 build() 内固定位置**同步** await？
    "预热"语义靠什么保住？（拍板项 3：后台任务写事件时机不确定 → seq 不可复现 →
    击穿 M2.12"逐事件一致"CI 强断言；预热 = 0.8 阈值提前做 + fast 档低延迟；真后台化 v2）
32. ⬜ 上下文压缩丢了信息怎么办？被摘要吸收的轮、被折叠的工具结果、被确定性丢弃的轮，
    各自还能找回来吗？（00 §6.2 面试考点原题：摘要只服务 prompt，events 原文永远是事实源；
    折叠文本带 tool_call_id 可回溯原文；丢弃轮在 messages 投影与事件流里原样躺着）
33. ⬜ 单条工具结果超预算的收缩在 executor（fast 档摘要），层聚合超预算的折叠在 builder
    （确定性折叠、绝不二次调 LLM）——为什么劈成两半、各归各家？（单条收缩发生在结果诞生时、
    产物随事件留痕 X4；层聚合是编译期装配决策；builder 再调 LLM 既与 M2.4 重复实现又破坏 I2）
34. ⬜ C34 说增强层失败 fail-open，为什么 `_compose_history` 的 try 只包 summarize 一行、
    不包紧随其后的事件写入？吞掉 `EventStoreUnavailable`/`EventWriteFenced` 会发生什么？
    （fail-open 兜的是"LLM 不好使"；事实源故障=服务不可用（02 §5）、围栏=所有权旁落（C2）；
    吞掉会让本轮 prompt 引用一条不存在于事件流的摘要——回放重建不出，I2 作废）

## M2.6 录制回放（2026-07-11 出题）

35. ⬜ 回放匹配键为什么是 `(session_id, scope, 道内序号)` 而不是 prompt 哈希？两种方案各自的
    失效模式是什么？（序号：prompt 微调零成本，但调用次序漂移会拿错条目——靠道耗尽/CassetteMismatch
    响亮暴露；哈希：改一个字全量 miss，重录成本让人不敢动 prompt——03 §7 明文排除）
36. ⬜ C10 四道独立计数防的是什么事故？（全局一道计数时，M2.7 接入滚动摘要后主循环的第 N 次
    调用会拿到摘要道的回复文本当对话回复——静默错配；四道分账 + 任一错位响亮失配）
37. ⬜ C31 归一化为什么 usage/latency_ms 豁免、而 summary 全文和 result 原文参与断言？
    （豁免的判据=墙钟产物或供应商实测值，重录必然波动；参与的判据=回放模式下确定——文本来自
    cassette chunk、digest 是内容的确定性派生、摘要文本来自 summary 道；豁免只滴 payload 顶层，
    递归滴除会误伤 result 内层同名业务字段）
38. ⬜ 与 VCR.py / pytest-recording 这类 HTTP 层录制工具的本质差异？（我们录的是 L2 语义流
    LLMChunk 不是 HTTP 报文——供应商格式差异被 L1 适配器吸收，换供应商/改重试策略不用重录；
    HTTP 层录制把传输细节焊死进基线，网关内部任何演进都会全量失配）
39. ⬜ Recorder 为什么半截流绝不入带？done 标志为什么必须放在 async for 自然结束之后？
    （把事故录成基线="红=有 bug"的信号契约被腐蚀；GeneratorExit（消费方 aclose）与中途异常
    都到不了 done=True 那行——控制流位置即守卫实现；与 ExactCache"完整流才入库"同哲学，
    load 的 StopChunk 收尾校验是第二道保险）

## M2.7 AgentLoop 总装（2026-07-11 出题）

40. ⬜ 闸门 #2 的"LLM 90s"为什么不是给 LLM 步包一层 `asyncio.timeout(90)`，而只是
    `deadline_s=90.0` 一行赋值？（C1：嵌套约束由 deadline 传播机制保证——L1 三段超时
    connect 5s/首块 25s/块间空闲 30s 已守护挂起形态；本地再计时是人肉算术，会误杀
    "块间健康但整流长"的合法慢流，且在重试/换路中途粗暴掐断；触发面=捕获 GatewayExhausted）
41. ⬜ canonical_json 为什么要先 loads 再 sort_keys dumps？坏 JSON 为什么以原始字符串为
    规范形？为什么不取哈希？（键序/空白抖动是模型输出常态，不归一则闸门 #4 形同虚设；
    网关不解析坏参数——连坏法都逐字相同当然算重复；字符串直比与哈希判定等价且失配时可读可调试）
42. ⬜ llm_call/llm_result 配对不变量（I6）如何支撑 M2.10 的半截判定？（进程内一切 LLM 步
    终局都有配对 result（status∈ok/interrupted/failed）——`_fail_llm_step` 单点结构性封死
    "忘配对"；于是"有 call 无 result"专属真崩溃，reaper 扫到即按恢复语义作废重发——
    进程内流中断与进程死亡是同一语义的两个触发面）
43. ⬜ GatewayRejected 为什么禁止兜底话术？（C6：全候选确定性拒绝=自家配置/协议 bug——
    错 API key、坏请求转换；重试与降级都无意义，发"请稍后再试"=把 bug 藏进客服话术；
    终止原因 gateway_rejected 在七类之外、不算闸门，I9 有测试钉死"零 assistant_message"）
44. ⬜ 三级预算为什么共用 token_budget_exceeded 一个终止原因？cause 怎么区分层级？
    （用户视角"额度没了"是同一件事，话术同一条；审计视角靠 payload cause：缺省=L2 会话闸门
    预检、l1_request_budget=单请求闸门、l1_tenant_quota=租户配额——D9；三级预算 =
    单请求(L1)/会话(L2 本步接电)/租户月度(L1 fail-open)）
45. ⬜ 会话级 token 计数为什么能从事件流重建、不加任何新列？（事件溯源推论：估算值随
    llm_call.input_tokens_est / llm_result.output_tokens_est 落盘，新 run 起点=扫本会话
    此二键求和——"事件即事实源"的直接兑现，测试断言 detail 报出的累计值恰等于历史估算和；
    C25 口径：闸门用估算尺，供应商 usage 只进账单）

## M2.8 Guardrails（2026-07-17 出题）

46. ⬜ 流式出口为什么必须句子级缓冲？代价是什么、在哪一层兑现？（逐字符看不到完整模式——
    手机号 11 位凑齐才认得出；整段等完在 SSE 下延迟不可接受；句子是"足以判断×延迟最小"的
    折中。代价=首字延迟 +约一个句子的生成时间（02 §2⑨/D14），M2 无用户可见流、代价在
    M3.10 兑现——tradeoff 面试主动讲。追问：为什么伪句要定长 200 切而不是整 buffer——
    切分点只许依赖缓冲内容，否则逐字符 feed 与整段 feed 切点漂移，破坏确定性不变量）
47. ⬜ C23：无条件 PII 截断错在哪？owned_values 方案的边界在哪？（客服必须能向用户输出
    其本人手机号/地址——无条件截断误杀合法回答，把防线变成故障源；方案=出口守卫接受
    允许清单，候选规范化（剔 -/空白）后字面等价→放行。边界：只做字面等价，"张三的手机 vs
    李四的手机"语义归属需要业务数据，是 L3 的知识（M3.8 注入真实值）；银行卡因与订单号
    正面冲突显式 v2）
48. ⬜ fail-open / fail-closed 分野一张表背下来（C34）。分类器挂了为什么绝不拒答用户？
    （fail-closed 只指确定性安全闸门：风险闸门/权限/审批/RLS——挡的是"危险动作被放行"；
    fail-open 是全部 LLM 增强层：入口分类器→仅规则库+audit、滚动摘要→截断/丢轮、
    工具结果摘要→硬截断——挡的是"增强层故障拖垮对话"。同一个网关异常在主循环是终止信号、
    在增强层是降级信号。分类器挂了拒答=把可用性押在最不可靠的组件上，且规则库底座还在）
49. ⬜ 为什么 Guardrails 不是第七道闸门？防线命中为什么走 COMPLETED？（闸门管"循环失控"
    ——终止原因 7 类/六道闸门是回放断言与口径快照钉死的（TERMINATION_GATES len==6）；
    防线管"内容安全"——拒答/截断后 run 是正常结束、用户收到了明确回复，语义上就是完成；
    审计靠 guardrail_triggered 事件承载而非终止原因，两个关注点不混一个枚举）
50. ⬜ 不可信包裹为什么不在 executor 层做？（X4 铁律：事件 payload 存原文——executor 落盘
    tool_result 必须无标记，否则回放重建的模型视界被污染；包裹是 prompt 注入面的事，loop 在
    结果产生的当下最清楚 source；M3.5 检索槽由 ContextBuilder 调同一个 wrap_untrusted——
    一处定义两处消费防两套标记格式。追问：假标记越狱怎么堵——text 内出现的开始/结束标记
    字面量先确定性改写（插 ·），产物恰一对真标记）

## M2.9 HITL 挂起-恢复与会话锁（2026-07-17 出题）

51. ⬜ 锁释放安全三连问（ADR-005 角色 5）：为什么释放必须带 owner token 且用 Lua CAD？
    看门狗解决什么、失败后为什么不重试不切后端？Redlock 为什么不用？（①A 的锁过期后 B 已获取，
    A 迟到的裸 DEL 会删掉 B 的锁；GET 比对与 DEL 分两步发会在中间被"过期+易主"插队——比对与
    删除必须在 Redis 端原子（十行 Lua）。②看门狗防"锁过期任务没跑完"；失败=锁已易主，重试徒劳、
    跨后端互斥不可证（D13）——lost 置位报告持有者，正确性交给 (session_id,seq) 唯一约束。
    ③单实例不需要；且 Redlock 防不了 GC 暂停型僵尸写者——正解是 fencing（Kleppmann），
    本项目的 fencing 化身=唯一约束+lease_generation）
52. ⬜ HITL 挂起状态存哪、进程下线为什么无损？恢复时上下文从哪来？（approvals 表+events
    事实源——内存零依赖；恢复=从挂起 run 的事件流重建工作序列：llm_result 存着模型侧 call id、
    tool_result 的 injected 留痕（X4）兑现"回放重建模型视界"；保事实级不保字节级——打断话术
    无事件不重建，与"半截 LLM 作废重发"同哲学）
53. ⬜ 为什么审批回调只翻 approvals 表、事件与 run_state 归恢复单入口？（回调可能被任何进程
    任何时刻调——自带副作用就得先取锁，"回调"就不轻了；副作用收进"先取锁再恢复"一条路径，
    并发语义只在一处论证。副产品：审批恢复与 M2.10 崩溃恢复同一条代码路径——
    日常流量天天在测灾难恢复逻辑（03 §5））
54. ⬜ TOCTOU：审批的是几小时前的参数快照，批准后为什么还要重跑前置校验？挂点与注入怎么分工？
    （批准与执行之间世界会变——订单可能已发货、余额可能已退完；PrecheckHook 挂点在 L2
    （机制：否决→不执行→原因回填模型继续，D19），校验逻辑在 L3（M3.9 注入订单状态/可退余额）——
    依赖倒置：运行时不知道"可退余额"是什么。参数本身也回炉：execute(approved=True) 重过校验①、
    只豁免风险闸门③）
55. ⬜ PG advisory lock 两种级别的差别？连接池下的泄漏陷阱？（session 级绑连接、xact 级绑事务——
    xact 级在首个事务 commit 即自动释放，撑不住跨多个事件写入事务的 run（C4 灵魂测试：持锁后跑
    完整 commit 事务、锁必须还在）；泄漏陷阱=不 unlock 就把连接归池，锁寄生在池中连接上直到重启——
    正解：专用 AUTOCOMMIT 连接、同连接显式 unlock 再 close、异常路径 invalidate 物理销毁）
56. ⬜ 挂起为什么不是终止？（TerminationReason 枚举冻结无 suspended——值进历史事件，改=破坏回放；
    语义上挂起的 run 没有结局、恢复后的 run 才有——一次会话恰一条 loop_terminated；
    _SUSPENDED 哨兵让 run 生成器干净收尾，锁释放、进程可下线）
57. ⬜ 停 Redis 时互斥去哪了？为什么锁降级方向与限流/熔断相反？（降级到 PG advisory——互斥换
    后端不换语义（C4"保住互斥而非放弃"）；限流/熔断可以降级进程内是因为配额/健康判断可按副本
    分治，互斥不可分割——1/N 份的互斥是零互斥。按依赖角色分野：成本可用性侧损精度保可用、
    安全侧只换后端不降语义；三层防线=Redis 锁（第一）/PG 锁（降级）/唯一约束（物理兜底））

## M2.10 恢复调度（2026-07-17 出题）

58. ⬜ 租约（PG）与会话锁（Redis）为什么是两个东西、各自挡什么？（锁防"两个活人同时干活"——
    毫秒级互斥、TTL 到点自动消失就完事；租约防"死人占着位置没人知道"——分钟级心跳、死后要
    留尸检线索（owner/generation/过期时刻）在事实源旁边供 reaper 扫描认领。一个管当下排他、
    一个管身后移交；后端也分开：锁挂了降级 PG advisory，租约本来就在 PG——故障面独立，
    续租任务与锁看门狗因此是两个独立 task 不合并）
59. ⬜ lease_generation 围栏已有了，为什么还要 (session_id, seq) 唯一约束兜底？（故障模型不同：
    generation 挡"旧持有者的续租/释放"——CAS 打空即感知；但 GC 暂停型僵尸在丢锁后、感知前
    仍可能发出写请求——事件间检查有粒度缝。唯一约束是存储层物理底线：两个写者抢同一 seq
    恰一个成功，输家 EventWriteFenced 终态自毁——fencing 思想（Kleppmann）的数据库化身；
    围栏保"尽早止损"、约束保"绝不写坏"，层次不同不可互替）
60. ⬜ reaper 随 broker 停摆为什么是可接受降级？答题怎么主动讲？（broker 即 Redis（ADR-005
    角色 4）——Redis 挂：会话锁降级 PG 互斥不丢（安全侧不降语义）、限流降级本地桶（成本侧
    损精度）、beat/reaper 停摆=崩溃恢复延迟拉长（可用性侧，Redis 回来自愈）；分野是"按依赖
    角色定降级方向"。主动讲：恢复不是丢了只是慢了——租约与事件都在 PG，reaper 一恢复照常
    认领；outbox 补投列 v2 不假装已有）
61. ⬜ 恢复期写工具"凭原幂等键重发"为什么安全？裸 order_id 做键为什么错？（安全性来自
    下游按键去重：reexecute 复用原 tool_call 事件 id——已执行返原结果、未执行正常执行；
    重新走 execute 会 write-ahead 出第二把键，同一逻辑调用两把钥匙、下游认成两笔（X1 同族）。
    裸 order_id 做键错在粒度：同单可以合法退两次（各 50），order_id 去重会拦掉第二笔合法操作
    ——键必须标识"这一次调用意图"而非"这个业务对象"，事件 id 恰是前者）
62. ⬜ recovery_count 为什么 release 时清零？C9 恰一次判定为什么最终放在 T5 transition
    而不是 lease 侧 CAS？（清零：计数器堵"毒会话崩溃循环"，任何一次干净收尾都证明不是毒
    会话——不清零则长寿会话攒满历史崩溃后永久 failed。判定权：mark_failed 的 lease 侧 CAS
    因 WHERE 含 NULL 兜底而**可重入**（首跑测试抓出：清列后 IS NULL 分支再次命中，双 reaper
    双赢双审计）；transition(RUNNING→FAILED) 本就是恰一次的状态机 CAS——T5 翻转天然该是
    判定点，赢家再清列写审计，崩在缝上=failed 无审计（无谎言方向，可接受））

## M2.11 长对话基准（2026-07-17 出题）

63. ⬜ 召回断言为什么用关键词包含式而不是 LLM 判分？局限是什么、谁来补？（确定性/零 token/CI
    可跑——LLM 判分自身是概率源，用它验收概率系统等于判据先失真；局限：只验"归一化后字符串
    在场"不验语义正确，靠 D6 高熵埋点压误报；两侧 [-\s] 剔除+全角冒号折半角是**排版折叠**不是
    语义等价——"晚上7点"照样判败；语义级召回归 M4.4 离线评测 LLM-as-judge，两套判据不互替）
64. ⬜ 回放不重跑模型，这份 cassette 到底回归住了什么？（两层分工：内容断言钉住"录制当时真实
    模型在滚动摘要压缩后答对了"这一历史凭证 + "回放可逐事件重建该轨迹"；日后改坏上下文管线时
    报警的不是关键词——是 (session_id, scope, 道内序号) 匹配键失配响亮报错（C10）与
    assert_exhausted 抓"轨迹变短"；摘要触发判定是确定性的⇒录制期每个触发点回放期必然复现，
    **结构本身就是断言**）
65. ⬜ 预算为什么要三道上限？MAX_LLM_CALLS 兜的是什么底？（token 与金额走账本实测（C25 账单侧）；
    上游偶发缺 usage 时适配器合成 0-token UsageChunk、账本如实记 0——前两道**失明**；行数不依赖
    usage 可信。另注意护栏侧还有第三把尺：闸门 #3 会话估算预算——录制 spec 必须覆盖默认 50_000
    至 400_000，因为 D8 口径是会话级累计（种子从全会话事件流重建），40 轮必超）
66. ⬜ 录制期一次辅助调用 fail-open，为什么整盘 cassette 就废了？（C34 fail-open 只留
    logger.warning——无事件、无 cassette 条目、无账本行；而摘要触发是确定性判定，回放期同一
    触发点必然复现且 FakeGateway 不会失败⇒summary 道被提前错位消费，回放事件流≠录制事件流，
    既有断言却可能全绿=基线内部自相矛盾、静默腐蚀 M4.3。定案：对录制器而言"**干净运行**"是比
    "成功运行"严格更强的要求——脚本挂 logging.Handler 捕告警作第六道自检+首个 fail-open 立即中止）
67. ⬜ 埋点值怎么选才扛得住压缩？实录出了哪些反例？（D6 三性质 + 两条实测补强：①**避开真实
    世界命名家族**——"文三路"被 fast 模型按杭州文一/二/三路先验变异成"文大路"（摘要是生成不是
    复制："双份在场"防丢弃、防不了变异）；②**顺着模型书写吸引子**——"19 点"被无视复述指令归一成
    "19:00"，改埋"19:00"让合规与习惯同向。经验规律：字母数字串六跑零变异，纯 CJK 专名是唯一
    变异过的类别；摘要 prompt 枚举清单外的事实（会员号/型号）需框成"诉求/结论"语义+复述强化）
68. ⬜ 思考型模型为什么会把网关"饿死"？修法为什么选请求侧关思考而不是适配器活性信号？
    （qwen3.7 系默认先流 reasoning_content 而适配器只认 delta.content——首块 25s 在重试层卡
    "解析后首 chunk"（asyncio.timeout 包 anext），思考期 socket 有读活动（httpx read 30s 不触发）
    但解析层零产出→饿死→重试同饿→双候选连锁 GatewayExhausted；且隐藏思考 token 计入 completion
    计费（探针实测 54→4 塌缩）。选关思考：平台不消费思考流，关闭=省钱+提速+根除，池内全系实测
    接受参数；活性信号方案（首个 reasoning delta 补发空 TextDelta）保留为"关不掉思考的模型"
    入池时的升级路径（00 §10.1 #41）——分野是"改生成语义 vs 改感知语义"）
69. ⬜ "幻影候选"glm5.2 是怎么潜伏两天的？入池三验为什么缺一不可？（写入时未实测——404
    model_not_found 是确定性拒绝，只有主候选也失败时才轮到它暴露：fallback 链断裂在"主候选
    健康"期间完全静默；实录五跑 fail-open 的"双候选连锁"实为"qwen 饿死+glm 秒 404"。三验各
    对应一类已实际发生的事故：存在性（幻影候选）、思考默认态（饿死+计费虚高）、关思考参数
    接受性（参数不被 fallback 候选接受=400=亲手拆容灾链））

## M2.12 毕业实验（2026-07-17 出题）

70. ⬜ 中断-恢复等价为什么必须"C31 归一化+半截步折叠+剔簿记键"三段预处理，而不是裸 diff 事件流？
    （裸 diff 数学上不可能绿：事件 id 是 uuid 两流必不同（C31 别名 e1..eN/a1..aM 解决）、墙钟与
    usage 必然波动（C31 豁免）、LLM 中断留下的孤儿 llm_call 是"作废重发"的物理痕迹（折叠删除，
    否则形态 B 恒红）、resume_run 的 iteration 单 run 重计与恢复重建 prompt"保事实不保字节"使
    iteration/input_tokens_est 必然漂移（剔簿记键）。剔到最后剩下的才是行为轨迹本体：类型序列+
    text/tool_calls/args/result/reason；且比较器自身要有两枚自证测试——防"恒真"与防"静默放水"）
71. ⬜ 真实冒烟为什么只断三条不变量+成本顶，不断言回答内容？（真实模型输出非确定，断文本=把
    CI 的确定性判据建在概率源上；三不变量（幂等键无重复+审计投影 1:1 / seq 连续 / 合法终止）
    是"无论模型说什么都必须成立"的结构承诺；gateway_rejected 从合法集除名因为它是配置/协议
    bug 信号（C6）；回答质量的评测归 M4.4 离线评测——回放测行为、评测测质量、冒烟测不变量，
    三套判据各管一段）
72. ⬜ 两条降级实录的失败方向为什么相反？（会话锁：安全件——停 Redis 后降级 PG advisory
    **换后端保互斥**，宁可慢不可双写（fail 向保守）；事件写入：事实源——停 PG 退避 0.1/0.2/0.4s
    后 EventStoreUnavailable **明确终止**，事实源不可用=服务不可用，绝不内存缓写"假装还活着"；
    对照 M1 限流/缓存的 fail-open（成本件降级放行）——三类件三方向，出发点都是"这个组件的
    失败伤害的是什么"：安全伤害>可用性伤害>成本伤害）
73. ⬜ LangGraph 的 interrupt 恢复与本项目恢复单入口的本质差异？（interrupt 恢复=**重放节点函数
    从头**——interrupt 之前的副作用重复执行，官方文档靠"别把副作用放 interrupt 前"的使用者自律；
    我们=**重建事实**：write-ahead 幂等键先落盘、恢复经事件流重建 working（保事实不保字节）、
    半截工具凭原键 reexecute、下游按键去重——防线是结构性的不是纪律性的。深一层：checkpoint
    体系"state 即真相"，恢复对错无独立事实源可证；事件溯源才让"中断-恢复逐事件一致"成为
    可机器断言的命题——compare-langgraph-m2 §3/§4）
74. ⬜ 停 PG 实录抓出的"形状盲区"（ConnectionRefusedError 裸穿白名单）说明什么测试哲学？
    （注入测试与真容器实录**互补不可互替**：注入测的是"语义分支"（给我 OperationalError 我会
    退避），实录测的是"形状边界"（真实故障到底抛什么类型）——SQLAlchemy 只包装 dbapi.Error，
    asyncpg 池建连期的 OS 级错误未经包装裸穿，M2.2 用注入的 OperationalError 永远测不到这个形状；
    修复=白名单纳入 OSError（builtin ConnectionError/TimeoutError 皆其子类，CancelledError 属
    BaseException 不受波及），回归测试先在现行代码上验证为红（红=钉住缺陷）再随修复转绿）

## M2 复盘追问（2026-07-18 出题，源自用户复盘现场提问）

75. ⬜ events 表 append-only 只增不删，会不会撑爆数据库？（先拆两个增长：滚动摘要管的是
    **上下文窗口**增长——summary_updated 自己还是新增事件，不省存储；**存储**增长归 C21 数据
    生命周期口径（02 §7.3，2026-07-07 评审落档）：v1 显式声明"演示系统保留期=项目生命周期"、
    实装列 v2——评审原则是"含 PII 原文不允许对保留期不表态"，声明本身就是防守。schema 不给
    治理设障四件：全表带 tenant_id（租户注销=按租户级联删天然成立）、(session_id,seq) 使"整会话"
    成为自包含的归档/搬迁单元、schema_version 保证冷数据永远可解析、全表无外键删除搬迁无级联
    爆炸；到期归档/删除走 Celery 任务（workers/ 基建 M2.10 已在）。单会话有界：闸门 #1 每 run
    10 轮 + 闸门 #3 会话 token 预算默认 50k——M2.11 录 40 轮须专门抬到 400k，反证默认下单会话
    事件量被政策钉死。热路径不吃全表体量：运行时查询全部走 (session_id,seq) 前缀索引 +
    messages/summary 投影，表再大热路径只随本会话规模走；events 行零 UPDATE 零 DELETE，
    真正的 autovacuum 压力点反而是 sessions（租约每 20s 一笔 UPDATE）。深水区下一问=用户删除权
    vs append-only：02 落档"物理删该用户 events + 投影留 tombstone、牺牲该会话可重放性"的显式
    取舍；评审另备 crypto-shredding（按用户密钥加密 payload、删键即删）讲思路不实装）
76. ⬜ EventWriter 为什么一个 run 一个实例，ApprovalStore 却谁都能随手构造？create 为什么是
    ApprovalStore 里唯一不带 CAS 的写方法？（writer 有内存状态 `_next_seq` 且有身份 run_id——
    内存 seq 只在"我是唯一写者"期间可信，而写权按 run 授予（锁/租约），writer 生命周期 ≡ 写权
    生命周期；恢复必开新 writer 经 open 重读流尾接续（resume 路径实证：新 run_id + EventWriter.open）。
    ApprovalStore 零内存状态、全部真相在表、每方法自开事务——审批天生跨 run 跨进程（开单在
    run 内、decide 在 API 层、消费在 resume 新 run、清扫在 reaper），"一 run 一个"根本无法服务；
    events 需要单写者因为 seq 是全序，approvals 行间无顺序耦合、行内竞争由 CAS 裁决。create
    不带 CAS：CAS 防"两人翻同一行"，create 是新增 uuid 新行、无同行竞争；语义重复单由上游拓扑
    防（开单点在持锁 run 内唯一）、孤儿单由 expire_due 清扫、双执行由三重互斥+幂等键封死。
    一句话：**有状态者要主人，无状态者随便用；翻转要抢章，新增只登记**）
77. ⬜ acquire 与 steal_expired 都在"抢租约"，为什么是两个函数而不是一个带参数的？（两种言语
    行为：上任/续任 vs 灾难抢救——三个非对称焊死在各自 WHERE 里：①**记账**：steal 必
    recovery_count+1（C9 毒会话判据的原料），acquire 绝不动账（正常上任不攒毒分）；②**上限**：
    recovery_limit 只能卡抢救、不能卡上任——否则死锁：steal 把 count 推到 limit 后
    ResumeHook→resume→acquire 若也查限，刚被授权的这次恢复当场被拒；③**重入**：acquire 允许
    同 owner（runtime 与 reaper 同进程同 host:pid，steal→钩子→resume 交接链靠它通行，重入也
    gen+1 换新凭据），steal 只对死租约（NULL/过期）出手、拿不了任何活租约（含自己的）。合成
    带 flags 的单函数 = 政策可被参数绕过、WHERE 不再是一条完整可审计的合法性陈述。再一层配对：
    list_expired 扫描只出候选名单，steal 原子重查才算认领——check-then-act 的 TOCTOU 由"act
    自带重查"消化）
78. ⬜ 到底什么场景会有"多个进程碰同一个会话"？steal_expired 的 WHERE 凭什么算"确认死亡"？
    （四类来源各配防线：①水平扩展无粘滞路由——下一条用户消息落任意 API 副本（M3.2 起），
    并发形态=用户双击/客户端重试两副本同时抢跑 → T1 CAS 恰一赢家；②HITL 挂起——"进程可
    下线"是设计目标本身，恢复常在另一副本/另一代进程；③崩溃接管——kill -9/OOM/滚动部署后
    由 reaper（独立 Celery 进程）认领续跑（m2_kill9 实录）；④僵尸——GC 停顿/分区/假死的旧
    持有者在接管后醒来继续写：gen 围栏（renew 打空→LeaseLost 自毁零事件）+ 唯一约束
    （EventWriteFenced）双层兜底（题 59）。"死亡"在分布式系统不可直接观测，唯一可观测的是
    "沉默超过 TTL"——steal 的 `expires_at <= now ∨ IS NULL` 就是死亡的**操作性定义**（NULL=
    T1 后 acquire 前夭折的幽灵）；定义可错（假死者可能活着），可错性的代价由围栏层买单，
    所以"判死"敢写成一行 WHERE。且 steal 的 WHERE 无任何 owner 分支：活租约两条 or 都不满足，
    谁的都拿不走——"只收尸、不夺权"是函数形状直接保证的。**追补**：双击/重试类竞态的裁决全在
    CAS 门（起跑=T1、恢复=T3、批准=decide），租约在裁决瞬间零参与——**CAS 定上任，租约管任期**：
    每个 CAS 赢家随即登记为持约人，使"赢家中途死了"从双写问题转为孤儿问题（reaper 可收）；
    另须分清：并发双击=互斥问题（CAS 管），迟到重试=幂等问题（L3 请求去重管，M3 范围）——
    后者 CAS 根本不拦、也不该拦）
79. ⬜ run 异常退出后 running 状态谁负责归位？为什么异常路径故意不做现场清理？（crash-only
    立场（C35 五段声明）：正常收尾由持权者亲手做——loop._terminate 翻 T4、pump 正常耗尽才
    release（release 在 try/finally **之外**，任何异常都跳过它，runtime._pump_with_lease）；
    非正常收尾（kill -9/事实源不可用/围栏自毁/未知 bug）一律不做现场清理，理由三条：①清理
    代码自身可能失败（PG 挂时拿什么 UPDATE run_state）；②按异常类型写清理永远写不全；③让
    恢复路径成为唯一清理路径=清理逻辑只有一份、且被 kill -9 实录锤炼过。归位写手全清单：
    正常/闸门终止=loop._terminate（T4）；审批拒/撤/超时=resume 轻量路径 T4；崩溃后发现其实
    已善终=reaper 认领分诊 a 支补翻 T4+release（零新事件）；崩溃后续跑=新 loop 终止时自己翻；
    毒会话=T5 →failed 不归 idle；僵尸（LeaseLost/Fenced）=谁都不翻，状态归继任者管。原则：
    **租约过期是时间事实（自动发生），状态归位是权力行为（必须持写权者 CAS）——run_state
    永远不会自己变**。**追补（"为什么 run()/APPROVED 分支看不到 transition"）**：翻转与"写
    收尾事件"是**同一动作的两半，收敛在单点**——T4 就住在 loop._terminate 里（写 loop_terminated
    紧接着翻 T4，D14 单点）、T2 住在 loop 挂起链路里；所以**凡是"驱动 loop"收场的路径**（run、
    APPROVED 续跑、recover b/c/d 支）**绝不自己翻**——loop 的结局（终止/再挂起）自带翻转，
    runtime 再翻=双翻（第二次 CAS 打空的噪音+破坏"T4 恰与 loop_terminated 配对"）；**只有
    runtime 亲手写收尾事件、不驱动 loop 的路径才亲自翻**——拒/撤/超时轻量路径（自己写
    loop_terminated 故自己翻 T4）、recover a 支（补翻崩在 loop_terminated 与 T4 之间缝里的
    状态）。判据一句话：**谁写收尾事件谁翻状态，委托 loop 的把翻转也一并委托**）
80. ⬜ reaper 抢到租约后为什么不自己调 AgentRuntime.resume，而要经 ResumeHook 间接？M2 生产
    链路无人注册钩子，系统靠什么不悬空？（三条理由：①resume 的第一个参数就是 AgentSpec——
    spec 是 L3 知识（哪个租户/什么 prompt/工具/策略），M2 没有 L3，workers 层永远装配不出
    它（依赖倒置的最尖锐后果）；②层纯净：reaper 不 import 任何业务（3.2#11），恢复逻辑全在
    钩子后面；③调度器≠执行器：钩子异常批内隔离（P6），单会话炸不中断整批。Celery 链路已把
    注册点接好（_reap_fresh 传 resume=_resume_hook），M2 注册者=kill -9 实验脚本的演示钩子
    （装配 demo spec + rt.resume(spec, sid, None)），真实钩子 M3.8 注册。无钩子自洽（C9）：
    抢租不恢复只 warning → 租约再过期再抢 → recovery_count 递增 → 超限 T5 failed——hookless
    也有终态，绝不无限空转。这是"挂点先行"家族的标准样本：ResumeHook/PrecheckHook/
    Memory·RetrievalProviderLike/entry_classifier——M2 造缝+钉住行为，M3 接电）
81. ⬜ 跑会话的进程死了，reaper 也死了——session 会永远卡在 running 吗？（不会"永远"，只会
    "暂停到下一个 reaper 上班"：死亡证明是**持久状态**（running+过期租约躺在 PG 行上）而非
    瞬时信号，恢复触发是**扫描**而非订阅——list_expired 无时间窗，过期 1 秒与 3 天一视同仁，
    reaper 重启后首轮全部收走；reaper 无状态无记忆（每轮从 PG 全量重推导，"待办清单"就是
    数据库本身），收尸人自己也是 crash-only——死了重启即可、无交接班；多副本下任何 worker
    的 reaper 都能收任何会话（steal CAS 使并发 reaper 安全）。期间代价=可用性不是正确性：
    T1 打空、新消息被拒，但事件/幂等键/count 全在；长期停摆不烧恢复预算（count 只随 steal
    次数涨、不随时间涨）。reaper 靠谁复活=进程监督层：#31 容器 restart 策略挂 M4.7、生产
    N worker 冗余、本地手动重启；同族已登记降级：Redis 全灭→broker 停摆→reaper 停摆=显式
    接受（02 §5/ADR-005），Redis 回来自动补课。哲学：每层系统最终触底于"有东西会重启进程"
    的运维假设——设计的义务是把该假设收窄到最便宜形态：恢复只需"最终任一 reaper 跑一轮"，
    且该条件无状态、可并发、可积压）
82. ⬜ 同一场"Redis 全灭"里，会话锁降级到 PG advisory 保住互斥，reaper 却允许随 broker 停摆
    ——为什么一个给后备、一个给接受？（性质类型不同：互斥是**安全性质**（任一时刻都不许破，
    破=双写事实源）→ 必须有 fallback，宁可慢不可断（C4 三件套）；恢复及时性是**活性性质**
    （允许暂停，只要最终发生）→ 显式接受停摆（ADR-005:45-47"broker 即 Redis，beat/reaper
    随之停摆——已接受的降级面，Redis 恢复后自愈；outbox 补投列 v2 展望，不假装已有"）。
    撑住"接受"的结构前提：恢复的**正确性**锚在 PG——死亡证明是持久行、扫描无时间窗（题 81），
    Redis 只承载**触发器**，丢触发器=延迟、不丢事实不坏不变量；且 Redis 全灭本就是深度降级
    世界（L1 已进本地桶/本地计数），为活性再造第二套调度基建违背"一个 Redis 六角色"的架构
    预算（ADR-005 备选方案：专用组件拼盘单人运维不起）。评审侧写：C7 抓的正是此前"停 Redis
    核心链路不断"叙事**未点名**这一停摆面——显式接受与静默悬空的区别就是有没有这一行字。
    判据一句话：**安全性质买 fallback，活性性质买 acceptance——钱花在"绝不能破"上，不花在
    "晚点也行"上**）
83. ⬜ RiskPolicy 为什么是同步二元谓词 (args, tenant_config)->bool？ToolContext 五字段运行时
    都有，为什么要打包注入而不让工具自查？（谓词四特征：**同步**=类型上就做不到在风险判断里
    问 LLM/做 IO（确定性安全闸门，C34 fail-closed 侧——async 都不给你）；入参是**已校验 args
    实例**（闸门排在①后，面对干净参数，幻觉字段已被 extra=forbid 拦掉）+**不透明 tenant_config**
    （阈值住租户配置、运行时不解释——同一工具异租户异阈值零改码）；**无身份入参**=判据是
    "操作+政策"而非"谁"（身份相关政策靠 L3 每会话装配 spec 时塞进 tenant_config）；返回 bool=
    只分流（直行/走审批）不裁决拒绝。ctx 打包注入四理由：①tool_call_id **无处自取**——它是
    write-ahead 时刻诞生的事件 id，per-call 而非会话属性（题 16 的正主）；②**窄腰最小权限**——
    handler 是纯 async 函数只见五根手指，允许自查=工具耦合 store+DB session、还看得到 lease/
    summary 等无关状态；③**快照语义**——frozen 的"调用时刻"身份，reexecute 凭原键可重造快照，
    现场查询不可复现；④**纪律拓扑化**——"身份唯一合法来源=运行时注入"靠"只有 executor 造
    ctx、handler 只收 ctx"的结构成立，与"模型说不出身份"（schema 剔除）是同一防线的两侧。
    实锚：demo_refund_apply 返回 ctx.tool_call_id（幂等键 echo 实证）、demo_ticket_create 记
    ctx.user_id、_demo_refund_needs_approval = args.amount > tenant_config.get(threshold)）
84. ⬜ arguments_json 长什么样、为什么是字符串不是对象？（OpenAI 线格式的双重编码现实：
    function.arguments 本身就是"装着 JSON 文本的字符串字段"，SSE 流里还是逐段碎片——适配器
    按 index 攒完整（M1.4），v1 以整体 ToolCallChunk 交付、不做增量解析（schema.py:73）；网关
    立场（schema.py:29-30）："保持模型输出的原始字符串——可能不是合法 JSON。网关不解析：怎么
    处理坏参数是 L2 的业务决策，不是传输层的"——传输层保真、判定权在业务层，坏 JSON=模型
    行为（ERROR 回填让它自我纠正+闸门 #5 计数）而非传输错误。三入口的信任类型学：execute 收
    **str**（不可信原话，过①严格校验）；resume 批准路把 approval.args 快照 json.dumps 回字符
    串走同一入口（回炉重验）；reexecute 直收 **Mapping**（当年校验过的档案，跳①）——**参数
    类型即信任等级**。落盘双形态：llm_result 存 arguments_json 原话（"模型说了什么"），
    tool_call 存 model_dump 规范形（"我们认定了什么"）；闸门 #4 的 canonical_json 同用规范形，
    键序抖动不误判）
85. ⬜ 工具调用链路里有两套 id，各自管什么、为什么严禁混用？（**对话协议 id** = ToolCall.id
    （"call_88ab…"，模型/供应商生成）：只活在对话协议里——下一轮 role="tool" 消息的
    tool_call_id 必须用它配对（OpenAI 线格式要求，配错=400 或答非所问），llm_result payload
    里也存它；**幂等键** = tool_call 事件 id（我们的 uuid，write-ahead 时诞生）：只活在事件流/
    ToolContext/投影/下游去重里。混用后果：拿模型 id 当幂等键=把去重语义押在供应商 id 生成
    习惯上（重发/重试时模型侧 id 可变），拿事件 id 配对话=模型认不出这是谁的结果。分界口诀：
    **对话的事对话 id 管，事实的事事件 id 管**——loop._feed_tool_message docstring 明写"两种
    id 严禁混用"（retro §7 坑 6））
86. ⬜ 用 LangChain 的 @tool 能实现我们 ToolDef 的全部功能吗（含 ctx 注入）？（能的两块：
    schema 三产物殊途同归（inspect+Pydantic，M1 对照 §8-3 已证）；"ctx 不暴露给模型"有对应物
    InjectedToolArg/InjectedState（Annotated 标注 → 从 tool-calling schema 剔除 → 调用侧注入）。
    不能的是治理层（compare-langgraph-m2 §2 命运表"七步留六步"）：① forbid 口径与坏 JSON 回填
    话术自己写（handle_tool_errors 只是"异常变 ToolMessage"的钩子）；②③ 权限/风险闸门/C15
    无概念——"写工具裸奔在框架里不是错误"；④ write-ahead 幂等键**最关键缺失**——ToolNode
    执行前不落任何事实，框架给得了 ctx 的**形态**、给不了"副作用前诞生的键"这个**内容**
    （能注入的只有对话 id → 题 85 的混用成为默认）；⑤ 超时/读写重试分野自己包（with_retry
    通用重试、不拦写重试）；⑥⑦ 规范化留痕/审计投影无；X1/连败禁用无——"模型自发重试会生成
    新调用，正是我们防的去重失效"。side_effect 可塞 metadata 但无消费者=恢复语义不存在。
    结论：@tool 是"说明书印刷机 + 参数座位"，治理层全部自建，建完后框架只省 ~30 行 dispatch
    ——ADR-003 行数账的工具节。面试答法：**接口问题框架解决得很好，治理问题框架留给使用者
    自律，我们把自律变成了结构**）
87. ⬜ 如果团队用 LangGraph，side_effect/risk_policy/risk_exempt 这层治理具体怎么落地？（三层
    迁移账：**声明层便宜**——自建 @governed_tool 装饰器包住框架 @tool，治理字段存自己的
    typed wrapper（塞 tool.metadata 是无类型 dict、防呆还得自写），C15 照旧 import 时炸——
    装饰器就是 import 时执行的函数调用，立法权在自己手里；**执法层要夺一个咽喉点**——弃用
    prebuilt ToolNode，自写工具执行节点：谓词 fail-closed → interrupt()（纪律：interrupt 必须
    在一切副作用之前——官方文档口头嘱咐的这条，正是我们"③闸门先于④write-ahead"的结构化
    版本：我们用步骤顺序焊死，框架用文档劝人）、READ 才允许重试、WRITE+超时自造
    RESULT_UNKNOWN 话术、asyncio.timeout 自己包——该节点 ≈ 把 ToolExecutor 塞进 LangGraph
    的一个 node；**保障层要补基建**——副作用前写自己的 journal 表拿幂等键、经注入参数交给
    handler（= 搬 store.py 的 write-ahead 半区，从此 checkpoint+journal 两个持久层的一致性
    自己对账）；审批五态/expires fail-closed（C7）/双坐席 CAS（C11）/前置校验挂点"框架侧全部
    要自建，等于把我们的 ApprovalStore 原样搬过去"（compare §3 原话），到期扫描还得配定时
    任务——reaper 又回来了。收束：**声明层一天、执法层一个节点、保障层半个 store**；搬完后
    框架真正承担的只剩图编排 + checkpoint + interrupt 的 pause 底座。面试价值：这证明治理层
    **可迁移**——它是覆盖在任意执行底座上的纪律，不是自研骨架的专利）
88. ⬜ 审批恢复和崩溃恢复分别走哪个执行入口？判据是什么？write-ahead 为什么必须在执行前？
    （入口分野：审批通过 → resume 走 **execute(approved=True)**——挂起发生在生命周期③，
    ④ write-ahead **从未发生**、没有键，必须走全程重新立据（①回炉重验+④新键），只免再过
    闸门③；崩溃恢复的悬挂工具 → **reexecute(原 tool_call_id)**——④ 已发生、键已存在、副作用
    可能半途，再走 execute 会立第二张字据=两把钥匙。判据一句话：**tool_call 事件在不在**。
    approved 免的是"过闸"，reexecute 免的是"立据"——两个免除项互补不重叠。write-ahead 先行
    的根本理由=崩溃三窗口全部可判定：④前崩=无事件无副作用（干净，作废重发）；④后⑦前崩=
    孤儿 tool_call（可愈，凭原键 reexecute+下游去重）；⑦后崩=配对完整（续跑）。反向方案
    （先执行后记账）的坏窗口是"**有货无账**"——副作用已发生但零记录零钥匙，不可修复；正向
    坏窗口是"**有账无货**"——凭原钥匙重办一次即恰一。write-ahead 的本质=把不可修复的窗口
    换成可修复的窗口；且幂等键必须先于副作用存在才能随 ctx 出门交给下游。**追补（"审批通过
    直接用 reexecute 不就行了"的三连反驳）**：①签名层——reexecute 要 tool_call_id，审批场景
    挂起在③、④从未发生，**没有这把钥匙**；②硬伪造一个 id → reexecute 以它写终局 →
    投影 _finish_invocation UPDATE WHERE event_id=伪id → rowcount 0 → **ProjectionError
    掀翻事务**（"write-ahead 顺序被破坏"）——投影层机器拒绝伪键；③最本质——批准的调用是
    **首次执行**，必须经 execute 铸自己的钥匙（fresh write-ahead），这样批准执行中途再崩，
    crash 恢复才有悬挂 tool_call 可认、才能 reexecute：**两入口是接力关系（execute 铸键→崩→
    reexecute 用键），直接 reexecute=跳过铸键=中途崩死即"有货无账"**——恰恰重演 write-ahead
    要防的灾难。参数信任面佐证：approvals.args 存 **LLM 原始参数快照**（loop json.loads
    (arguments_json)，D6），tool_call.payload.args 才是 model_dump **规范形**——审批路必须
    回炉①（runtime 特意 json.dumps 回字符串走全门，题 84"参数类型即信任等级"活案例），crash
    路拿的是已规范化档案才有资格跳①）
102. ⬜ reap_once 里 steal 打空后那段分诊在干什么？_reap_fresh 为什么不能省掉直接
    asyncio.run(reap_once(...))？（①steal 返回 None 是**多义的**——WHERE 三条件任一不满足都
    给 None：被并发赢家抢走（租约变活）/已被别的 reaper 判死（非 running）/原主僵尸自愈续租
    （租约变活）/**超限**（count≥limit，判死路径的正主）。分诊=查快照 (count,last_owner,
    run_state)：count<limit 或非 running → 别人处理了，安静走人；两者都过 → T5 CAS 判死
    （恰一次判定权，偏差#7：多 reaper 同到此处只有一个赢，输家安静）→ 赢家 clear_lease（无
    CAS，failed 终态无竞争者）→ 临时 writer 写 RECOVERY_ABANDONED 尸检三键。count 单调增
    保证判定不回退（快照值直接进审计）。**边界观察（候选⑥）**：判死谓词只查 count+state、
    **不查租约活性**——若另一 reaper 恰在 count=limit-1→limit 抢到并正在恢复（第 limit 次
    合法尝试进行中），本 reaper 快照见 count=limit∧running → T5 判死 + clear_lease 会**掐掉
    进行中的最后一次合法恢复**（围栏保安全：被掐方 LeaseLost 自毁零事件，无正确性损失，但
    "第 limit 次尝试被允许却被中途处决"语义不净；**已修：复盘补丁五 `b0e438b`**——
    _session_snapshot 四元组 DB 端算 lease_alive、判死分支活租约让行（无为），钩子模拟竞态
    交错测试**先红后绿**，552→553）。②_reap_fresh 三职责，省不掉：**async 资源帧**——asyncio.run 只接一个协程，
    而"create_engine→用→await dispose()"的资源生命周期必须整体发生在同一事件循环内（dispose
    是 async；不 dispose 则连接绑死循环、loop 关闭时报错泄漏），必须有个 async 函数当循环内的
    资源管理帧；**组装根**——reap_once 六参数全注入（薄壳厚仁的可测性来源），settings/owner/
    _resume_hook 的聚合总得有人做，_reap_fresh 就是 worker 语境的"组装在边缘"（对位 AgentRuntime
    ._assemble/build_session_lock）；**三层分工**——reap_once=逻辑肉（纯注入）、_reap_fresh=
    组装+资源（async）、celery task=皮（sync+日志），各层独立可测可换。**追补（为什么每任务
    独立 NullPool 引擎）**：两个决定两条理由。①独立引擎（不复用全局 get_engine()）——机制链：
    asyncio.run 每任务**新建并关闭**一个事件循环；asyncpg 连接内部持有创建时 loop 的
    future/transport，**绑死出生 loop**；而池的本质=跨调用保留连接——任务 #2 会从池里借到
    "loop #1 的连接"→"got Future attached to a different loop"炸。全局引擎是 API 进程
    （长命 uvicorn loop）的资产——**池是 event-loop 级资产不是进程级资产**。②NullPool
    （新引擎也不要池）——池的收益前提是"绑定物长命、连接可复用"，这里 loop 一任务一死，
    池内连接对下个任务零价值；NullPool=即用即还即关，任务结束零持有，`await dispose()` 从
    唯一防线降为保险；成本（每操作新建连接 ~ms）在 30s 节奏下可忽略。一般原则：**资源生命
    周期必须匹配其绑定物的生命周期**。对照：API 进程=全局引擎+真池；worker=每任务引擎+
    NullPool+dispose。为什么不在 worker 养长命 loop 复用池：可行但要线程+Celery 信号协奏，
    30s 节奏下池零收益、复杂度不值。错误形态的险恶：**第一次任务好、第二次才炸**——"测试
    跑一次全绿、生产第二拍死"的经典 flaky，故列 §7 陷阱 2/3.2#8）
89. ⬜ 工具执行为什么可以重试？失败原因有哪些？（**三层重试体系**：执行器内重试——同一把
    钥匙（④只立据一次、重试全在⑤）、仅 READ 且作者显式声明 retries>0、退避 0.2×attempt，
    理由=读无副作用、重跑等于再问一遍；模型自发重试——新钥匙（新 write-ahead），仅当上次是
    "已知失败"（ERROR）才安全，RESULT_UNKNOWN 话术专门封死这层（X1）；恢复期重执行——原钥匙
    （reexecute），仅崩溃分诊 b 支。**失败谱按站位**：门口=幻觉名/已禁用（不进连败账）；
    ①=坏 JSON/非对象/ValidationError（进账）；③=谓词崩溃 fail-closed（进账）、命中闸门=
    分流非失败；⑤=READ 超时耗尽与 handler 异常（进账）、WRITE 超时=RESULT_UNKNOWN（**不进
    账**——结果不明≠工具坏，它可能成功了）；⑥=摘要钩子失败 fail-open 非失败；append 炸=
    基础设施裸穿非 outcome。连败账只记"工具或参数通道真的坏"。**灰区（推演，M3.7 handler
    契约候选）**：分类按异常类型近似"模糊 vs 确定"——写请求发出后连接重置，物理上模糊却以
    异常形态到达→ERROR→模型可重试新键；缓解三层=handler 纪律（发出后不确定的传输错误按
    超时语义处理）+ 下游业务级幂等（X2 评审当年点过"所有写工具下游都去重是无人担保的前提"）
    + 高危写多走 HITL 收窄窗口。**追补两点**：①**同名异命**——同样是 OperationalError，从
    append 抛出=事实源没了→裸穿终止 run；从 handler 抛出=该工具的私有依赖坏了→ERROR+连败
    +禁用：世界分界按"从哪抛出"划、不按异常类型划；②**本地取消≠远端撤销**——asyncio.timeout
    的机制是取消内部协程再转 TimeoutError，超时后 handler 本地已被掐死不再跑，但它发出的
    HTTP 请求可能仍在下游处理中——这就是"副作用可能已在下游生效"的物理基础；CancelledError
    属 BaseException，except Exception 接不到→用户取消穿透执行器（与 append 同款））
90. ⬜ ContextConfig/LoopPolicy 为什么不进 config.py 的 Settings？（居所判据三条：①**权属**——
    Settings 装平台物理学（DB/Redis URL、租约 TTL、扫描间隔：全租户一致、运维定），注入面装
    租户策略（预算/阈值：M3.1 起按租户从配置注入，同进程异租户异配置）——最锋利的对照对：
    approval_ttl_s 住 LoopPolicy（审批时限=业务策略）而 lease_ttl_s 住 Settings（租约=调度
    物理学），两个"TTL"分居两处，判据即此；②**作用域**——Settings 是 lru_cache 进程单例，
    注入面 frozen 随 run；③**可复现性**——Settings 读环境/.env（cwd 陷阱在案）=不可复现输入，
    ContextConfig 随 spec 进回放、字节一致，测试零环境构造即得）
91. ⬜ 历史层的保留策略三问：孤儿 user 从哪来？预算不足时丢谁？被丢的轮去哪了？（①末尾
    _push 首先是**常规收口**——最后一轮永远没有"下一条 user"来触发收口，没有它每场对话的
    最后一轮都会蒸发；孤儿只是 assistant 恰为空的特例，四类来源：崩溃（user_message 恒首
    事件已落、assistant 没来得及）/gateway_rejected 零话术终止（C6 fallback=None——**设计内**
    孤儿，配置 bug 不许被话术掩盖）/挂起后拒绝·撤回·超时轻量路径（无 assistant_message）/
    LeaseLost 自毁零事件；立场="用户确实说过的话不许从历史里蒸发"。②丢的方向是**最新优先
    保留**：reversed(uncovered)+装不下即停=保最新轮的连续后缀，丢的是较老的 uncovered——
    "新消息一条不留"只在单轮>budget_h 的量级异常下发生（D11 保 user 原文、历史层空、events
    兜底），0.8 预热阈值正为减少这种突发。③被丢≠丢失：下次 build 重读 turns、need 仍超阈
    →下次摘要 k 从最老吃起→被丢的轮被摘要**收编**——是延迟压缩不是丢弃，每 build 一摘多轮
    收敛；不跳装的理由=宁要时序连续的后缀、不要"第3轮第5轮"带洞的历史。**追补（复盘现场
    揪出的候选）**：摘要 vs 近轮是另一层优先级——摘要先装、近轮吃剩余，摘要肥大时近轮可被
    挤到零。这优先级本身是设计（摘要=全会话根基唯一载体：身份事实全在早期轮，丢摘要=失忆、
    丢近轮=细节暂缺且会被下次摘要收编；M2.11 探针实验即此优先级的验收）；但**摘要长度无
    生成期上界是真软肋**——_SUMMARIZE_PROMPT 只有语义压缩指令无字数限制、summarize 请求未设
    max_tokens、落库不 clip（插入期 clip 只管 prompt 侧、事件里全文进下次 source）——若 fast
    模型持续产出接近 budget_h 的长摘要，"暂时挤空"会变"长期挤空"。现实缓解=压缩指令+fast 档
    输出习性+M2.11 实测健康；**终裁（2026-07-19 复盘补丁三，两轮议定）**：落库
    clip 与生成侧 max_tokens **双双否决**，只改 prompt 版面——插入期摘要至多占
    allowed×_SUMMARY_PROMPT_SHARE（0.5），且**仅当有 uncovered 近轮排队时生效**（无人排队
    不白扣版面）。否决理由链：落库 clip=**租户策略污染不可变事实**（history_budget 按租户
    注入，clip 落库让配置漂进事件史，日后调大预算旧摘要已残；X4/cs-11 口径，与 executor
    result 全文+injected 留痕同族）；max_tokens=**解码级硬截断把半句残话写进事实源**再喂
    下次 source，且触顶信号被钩子静默吞掉——为防低概率跑飞引入常态性残句，不值。修复靶心
    （最新轮盲窗）由版面份额结构性关闭：近轮永远有 ≥(1−份额)×allowed 的保底席位。显式接受
    的残余边界：摘要生成长度理论无界——跑飞的代价=summarize 成本上升（ledger 可见）+
    source 变肥，prompt 已由份额 clip 保护，无用户可见伤害）
92. ⬜ replay 三细节：四道为什么恰是这四道？request_digest 为什么排除那四个字段？裸 complete
    是不是死代码？（①四道 = 一次 run 内 LLM 触点的**完整普查**：main（循环本体）/summary
    （滚动摘要钩子）/guard（入口分类器）/tool_digest（结果收缩钩子）——分道判据是**计数独立
    变化**：四者各随预算压力/租户开关/结果大小独立波动，分开后任何源的次数变化被精确定位到
    道。M2.8 entry_classifier 默认关的拍板是它的活教材：恒开会让无 guard 道条目的既有 cassette
    全红——但红在"guard 道耗尽"这个**准确诊断**上，而非 main 序号错位的胡话；②排除
    request_id/session_id/tenant_id/deadline_s = **语义指纹**口径（与 cache.py 同一把尺，全仓
    一个指纹概念）：指纹回答"是不是同一个问题"——请求 uuid 是水管编号、session/tenant 是
    "谁在问"（租户隔离在缓存 key 前缀层实现、不靠哈希）、deadline 是"愿意等多久"，都不改变
    模型会怎么答；留下的 messages/tools/tier/temperature/max_tokens 才是问题本体；③裸
    complete 不是死代码，是**通行证 + 退化语义**：类型层它让 Fake/Recorder 满足 GatewayLike
    （协议是入场券，否则传不进 AgentRuntime）；语义层"裸 complete ≡ scoped('main')"是被测试
    钉死的契约（test_replay_fake_gateway——不懂分道的通用消费方拿到主道语义）；runtime 主
    路径确实只走 scoped 视图——"生产不调用"与"结构必需"并不矛盾）
93. ⬜ guardrails 入口/出口的三处形态不对称，根因是同一条？（①**有状态 vs 无状态**：check_input
    是门面方法（一次裁决无累积），output_guard 是**工厂**（每个文本出口 new 一个 OutputGuard——
    buffer/released_tail/hit 是流式累积态，共享实例=上轮污染下轮，同"有状态者要独立实例"族）；
    ②**LLM+正则 vs 纯正则**：入口有 classifier 增强、出口只有正则；③入口一次调用、出口每句
    都要判。三者同根：**输入是完整到达的、输出是逐步生成的**。派生的判断性质差异=出口该不该
    上 LLM 的真答案：入口判"意图是否可疑"（模糊语义，LLM 有增量），出口判"是否含已知敏感物"
    （system 片段/工具名/PII——我手上就有原文与清单，是精确匹配，正则更可靠且 LLM 会漏会幻觉）；
    加 LLM 到流式出口还会破 feed≡整段确定性（非确定+延迟入回放路径）+ 每句一次往返延迟爆炸。
    留白：语义级出口检查（跨租户泄漏）确有挂点——在 final_check（终局一次、非流式路径）而非
    feed，将来若上 LLM 从这里进，绕开确定性与延迟两道墙）
94. ⬜ OutputGuard 三追问：max_hold 引入 _released_tail 值不值？feed 与 final_check 冗余吗？
    args schema 外泄为何不拦？（①**尾窗不是 max_hold 的意外负担、是"切分放行"的固有需求**：
    敏感串可跨**句**边界（system 片段横跨两句号），单句扫描本就漏——纠因果，_released_tail
    由"按句切放行"引入、非 max_hold；max_hold 只多加"伪句"一种切法，尾窗对句界/伪句一视同仁。
    max_hold 本身解决**活性/DoS**：无上限持有=攻击者发永不带标点的超长串→无限持有、首字延迟
    无穷、内存涨；200=正常句宽松上界，超之强制切检。去 max_hold→DoS，去尾窗→跨界漏检，缺一
    不可；"整 buffer 当伪句"被否因切分点随增量边界漂移破 feed≡整段。②**feed=及时止损、
    final=完备兜底，不冗余**：feed 逐帧命中即停后续放行（让流式"边生成边显示"可行），
    但分句检查有边界漏网（伪句恰切开 PII）；final_check 对完整文本一次过全部匹配器=feed 的
    确定性超集，补漏。只留 final→退化聚合、流式意义全失；只留 feed→边界漏网。**纠误解**：M2
    "等完整回复"不是 final_check 造成的——M2 本就聚合单发（_llm_step 已消费完整流拿到完整
    turn.text，无用户可见流）；M3.10 真流式下 final_check 只在流末一次、不阻塞前面已 feed 放行
    的显示。二者命中语义差：feed 命中=前缀已流出→truncated 止损；final 命中=M2 时 assistant
    尚未落→整条替换 final_replaced。③**args schema 不拦是范围选择非缺陷**：三族（system 片段/
    工具名/PII）是精选高敏感物；args schema 本就在 prompt 里发给模型=半公开业务契约，泄漏危害
    有限（真防线是权限系统+严格校验+风险闸门，模型知道参数格式也调不动没权限的工具——呼应站9
    "不指望出口守卫兜住一切"），且形态多变难精确匹配。与银行卡不防/自由文本 PII 不防同族=v1
    显式召回边界；租户若认定内部结构敏感=v2 可配扩展点（三族构造期可加匹配器））
95. ⬜ T1 CAS、租约、(session_id,seq) 约束都在了，会话锁的意义是什么？（先认事实：M2 全程
    lock=None 直通、kill -9 实录也没用它——M2 的正确性由 CAS+租约+约束扛，锁是"挂点先行"
    家族成员（主链路接电 M3.2）。它买三样：①**让冲突死在最便宜的地方**——约束-only 世界：
    第二写者先写 user_message、烧一次真 LLM 调用、再在 seq 冲突上爆炸（保真相但留半截尸体+
    真金白银）；T1 CAS 把拒绝提前到一次 PG UPDATE；锁再提前到 Redis 前门 sub-ms 一次 SET NX
    →409（ADR-005 备选方案原文："限流/锁这类每请求多次的操作会把连接池打满——PG 管持久事实，
    Redis 管易失协调"）——双击/客户端重试风暴由 Redis 吸收，不进 PG 连接池；②**通用互斥 vs
    特化闸**——T1/T3/steal/T5 是四个逐路径手工设计、逐个证明正确的专用 CAS；M3 API 层会长出
    更多"读会话-决策-写事件"的复合操作（消息准入、取消审批…），每条新路径都发明一个正确
    CAS 是脆弱的，"先 hold_session_lock 再动会话"让新路径**默认安全**；③**持有期失锁感知**
    ——run_state 没有心跳概念，held.lost 给活着的持有者一个"你已失去互斥"的主动信号（分工：
    租约心跳管"死后被接管"，锁看门狗管"活着时自知失权"）。五层防御定位一句话：**锁=最外、
    最便宜、最通用；CAS=已证明的专用闸；租约=死亡交接；围栏+约束=物理底线**。
    **追补（HeldSessionLock 三字段之问）**：实况比"只用了 lost"更彻底——locks.py 内部看门狗
    与 release 用的全是**闭包局部变量**（session_id/token 字段零内部消费），且 runtime 的
    _maybe_lock 干脆 `yield None` 把整个 held 丢弃——今天生产代码连 lost 都只写不读（读者在
    测试，消费接线在 M3.2）。三字段的理由：这个对象是发给调用方的**收据**不是锁的机件——
    凭据三要素=哪个会话（多锁持有/日志关联）+什么身份（**SessionLock 三方法全要 token**：
    不暴露它，持有者无法做任何带外操作——提前释放/手动续期/redis-cli GET 比对排障"这把锁
    是不是我的"）+还有没有效（lost：Event 而非 bool——可 is_set 轮询也可 await wait，M3.2
    的自然接线点是喂 cancel/事件间检查【推演】）。与 ToolContext 同族：**凭据自包含**是本仓
    一贯风格；诚实定性：今天是"无消费者的自描述字段"，严格 YAGNI 派可只返回 Event（日后加
    字段不破坏兼容），这是风格判断题不是对错题）
96. ⬜ 方法论：怎么决定一个类持有哪些属性/构造参数？（**属性五分类**——① 协作者=我要主动
    调其方法的对象（gateway/builder/executor/factory/registry/approvals），存引用；② 配置=
    决定我行为但我不改的只读参数（config/policy/tenant_config/各阈值）；③ 身份=这次运行"是谁
    在哪"、贯穿全程从外带入（session_id/run_id/tenant_id/user_id/token_seed）；④ 可变状态=
    只有我改写、体现"我记着什么"（_iteration/_violations/_turns/_repeat_streak/_tokens_used/
    _fail_streaks/_cursors/_buffer）——**有可变状态 ⇒ 每 run 一实例**，这是全仓"一 run 一
    executor/builder/writer/loop"的根因；⑤ 测试缝=不确定源做可注入、默认给生产值（sleep/
    id_factory/cancel_event/now）。**两条分界线**：(a)**生命周期匹配**——run 内不变的进
    __init__（①②③⑤），每次调用才变的进方法参数（user_input/messages/working 进 run()/build()
    不进构造）；判据=这个值只在单次方法调用有意义就是参数不是属性。(b)**最小持有**——宁持窄
    协议不持大实体（builder/executor 持 EventSink 不持 EventWriter）、宁持切片视图不持全权
    （loop 持 scoped_view('main') 不持真 gateway）、职责边界决定"不持有什么"（builder 只管
    messages 不碰 tier/deadline——D3）。一句话：**协作者答"我要调谁"，配置答"什么定我行为"，
    身份答"我为谁跑"，状态答"我记着什么"，测试缝答"哪里要可控"；不变入构造、每次变入参数、
    能窄则窄**）
97. ⬜ 崩溃能发生在任意点，万一 user_message 还没写就崩了怎么办？为什么崩溃恢复也走 resume_run？
    （核心：**恢复不问"崩在哪行"，只问"事实源现在长什么样"**——事件溯源不需枚举崩溃点，只需
    保证事实源每个可能状态都有确定恢复动作。首跑时序=T1(idle→running)→acquire 租约→open→
    assemble→loop 第一件事 append user_message（恒首事件 I5/D19）。三窗口：①**T1 之前崩**
    （run_state 仍 idle）→ reaper 扫描条件是 running，**根本不认领**→ 会话干净如初，用户重发=
    全新首跑，不碰 resume_run；②**T1 后、user_message 前崩**（running 但零事件）→ reaper 认领
    → _recover_locked 读到零事件 `if not rows: raise ValueError` → reaper 批内隔离 → 反复 steal
    使 recovery_count 涨 → 超限 C9 判 failed。**安全但非最优**（一个零副作用的 run 被判死；更优
    雅是读零事件时 running→idle 让其可重跑——已知边界，M4.0 候选）；③**user_message 后崩**
    → 四支分诊 → resume_run 续跑（真正的恢复场景）。为什么走 resume_run:**user_message 落盘=
    run 有了"事实基础"**,恢复=从事实基础续跑,而 resume_run 的定义就是"从已有事实续跑"(不重写
    user_message/不过守卫/working 从事件流重建),与 run 唯一差别是进场方式,进场后共用 _main_loop。
    最深一层:**user_message 之前没有任何副作用**（未调 LLM 未执行工具）——write-ahead 的"副作用
    前先有事实"使这个窗口成为恢复的**免费区**：怎么处理都不会重复/遗漏副作用。user_message 恒首
    事件的设计价值=让"有没有它"成为"run 是否真正开始"的清晰判据）
98. ⬜ resume_run 不过入口守卫，若崩溃恰在 append user_message 之后、check_input 之前，恢复时
    这条输入不就绕过了守卫？（先澄清：check_input **不会"验证失败"**——分类器挂了它 fail-open
    返 verdict 不抛（C34），"没检查"只可能来自**崩溃**卡在 loop.py:214-218 之间，窗口极窄
    （append 提交后、本地正则扫描前，无外部慢 await）。质疑精确成立：此窗口事件流只有
    user_message、无 guardrail_triggered，崩溃分诊走 c/d 支→resume_run→直接进 LLM 调用，
    resume_run 注释"历史输入挂起前已检"对本窗口是**假的**（审批恢复场景才真——那里 run() 开头
    检过）。**但仍安全，因入口守卫不是安全边界**（站9核心立场）：它只做 HIGH 拒答（省一次 LLM）
    + MEDIUM 打标（加 SUSPICION_NOTICE），绕过=概率防护降一层；真墙全在后面且都在——权限系统
    （ctx 身份注入模型不可控）、RLS+归属校验（跨租户/他人数据拿不到）、HITL 风险闸门（危险写
    仍要审批）、OutputGuard（系统提示/工具名/PII 不外泄）。纵深防御=绕过第一层概率闸不构成
    洞穿。为何 resume_run 不补检：共用入口，审批恢复场景重检纯浪费+会重复写 guardrail_triggered
    事件（污染事件流/威胁逐事件一致）；守卫确定性、非边界，不值为极窄窗口加复杂度。定性：**非
    安全缺陷（纵深防御兜住），是注释理由不覆盖全场景的精确性问题**——若要"所有进 LLM 的新输入
    都过守卫"更强不变量，崩溃恢复可补检，低优先级 M4.0 候选）
99. ⬜ AgentLoop 为什么不持有 session_id 字段、每次从 self._events 读？（事实：loop 6 处
    session_id 全走 self._events.session_id，__init__ 无 session_id 参数——_Tap.session_id
    property 转发 writer，EventWriter 是权威源。三层理由：①**单一事实源**——session_id 是
    事件的固有属性（每条事件盖 session_id/run_id，是 writer 落盘时写的），其天然拥有者就是
    writer；loop 自存=同一事实两份拷贝，读者要问"这俩一定相等吗、谁权威"；②**杜绝跨会话
    错配灾难**——6 个消费点（LLMRequest 回放匹配键/approvals.create/T2/T4 transition）全要
    和"writer 正在写的那个会话"对齐；从 writer 读，物理上不可能"事件写到会话 A、状态翻转
    作用到会话 B"；③**共用 _Tap 的三组件天然同源**——loop/executor/builder 共享同一 _Tap，
    都从同一 writer 读身份，"同 run 内各组件看到同一 session_id/run_id"免证成立，不靠组装时
    多点传参正确。**对照 tenant_id 为何自持**（self._tenant_id）：tenant_id **不是** writer 的
    属性（events 表无 tenant_id 列，它在 sessions/approvals），writer 给不了，loop 只能自持。
    深化题96：**身份类属性的持有判据不是"它是不是身份"，而是"谁是这个身份的权威源"——已被
    某协作者权威持有的（session_id/run_id←writer）就从它读，无权威源的（tenant_id）才自持**）
100. ⬜ tenant_id 为什么不进 events 事实源？（事实：events/messages/tool_invocations 无
    tenant_id 列，sessions/approvals/usage_ledger 有。核心：**tenant_id 是 session 的属性、
    不是 event 的属性**——一个会话从生到死属于同一租户（session_id→tenant_id 是不可变函数
    映射），events 每条已带 session_id，tenant_id 可 JOIN sessions 推导得到=冗余。规范化 vs
    去规范化的判据是**访问模式 + 写频**：①events=运行时事实流，访问总在会话上下文（writer 绑
    一会话、恢复/回放读一会话——已有 session_id，需 tenant 时 JOIN 一次），且**高频 append**
    （每步一条，冗余列有写放大）→ 规范化不冗余；②usage_ledger=计费聚合，"按租户/天聚合成本"
    若每次 JOIN 海量账单是性能灾难 → 去规范化冗余换查询性能；③approvals=安全校验自包含
    （M3.9 operator.tenant_id==approval.tenant_id 防跨租户审批，安全校验少依赖 JOIN 更稳）→
    冗余。**判据一句话：可推导的值默认不存（规范化），当"推导代价（JOIN 性能/安全依赖）>
    冗余代价（写放大/漂移风险）"时才去规范化**。writer 不管 tenant_id=events 表设计上无此列=
    规范化决策的结果，tenant_id 权威源是 sessions。呼应题99：**同一"单一事实源/不存可推导值"
    原则，内存层（loop 不自存 session_id←writer）与数据库层（events 不存 tenant_id←sessions）
    各体现一次**。代价面（诚实）：events 无 tenant_id 使其 RLS 隔离要走 session_id 子查询而非
    直接 USING(tenant_id=…)，M3.3 落地——规范化不免费，省写放大换 RLS 多一跳）
101. ⬜ RAG 服务/数据库异常怎么处理？loop 为什么一部分 catch 一部分不 catch？（**异常处理
    按性质分层落在最有资格处置它的那一层，不集中在 loop**——三类去向：①**能编码成结局的**
    （工具业务失败/注入命中）→ 不抛，编码成值（ToolOutcome 五结局/EntryVerdict），executor/
    guardrails 内部消化；②**增强层可降级失败**（辅助 LLM/检索/摘要）→ **产生地** fail-open+
    留痕（C34），如 context.summarize 的 try 只包 summarize 一行、executor._shrink 摘要钩子挂
    走硬截断；③**基础设施失败**（事实源不可用/围栏）→ **裸穿终止 run**，不在 loop catch，归
    runtime/reaper。loop 的 except 只罩 _llm_step 那一次网关调用（三组六类），因为网关是它直接
    调用且失败语义明确、它能给有意义响应（映射终止/半截重发）；事实源异常它给不了有意义处置
    （该终止整个 run）故裸穿。**问1 RAG**：期望=增强层 fail-open（检索挂→这轮不带检索、宁可
    答得粗，M3.5"检索失败走兜底宁可说不知道"）；**当前实装无 try**（context.py:172/181
    memory.fetch/retrieval.search 裸调用），异常裸穿 build→终止 run——M2 恒 None 无行为差异，
    **缺陷候选①，M3.5 接 RAG 必补 fail-open（形如 summarize 的 try）**。**问2 DB**：写事件
    (append)=三岔口（瞬态 Operational/Interface/OSError 退避3次→EventStoreUnavailable 裸穿/
    围栏→Fenced 自毁/bug→裸抛）已实装；**读查询/CAS**（_load_turns/_summary_state/transition/
    decide）**无 try 无退避**，失败裸穿终止（事实源不可用=服务不可用，同哲学）。**不对称**：写
    有退避（瞬态抖动不杀 run）、读/CAS 无退避——可讨论的简化（M2 读失败罕见；哲学上若写值得
    退避、读同样瞬态也可论证值得，M3 生产化可给读加退避），非缺陷（裸穿安全不写坏）。收束：
    **loop 只处理"它直接调用且能有意义响应"的异常，其余按性质在别处 fail-open 或裸穿终止——
    这不是遗漏，是异常落在最有资格的层**）
103. ⬜ JWT 双密钥窗为什么"先 current、仅签名不符才试 previous"？空钥/弱钥为什么抛 ValueError
    而不是回 401？（①轮换语义：previous 只为救"旧钥签的在途票"，而过期/格式坏换哪把钥匙都救不
    回来——白试只添延迟与混淆；②失败分家：401=客户端 token 问题、ValueError=服务端配置 bug
    fail-loud——错配混进 401 会让运维在 401 海里找不到真凶（与 openai_compat 空 key 快速失败同
    哲学）；③弱钥 <32B 违 RFC 7518 §3.2 MUST，PyJWT 只发 InsecureKeyLengthWarning——按"配置
    错误启动时炸"升硬错误；实录：M3.1② 交付稿测试密钥 19B 触 22 条告警才补此闸，教训=安全参数
    按规范下限起步；④alg 混淆防线：decode 显式 algorithms=["HS256"]+require 四 claim 清单——
    none 票/缺 exp 永不过期票进不了门。锚：api/auth.py、tests/api/test_auth.py）
104. ⬜ tenants/users 为什么落 core 不落 apps？tenancy.py 为什么又声明一遍 SessionFactory 而不
    import store.py 现成的？（①D1 唯一解：认证(api)/预算闸门(gateway)/AgentSpec 装配(apps) 三
    消费方都要读租户，层契约 api|workers→apps→runtime→gateway→core 下三者共同可达的层只有
    core——不是偏好是层代数；②SessionFactory 是结构型别名（零参可调用返 AsyncSession），core
    向上 import runtime 即分层违约——结构类型只认形状，重复声明是分层的正确代价；③为什么不把
    别名下沉 db.py 两边共用：动 store.py=触"M3 对 L2 零修改"红线，一行结构别名无行为可漂移，
    复杂度/收益倒挂——"值得一个显式重构提案"与"不值得触冻结面"的边界案例。锚：core/tenancy.py:24-26）
105. ⬜ 预算闸门切表后的"三态"各是什么语义？budget≤0 为什么连账本 SUM 都不打？（①resolver 在场
    即预算事实源（#13：解释权整体移交 tenants 表，静态 Settings 值退役为遗产参数）；②三态：
    resolver 值 / 静态配置（resolver=None，行为与 M2.4 逐字节一致——**由既有预算测试零改动全绿
    作证**，"老测试群当不变量证据"本身是手法考点）/ None=读挂 fail-open 跳闸门（与账本读挂同
    路：成本护栏不是安全边界）；None≠0——0 是"该租户显式无预算限制"，混淆会把"表抖了"当"不限
    额"；③≤0 短路免打全月 SUM（#22 热路径关怀）；④TenantDirectory 60s TTL 只缓存命中不缓存
    miss——负缓存会让刚种子的租户在 TTL 窗内被 401/403 误伤。锚：router.py
    _resolve_monthly_budget、tests/gateway/test_router.py resolver 四测）
106. ⬜ mypy 为什么拒绝把 dict[str, str] 赋给 dict[str, object]？Mapping 为什么能救？（①不变性
    invariance：可变容器读写双向——若允许协变，持 dict[str, object] 引用的一方可合法塞 int，
    砸掉 dict[str, str] 持有方的类型假设；②实录（M3.1① seed_demo 交付稿缺陷）：TENANTS 值混
    str/dict/int 推断 dict[str, object]、USERS 全 str 推断 dict[str, str]，同函数两个 for 复用
    变量名 row 相撞；③修法对比：显式 list[dict[str, Any]] 注解根治推断分歧，给循环变量改名只是
    躲过这一次（日后加非 str 字段推断又漂）；④Mapping 只读故值协变——仓库
    AgentSpec.tenant_config: Mapping[str, Any] 用 Mapping 是同一条理。教训：异构 dict 常量必须
    显式注解，不赖推断。）
107. ⬜ /v1/usage 的金额为什么以字符串出线？operator 点名他租为什么 403 而不是静默改写成本租户？
    （①FastAPI 按返回注解 dict[str, Any] 建 response_model → 走 pydantic v2 序列化 → Decimal
    缺省编码为**精确小数字符串**——"钱不过 float"（metering.py 账本口径）自然延伸到线上表示，
    下游 Decimal(str) 解析无损；对照：fastapi.encoders 直通路径的 decimal_encoder 才是 float
    ——交付稿曾按后者答错，测试红了才纠正（题面本身即"框架序列化路径分岔"考点）；②403 vs 静默
    强制过滤：静默改写会在审计日志留下"请求 tenant-b 返回 tenant-a 数据"的错乱记录，显式拒绝
    口径干净——正是对抗④"跨租户审批 403"同款语义在读端点的预演。锚：api/usage.py、
    tests/api/test_usage.py）
108. ⬜ `from __future__ import annotations` 是什么？它怎么把 /v1/chat 打成全量 422 的？
    Python 3.14 的 PEP 649 为什么能终结这类坑？（①三形态：默认=def 时求值存**实物**（名字须
    当场存在，前向引用/TYPE_CHECKING 断环全炸——仓库 loop.py 的 TYPE_CHECKING import GatewayLike
    正靠 future 模式才成立）；PEP 563=存**字符串便签**，运行时消费者（FastAPI/pydantic）用
    get_type_hints 还原，查找范围只有**模块全局**；PEP 649（3.14 默认）=编译成隐藏 `__annotate__`
    嵌套函数惰性求值，**闭包天然可见**——时机与地点都对。②事故机制（M3.2 实录）：rate_limited
    依赖工厂的内层 `Annotated[Principal, Depends(role_dep)]`，role_dep 是闭包参数、便签还原查
    无此人 → FastAPI 把参数退化成**必填 query** → 全量 422（loc=["query","principal"] 一眼定案，
    探针脚本打 detail 是排查关键一步）；auth.py 同构写法没炸只因 current_principal 恰是模块
    全局名。③修=该文件弃 future import（注解回 def 时求值捕获闭包）+注释说明；升 3.14 后全仓
    删 future import 连注释一起退役（00 §10.1 #45）。④口诀：只有 mypy 看的注解便签随便贴——
    mypy 读源码不读运行时，这类 bug 它抓不到；运行时框架要读的注解，名字必须模块全局可查。
    锚：api/ratelimit.py 头注、scratch 探针实录、00 #45）
109. ⬜ rate_limited 为什么是 def 而它返回的 dependency 是 async def？current_principal 体内
    零 await 为什么也 async def？（①总原则：**async def 标注的是函数体执行期间需要等待**，
    不是"与异步有关"；调用 async def ≠ 执行——只造协程凭证，await 才兑现函数体。②工厂必须
    def：rate_limited 体内纯装配零等待，且 `_ADMITTED = rate_limited(...)` 跑在 **import 期**
    ——彼时无事件循环、无人能 await；若 async def，FastAPI 拿到的是协程对象不是依赖函数。
    仓库同款：runtime._make_summarizer / auth.require_roles（工厂 def、产品 async def）。
    ③内层有 `await limiter.try_take`（生产=Redis IO）→ 硬语法必须 async def。
    ④current_principal 零 await 仍选 async def 是 **FastAPI 调度规则**下的优化：普通 def
    依赖被框架防御性丢**线程池**执行（它不敢赌你体内无阻塞），微秒级纯 CPU 白付线程切换；
    async def 直跑事件循环。三类口诀：有 await→async def；零 await 纯 CPU→FastAPI 里选
    async def 免线程池；零 await 但有**阻塞**调用（同步 requests/time.sleep/同步 DB 驱动）
    →必须 def 进线程池——写成 async def 会卡死整个事件循环（三类里唯一致命错法）。
    ⑤与题 13 连成一族（判据=调用那一刻拿到什么 + 函数体执行时等不等）：def→结果 /
    async def→凭证 / def→AsyncGenerator 流（GatewayLike.complete）/ def 工厂→async 工具
    （本题）。锚：api/ratelimit.py、api/auth.py、runtime.py:76 _make_summarizer）
110. ⬜ post_chat 做了限流、L1 网关又做限流——为什么两次？（**两本账数的不是同一种东西**：
    入站 `inbound:{tid}` 数**用户消息**（HTTP 请求，门口扣 1）；出站 `tenant:{tid}`/
    `provider:{p}` 数**上游 LLM 调用**（每次真调用扣 1）。二者比例不可预知也不可互推——
    三比例实证：①工具多轮 run：入站 1 : 出站 N（主循环×轮数+摘要道+分类道，一条消息合法
    放大成十次上游调用）；②缓存命中/FAQ 直答：入站 1 : 出站 **0**（router 缓存在一切闸门
    之前）；③reaper 恢复续跑：入站 **0** : 出站 N（根本没有 HTTP 请求，只有出站门管得到）。
    保护对象不同：入站保**自己**（连接/线程/DB/锁——在花一分钱、碰一条连接前把刷子挡在门外，
    "被拒的请求不该消耗资源"）；出站保**供应商配额与钱包**（合法请求的内部放大流量）。行为
    因此不同：入站即问即答 max_wait=0+Retry-After（门口排队占住 HTTP worker）；出站可短排队
    max_wait=10（请求已在处理中，平滑突发优于失败）。只留一道的反证：只有入站→loop 放大与
    恢复路径的上游流量失控；只有出站→刷子走完认证/建行/取锁/build 才被拦，自己先被打穿。
    分层佐证：L1 眼里没有"HTTP 请求"概念、api 层不知道 loop 会打几次——各守各门是分层的
    自然结果。机制复用账本分立：同一把 Lua 令牌桶（D6），三个 scope 三本账。类比：小区大门
    管访客频次，高速收费站管车流量——一次来访可能上多次高速，也可能不出门。锚：02 §1、
    api/ratelimit.py、gateway/router.py 缓存与限流段）
111. ⬜ RLS 是什么？它生效需要哪三件事？它替代 WHERE 吗？（①定义：PG 内置的表级自动过滤器
    ——装策略后**数据库自己**给每条打到该表的查询追加过滤，忘写 WHERE 的查询、注入进来的
    恶意 SQL 同样被拦（过滤在库内，绕不过）。②三件套（恰对应 M3.3① 三交付物）：表上有策略
    （手写迁移 CREATE POLICY——USING 管能看什么/WITH CHECK 管能写什么，缺一半扇门）+
    每事务报身份（tenant_ctx：ContextVar 每任务独立副本 → "begin" 钩子 set_config 第三参
    true=事务级，连接归池不残留——探针实证；未设=空串比对不中=fail-closed 空集）+ 查询者
    无后门（低权 aegis_app 无 BYPASSRLS——owner/超管天生绕过，"低权角色不建、兜底防线等于
    没有"）。③定位：**不替代 WHERE**——应用层 WHERE 是第一防线（快、意图明确），RLS 是
    安全带（防某处忘了/被绕过）；验收即防线定义："绕过 Repository 的裸 SQL、未设上下文 →
    空集"。④为什么必须 LOCAL/事务级：连接池复用，会话级 SET 会把 A 的租户寄生在连接上带给
    下个借走连接的 B（00 §7.2 面试考点原题）。锚：core/tenant_ctx.py、迁移 c895f9007bf7、
    tests/test_rls.py）
112. ⬜ 为什么要 owner 双轨引擎？平台维护为什么不"冒充租户"？（①RLS 后应用身份=aegis_app
    逐事务过滤，但一类工作天生跨租户：reaper 扫全库过期租约（app 身份+无上下文=空集=
    **reaper 瞎了**，崩溃恢复整体失效）、种子一次建两租户、mint_token 在任何上下文之前查人、
    对账聚合、alembic 要 DDL 权（aegis_app 只有 DML）。②维护面定性（D4）：平台自己不是租户
    ——reaper 救 A 的会话不是"冒充 A"而是操作系统做例行维护，伪造上下文既不诚实也不可行
    （伪造哪个？）。③为什么必须两个引擎而非一个引擎切模式：**权限属于连接的登录身份**，
    aegis_app 无法自我升级——能升级则 RLS 是纸糊的；两条连接串→两个池→钩子只挂 app 轨。
    类比：店员门禁卡（刷卡先报店号）vs 物业总钥匙（查全楼但不冒充任何店）——两种权限做不进
    同一张"按需变身"的卡。④consumers 名单：reaper 自建 owner 引擎（M2.10 起天然合规）、
    seed/mint 显式切 owner（M3.3②）、alembic env 读 database_url。锚：core/db.py 双轨、
    scripts/seed_demo.py、00 §10.1 #18）
113. ⬜ M3.3 两发探针各抓出什么？"伪码照抄必翻车"在本步的两个实例？（①探针一：计划 D2 伪码
    `exec_driver_sql("... %s ...")` 在 asyncpg 方言**语法错误**——exec_driver_sql 原样透传
    给驱动，asyncpg 只认 $n；正解=`text(":tid")` 具名绑定走 SQLAlchemy 编译层（方言无关）。
    同一发探针还证实 set_config 第三参 true 的事务级语义：事务结束值蒸发、连接归池不残留
    （"为什么必须 LOCAL"的机制版证据）。②实例二：02 §7.2 规划文本的策略样例带 `::uuid`，
    而实装租户 id 是 String(64) 形如 tenant-a——照抄运行期即 invalid input syntax（U1，
    M3.0 已预警、D2 落地 text 比较）。③方法论：**计划/设计文档里的代码片段是缝蓝图不是事实
    ——写任何"框架边界上的"语句（参数风格/序列化/事件时机）前，2 分钟探针比 20 分钟推演可靠**；
    与 M3.1④ Decimal 序列化、M3.2 future-annotations 同族（框架行为三连课，全部探针/测试
    实证定案）。附带一课（⒂）：测试断言的"粒度前提"也要对实况——usage 单会话跑四查询，
    断言"四次开会话"被真实行为纠正。锚：scratch 探针实录、plans/m3-detailed #14c ⑿⒂）
114. ⬜ tenant_context 的 reset 有什么用——反正每次请求都会 set 新值？（先承认：就 get_usage
    当前函数体，裸 set 也跑对（查完即返回、任务死上下文陪葬）——reset 买的不是今天这条路径，
    是**原语对所有调用点的组合安全**。①"借用必须归还"：with 块后同任务的后续代码要回到
    本色身份——审计写入（M4.1）、**SSE 流式期（M3.10：endpoint 返回后生成器仍在同一任务
    继续跑）**、Celery 任务体内的子步骤（M3.4 嵌套第一现场）；裸 set 让借来的身份静默延续
    到块外，查询"都对"但后续写入落错租户域——不可见 bug 的经典形态。②嵌套安全：
    reset(token) 精确还原**上一个状态**（含"未设"态），内层借用绝不毁外层——原语若靠
    "没人嵌套"才正确，就是隐形耦合。③两个成对惯用法（判据=值该活多久）：**本色身份**
    （current_principal）=裸 set，任务生命周期陪葬；**借用身份**（tenant_context）=with
    成对，代码块生命周期归还。④诚实边界：任务陪葬论证依赖宿主行为——生产 uvicorn 每请求
    新任务 ✓，但测试 ASGITransport 在**调用方任务内**跑 app、多请求共享一个任务，裸 set
    会跨请求残留（authed 端点每次重设自愈故今日无害）；**with 归还不依赖任何宿主假设**——
    两者中更硬的那个。锚：core/tenant_ctx.py、api/auth.py vs api/usage.py 对照）
115. ⬜ ContextVar 什么时候"绑定到请求"？生命周期是什么？（三分体：**ContextVar=槽位定义**
    （tenant_ctx.py import 期创建，进程级永生，本身不存请求值）；**Context=一张绑定表**
    （{槽位→值} 映射）；值活在表里、表跟着任务走。绑定时刻拆两步：①**容器时刻**=uvicorn 为
    该请求 create_task 那一瞬——asyncio.Task 创建时 copy_context() **快照复制**创建者的表，
    此后该任务的每一步都在这份私有表内执行（表里租户尚为 None）；②**写值时刻**=同任务内
    current_principal 验签后 .set()——只改自己那份表。派生规则：任务内再 create_task（如
    _pump_with_lease 心跳）→ 子任务**在创建瞬间快照复制**当时的表——之后父子各写各的、
    互不传播（是复印不是共享）。死亡：任务结束→表无人引用→GC，值随之蒸发（"任务陪葬"的
    机制版）。四级生命周期阶梯：**槽位=进程级 ⊇ 绑定表=任务/请求级 ⊇ with 借用=代码块级 ⊇
    set_config=DB 事务级**（最后一级在 PG 世界，由 begin 钩子逐事务桥接——钩子在任务的执行
    步内同步跑，天然读同一份表，/ctx 测试与录音工厂实证）。类比：槽位=表格上的栏位定义；
    每个任务进场领一张**复印表**；set=在自己表上填字；create_task=把当前表复印给新员工；
    散会表格进碎纸机。锚：core/tenant_ctx.py:23、api/auth.py、runtime.py _pump_with_lease）
116. ⬜ JWT"密钥存在 Bearer 头里"没事吗？（概念纠偏：Bearer 里是 **token（票）不是 secret
    （钢印机）**——token=header.payload.signature 三段 base64url；签名由 HMAC(前两段, secret)
    算出但**不包含** secret（单向）；secret 只活在服务端 .env→SecretStr，线上永不传输。
    ①JWT 给的是**完整性/真实性不是机密性**：payload 只是 base64 编码**不是加密**——任何
    持票人都能解读 sub/tid/role（一行 python 可自证），所以 claims 只放非机密标识、绝不放
    secrets；篡改 payload 会使签名失配→InvalidSignatureError→401（test_bad_signature 钉死）；
    没有 32B secret 无法伪造有效签名。②但 **token 本身是凭证**（bearer=持票人：谁拿着谁就是）
    ——保护责任转移到：传输 TLS（生产，M5.3 部署面；本地 dev 明文可接受）、放 header 不放
    URL（query 会进日志）、不打日志、**短 TTL 界定失窃损失**（2h/8h 正是为此）。③诚实边界：
    无状态 JWT v1 **不可单票吊销**——泄露只能等过期或轮换 secret（双密钥窗轮换=废掉旧钥
    全部在途票，是核选项不是手术刀）；单票吊销需服务端黑名单=引入状态，v2 取舍。类比：
    演唱会门票（防伪花纹=签名/票面人人可读/持票即入场/有场次时效）vs 后台钢印机（永不
    出后台）。锚：api/auth.py、题 103）

<!-- —— M3.4 摄取流水线（2026-07-24 收口追加，117–123）—— -->

117. ⬜ embedding 为什么是独立的 EmbeddingClient，而不是给 LLMGateway 加个 embed() 方法？
    （D5 裁决三层：①**语义面不重合**——embedding 无档位路由/无流式/无缓存/无熔断语义，塞进
    LLMGateway 会污染 LLMChunk 判别联合契约（"返回向量的 complete"是什么 chunk？）；②**共享
    的只有三样**且各有单一事实源：状态码翻译表 raise_for_status（防两份表漂移）、共享 HTTP
    客户端、计量账本（新方法 record_embedding，tier="embedding" 是自由字符串——Tier 是 chat
    档位契约禁扩枚举）；③**重试口径相反而尺子相同**：chat 只许首块前重试（半截不换路），
    embedding 非流式读语义幂等、整调用可重试——但白名单 RETRYABLE_ERRORS 与退避公式
    compute_backoff 复用 resilience 同一把尺。追问"何时该合"：出现第三个通道（rerank/多模态）
    时抽 BaseChannel，两个样本先忍受轻微重复。锚：gateway/embeddings.py、plans 14d D5）
118. ⬜ 断点续传为什么不需要进度表？崩溃在任意一步会发生什么？
    （核心：**IS NULL 谓词即进度**——embedding 列可空（①的表设计）承担了状态机职责：NULL=待
    回填、非 NULL=已完成，回填循环 `WHERE embedding IS NULL ORDER BY seq LIMIT batch` 每批
    独立事务提交。逐窗口推演：崩在切块前=重试从头（幂等：count==0 才切+UNIQUE(document_id,seq)
    兜并发重复）；崩在第 N 批后=前 N 批已提交、重试自然从 N+1 批续（谓词天然出队）；崩在 DONE
    前=全部已回填、重试零 embed 调用直落 DONE（no-op 幂等有测试）。对比显式进度表的失效模式：
    进度行与数据行两处事实源，崩在"数据已写进度未更"的缝上就双写或漏写——谓词方案让数据自己
    就是进度，缝不存在。代价：无法表达"第 3 块失败过 5 次"这类细粒度诊断（v1 接受，Celery 任务
    级重试兜）。锚：workers/ingest.py ingest_once、tests/workers/test_ingest_resume.py）
119. ⬜ api 和 workers 互不 import（层契约 |），API 怎么把任务投给 Celery？
    （wire 契约三件套（决策 A）：①**任务名常量放共同下层**——INGEST_TASK_NAME 落 apps/support/
    rag/ingest.py，api 与 workers 都在 apps 之上、都能 import，消灭双份字符串；②api 侧**只发
    不收的轻量 producer**——celery.Celery(broker=...) 是三方库对象不是 aegis.workers 代码，
    send_task 按名投递不需要任务代码在场（名字就是契约，如 HTTP 路径之于客户端）；③**两端一致性
    进 CI**——测试同时断言"常量==注册名"与"模块在 include 里"（include 是 worker 装载任务的唯一
    链接点，漏改=部署哑火而测试全绿）。对照 `.delay()`：它要 import 任务函数=api→workers 依赖边，
    计划伪码在五层化后作废（偏差 14d A）。追问：消息丢了怎么办——行先落库（PENDING），broker 挂
    =503 诚实降级+行可重投（ADR-005 角色4；outbox 归 v2）。锚：api/kb.py build_enqueue、
    tests/workers/test_ingest_resume.py test_task_name_wired_on_both_ends）
120. ⬜ 讲一个"注释在说谎"的真实缺陷：split_text 的越界块是怎么漏进来又怎么被抓住的？
    （缺陷解剖：主循环里"种子+新段装不下就丢种子"写成了 `elif`——而 flush() 总与同轮 append
    连续执行，任何一轮开始时"buf 非空∧fresh==0"不可能成立，elif 分支是**结构性死码**；后果：
    flush 后同轮把新段 append 进种子，块可达 target+overlap（反例 30+380/400/50 → 410 token），
    注释"绝不产出超预算块"为假。抓法：两路独立校验（一路结构归纳证明分支不可达、一路影子库
    实跑反例）撞出同一条；修复一词 elif→if（flush 后 fresh==0，第二个 if 变成对"种子+新段"的
    重新验算），回归测试 test_overlap_seed_never_busts_budget 钉死。方法论：**不变量注释必须有
    测试作证**——no branch coverage 也照不出死分支，"写了防线"和"防线可达"是两件事。锚：
    apps/support/rag/ingest.py split_text、tests/apps/test_ingest_split.py）
121. ⬜ Celery 任务里为什么 DB 引擎、HTTP 客户端、租户上下文三件都要"任务局部"？
    （根因一个：**任务壳每次 asyncio.run 新建 event loop**，而三种资源都有 loop/任务亲和性——
    ①asyncpg 连接绑创建时的 loop，复用全局 get_engine() 池=下个任务炸 "attached to a different
    loop"（reaper 3.2#8 先例，NullPool 任务局部引擎）；②httpx keep-alive 连接同理，shared_client
    单例在 worker 里隔次任务交替炸裸 RuntimeError('Event loop is closed')——且非 httpx 异常、
    绕过翻译阶梯（②校验 major，真 HTTP 探针实证；修=build_embedding_client 双参数化）；
    ③ContextVar 值活在任务的绑定表里，tenant_context 必须在任务体内设（#18）——否则 RLS 写路径
    被拒、计量 INSERT 被 WITH CHECK 拒再被 fail-open 吞成静默丢账。ingest 与 reaper 的对照：
    同为任务局部引擎，ingest 连 **app 角色+guard**（逐租户任务冒充租户过 RLS）、reaper 连
    owner（维护面跨租户扫描，D4 对偶）。锚：workers/ingest.py _ingest_fresh、workers/reaper.py）
122. ⬜ embedding 用量该计入租户月度预算吗（拍板 F）？正反方都说一遍。
    （现行口径=**计入**：month_spend 的 SUM 只滤 cached=False 不分 tier，record_embedding 行
    天然入账。正方：预算是成本闸门，"管的是真实花销"（month_spend docstring 原文）——摄取
    100 万 token 就是真花了钱，预算闸门本该看见；ADR-006 也明言 embedding 过网关计量；实现
    零改动。反方：embedding 单价比 chat 低两个数量级，大规模摄取会挤占对话额度、租户体感
    "上传文档把客服聊天额度吃光了"——若要拆，改法是 month_spend 加 tier!='embedding' 过滤
    +独立摄取预算（成本：两个预算面、两处对账）。裁决依据：v1 演示量级（万级 chunk≈几百万
    token embedding ≈ 几毛钱）不构成挤占，"一个预算管所有真实花销"的简单性赢；量级变了再拆
    ——这是有升级路径的取舍不是终局。锚：gateway/metering.py month_spend/record_embedding、
    plans 14d (21)）
123. ⬜ 上传文档的原文存哪？四个方案怎么排除三个（拍板 G/偏差23）？
    （问题成立的前提是计划内在矛盾：任务 wire 签名两次钉死只带 (document_id, tenant_id) ×
    API 行为"落 documents(PENDING)、chunks 不动" × P6 表设计无原文列 → worker 拿不到原文。
    四方案：①**documents 加 text 列（采纳）**——文档级事实归 documents 列（P6 口径自洽）、
    任务凭 id 自足、崩溃任意点可凭库重跑、可 \d 审计；②meta JSONB 塞原文（否决：违背"文档级
    事实归列"、JSONB 整值重写、不可审计——meta 的契约是"平台不解释"不是"什么都能塞"）；
    ③Celery 消息携带原文（否决：比加列更大的计划偏离——直接破 wire 签名；原文进 Redis 内存；
    **消息丢=原文永久丢，断点续传在切块前就断了**——与 ADR-006 承诺冲突）；④API 侧切块
    （否决：违反 00 §7.1"切块归 worker"与 02 §6"慢活不进事件循环"两条上位口径，且幂等逻辑
    整段作废）。方法论：**修计划矛盾选"同时满足全部已钉死约束的最小增量"**，而不是挑一条
    约束去松。锚：migrations c28efda87e6a、plans 14d (23)）
124. ⬜ ContextVar 的"当前上下文"到底跟着谁走？三种摆位各画一遍泄漏范围。
    （核心机制：Task 创建时 copy_context()——**set 执行那一刻你在不在 Task 里，决定改的是
    哪份 context**。三形态探针实证（M3.5 scratchpad）：①协程内 set（ingest 内胆现行摆位）
    →改的是任务拷贝，asyncio.run 返回即弃，reset 冗余但无害；②同步壳 set（计划稿"任务体
    首行"的合理变体）→改的是 worker **线程**的基础 context，run 返回后仍在；③--pool=solo
    单线程顺序吃任务→②不 reset 时上一单租户漏进下一单，guard 注入的不是空串而是错租户
    ——RLS 全过、只是过成了别人=**静默串租**，且泄漏黏性（下游成对 reset 只能还原到已脏
    基线）。结论：原语 set/reset 成对写死（tenant_context CM），调用点免背"我这个摆位要不要
    还"的证明义务=摆位无关性；auth 裸 set 是边界语义（任务级生灭+下一请求必覆写自愈），
    usage 的 with 是嵌套借用语义（借了必须还——M4 响应期中间件是排期中的读者）。附刺：
    测试的 ASGITransport 直接 await app、连续请求共享任务 context——"一请求一任务"是部署
    形态不是语言保证。锚：core/tenant_ctx.py、workers/ingest.py:162、api/auth.py）
125. ⬜ RetrievalProvider 为什么不许在 search 里自己 tenant_context(tenant_id)？这跟 #42 的
    fail-open 又是什么关系？
    （两问一体=交付③的两个边界决定。自冒充问题：RLS 第二防线的价值在"**环境身份（认证边界
    建立）× 参数租户（调用方声称）**"交叉核验——装配 bug 把 B 的 tenant_id 传进 A 会话时，
    不自包=USING∩WHERE 空集、泄漏不发生、bug 以检索失败形态可见；自包=环境被改写成 B、
    B 语料进 A 对话=对抗①泄漏方向被亲手短路（AI 交付稿真犯过、用户评审揪出撤修——偏差(32)）。
    写侧同构：计量 _record 若自包，WITH CHECK 从"拒错账+告警"退化成恒真橡皮图章=静默串租
    记账。全仓身份宣告封闭名单四处：auth 验签/任务内胆/脚本 main/usage 特批（403 后显式借用）。
    fail-open 归属：吞错位置决定谁看得见真相——域对象 Retriever fail-loud（评测/演示要诚实
    异常），适配器在 L2 边界 except→() 留痕续跑（C34：检索是增强层，抖动不杀 run=#42 修案 a，
    L2 零改动）。锚：retrieve.py RetrievalProvider、00 §10.1 #42、tests test_provider_fail_open_*）
126. ⬜ pgvector 带 WHERE 的召回怎么保证（两层表述）？再补两个实测细节：float32 与
    距离/相似度。
    （两层表述背熟：**越权隔离=硬保证**（显式 WHERE tenant_id 第一防线+RLS 兜底，绝不"反正
    有 RLS"）；**召回完整性=质量保证**（HNSW 是先近邻后过滤——索引内后过滤，WHERE 淘汰
    候选后命中不足=漏召回，不是漏隔离）。两开关：小租户 `SET LOCAL enable_indexscan=off`
    精确扫（万级全扫既正确又够快——租户规模设定使"备选即主选"合法）；大租户
    `hnsw.iterative_scan=relaxed_order` 迭代补扫（pgvector ≥0.8）；SET LOCAL 事务级、必须与
    查询同事务。判定用租户 chunk 计数+60s 进程缓存（错判一档只伤质量微差不伤隔离=可缓存
    判据）。实测细节：①vector 存储是 **float32**——0.6 回读 0.6000000238（~1e-8 噪音），断言
    一律 approx；②`<=>` 返回**余弦距离**（0=同向），相似度=1-距离——拿距离当相似度比阈值
    方向就反了。锚：retrieve.py _SEARCH_SQL/两 SET 常量、ADR-006、scripts/calibrate_*）
127. ⬜ 轻量重排的 0.7/0.3 权重起了什么真实作用？阈值为什么判"整组"而不逐条过滤？
    （权重的战果有实测凭证：查询「优惠券怎么领取」对退货语料 sim=0.4473——任何纯相似度
    阈值（0.35）都会放它过去产生离题引用；关键词覆盖 0 让 score=0.7×0.4473=0.3131 被拒。
    反向能力：字面锚点（R68/单号）相似度略低但覆盖全中时反超语义近邻（0.86>0.63，测试
    钉死）——向量召回偏爱同族近义词、覆盖率把字面命中拉回来（M2.11 录制教训同源）。候选池
    3×top_k 是重排的前提：池只有 top_k 大，反超无从发生。阈值整组判定 all(score<θ)→[]：
    要么这组整体可用、要么整体不可用——逐条过滤剩两条弱相关更误导，空列表让上游走"宁可
    说不知道"。校准口径：分离窗 [0.31,0.45] 含 0.35，1 块语料首测维持、M3.11 扩容复核——
    结论边界如实声明是简历数字纪律的延伸。锚：rerank.py、retrieve.py search 第 5-6 步、
    scripts/calibrate_retrieval_threshold.py docstring）

## M3.6 意图路由（2026-07-25 出题）

128. ⬜ 意图路由为什么用小模型单次调用，而不是让主 Agent 顺手判断？它为什么"不是 Agent"？
    （考点五连第一题（00 §7.2）。三层答：①**成本与延迟**——分诊在每条消息旅程第⑤步
    （02 §2），fast 档单词输出实测 <1s、约 250 token；若让主 Agent 判断=每条消息都先起一整套
    循环（上下文组装/闸门/事件落盘），分诊的价值恰是让 FAQ 这类简单消息**不进**循环（直答
    旅程结束，重复问再叠精确缓存 8ms——实测凭证 measure_intent_latency）；②**确定性边界**——
    ADR-002 决策 2 原文"不是 Agent（无循环、无工具）"：一次调用、绝不重试、输出不可解析不
    追问——一旦允许重试/追问就在向 Agent 滑坡，"便宜且快"的价值消失；③**失败落点**——
    C34/D8：分诊是增强层，挂了→Intent.AGENT 直走主 Agent 标准档（fail-open）——兜底不是
    降级裁决而是"换一条同样正确的路"（主 Agent 本就能处理一切意图），这是它与 build_classifier
    的分野（那边 ValueError 上抛转规则库兜底，这边落点内聚成枚举值）。追问"错分了怎么办"：
    RAG/TOOL/AGENT 三路同入主 Agent（v1 单 Agent 同时具备检索与工具，区分只影响是否预热
    检索——ADR-002 决策 1），错分代价=少一次预热非答错；FAQ 错分分两态：自足问题有 faq_digest
    兜着，**指代上文的跟进问（「一般要多久？」）是上下文盲窗**——四路唯 FAQ/HANDOFF 绕过
    主 Agent，直答拿不到轮 1 语境会用通用条款答非所问（用户 2026-07-25 揪出，14f 后置修订）；
    修=M3.8 接线守卫：FAQ 直答仅会话首条消息生效，有历史判 faq 一律按 AGENT 进主 Agent
    （确定性清零，不靠分类器判自足性；缓存 <50ms 场景=新会话首问，守卫放行不受损）；
    HANDOFF 错分是体验问题非安全问题。锚：apps/support/intent.py、ADR-002、00 §2.2 C34、
    plans §4.6/§4.8 守卫条款）
129. ⬜ _parse_intent 为什么"恰含一词才算数"？宽容解析和严格白名单的边界在哪？
    （对照 build_classifier 的严格白名单（"High."/"高"一律 ValueError）：两边同一哲学——**绝不
    把不可靠输出洗成可靠裁决**，差异只在宽容度与失败落点。意图解析多一层子串救回（"分类：
    faq"/"faq。"归位）是因为失败落点便宜（AGENT=标准档，错杀=多花一次标准档调用）；guard
    分类器不做子串救回是因为裁决进安全面（MEDIUM 打标/HIGH 拒答），子串匹配会把"含 high
    字样的解释长文"洗成 HIGH 误杀良性输入。共同底线：歧义（"faq或rag"两词命中）与零命中
    一律走失败落点——宽容只救**格式**不救**语义**。工程细节：白名单 _INTENT_WORDS 直接引用
    枚举成员，词表与解析同源零漂移面；AGENT 不在其中——它是我们的失败落点不是模型词汇，
    模型幻觉输出"agent"按零命中处理（殊途同归标准档）。锚：intent.py _parse_intent、
    guardrails.py:239-242）

## M3.7 模拟业务与工具五件（2026-07-25 出题）

130. ⬜ 幂等键从哪来、到哪去？"双击不产生两笔退款"的完整链路谁在保证什么？
    （全链五站背熟：①executor write-ahead——tool_call 事件先落盘、**事件 id 即幂等键**（M2.4：
    幂等键=事实源身份不是随机数）；②ctx.tool_call_id 透传（tools.py:40-41 契约，LLM 不可控）；
    ③工具侧 post_write 带 Idempotency-Key 头（§4.7 不变量 2：写工具一律带键，例外会繁殖）；
    ④mock 侧 claim=INSERT ON CONFLICT DO NOTHING、**PK 就是键**——恰一次由唯一索引仲裁，
    不靠应用层锁（并发同键：后到者在唯一索引上等先到者提交→rowcount=0 走回放）；⑤撞键回放
    台账 payload+duplicate:true——同键即同操作，二击金额不同也返首击快照（防模型紊乱参数
    重发）。**单事务化**两红利：崩溃零中间态；校验失败回滚连 claim 一起撤=失败不烧钥匙。
    台账为什么落 PG 不落内存：恢复期"凭幂等键安全重发"（M2.10）要求去重记录跨崩溃存活。
    追问"下游不去重怎么办"：X2 评审点过"下游都去重是无人担保前提"——纵深还有 X1 结果不明
    封重试+高危写走 HITL 收窄两层。锚：executor.py:158-173、_shared.post_write、
    mock_backend/app.py _claim_and_execute、demo_tools_acceptance 幕 B 实录）
131. ⬜ 归属校验为什么在工具体内而不是 risk_policy？为什么三种失败必须同一句话？
    （两道闸门分野（§4.7 陷阱 3）：归属是**权限**——fail-closed 拒绝，判据吃 ctx（运行时注入、
    模型不可控）；risk_policy 是**风险**——放行但要人批，谓词签名 (args, tenant_config) 里
    **没有 ctx**（类型层就写死了它不配做权限判定）。话术纪律：他人订单/跨租户/不存在三路
    **逐字节同一句**"订单不存在或无权操作"——区分"存在但无权"=泄露他人订单号的有效性
    （枚举攻击面），02 §7.2 第 2 层；测试以三路响应相等钉死。纵深四层：mock WHERE tenant→
    RLS→工具 tenant+user 双比对→（M3.9 批准后重校验）；防线归属在工具——mock 交出行、
    判定权不外漂（否则统一话术失去判定原料）。业务拒绝回 dict 不抛异常的理由：拒绝是"成功
    的观察"非工具故障，抛异常进连败账、两次越权就禁用工具反伤合法用户。锚：
    _shared.fetch_owned_order、test_denial_uniform_three_ways、demo 幕 C 实录）
132. ⬜ #43："发出后传输模糊错误"为什么转 TimeoutError 而不是自己造新异常类型？
    （问题本体（复盘题 89 灰区坐实）：X1 只把 TimeoutError 判"结果不明"；连接重置等物理上
    同样模糊的传输失败若走普通 Exception→ERROR→模型带新键重试→下游只按我方键去重即双写。
    修案(a) 的关键发现：executor.py:184-199 的 except TimeoutError 包住 await handler(...)——
    **handler 自抛与 asyncio.timeout 到期走同一分支**，转译一行白拿 RESULT_UNKNOWN+封死重试
    话术+tool_error 留痕全套，executor 零改动。分界线=副作用可能性：ConnectError/ConnectTimeout
    =连接未建立、请求没到对端、零副作用→保留 ERROR 语义（模型可安全改道）；发出后的
    ReadError/协议错=对端可能已处理→与超时同等对待。不造新异常的理由：X1 语义就是"结果
    不明"，新类型=第二套半截语义——executor 加分支、断言面扩大，复用现成路径是契约收敛
    不是偷懒。锚：_shared.post_write、拍板Ⅰ（plans 14g）、test_write_transport_contract_43）

## M3.8 主 Agent 装配与转人工（2026-07-25 出题）

133. ⬜ tenants.config 的三个键（tools/faq/approval_threshold）各自怎么传入、在哪一层被谁
    解释？"装配期读"与"执行期读"的分野是什么？
    （用户 2026-07-25 现场提问原题。三键三路：①**faq**——service 层自己消费（handle 里
    get("faq")）：守卫第二道退出+直答的 system 原文（intent.py 不加前缀=措辞权在租户，机制
    不定政策）；刻意不进主 Agent prompt——主路径答 FAQ 靠 KB 检索（M3.11 语料含 FAQ 文档=
    守卫补集）；②**tools**——装配期消费：build_agent_spec 白名单点名 ALL_TOOLS 货架、顺序=
    config 书写序、未知名启动炸；B 没配 refund_apply 的效果是**schema 根本没进过 B 的
    LLMRequest**（削攻击面靠"不装"不靠"装了拦"）；③**approval_threshold**——原样透传：
    config 整个塞 AgentSpec.tenant_config（spec.py:152"对运行时不透明"）→executor 风险闸门
    递给谓词（executor.py:150）→refunds.py 谓词才第一次读懂它。分野：tools/budget/ttl/
    entry_classifier 装配期固化进 spec（一次 run 冻结=回放一致性）；threshold 执行期现读——
    因为 risk_policy 是工具自带谓词、工具不知道会被哪个租户装配，(args, tenant_config) 签名
    让同一工具对象在不同租户有不同阈值行为（工具可复用、策略随租户走）。身份与配置分离：
    JWT 只带 tid、config 恒由服务端读库——用户与模型都碰不到。锚：agent.py、service.py
    handle、executor.py:150、refunds.py）
134. ⬜ FAQ 直答守卫为什么放 service 层而不是让分类器/prompt 自己解决？"先答后写"防的
    是什么？
    （层次答：INTENT_PROMPT 的自足限定是**统计优化**（模型判"自足性"不可靠），守卫是
    **结构保证**——判据"会话无历史"（messages 投影计数）是确定性谓词，直答只可能发生在
    首条消息上，指代跟进问被结构性挡回主 Agent（历史层在场）。守卫为什么不放 intent.py：
    分类器是单条消息的纯函数（无 DB），历史判据需要查库=service 编排层的职权；分层上
    intent 保持"机制"、service 持有"政策"。**先答后写**：直答分支 user_message 由 service 写
    （D7），若先写后答、answer_faq 失败回落主 Agent 时 loop 会再写一条=双写；先收齐答案
    再落双事件，失败时零残留、回落路径干净（U8"绝不双写"在直答分支的镜像）。直答失败
    回落主 Agent 而非报错：直答是主路径非增强层，但主 Agent 是"同样正确的路"——回落即
    fail-open 且语义无损。锚：service.py _faq_direct/_has_history、plans 14f 后置修订、
    demo_chat_acceptance 幕 B 实录）
135. ⬜ 幕 C 首跑为什么 FAIL？"A 面正常、B 面空集"这个组合暴露了哪两课？
    （实录题（2026-07-25）。机制链：tenants 表在 RLS 覆盖名单内（c895f9007bf7 五表之一）；
    验收脚本 _act_c 在 tenant_context 块外读 tenant-b 配置→current_setting 未设→策略不命中
    →空集→get_tenant None→service 合成空配置→工具面 []。**这是对抗①防线在配置面的真实
    开火**：无身份读他租数据被挡成"查无"，WARNING 是留痕按设计工作。而 A 面"正常"是
    **TenantDirectory 60s TTL 缓存残影**——幕 A/B 已在 tenant-a 上下文内把行载入缓存，幕 C
    读 A 是缓存命中根本没碰库。两课：⑴脚本身份声明是**每幕/每租户**义务——"封闭名单
    第四处（脚本 main 自包）"不等于包一次就完事，跨租户动作各包各的；⑵**TTL 内缓存残影
    不能当正确性证据**——缓存把身份错误暂时藏住，暴露与否取决于访问顺序（比"测试残留"
    更隐蔽的环境依赖形态）。生产无此缺陷：auth 验签即设上下文，service 只读请求者本租户。
    锚：demo_chat_acceptance._act_c 注释、tenancy.py TenantDirectory（只缓存命中）、
    c895f9007bf7、plans 14h (47)）

<!-- M3.9 HITL 业务闭环（2026-07-26 收尾追加，题 136–142） -->

136. ⬜ 会话锁与租约为什么缺一不可？各答什么问题、各自失效时靠什么兜？
    （一句话：锁答"现在有没有人在场"，租约答"这个 run 归谁、死了没有、第几代"。锁=活体
    互斥：快、短命、可降级（Redis TTL/PG advisory），过期**无痕**——正因无痕才扫描不出死亡；
    对外语义 SessionLockHeld→409。租约=持久所有权账本：sessions 三列住在事实源里，run 级
    （acquire WHERE run_state='running'）、可扫描（ix_sessions_reaper）、带版本（generation
    围栏——GC 僵尸醒来 renew 打空 LeaseLost 自毁零事件）。纵深三层：锁→租约 generation→
    (session_id,seq) 唯一约束。只留租约不行：拒绝族/取消/直答分支在无 run 在飞时也要互斥，
    而租约按定义那时不存在。锚：locks.py、store.py:535-673、runtime._pump_with_lease、
    题 77/95 连线）
137. ⬜ post_chat 没有 with tenant_context，RAG 检索的租户身份从哪来？这个隐式契约何时会断？
    （设值在认证依赖链：current_principal 验签即裸 set（auth.py:142-145）——async 依赖与
    handler 同 asyncio 任务，ContextVar 任务局部随请求生灭，故"只 set 不 reset"。封闭名单
    五处各形态：auth 裸 set/usage 特批/approvals 特批/Celery 任务内胆 with/脚本 main。断裂
    三条件：①current_principal 改 sync（线程池执行、set 粘线程上下文回不来——M3.5(32)
    三形态探针之一）；②BackgroundTasks/create_task 脱离请求任务；③叶子自设上下文（撤修
    方向）。防线不单靠它：Retriever WHERE tenant_id ∩ RLS USING 交叉核验，装配错=交集空=
    安全失败。锚：test_authed_request_sets_tenant_context、plans 14i）
138. ⬜ #44 的三个崩溃窗口分别是什么？为什么"钩子先查单再 resume(approval_id)"救不了？
    （W0=decide 后 resume 未起步：awaiting 无租约（挂起干净释放 D2）——租约扫描结构性
    看不见，归对账 sweep；W1/W2=T3 已翻 running 后崩：resume(approval_id) 的 T3
    CAS(awaiting→running) 必打空、按"并发赢家已处理"安静返回——换入口是死路；W3=execute
    完成 attach 前崩：换入口重执行走**新** write-ahead 事件 id=新幂等键，下游按新钥匙放行=
    真双写。修=_recover_locked a+ 认领支三窗分路（原语义执行/原幂等键 reexecute/只补
    attach）；attach 的 event_id 是"批准已兑现"的唯一持久凭证——认领判据 approved∧
    event_id IS NULL 由此而来。锚：runtime.py a+ 支、00 #44、test_recover_approved_claim）
139. ⬜ 为什么会出现"会话 awaiting 而审批单已决"？sweep 为什么不信 expire_due 的返回值？
    （决案=行级 CAS 一瞬（C11：decide 只管 approvals 一张表），兑现=带锁、带外部副作用、
    秒级的过程——不可原子捆绑，两步之间必有缝。生产者四路：审批 API decide 后崩/异常
    （decide 已 commit，HTTP 报错不回滚它）、取消端点同款、expire 批量翻转与逐单踢之间、
    同步消费拉长窗口。expire_due 只返回**本轮新翻**的单——崩溃后下轮不再返回=永久孤儿；
    解=approvals 表自身即 outbox（status=意图已录、awaiting=未兑现），sweep 每轮从持久
    状态重推意图而非信任调用轨迹；误踢安全=锁串行+T3 CAS 恰一赢家、输家安静零事件。
    追问：为什么不需要独立 outbox 表（状态字段已完整编码"待投递"）。锚：hitl.sweep_once
    docstring、14i 拍板Ⅵ）
140. ⬜ sweep 的"最新单"判据在防什么误杀？测试里为什么必须显式给 created_at？
    （误杀链：旧 EXPIRED 单+新 PENDING 单（新审批周期）时按旧单踢——resume(旧单) 的 T3
    CAS 会**成功**（会话确实在 awaiting，但等的是新单！）→approval_expired+CANCELLED 把
    等新单的 run 杀掉。判据=只看最新一张：最新 pending=正常等待不动。测试面：SAVEPOINT
    夹具下各 begin() 是同一外层事务的 SAVEPOINT，PG now()=事务起始时钟→created_at 全同
    无法排序；生产中同会话审批单由不同事务先后创建、天然可序——夹具与生产的时钟语义
    差要显式补（_seed_approval created_delta）。锚：test_sweep_latest_approval_wins）
141. ⬜ worker 为什么每任务新建全部连接？"loop 感知的聪明单例"为什么被否决？
    （不变量：**连接生命周期 ⊆ 创建它的 event loop 生命周期**。worker 任务壳=asyncio.run
    每任务新建并关闭 loop；进程单例绑首次创建的 loop→隔次任务交替炸（间歇性=最阴险，
    M3.4② 真实 HTTP 探针实录）。四处绑定面：get_engine/get_redis/shared_client/
    mock_client。否决聪明单例三理由：旧连接无法在已死 loop 里 await 善终=泄漏；隐藏魔法
    违反"组装在边缘"（M2.9 对 get_redis 已否决一次）；NullPool 下每任务代价毫秒级 vs 秒级
    任务、API 热路径保留池化红利。解的三件套：配置源提取（new_redis/http_client 单例与
    任务局部唯一口径）+工厂参数化（build_gateway/build_session_lock）+安装缝
    （set_mock_client，--pool=solo 串行前提）。锚：hitl._task_runtime、M3.4 决策 C）
142. ⬜ 审批 API 为什么要 owner 工厂做授权查读？403 与 404 在这里为什么必须分？
    （RLS 下 operator 的租户上下文读不到他租单——同一个"查无"分不清"不存在"（404）与
    "存在但无权"（403=00 §7.2 对抗④验收字面）。授权判定需要平台视角：owner 单行按主键
    读、只服务 403/404 判定（滥用面压到最小、经 create_app 注入缝可测）；判定后一切写与
    恢复回 tenant_context(单据租户) 走 app 工厂（usage admin 特批同款=冒充封闭名单第五处）。
    对照面试金句：用户面会话归属用 404 不泄露存在性（#19），staff 面越界用 403 显式点名
    ——两种泄露威胁模型给出两种相反的答案，"该藏则藏、该吼则吼"。锚：approvals.py
    docstring、14i 拍板Ⅲ、test_operator_cross_tenant_403）

<!-- M3.10 SSE 双通道（2026-07-26 收尾追加，题 143–149） -->

143. ⬜ 逐 token 流式为什么必须在 L2 开缝？"观察者不改变事实"不变量指什么、怎么被测试作证？
    （事件流刻意不含 token 帧（events.py:43：SSE 逐 token 是通道问题、事件粒度到"步"），
    _llm_step 把 TextDelta 聚合内部消化——通道层结构性拿不到增量；两条备选皆死路：等
    assistant_message 整段发=放弃流式违 ADR-007 动机、msgbuf 轮询=写缓冲的正是拿不到
    增量的 API 层。缝=run/resume keyword-only text_sink（每请求物不挂进程级构造——
    precheck 教训反面）；OutputGuard"逐字符≡整段"不变量（M2.8 预埋、D14 首字延迟
    代价"在 M3.10 兑现"原文）保证聚合/逐帧两模式 visible/hit 一致→事件字节相同。
    不变量="事件流与 sink 在场与否无关"：sink 只作用通道、异常降级不拖垮 run；
    作证=同剧本双会话事件逐条相等测试+既有 792 全绿零改动。锚：loop._llm_step/
    _finish_text、test_text_sink、14j 拍板Ⅱ）
144. ⬜ POST 通道为什么要队列解耦？客户端断连时为什么不取消 Agent run？
    （单生成器无法边收边吐：token 在消费者 __anext__ 阻塞（整段 LLM 流在 _llm_step
    内消化）期间到达，不入队只能攒批到事件边界=伪流式。断连不取消=run 是事实生产：
    杀掉=半截 llm_call 进崩溃恢复域、工具半途成 X1 面——观察者离场不该制造事故现场；
    脱缰生产者入强引用池继续写事件与 msgbuf，用户经 GET 通道重连补收（ADR-007 断线
    语义与 msgbuf 的合订本）。对照：loop 侧 sink 异常同哲学（通道死了事实照产）。
    锚：service.handle/_BACKGROUND、14j 拍板Ⅱ）
145. ⬜ SSE 化之后 409 等状态码怎么保住？流中出错为什么只能发 error 帧？
    （HTTP 铁律：状态码在首字节前定死。端点 peek 首帧——锁被占/T1 竞态发生在首帧
    之前（runtime 起步即取锁），anext 一帧让原 except 阶梯照常映射 409（M3.2 契约
    保持）；首帧后异常无法改码→error 帧收流（打码话术），已落盘事件不受影响、GET
    重连取回真相。代价=TTFB 推迟到首句（守卫句界缓冲），与 D14 首字延迟同源。
    锚：chat.post_chat peek/_relay、test_lock_held_409/test_infra_error）
146. ⬜ 跨副本事件通知为什么选 PG LISTEN/NOTIFY 不选 Redis pub/sub？LISTEN 为什么必须独立
    原生连接？"伪唤醒安全"靠什么成立？
    （C22 三理由：事务提交才发=通知到时事件必可读（Redis pub/sub 与事实源两条时间线、
    还给 Redis 加新降级面）；触发器与表同生命周期；断连兜底=after_seq 轮询天然存在。
    独立连接：LISTEN 绑定物理连接，从 SQLAlchemy 池借的连接随归还即失聪（§7 陷阱 7）。
    伪唤醒安全=通知只是路由键（session_id:seq 不消费内容），等待方醒来一律重查增量
    ——丢通知=多等一个轮询节拍，多通知=多查一次空集，两个方向都无害。实证：批准后
    续跑帧早于批准 HTTP 响应返回推达 GET 流。锚：notify.py、迁移 d41be6a90c27、
    00 §2.2 C22）
147. ⬜ GET 重订阅通道的关流判据为什么是两条？awaiting 会话为什么必须保持在流？
    （判据一=批内见 loop_terminated（主 Agent 会话的自然终点）；判据二=会话已归
    idle/failed 且无增量——**FAQ 直答类会话没有终止事件**（不经 loop），只看判据一
    会挂死轮询。缺判据二挂死、缺判据一会在"终止事件已写、T4 未翻"的缝上早退。
    awaiting 保持在流=ADR-007 立项之问的答案本体：审批挂起数小时后，续跑输出从这条
    连接送达（POST 流早已收束）。锚：stream._gen、test_live_tail、ADR-007 背景段）
148. ⬜ 原生 EventSource 为什么在本项目用不了？服务端为此改了什么？
    （EventSource 规范不支持自定义请求头→Bearer 认证只剩"JWT 进 URL"一条路，违安全
    底线（凭证进访问日志/代理缓存/Referer 泄漏面）。服务端**零改动**：id:/Last-Event-ID
    协议原样实现——改的是前端消费形态（fetch 手写解析+自记游标+手动重连）；未来上
    cookie 认证即可切回原生。层次答：协议兼容性保持在服务端、认证约束消化在客户端，
    折衷不外溢。锚：chat.html 头注、ADR-007 实装注记 2）
149. ⬜ 幕C"页面没有改变"实录：三段隔离怎么定位？暴露了事件溯源 UI 的哪条标配件？
    （实录题（2026-07-26）。嫌疑三段：服务端唤醒/流被早关/前端 JS。隔离法=分层探针：
    ①httpx 端到端探针（真实挂起→GET 挂流→批准）证服务端瞬时推达；②浏览器面板全流程
    复现证前端正确；③排除后唯一自洽解释=用户排障期间页面刷新——JS 状态（含挂着的
    订阅流）随页面消失且每次载入随机新 sid，批准推给无人订阅的旧会话。根因非缺陷而是
    可用性缺口：**事件溯源 UI 的会话身份必须可携带**——前端状态天生易失，"重入+重放"
    是标配件不是锦上添花（服务端本就支持，缺的只是 sid 可编辑一个把手）；自证一击=
    粘旧 sid+断线重连，"丢失"的回复从事件流里完整重放。锚：14j 偏差(56)、
    probe 实录、chat.html sid title）

<!-- M3.11 种子评测集与演示数据（2026-07-27 收尾追加，题 150–154） -->

150. ⬜ 评测集判据设计两纪律是什么？「B 检空集→字面核证」的口径演变怎么讲成方法论？
    （纪律一=判回答不判 query 复述：must_not_contain 只放他租户事实字面（保修时长/金额），
    复述产品名零泄漏——否则「未找到灵犀…的相关信息」被误杀；纪律二=判据强度随语料几何定：
    查询方语义域远（B 问数码产品）才断言 fallback_or_handoff，自有近邻文档（A 问会员权益）
    只断言 no_leak。演变实录：M3.5 时点 B 空库、「空集」是廉价判据；扩容后 threshold=0
    观察位必返 top-5 B 自家块（WHERE+RLS 结构保证）——判据升级为「命中文本零 A 字面+
    过阈值条数如实报告」；B 用户问退货命中 B 自家售后=合法行为，恰印证 no_leak 设计前瞻。
    方法论一句话：**判据的前提条件（语料几何）变了，判据必须跟着换——否则假阳性淹死
    真信号**。锚：evals/README §3、calibrate B 检修订、14k(59)(62)）
151. ⬜ seed_corpus 为什么设计成三分支？「幂等即省钱闸」与「原文变更删块重建」各防什么？
    （三分支：未变且 DONE→整篇跳过（零 API 调用=重跑不重花钱，幂等与成本闸是同一个
    谓词）；未变未完→直接 ingest_once（IS NULL 回填续传，与 worker 重试进场完全同构）；
    新增/变更→upsert 原文+复位 PENDING+删旧块全新摄取。删块重建的哲学：chunk 是原文的
    **派生物**，原文换了派生物必须整体重建——不存在增量补丁（部分旧块+部分新块=检索
    会返回两个版本的混合事实）。种子即初始化入口（D12）的完整语义在此闭合：改种子重跑
    =一键重建，演示改动（订单退款/语料变更）全部复位。锚：seed_demo
    seed_corpus_for_tenant docstring、test_seed_corpus_lifecycle）
152. ⬜ L3 cassette 录制为什么把 spec 从种子常量构造而不读库？「干净录制」在 L3 多出哪两个面？
    （I1 定义性同源：录制与回放冒烟从同一常量构造 spec——DB 配置漂移不再是回放断裂面；
    常量↔库的一致性另有保证（seed upsert 幂等+常量钉测试），两条职责分离。L3 新面①：
    检索 fail-open 空集≠阈值拒答空集——前者是异常被吞的假象（回放期检索层不炸→行为
    分岔），logging trap 捕留痕即自检失败不落盘；新面②：录制必须关缓存（缓存命中吃掉
    main 道条目→道内序号错位）。与 M2.11「干净录制>成功运行」同宗：录制器对"成功"的
    标准比生产更严——cassette 是未来所有回归的基线，基线里的每个侥幸都会变成回放期的
    谜团。锚：record_l3_cassettes docstring、LogTrap 双挂点）
153. ⬜ 预算盘 main 道零条目——「零调用 cassette」为什么仍是有效回归资产？
    （闸门 #3 是调用前预检（tokens_used+input_est>budget 判在 LLM_CALL 事件之前，
    loop.py:289），预算 100<system 估算≈160→首轮即终止、网关零消费。cassette 录的是
    **行为轨迹**不是模型输出：回放断言=同 spec 同输入→同点终止（token_budget_exceeded）
    +FakeGateway.assert_exhausted（空盘放空）；改坏预算编译/估算尺/预检位置任一环，
    回放即红。80 字节的空盘与 5KB 的 HITL 盘在 M4.3 眼里同等有效——回归资产的价值在
    确定性不在体积。锚：budget_token_exceeded.json（80 字节）、
    test_budget_cassette_replays、loop.py 闸门 #3）
154. ⬜ 本步两个 Python 陷阱：excluded.items 撞名与 importlib×dataclass——共同病根是什么？
    （①insert(...).excluded 是 ColumnCollection 语义的命名空间，`.items` 命中容器协议
    **方法** items() 而非同名列——拿到 bound method，延迟到 JSON 序列化才炸；列名撞
    items/keys/values/get/update 时必须下标访问 excluded["items"]。②future-annotations
    模块含 @dataclass 时，importlib 装载必须先 sys.modules[spec.name]=module 再
    exec_module——dataclasses 反解字符串注解查 sys.modules[cls.__module__]，未注册得
    None；M2.11 惯用法没炸只因当年脚本无模块级 dataclass（隐藏前提）。共同病根=
    **训练分布里的"常见形状"带隐藏前提**：attribute 访问通常等价下标、module_from_spec
    通常不必注册——前提破裂点恰在框架的动态反射面。对策与硬规则 8 一脉：不信"通常"，
    信可执行验证（两处皆影子排练在用户跑门之前抓获）。锚：14k(57)(60)、seed_demo
    刚性注释、test_l3_cassette_smoke._script 注释）

<!-- M3.12 毕业验收（2026-07-28 收尾追加，题 155–158） -->

155. ⬜ 兜底率 60%→80%→100% 三轮闭环：真编造与判据漏报怎么区分？处置为什么分两路？
    （R1 okb-03/04=真编造：语料零依据却给出赠品品牌/供应商名——模型先验填充具体事实，
    抽象禁令"绝不编造答案"拦不住（模型不认为那是编造）；处置=prompt 规则 3 禁令**具体化
    到事实品类**（品牌/供应商/赠品/活动/日期/价格）+处置动作（一律按「没有找到」）。
    R2 okb-02=判据漏报：「暂未在知识库中配置费率」诚实声明库缺、零编造——是判据信号集
    没覆盖"暂未/暂无"合法变体；处置=信号集反哺（判据修自己，不动模型）。区分的判准：
    **回答里有没有语料外的具体事实断言**——有=模型问题改 prompt，没有=判据问题改判据。
    改错方向的代价：把判据漏报当模型问题会污染 prompt、把编造当判据问题会洗掉真缺陷。
    锚：m3_acceptance §4、14l(65)）
156. ⬜ 启发式判据的假阳性面：R1 okb-02「不提供分期付款服务」为什么"判对了但不该算对"？
    （该回答同为无据断言（语料没说不提供分期）——只因断言方向碰巧撞上"不提供"信号词
    被机器判为触发。信号词判定测的是"话术形状"不是"事实依据"，两者在多数样本上相关、
    在这类样本上脱钩。三层判定架构由此定案：机器信号集=绊线（快、可复现、进 CI）→
    人工归因=抽查纠偏（00 §7.2"逐条归因"条款的用途）→ LLM-as-judge=语义终裁（M4.4，
    判"回答是否含语料外事实断言"而非判词形）。面试金句：**启发式判据的价值不在准确率
    而在可复现性——它的错误是系统性的、可归因的，比"人眼扫一遍"的随机遗漏更可治理**。
    锚：record_l3_cassettes._FALLBACK_SIGNALS docstring、evals/README §3、14l(68)）
157. ⬜ 对账面 RLS 盲区三次现形（M3.5 叶子自包裹/M3.8 无身份读配置/M3.12 上下文外读账本）：
    为什么"静默空集"比报错更危险？
    （RLS 的 fail-closed 形态=USING 谓词不命中返回空集而非异常——安全面是对的（不泄露），
    但对**读自己账**的代码构成陷阱：空集是合法返回值，调用方无从分辨"真没有"与"看不见"。
    三次形态谱：叶子自冒充短路交叉核验（写面）/缓存残影掩盖身份错误（读面）/上下文外
    对账归零+预算护栏盲飞（对账面）。系统性对策=D4 口径补全：**维护面、种子面、对账面
    三类平台视角操作一律 owner 引擎显式声明**，租户视角只出现在请求/任务边界（封闭名单）；
    数字对账加"非零 sanity"习惯（首跑 tokens=0 本身就是警报）。锚：14l(67)、
    perf_m3/_spend docstring、M3.5 偏差(32)）
158. ⬜ prompt 冻结后首次修订：重录纪律怎么运转？为什么冒烟测试不需要跟着改？
    （纪律链：SYSTEM_PROMPT_TEMPLATE 变更 → M2.6 README §3"改 system prompt → main 道
    必变" → 重跑 record_l3_cassettes（文件名稳定、覆盖即 diff）→ 五盘自检全过才落盘。
    冒烟不红的结构原因=**匹配键 (session_id, scope, 道内序号) 刻意不含 prompt 哈希**
    （M2.6 D2：prompt 微调不至于全量 miss）——回放消费的是"录制时的响应序列"，行为断言
    （终止原因/工具序列/道形状）对措辞不敏感。代价与收益的对偶：键不含 prompt=重录
    自由度高，但"prompt 变了行为没变"要靠重录后自检+diff 审查人工确认（README §4
    条目数变化必须能说出为什么）。本次是该纪律 M2.6 定稿以来第一次真实运转。
    锚：14l(66)、tests/cassettes/README §3§4）

## M3 全量复盘 · 站 1 租户底座与隔离（2026-07-27 出题；`core/tenancy.py` + `tenant_ctx.py` + `db.py` + 迁移 `6304edbb4760`/`c895f9007bf7`）

159. ⬜ 低权角色为什么是 RLS 的**存在前提**而不是加强项？PG 里哪几类身份根本不进入策略求值？
     你的 owner 引擎属于其中哪几类（诚实版）？
     （不进策略求值三类：superuser / 带 `BYPASSRLS` 的角色 / **表 owner**（除非 `FORCE ROW LEVEL SECURITY`）。
     实测：`aegis` 三重全占（rolsuper=t、rolbypassrls=t、全表 owner），`aegis_app` 三项皆无；
     全表 `relforcerowsecurity=f`。所以"应用切低权角色"不是加固，是让第 3 层防线**从不存在变成存在**。
     生产收窄向：维护角色仅保留 owner 身份、去掉 superuser/BYPASSRLS。锚：迁移 `c895f9007bf7`、db.py:32-64）
160. ⬜ 策略只写 `USING` 不写 `WITH CHECK` 会怎样？既然两个表达式一样，为什么仍要写两遍？
     （**缺 `WITH CHECK` 时写侧回落到 `USING`**——探针 A 实测：只写 USING 的策略下跨租户 INSERT 依然被拒。
     所以"漏写=当下越权写"是错的。真价值在**未来**：探针 B 把 USING 放宽成
     `tenant = current OR tenant = 'shared'` 且不写 WITH CHECK → 租户 A 成功写入 shared 区且全租户可见；
     探针 C 补一条更窄的 WITH CHECK → 拒绝。结论：**写两条是把"能读什么"与"能写什么"拆成两个独立旋钮**，
     不写等于宣布"写权限永远跟着读权限走"，而读侧是最容易被业务放宽的那一个。锚：本轮探针 A/B/C）
161. ⬜ `USING` 与 `WITH CHECK` 的四操作矩阵是什么？为什么读侧不匹配是"静默过滤"、写侧不匹配是"报错"——
     这个不对称是设计还是历史包袱？
     （SELECT: 仅 USING；INSERT: 仅 WITH CHECK；UPDATE: USING 管旧行可见性 + WITH CHECK 管新行；DELETE: 仅 USING。
     不对称是设计：读侧报错本身会泄露"那里有东西"，静默过滤才符合隔离语义；写侧静默丢弃是更坏的行为，
     必须 fail-loud（`42501`）。一句话记法：USING=你够得着哪些行，WITH CHECK=你留下的行长什么样）
162. ⬜ `current_setting('app.tenant_id', true)` 的第二个参数为什么必须是 `true`？改成 `false` 之后
     失败形态从什么变成什么，哪个更好？
     （`true`=missing_ok，设置项缺失返回 NULL 而非抛错。于是 fail-closed 有两条腿：钩子在场但未设上下文→`''`
     比较为假；**钩子压根没挂**→NULL 非真——两条都塌缩成空集。改 `false` 则第二种情形变成查询异常，
     把"上下文没设"的配置问题伪装成"数据库炸了"。代价见 166：空集与"不存在"从此不可区分）
163. ⬜ `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` 与 `CREATE POLICY` 之间那一瞬间发生了什么？
     为什么在你的项目里外界看不见它？
     （ENABLE 是开关、POLICY 是规则；**开关开了且零策略 = 对所有非 owner 全拒**。两句之间存在"全线空集"窗口，
     被 alembic 的迁移事务藏住——PG 的 DDL 是事务性的。这是 PG 相对 MySQL 的真实优势，也是"迁移必须在事务里跑"
     的一个具体理由）
164. ⬜ `GRANT ... ON ALL TABLES` 与 `ALTER DEFAULT PRIVILEGES` 的分工是什么？后者有一个关于"谁创建对象"的
     隐藏前提，说出来。为什么"新表自带 ENABLE RLS + 策略"仍然是必须的前置义务？
     （ALL=执行时刻的一次性快照；DEFAULT PRIVILEGES=对**未来**对象的持续规则，但不写 `FOR ROLE` 时隐含
     `FOR ROLE current_user`——只覆盖**由执行者创建**的对象（我们这里全链由 `aegis` 跑迁移故闭合）。
     **DEFAULT PRIVILEGES 只管 DML 授权，RLS 不隐式继承**：M3.4 documents/chunks 与 M3.7 mock 两表
     各自迁移都自带了 ENABLE+策略，实测九表全覆盖=两次义务都没漏。锚：plans 14c 偏差 ⒁）
165. ⬜ 你的自增主键是 `serial` 还是 identity？这对权限有什么影响？漏授 sequence 权限的症状长什么样？
     `events` 表为什么不在 sequence 名单里？
     （实测：chunks/messages/tool_invocations/usage_ledger 四表用 `nextval('..._id_seq')`=**serial**，
     插入要 sequence 的 USAGE 权限；identity 列则由系统内部拥有、权限随表。漏授的症状很偏：SELECT 全正常、
     对这四张表的 INSERT 全挂 `permission denied for sequence ...`。events 的 `id`(varchar) 与 `seq`(int)
     **都由应用赋值**——id 必须应用生成是因为同事务投影要在 flush 前引用 `event.id`，自增此刻还是 None；
     seq 由单写者串行赋。**一张表用不用 sequence 由它的写入模型决定**）
166. ⬜ RLS 的 fail-closed 撞上成本闸门的 fail-open，会合成出什么？给出你项目里的完整链路。
     （链路：缺租户上下文 → RLS 空集 → `TenantDirectory.get_tenant` 返回 None → `monthly_budget` 返 0
     → router 判"0=闸门关闭" → **放行，且不报错不告警不留痕**。两个各自完全正确的失败方向叠出静默失效。
     一般化判据：**凡"读不到就放行"的逻辑，都要先问这个'读不到'是不是自己造成的**。
     三次现形与系统性对策见题 157）
167. ⬜ 租户上下文为什么用 `ContextVar` 而不是 `threading.local`？钩子在**哪个时刻**读它，这带来什么时序约束？
     （asyncio 一个线程跑成百上千协程，`threading.local` 会让它们共享一份租户 id=串租；ContextVar 语义是
     "每个 asyncio 任务持独立副本"，正好匹配"一请求一任务"。钩子挂 `"begin"` 事件=**在 BEGIN 时刻**读值，
     所以**上下文必须先于事务**：事务已开之后再进 `tenant_context` 无效（usage 端点的嵌套切换必须在开会话之前）。
     邻域：SAVEPOINT 不触发 `"begin"`；`--pool=solo` 的 Celery 里同步壳 set 不 reset 会跨任务黏住上下文
     ——M3.5 ContextVar 三形态探针）
168. ⬜ `events`/`messages`/`tool_invocations` 为什么不在 RLS 覆盖面？这是安全妥协还是规范化结论——怎么辩护？
     （它们没有 `tenant_id` 列（租户是会话的属性不是每条事件的属性——规范化判据，见题 100），
     而 RLS 的适用前提就是"行上带租户列"。它们的隔离靠**会话归属校验**（#19：tenant+user 双匹配、
     不符 404 不泄露存在性）。答法：**边界由规范化定，不是安全等级妥协**；反问自己的检查点是
     "有没有一条路径能不经过会话行就读到事件行"）
169. ⬜ `TenantDirectory` 为什么"只缓存命中、不做负缓存"？说出两个理由——一个是当初写下的，一个是 M3 走完才看清的。
     （写下的：负缓存会让新种子的租户/用户在 TTL 窗内被 401/403 误伤。事后看清的：**RLS 下"读不到"与
     "不存在"返回同一个 None**，做了负缓存则一次缺失上下文的读会被钉死 60 秒——把瞬时 bug 放大成
     持续性静默故障。第二个理由比第一个更硬）
170. ⬜ `tenants`/`users` 两表为什么落在 `core` 而不是 `apps`？是谁"算"出了这个居所？
     （认证（api）、预算闸门（gateway）、装配（apps）三个消费方都要读租户；分层契约下
     `gateway` 不许 import `apps`、`api` 与 `workers` 互不 import——三者共同可达的层只有 `core`。
     **分层契约把数据模型的居所算出来了**，这是 D1 的"唯一解"而非偏好。同族现象：`SessionFactory`
     别名在 core 与 runtime 各声明一份——结构化类型只认形状，重复声明是分层契约下的正确代价）
171. ⬜ 迁移里的 `CREATE ROLE` 为什么必须幂等？这个性质被哪条真实工艺消费？明文口令已经进了 git 历史，
     在"已推送历史不改 + 迁移不可变"的约束下，生产怎么办？
     （PG 没有 `CREATE ROLE IF NOT EXISTS`，只能 `DO` 块先查后建；角色是 **cluster 级**对象，
     同实例建第二个库时必然已存在。被消费的工艺=**M3.7 起的影子库门**（`aegis_shadow` 空库全链迁移重放
     =裸库自举验证），以及 downgrade/upgrade 往返与 CI 重跑。生产路径：迁移只保证"角色存在"、
     不管理凭据——由部署侧（compose/IaC/secrets）预建角色并管口令，**这段代码已经写成了那个形状**；
     或另起一笔迁移 `ALTER ROLE ... PASSWORD`（值取自环境变量）。理论竞态：查与建之间非原子，
     并发迁移会撞 `42710`，实践上被 alembic_version 行冲突挡住）

## M3 全量复盘 · 站 2 认证与应用工厂（2026-07-27 出题；`api/auth.py` + `main.py` + `ratelimit.py` + `scripts/mint_token.py`）

172. ⬜ alg 混淆的两种形态是什么？为什么"让 token 自己声明用什么算法验证自己"是根本性错误？
     （① `alg:"none"`+删签名；② `RS256→HS256`——**用公开的公钥当 HMAC 密钥**签票，人人可签。
     根因=验签方信任了不可信输入里的算法声明。修法唯一：`decode(..., algorithms=[白名单])` 由**验签方**钉死，
     不看头部。PyJWT 为兼容默认不强制该参数，所以必须我们传。证人 `test_alg_none_rejected`。
     同族：`options={"require": [...]}` 堵"缺失即通过"——没有 `exp` 的票=永不过期票，
     而它在代码里长得和正常票一模一样。**一般化：安全校验里"可选字段"是危险默认，必须先断言存在性**）
173. ⬜ 为什么空密钥/弱密钥必须炸成 500 而不是 401？做成 401 会让排障走向哪里？
     （`ValueError`（配置 bug，fail-loud）与 `InvalidToken`（客户端问题→401）**刻意分家**。
     空钥走 401 的现象是"所有人登录失败"→ 运维会查用户/网络/客户端，唯独不会怀疑"服务端没配密钥"，
     因为 401 明写着"你的凭证有问题"。证人测试名本身就是不变量：`test_empty_secret_is_config_error_not_401`。
     与 C34 的关系：**失败方向有三种**——安全闸 fail-closed / 增强层 fail-open / **配置错误 fail-loud**。
     弱钥 <32B 升硬错误的由来=RFC 7518 §3.2 MUST ≥256bit，PyJWT 只发 InsecureKeyLengthWarning
     （M3.1 偏差 ⑷ 实录 22 条告警）；教训=**涉密钥/长度类安全参数，交付稿按规范下限起步**）
174. ⬜ 双密钥窗为什么**只在签名不符**时才试旧钥？无差别试两把会掩盖什么？完整轮换操作序是什么？
     （换钥匙只能救"签名不符"一种病：过期票用旧钥解出来还是过期。无差别重试会让最终抛出的是
     第二把钥匙的失败原因——把"票过期了"掩盖成"签名不符"。同族哲学=M1"重试幂等错误是错误说法"
     （题 3）：**能重试的不是某类错误，是某类原因**。轮换序：①新钥→current、旧钥→previous
     ②等待 ≥ 最长 TTL（staff 8h）③清空 previous。代价=窗口期两把钥都有效＝旧钥泄漏后的有效攻击窗，
     所以窗口不能开太久。证人 `test_previous_secret_window`）
175. ⬜ 入站限流依赖为什么必须包在角色依赖的**外层**？给出"顺序反了"的具体攻击。
     （`_ADMITTED = rate_limited(require_roles(USER, ADMIN))`，chat.py:44。顺序不只是策略，是**数据依赖**
     强制的——限流 key 是 `inbound:{principal.tenant_id}`，没有 principal 就算不出 key。
     反过来的攻击：未认证请求也消耗某租户令牌 → 攻击者用伪造 token **以别人的名义拒绝别人的服务**。
     一般判据：**认证必须先于任何按身份计费的动作**。链序 401→403→429 由嵌套 Depends 自然保证）
176. ⬜ 入站限流为什么即问即答不排队，而出站限流可以排队（`max_wait>0`）？判据是什么？
     （出站保护**供应商**：等一等上游就缓过来，且请求已花钱进系统；入站保护**自己**：
     **排队等于替攻击者保管请求**——连接/内存/任务全占着。入站限流的价值恰恰是快速拒绝。
     实装用 `try_take` 而非 `wait_take(max_wait=0)`（偏差 ⑼）：直接拿到 (放行, 建议等待) 二元组，
     `Retry-After` 是 Lua 桶的**真实提示**而非拍定常数；`max(1, ceil(wait))` 满足 HTTP 语法）
177. ⬜ `from __future__ import annotations` × 依赖工厂闭包为什么导致全量 422？`loc:["query","principal"]`
     是怎么断案的？规律的一般表述是什么？
     （链：PEP 563 让注解变字符串 → FastAPI 用 `get_type_hints()` 在**模块全局名字空间**反解 →
     拿不到函数闭包 → `Annotated[Principal, Depends(role_dep)]` 里的 `role_dep` 是闭包名、全局不可见 →
     反解失败 → 参数退化成**普通必填 query** → 每请求 422。物证=`detail.loc` 直接指出被当成 query。
     修=该文件弃 future import（注解按 def 时求值，闭包名此刻可见）。`auth.py` 不受影响因为其内层注解
     引用的 `current_principal` 是**模块全局名**。一般表述：**依赖工厂内层注解引用的名字必须模块全局可见，
     否则该文件放弃 future annotations**。根治=Python 3.14 PEP 649，登记 00 §10.1 #45，
     **M3–M5 期间禁做**（范围纪律）。锚：ratelimit.py:8-12、偏差 ⑾、题 108）
178. ⬜ JWT 无撤销的代价是什么？你用什么压住它？要做即时撤销得付出什么？
     （自包含凭证=签发后服务端不持有任何状态，换来验签零 DB 往返；代价：离职/降权/密钥疑似泄漏
     在票过期前无法作废，且缺 `jti` 连"黑名单单张票"的身份都没有，唯一止血是轮换密钥（核选项，踢所有人）。
     对策=短 TTL（user 2h/staff 8h），撤销延迟上界≡TTL。要即时撤销就得引入黑名单或改成不透明 token
     +服务端会话——**等于把无状态这个好处退回去**。连带事实：请求路径**根本不查 users 表**
     （role 直接来自 claim），所以角色变更同样有 TTL 延迟；这也把题 169 家族的
     `_users` 缓存风险锁在"当前不可达"——但一旦为了即时降权接上 `get_user`，它立刻变成可达越权面）
179. ⬜ `approvals_lookup` 为什么必须走 owner 工厂——这算不算绕过隔离？
     （RLS 制造的判定悖论：app 引擎下"这单不存在"与"这单是别人租户的"都返回空集，
     而审批 API 必须区分 404 与 **403（对抗④）**。要作出区分必须**先以平台视角看见那张单，再判断归属**。
     不是绕过隔离——**403 本身就是隔离在起作用的证据**。与题 159/166 同族：RLS 藏起了存在性，
     于是需要一个显式的、被点名的平台视角入口（`create_app` 第八注入参，M3.9② 拍板Ⅲ）。
     对**坐席**这个角色，"存在但不是你的"是可以告知的信息——判据是角色而非机制）
180. ⬜ `/healthz` 为什么不查依赖？查了会在故障时发生什么？
     （liveness 挂了触发**重启**，而"数据库连不上"重启应用毫无帮助——只会在故障期把所有副本
     反复杀掉，把一个下游故障放大成全面雪崩。查依赖的是 readiness（摘流量不重启），v1 未做属已知边界。
     一般判据：**探针的语义由它触发的动作决定**）
181. ⬜ FastAPI 依赖写 `def` 与 `async def` 有什么区别？为什么 `current_principal` **必须**是 `async def`——
     写错会出现什么现象，为什么这个现象特别难排查？
     （探针实测：`def` 依赖跑在 **AnyIO worker thread**、`async def` 跑在 MainThread；
     同步依赖里 `ContextVar.set()` 的值端点**读不到**（`to_thread.run_sync` 传的是 context **拷贝**——
     **读得到，写不回来**）。故 `current_principal` 若写 `def`，`current_tenant_id.set()` 丢失 →
     站 1 的 RLS 钩子每事务注空串 → 全线空集且**零报错**，与"真的没数据"不可区分（题 166 家族）。
     另两条理由：① `rate_limited` 的类型契约要求 `Callable[..., Awaitable[Principal]]`，写 `def` 直接 mypy 红；
     ② 纯内存判断进线程池是开销倒挂，且 40 槽的池是全局共享稀缺资源，会拖垮真正需要线程的阻塞操作。
     判据：**`async def` 是默认，`def` 是"我确实要阻塞，请把我踢出事件循环"的显式申请**）
182. ⬜ 你设了 JWT TTL，那**续约**怎么做？没做的话是漏了还是裁了？
     （过期**校验**完整：`exp` 是强制 claim，`ExpiredSignatureError`→401，单元+端到端两层证人。
     **续约零机制**（grep 实测：全仓 renew 命中全是 M2.10 会话租约，与 JWT 无关），
     实际续约动作=重跑 `mint_token.py` 粘新票。定性：P7"不做登录端点"的**下位推论**——
     refresh 需要发/换/存三个锚点，没有登录体系就无处安放；但该推论在 P7 与 02 §7.1 **均未被显式登记**（观察⑧）。
     三形态：(a) 滑动过期 (b) refresh 双票制 (c) 只做到期引导。**(a) 是陷阱**——只要一直用就永不过期，
     活跃的被盗 token 永不失效，直接拆掉"短 TTL 压住无撤销"这条唯一对策（题 178）；
     **看似正交、实则摧毁另一条防线**是安全设计里最难被评审发现的一类改动。v1 正解=(c)（服务端已在
     401 detail 里带 `ExpiredSignatureError`，客户端分个支即可），v2 正解=(b)。
     连带债：TTL 分档逻辑只有 mint_token 一个消费点且零测试（观察⑦）——**TTL 生命周期只闭合了签发一端**）
183. ⬜ SSE/长连接的认证与普通 HTTP 请求有什么本质区别？你的流在 token 过期后会发生什么，窗口由什么收口？
     （HTTP 每请求重认证；SSE 是**连接级一次性**——`Depends(require_roles)` 与 `_ensure_owned` 在响应开始前
     跑一次，`_gen()` 内不再看 `exp`。所以"连接建立时有效、流中过期"会继续推送。
     窗口**有界**：关流两判据（`state["terminated"]`，或 run_state ∈ {idle, failed, None} 且本轮无增量）
     收口在**一次 run 的时长**内，不是永久。属已知边界（观察⑨）；v2 收窄形态=唤醒点周期性重校验 exp。
     锚：stream.py:98-160）

## M3 全量复盘 · 站 3 会话入站与用量（2026-07-27 出题；`api/chat.py` 准入面 + `api/usage.py`）

184. ⬜ 为什么归属不符回 404 不回 403？同一个系统里 `/v1/sessions/{id}/events` 却对 operator 回 403——判据是什么？
     （404 让"不是你的"与"根本没有"不可区分——**会话 id 的存在性本身是信息**；403 等于承认"存在但不归你"。
     events 端点回 403 是因为**对坐席这个角色，存在性可以告知**（他本就有本租户 trace 的查看权，
     跨租户是越权而非不可知）。**判据是角色而非机制**。连带：events 端点刻意用 `approvals_lookup`
     （owner 工厂）查读，理由同题 179——RLS 下 404/403 判定需要平台视角）
185. ⬜ chat 端点的 `except` 阶梯为什么必须是 `SessionLockHeld` → 事实源三类 → `RuntimeError`？
     顺序错了会怎样？中间那层为什么**裸穿**？
     （`SessionLockHeld`/`EventStoreUnavailable`/`EventWriteFenced`/`LeaseLost` **全是 `RuntimeError` 子类**——
     把最宽的放前面会让前两条永远不可达，**异常阶梯的顺序不是风格是可达性**。中间层裸穿因为它们是
     **事实源坏了**，不是"你的请求有冲突"：409 的语义是"再试一次有用"，而事实源坏了再试只会再坏一次，
     裸穿→500→告警才对。同 M2"绝不 except GatewayError 基类"哲学：**捕获范围必须与你能给出的处置
     精确匹配**。`SessionLockHeld` 同时覆盖锁占用与租约占用两信号（M3.0 核对 #3），对用户是同一件事）
186. ⬜ 为什么要 peek 首帧？不 peek 会破坏哪条契约，根因是异步生成器的什么性质？
     （异步生成器体在第一次 `anext` 前**一行都不执行**，而取锁/T1 迁移都在体内 → 直接返回生成器会让
     FastAPI 先发 200+`text/event-stream` 响应头，之后才取锁撞 `SessionLockHeld`，**状态码已定死**，
     M3.2 的 409 契约作废。peek 把"生成器体第一段"拉到响应头之前。一般模式：**异步生成器的惰性会把
     启动期错误推迟到消费期，而 HTTP 状态码只有一次机会**。
     `except StopAsyncIteration → _short_stream([])` 理论不可达但诚实给空流）
187. ⬜ 取消为什么只认结构化布尔字段 `cancel_pending_approval`，不做自然语言识别？取消为什么不是"删单"？
     （**安全动作必须有确定性触发路径**——撤销一张待审批的退款单绝不能建立在"模型觉得用户想取消"之上
     （同 M2.8"防线一律确定性状态机"）。取消=`ApprovalStore.cancel` CAS 翻状态 + 走 `resume(approval_id=)`
     的 M2.9 拒绝族路径：写 `approval_cancelled` 事件、终止 run、状态机复位——**一次完整留痕的状态迁移**。
     CAS 失败回 409 而非强改：用户/坐席 decide/reaper 到期**三方赛跑，绝不覆盖赢家**（C11））
188. ⬜ 端点为什么不自己取锁？（M3.2 计划原本要求"端点持锁覆盖全程"）
     （实况：锁由 `AgentRuntime._maybe_lock` 内部持有，端点预取会**自撞自己**。定案=锁全权归 runtime、
     端点只负责把 `SessionLockHeld` 翻译成 409。这是信任序第一条（**实际代码 > 计划**）的现场应用，
     偏差 ⑻）
189. ⬜ `_ensure_session` 在 RLS 落地后为什么行为变了？"新增一层防线会改变上层代码的可达路径"——
     还能在项目里找出同族的地方吗？
     （探针实测：RLS 在场时他租占用的 session_id → SELECT 被过滤成 None → 走**首见建行**分支 →
     INSERT 撞 PK → `IntegrityError` → 回读**仍空** → `.scalar_one()` → `NoResultFound` → **500**；
     而测试连 owner 无 RLS，同一场景走 `row.tenant_id != ...` → 404。根因是时间顺序：
     `_ensure_session` 写于 M3.2、RLS 上于 M3.3，**那半个条件被 RLS 抢答成死代码，它原本负责的情形
     滑进了建行分支**。危害：非数据泄漏，但是**存在性 oracle**（500 vs 200），与 docstring
     "不泄露存在性"的声明不符。三端点命运对照（同一"读出来再比对"模式）：chat=None 意为"可建"→ 500 ／
     stream=None 意为"不存在"→ 404 ✅ ／ events=owner 工厂看得见 → 403 ✅——**命运取决于 `row is None`
     被赋予了什么语义**。修=回读改 `scalar_one_or_none()` + None 抛 404（两行，改完 RLS/非 RLS 行为一致）。
     登记 00 §10.1 #46）
190. ⬜ 你的四大对抗测试跑在 RLS 打开还是关闭的世界里？这对"隔离全绿"这句话意味着什么？
     （grep 实测：**全仓唯一用 `aegis_app` 引擎的测试文件是 `tests/test_rls.py`**；根 conftest 的
     `TEST_DATABASE_URL` 默认 `aegis:aegis`=owner（超管+BYPASSRLS+表 owner 三重豁免），
     所以 `test_adversarial.py` 四大对抗集中面**跑在 RLS 关闭态**。分工本身合理（对抗测第 1/2 层、
     test_rls 测第 3/4 层的通用性质），但后果是**"业务代码 × RLS 在场"这个交互面在 CI 里几乎没有证人**——
     M3 已在这条缝踩四次（M3.5 叶子自包裹／M3.8 无身份读配置／M3.12 对账面归零／复盘站 3 的 500），
     前三次全是人肉在真实链路撞出来的。精确表述：**"应用层隔离有 CI 集中对账面；RLS 兜底层有独立性质测试；
     两者的交互面目前主要靠真实链路人肉验证"**——这句经得起追问，"四大对抗全绿所以隔离没问题"经不起。
     登记 00 §10.1 #47）
191. ⬜ `_relay` 为什么要单独 yield `first`？`except Exception` 为什么不能写成 `except BaseException`？
     （① `first` 已被端点 `anext` 从生成器取走，**异步生成器无 push-back**，不拼回去这一帧静默丢失；
     顺序不能反因为 SSE **帧序即语义**。`_relay` 本质=手写的 `chain([first], rest)`（标准库无异步 chain）。
     ② `GeneratorExit`/`CancelledError` 继承 **`BaseException` 不是 `Exception`**——客户端断连时 Starlette
     `aclose()` 生成器抛 `GeneratorExit`，捕了会把"关标签页"这种正常行为记成 `logger.exception` 全栈
     （告警疲劳），还会试图往死连接写 error 帧二次失败。**这里的 `except Exception` 是承重的**。
     ③ 替代设计"两段式协程 eager 抛错"在此不成立：`SessionLockHeld` 在 `classify`（一次真实 LLM 调用）
     **之后**的 `_run_main` 里才抛，启动期与产出期交织切不开；硬切要把取锁提前到分类之前=真实行为变更。
     **peek 的本质=用"第一帧到达"等价于"启动成功"**，靠 `_produce` 的 `finally` 哨兵恒发 +
     `handle` 末尾 `await produced` 重抛两行共同保证。锚：chat.py:109-119/172-189、service.py:159-185）

## M3 全量复盘 · 站 4 摄取流水线（2026-07-28 出题；rag/models+ingest / gateway/embeddings / workers/ingest / api/kb + 复盘补丁一二）

192. ⬜ `INGEST_TASK_NAME` 为什么必须住 `apps`？`.delay()` 为什么作废？跨进程之后，契约的保障机制发生了什么质变？
     （层契约 `api | workers` 互不 import → api 拿不到任务函数引用 → 只能 `send_task` 按名投递 → 任务名成为
     wire 契约，居所必须是双方共同下层；apps 而非 core 因为"摄取一篇文档"是业务概念（居所判据=平台物理学 vs
     业务语义，题 90 同族）。质变：进程内契约=函数签名，改错 mypy 当场红；跨进程后契约退化成**一个字符串**，
     编译器与类型检查全部失灵——写错一个字母 = api 照常 202、消息进无人监听的队列、零报错。所以两端同源常量
     + CI 断言（test_task_name_wired_on_both_ends 连 include 都锚死）不是洁癖，是**把编译器丢掉的保障用测试
     补回来**。锚：rag/ingest.py:12、kb.py:44-52、决策 A=plans 14d）
193. ⬜ `split_text` 三级降级各承诺什么？`target_tokens=400`/`overlap_tokens=50` 的取舍两边各是什么？
     （L1 段落=绝不腰斩段落、聚合到预算即封块；L2 句界=单段超预算的让步；L3 硬切窗=什么都不保证、只保预算。
     每级都是"上一级承诺做不到时的最小让步"——与 L1 fallback 矩阵、handoff 摘要三档同形。400：太小→语义
     碎片化召回拼不回上下文；太大→单块多话题向量取平均谁都不像、且吃 ContextBuilder retrieval 预算（六层
     编译下游）。50：买"答案跨块边界"保险，付索引行数膨胀；种子=尾部完整段落装不下宁缺毋滥（0 种子合法）。
     锚：rag/ingest.py:21-33 docstring）
194. ⬜ 复述 `elif` 死分支事故：反例怎么构造？怎么证明该分支从未执行过一次？真正的教训是什么？
     （反例 30+380/400/50：P1=100,P2=30,P3=380——P3 触发 flush 后同轮 append，种子 30+380=410>400 越界。
     可达性证明=枚举进入 `elif`（fresh==0∧buf 非空）的全部产生路径：循环起点 buf 空／flush 只发生在同轮 if
     命中处而 elif 被跳过／超长段分支清 buf 且 continue——无第四条路，100% 死代码。教训：**永不可达的防御
     分支比没有更危险**（制造"已防住"假象），注释"绝不产出超预算块"说谎一整个交付；一般化=**不变量注释必须
     有测试作证**。修=elif→if 一个词+回归钉子 test_overlap_seed_never_busts_budget；宁丢重叠不破预算
     （重叠是优化、预算是不变量）。两路独立对抗读码各自撞出同一条。锚：rag/ingest.py:61-66、偏差(24)）
195. ⬜ `flush()` 收种子时那个 `break` 为什么不能写成 `continue`？切块产物为什么"不是原文子串"、后果是什么？
     （continue=跳过大段继续往前找小段 → 种子变成原文中**不相邻段落的拼接**=伪造一段不存在的上下文喂给
     embedding 与主 Agent；重叠的全部意义是"保住与下块相邻的上下文"，不连续即无意义。产物经 strip+join
     重拼非逐字节子串，且 chunks 无 (start,end) 偏移列 → "答案出自原文第几行"的引用溯源 v1 **结构上不可能**
     （非"还没做"）；要做=加偏移两列+切块保字节对齐=schema 变更。锚：rag/ingest.py:45-50、站 4 观察）
196. ⬜ embedding 通道为什么独立类而不塞进 `LLMGateway`？它与 chat 通道的重试对照表里，所有差异的唯一根因是什么？
     （complete 契约=档位/熔断/缓存/流式/三组六类，embedding 每项都不成立——塞进去要么污染 LLMRequest/LLMChunk
     要么门面开 if 分支；判据=**当复用逼你在门面上加分支，那不是复用是耦合**（D5"受控扩展"）。共享的是下层
     工具（raise_for_status 翻译表/shared_client/账本/RETRYABLE_ERRORS+compute_backoff 同一把尺），不共享
     上层门面。差异唯一根因：**embedding 是纯函数调用**（同入同出零副作用、读语义幂等）→ 整调用可重试；
     chat 首块后产生不可撤销的下游可见效果 → 只在首块前重试（红线一）。锚：embeddings.py:1-10、93-103）
197. ⬜ `embed()` 开头的 str 防呆防的是什么？三重形状校验为什么 fail-loud，同文件计量却 fail-open——判据一句话？
     `encoding_format:"float"` 与形状校验是什么关系？
     （str 满足 `Sequence[str]`（元素也是 str），mypy 不报——运行时按**字符**逐个向量化：烧钱、结果全垃圾、
     零异常，"类型系统允许、语义荒谬"的缺口只能运行时堵。判据=**这个缺陷会不会被后续环节发现**：错位/缺维
     向量是检索侧静默垃圾（无下游信号）→必须当场炸；账目缺口有 M1.12 对账脚本暴露→可吞。第三重校验专抓
     index 重复/缺失（前两重全过但 slot 空）。encoding_format 钉浮点数组形态是校验前提——上游缺省可能回
     base64 字符串，len(vec) 量的就是字符串长度，三重校验全部失灵；两行必须一起读。锚：embeddings.py:84-86、
     121-122、133-145、149-162）
198. ⬜ shared_client 跨 event loop 那枚 major：故障形态为什么是"隔次交替炸"？为什么 CI 永远抓不到？
     抛的为什么是裸 RuntimeError、危害比"炸"本身深在哪？一般原则一句话？
     （Celery 每任务 asyncio.run=新 loop；keep-alive 连接绑创建时 loop。任务1建连成功→连接留池；任务2复用
     死 loop 连接→炸；坏连接被丢→任务3新建成功→任务4再炸——交替。CI 不复现因为测试从不连续跑两次
     asyncio.run；靠真实 HTTP 探针实证。裸 RuntimeError 不属 httpx.* 任何一支 → **笔直穿过 _post_once 三段
     翻译阶梯**，冲到 Celery 壳被当未知故障重试 6 轮，documents.error 里的死因指不到病灶。原则：**单例的
     作用域必须等于它所绑资源的作用域**——uvicorn 进程级 loop 配进程级单例；Celery 任务级 loop 配任务级
     资源（修=工厂双直通参 session_factory+client，任务 async 入口自建 finally 关）。NullPool 多买确定性：
     引擎存续期零驻留连接。锚：workers/ingest.py:151-166、factory.py:73-91、plans 14d ②major）
199. ⬜ "断点续传的全部实现=一个 IS NULL 谓词"——展开讲；"失败重做的粒度"原则在本站出现了哪三个尺度？
     四步为什么 crash-only 而 M2 的 run 不是——判据一句话？
     （embedding 可空列身兼待办队列+进度条：重试进场已回填行天然出队，零游标零进度表零 checkpoint。三尺度：
     重试放批级（_embed_batch）/事务放批级（每批独立提交）/续传粒度=批——统一口径=**失败重做的粒度应等于
     "结果可被独立保存"的粒度**（acks_late 后兑现为现金：重投重复成本上界=一批 10 块）。crash-only 判据=
     **外部副作用能否被重放到同一终态**：embedding 结果可幂等保存，重做唯一代价是重复计费→四步全收敛
     （赋值/条件插入/按谓词消费/赋值）零补偿代码；LLM 一旦吐字=不可撤销下游可见→必须 write-ahead+租约+
     恢复分诊。附：步骤① 无 WHERE tenant_id、隔离全交 RLS 是安全的，当且仅当"读不到"与"不存在"在语义上
     是同一件事（#46 的反面教材=None 被赋予"首见可建"语义）。锚：workers/ingest.py:97-120、71-78）
200. ⬜ documents.id 用应用侧 uuid、chunks.id 用 serial——同模块两种 id 策略的判据？`status` 为什么"是进度
     不是心跳"？为什么不能拿它做 CAS 认领互斥？
     （判据=**谁在什么时刻需要这个值**：doc_id 要在提交前进 202 回执与消息载荷（events uuid 同理）；块 id
     无提前消费方且量大，serial 省空间天然有序。status 刻意不表达"谁在干、活着吗"——真活性在 Celery 侧；
     对照 sessions.lease_*=真活性字段，分野判据=**有没有抢占者需要据此判死**（摄取无抢占者）。CAS
     status==pending 会当场掐死合法重试（第二次进场已是 PROCESSING）；根因=互斥需要"所有者+到期+代次"
     即租约语义，**进度字段不含所有权语义，在原理上就不能做互斥**。站 4 并发结论：v1 无可达并发路径，
     切块步的唯一索引仲裁是重试幂等锚的免费副产品而非并发设计——注释放大了防护范围与 elif 同病（候选⑦，
     处置=按 C30 先例显式冻结前提）。锚：models.py:45,64、workers/ingest.py:71-95）
201. ⬜ 复盘补丁一：ack 是什么？acks_late 的"一格位移"改变了什么？为什么说"恰好一次投递不存在"？
     visibility_timeout 为什么从此是一条不变量？"beat 扫描重投"为什么被否决？
     （ack=broker 的签收单，唯一作用是回答"这条消息还需不需要再投"。默认 ack-early：收到即 ack→整个任务体
     跑在"消息已不存在"状态→worker 崩=恢复线索被提前销毁（不是缺恢复机制，是连线索都没了）。acks_late=
     执行完才 ack→崩溃后消息留在 unacked 被重投。**恰好一次=至少一次投递×幂等消费的合成效果**——本项目
     已有两处正确合成（M2.4 write-ahead×幂等键/M3.7 PK=幂等键×ON CONFLICT），摄取是唯一"幂等消费者造好了、
     投递停在至多一次"的地方，两行配置把拼图拼上。Redis transport 无原生 ack：kombu 用 unacked 哈希+zset
     模拟，kill -9 走 visibility_timeout（默认 3600s）扫描还原——**任务时长 ≪ visibility_timeout 是新增
     不变量**，超过它=同一消息被第二个 worker 捞走=至少一次退化成并发执行（调低它加速恢复时下限必须远大于
     最长任务时长）。扫描重投否决：卡住判据只能超时启发式→必然误判慢而未死→结构性引入并发→须给 documents
     配租约=重做一遍 M2.10；acks_late 在 unacked 期不重投、不引入并发——两修向的代价差一个数量级。
     配置改了≠行为验证了：kill -9 实录（四断言含"账本重复行≤1 批"）挂 M4.0。锚：celery_app.py:28-29、
     00 §10.1 #48、`944e5ee`）
202. ⬜ 复盘补丁二：FastAPI 的 def→线程池分诊在什么范围内生效？它与站 1 "同步依赖 ContextVar 写不回来"
     是什么关系？"send_task 毫秒级 v1 接受"这句论证错在哪？回归钉子为什么用线程身份作证词？
     （分诊只对 **FastAPI 自己调用的**路径函数/依赖生效——async 函数体内的普通同步调用原地跑在 loop 线程，
     没人帮你挪。与站 1 是同源反坑：挪线程池=保 loop 牺牲 context 连续性（ContextVar 写不回来→RLS 空集）；
     留 loop=保 context 牺牲并发（阻塞是**全进程的**：判据不是"快不快"，是最坏耗时×频率全进程能否接受）。
     论证只覆盖成功路径，而 enqueue 存在的意义之一就是会失败：broker 失联=建连超时（celery 5.6.3 默认 4s，
     实测读 defaults 非估算）×发布/连接两层重试——ECONNREFUSED（停容器）亚秒、网络黑洞秒级~十余秒；
     v1 单机 127.0.0.1 只可达前者，风险随 M4.7 容器化上升。CI 的 503 测试注入即时异常=只测语义分支不测
     阻塞形态（M2.12 教训只有前一半）。钉子用线程身份因为回退成直调**无任何行为差异可测**（照常 202 全绿）
     ——唯一可观测证词=执行线程≠loop 线程（ASGITransport 同 loop 派发，get_ident 即 loop 线程）。
     修=await run_in_threadpool 一行，异常穿池原样传回、签名/503 分支零动。锚：kb.py:77-81、
     00 §10.1 #49、`6d2c531`）
203. ⬜ kb 入口的租户身份为什么"不可表达优于表达了再拒绝"？三层怎么叠的？同一条链尾部 Celery 消息里
     tenant_id 却完全由发送者控制——这个不一致为什么可以接受？
     （KbDocumentIn 刻意无 tenant_id 字段="往别人租户塞文档"在协议层**说不出来**；校验代码会写错/被删/被绕，
     结构性缺席没有代码可错。三层：schema 不含（说不出）→值取 JWT（说了没用）→RLS WITH CHECK（代码错了
     库也拒）。消息侧可表达但可接受，因为 worker 端的信任根不是消息——任务冒充 tenant_id 进 tenant_context
     走 **app 引擎+RLS**：伪造租户 id 时步骤① SELECT 被 RLS 滤成 None→LookupError fail-loud（伪造的租户
     看不见真文档），写侧 WITH CHECK 再兜；即"消息不可信，但消费它的世界是 RLS 世界"。真正的边界=能往
     broker 写消息的人（Redis 绑 127.0.0.1+无认证=v1 已接受面）。另两道防线对照：角色矩阵（operator+）防
     知识库投毒在入口、wrap_untrusted(source="retrieval") 防内容当指令在出口——两道都在才叫"检索内容
     不可信"落地。锚：kb.py:39-41,70、workers/ingest.py:74-76）
204. ⬜ "202 的回执是一张空头支票"——本站四个单元的边界怎么在这里合流？为什么说无查询端点是"可观测性
     单点缺失"而不是一条普通的范围裁剪？
     （全仓无 GET /v1/kb/documents/{id}，而 kb.py docstring 写"document_id 即后续查询句柄"=承诺了不存在的
     东西。合流：空文本→零块 DONE（"成功地什么也没做"）／FAILED 文档已回填块照常进检索（检索 SQL 不 JOIN
     documents 不看 status——控制面说"失败了"数据面在答题）／崩溃卡 PROCESSING（补丁一前是永久）——
     **三种异常终态运维一个都看不见**，前三条边界能长期潜伏正因第四条。修的成本极低（读四列 status/
     chunk_count/error/updated_at，RLS 天然隔离，约 15 行）；归位 M4.2 治理面不在复盘顺手加（候选⑧）。
     连带：API 入口无去重（同文两传=两套 chunks 稀释 top_k 召回，seed_demo 反而有三分支幂等——两个入口
     一幂等一不幂等，候选⑨）。锚：kb.py:61-63、retrieve.py:53-59）
205. ⬜ 站 4 候选②："分层重试时，外层的捕获面必须比内层更窄或同宽"——本站哪里违反了？后果多大？怎么修？
     （EmbeddingClient 白名单只重试 RETRYABLE_ERRORS 三类、AuthError/BadRequest 裸抛不重试（docstring 明写）；
     但 Celery 壳 except Exception 无差别 retry×5——**内层的分类工作被外层抹平**：API key 配错这种 100%
     确定性失败被完整重试 6 轮（退避共约 31s、内层各打 1 次=18 次注定失败的 HTTP 调用）才 FAILED。危害低
     （401 便宜、IS NULL 保已成功批次、终态正确），但 docstring 那句"不重试"只在局部为真。修向=壳加
     except (AuthError, BadRequestError) 直接 mark_failed 不 retry（workers→gateway 层序合法）。
     一般化：写"外层兜底"前先问一句——它会不会吃掉内层刚做完的区分。锚：embeddings.py:8、
     workers/ingest.py:185-193）

## M3 全量复盘 · 站 5 检索与重排（2026-07-28 出题；rag/rerank.py / rag/retrieve.py + RetrievalProvider + #42 + 校准实录）

206. ⬜ "隔离的两层表述"（ADR-006 面试点名）：两层各是什么性质、什么机制、失败后果差在哪？
     为什么"绝不'反正有 RLS'"？
     （越权隔离=**硬保证**（安全面）：SQL 显式 WHERE tenant_id 第一防线 + RLS 第二防线，失败=数据泄漏
     不可接受；召回完整性=**质量保证**：双开关扫描模式，失败=漏几条结果、体验损失。双防线价值恰在
     **独立**——一道写在查询里、一道写在库里，绕过应用也在；任何一道被当成"反正有另一道"的理由，
     双防线就退化成单防线加一句安慰。锚：retrieve.py:3-8）
207. ⬜ HNSW 带 WHERE 为什么会漏召回？双开关各治哪一段？"备选即主选"怎么合法？
     relaxed_order 与本项目哪个组件有咬合？
     （HNSW 是近似最近邻：图遍历先取 ef_search 个索引空间近邻**然后**才 WHERE 过滤=索引内后过滤——
     租户占全表 1% 时 40 个近邻期望剩 0.4 条，LIMIT 15 实得 0/1 条：**不报错不变慢，静默查不到自己
     的数据**；租户越小被滤得越狠。小租户（≤10_000）enable_indexscan=off 强制精确扫 recall=100%；
     大租户 hnsw.iterative_scan=relaxed_order 迭代补扫（pgvector ≥0.8.0）。备选即主选：演示两租户全在
     万级下，精确扫是唯一在跑的主路径——合法性靠 01 §5 把租户规模写进产品设定，不靠含糊。
     relaxed_order 返回序轻微乱序换速度——**我们反正全池重排**，SQL 序只剩"进池资格"意义，严格序是
     白付的钱：rerank 的存在让 relaxed 白捡。锚：retrieve.py:62-63、110）
208. ⬜ `enable_indexscan = off` 是"关一类计划"还是"关一个索引"？它今天的爆炸半径为什么恰好是
     一条语句？有什么更精确的替代？
     （它关的是**计划类**（事务内所有 index scan），不是 HNSW 一个索引——恰好起效因为 HNSW 只能以
     "按距离 ORDER BY 的索引扫描"形态被用；tenant_id 的 btree 仍可走 bitmap scan（enable_bitmapscan
     未关=隐含前提）。爆炸半径=1 语句是**数据依赖保证的**：扫描模式取决于 count，所以 count 必然在
     SET 之前执行、SET 之后只剩 _SEARCH_SQL 一条——不是纪律是因果。精确替代=表达式包装
     `ORDER BY (embedding <=> ...) + 0`：优化器只按裸表达式匹配索引，+0 让**这一个 ORDER BY** 认不出
     HNSW，其余索引全不受累——语句级×索引级，vs 大锤的事务级×计划类。取舍：大锤自文档（读起来就是
     "强制精确"）且今天半径=1，留大锤对；实际计划形态（bitmap vs seq）未 EXPLAIN=观察㉑。
     锚：retrieve.py:62、109-111）
209. ⬜ SET LOCAL 为什么必须与查询同事务？这个约束和项目里哪个机制同族？"SET 确实发出了"这种
     不可见生效怎么测？
     （SET LOCAL=事务级，无 begin() 包裹时 autocommit 让它自成事务、立刻蒸发——后续查询用默认参数跑：
     **不报错不变慢，只是静默漏召回**（陷阱 4）。同族=tenant_ctx 的 set_config(..., true)：凡"改变这条
     连接行为"的状态在连接池世界必须绑事务生命周期，否则是下一个借到连接者的惊喜。测法=连接级
     before_cursor_execute 捕获，断言 SET 语句发出且与查询同连接——机制先 scratchpad 探针实证再进
     交付（test_small/large_tenant_uses_*_scan）。锚：retrieve.py:111、tenant_ctx.py:26）
210. ⬜ 检索为什么裸 SQL？"唯一入口"纪律怎么维系？CAST(:qvec AS vector) 与 1-距离换算各防什么坑？
     （00 §2.2"报表裸 SQL/实体 ORM"两头都不沾——真理由是三要件 ORM 表达不了或更糟：<=> 算子/
     SET LOCAL/CAST 文本向量传参，ORM 只提供遮蔽。唯一入口=docstring 宣告"<=> 只许在此出现"+可重跑
     grep（全仓作查询仅 _SEARCH_SQL 一处）——封装靠约定+grep，与 replay 四道普查同款手段：**裸 SQL 的
     自由用集中来赎**。CAST+具名绑定：asyncpg 只认 $n 占位，具名绑定走 SQLAlchemy 编译层（M3.3 偏差⑿
     %s 语法错同族）；向量走 pgvector 文本形态=0.5 零依赖路径写侧对偶。1-距离在 SQL 内换算：<=> 返回
     距离（0=同向），换算做在唯一入口内，出了这条 SQL 全世界只见相似度——**语义翻译做在边界上，
     消费方拿不错量纲**（陷阱 3：拿距离比阈值方向就反了）。锚：retrieve.py:50-60）
211. ⬜ rerank 凭什么存在？「优惠券」战果的完整机制？score 有几个消费者——这如何反过来解释
     "权重不进 Settings"？
     （向量检索的结构性盲区：embedding 把语义家族聚一起，对字面锚点（型号/单号/专名）不忠——R68 Pro
     与 R70 Max 是近邻（M2.11 实录：纯 CJK 专名劣于字母数字串）。战果方向反着来：off-topic「优惠券」
     打 A 语料 sim=0.4473 **> 阈值 0.35**，纯 sim 会放行离题内容进上下文；A 全库零该字面（语义锚 lint）
     →coverage=0→0.7×0.4473=0.3131<0.35 拒答。**score 两个消费者：排序＋阈值闸**——rerank 重定义了
     阈值闸的量纲，0.35 是对复合分校准的不是对裸 sim；故权重与阈值是**一对**，动一个必须重校另一个
     ——能被单独拧的旋钮不该与别的旋钮存在隐式耦合，这就是权重连注入缝都不留的理由（可注入性梯度：
     阈值有缝/扫描线有缝/时钟有缝/权重没有——**可注入性本身是一种声明**）。锚：rerank.py:19-22、
     retrieve.py:132-135）
212. ⬜ 匹配单元为什么选相邻二元组——单字和分词器各输在哪？孤字分支是防御性代码吗？跨词边界的
     二元组是噪音吗？"R680 含 R68"过匹配为什么在实践中几乎不可能错排？
     （单字：中文单字太常见，任何文本对任何查询覆盖率饱和到 1.0=信号失效；分词器：词典依赖/版本漂移/
     未登录词——"确定性的粗好过有依赖的精"（C25 不引 tiktoken 同哲学）；二元组=无词典近似分词（中文
     词多两字）。孤字分支不是防御：没有它单字查询永远零单元、0.3 权重白瞎——是唯一让单字贡献信号的
     路径。跨界二元组（"退款政策"→款政）是**特性**：它只在文本同样连续出现该四字时命中=自动奖励
     短语级连续命中，标点切 run 防误奖——一个没写短语匹配代码的短语匹配器。过匹配无害的机制=
     **分母稀释**：查询"R68 Pro 保修多久"产 {r68,pro,保修,修多,多久} 五单元，《R680 促销》只污染
     r68 一格→coverage≈0.2 vs 正主≈0.9；单个过匹配单元的污染量被钉在 1/|units|×0.3 以内，查询越具体
     单元越多、每格污染越小——**误差按单元发生，聚合后稳健**，同时 0.7×sim 侧保修问题离促销文档
     语义甚远。这就是"接受一个信号的粗糙，条件是权重与粗糙度相称"的算术版。锚：rerank.py:44-67）
213. ⬜ 阈值 `all(h.score < threshold)` 的语义精确说是什么？为什么不逐块过滤？空池为什么"天然归入
     检索失败"？
     （**集体闸=跑题检测器，不是逐块过滤器**：只有全体低于阈值才拒；一条过线则整个 top_k 连低分
     成员一起放行——阈值防离题查询（那种场景全体都低）；在题查询的 3、4 名低分块往往是同主题邻块
     带上下文价值，逐块过滤会把上下文饿死成孤块；且低分块排后面，builder 按预算装填时它们本来最先
     被挤掉——**预算是比阈值更细的第二道筛**。空池：all() 对空序列返 True=空真被正用——无语料/全被
     NULL 谓词排除/SQL 零命中三种"没东西"与"全不相关"走同一出口 []，调用方只需理解一种失败。
     锚：retrieve.py:133-135、00 §7.1 M3.5 行）
214. ⬜ 偏差(32)：AI 稿在 search 里自包 tenant_context 为什么是设计缺陷？装配 bug 传错租户时，
     有无自包各发生什么？"环境 A × 参数 B"时六步各看到什么？
     （自包看似更稳实为把 RLS 第二防线**焊死成第一防线的镜像**。装配 bug（会话属 A、参数错成 B）：
     无自包=环境 A（边界设的）×WHERE B→USING(A)∩WHERE(B)=空集，泄漏不发生、bug 以检索失败形态
     **可见**；有自包=叶子把环境也设成 B→两道防线同时放行 B→**B 语料进 A 会话**=对抗①泄漏方向。
     RLS 兜底的全部价值在"环境身份×参数租户"是**两条独立来源的交叉核验**，叶子自冒充让它退化成
     自我核验。六步推演：①embed 正常（不碰 DB）②计数 WHERE B∩USING(A)→count=0→精确扫模式
     ④空集⑥空池 all()=True→[]——**每步都向安全失败收敛，无一步需要专门代码**：交叉核验是架构
     性质不是功能。定案=身份恒由边界建立（auth 裸 set/任务内胆/脚本 main/usage+approvals 特批——
     全仓封闭名单）；search docstring 把前提写成显式契约（对照站 4 候选⑰做对了的样板）。
     锚：retrieve.py:10-12、100-104）
215. ⬜ #42 的完整弧线：缺陷为什么在 M2 是"孵化期"？修案 (a)/(b) 各是什么、为什么选 (a)？
     "失败语义属于消费边界"怎么讲？#42 为什么其实是半闭合？
     （案发=M2 复盘站 7（题 101）：context.py 第②④层裸 await provider——一抛 build 死整个 run 死；
     M2 两 provider 恒 None 不可达=零行为差异，缺陷孵化中；M3.5 接真 RAG 前夜必破壳（"检索抖一下
     杀掉整个对话"vs 00 行"检索失败走兜底"）。(b) 修 L2 builder 加 try——否：不止冻结面，C34 留痕要
     source 语境、话术可能分 provider，L2 不该知道；(a) 修 L3 适配器 try 包 provider 异常返 ()+warning，
     L2 零改动——裸 await 依旧裸，但它 await 的东西**从此承诺不抛**。深层：同一个 Retriever.search，
     AgentLoop 视角=增强层要 fail-open（C34），校准/评测/演示视角=被测对象要 fail-loud——**失败语义
     不属于共享核心，属于每个消费边界**；域对象保持诚实，吞错只发生在消费者专属的边界上（站 4
     "会不会被后续环节发现"判据的推进版）。半闭合=修复只覆盖 retrieval 侧：context.py:172 memory
     裸 await 仍在场（v1 恒 None 不可达；v2 memory 实装若不知道"fail-open 是 provider 义务"原样复发，
     该义务目前只活在 RetrievalProvider docstring——观察㉒，修=§10.3 升级路径补一句）。
     锚：context.py:171-186、retrieve.py:150-173、00 §10.1 #42）
216. ⬜ wrap_untrusted 为什么包在适配器而不是 Retriever 或 builder？防标记伪造是怎么做的？
     "包裹后文本进预算尺"防什么账目错误？
     （三选一判据=谁的世界需要什么形态：Retriever 被校准/评测/演示直调、它们要裸文本（校准打印
     h.text 找 A 字面，包了标记污染判据）；builder 是 L2 冻结面且不知道 source 填什么；适配器=进入
     prompt 注入面的唯一门口——X4：事件与库存原文，包裹只发生在注入面。防伪造：text 内出现的
     开始/结束标记字面量先被插 · 改写——否则语料自带假结束标记可"越狱"出包裹让后续内容变回指令。
     包裹在装填**之前**→_pack_snippets 量的是含标记真实负载；反序则预算系统性低估每条几十 token
     的标记开销。附：检索层 by_score=False=排序主权让渡 provider（Protocol 承诺"返回时已重排"，
     将来 MMR 类多样性交错不被 builder 一句 sorted 毁掉）；记忆层无此承诺才 by_score=True。
     锚：guardrails.py:320-328、retrieve.py:172、context.py:93-108）
217. ⬜ 校准脚本的"观察哨"设计是什么？B 检判据为什么换代——"判据的绿可能只是世界恰好简单"怎么讲？
     分离窗的长期趋势是什么？
     （threshold=0.0 实例=观察哨：让所有候选带分现形；判定谓词与生产同式（all(score<阈值)，单测钉
     同构）——**改的是观察哨参数，不是判定逻辑**（观察与判定分离）。三纪律：成本上限写死 docstring
     （6 次 embedding <¥0.0002）/scripts 不进 pytest 收集面=CI 零真实无损/身份由脚本 main 自包=封闭
     名单第三形态。B 检换代：首轮判据"B 查 A 短语→空集"能绿只因 B 恰好空库；扩容后 B 有自家语料，
     threshold=0 哨对 A 短语**必然**返回 B 自家 top-5（WHERE+RLS 结构保证只能是 B 块）——判据没变错，
     **变得不可满足**；换代=字面核证双条：①命中文本零 A 专有字面（真泄漏面）②过阈条数如实报告
     （B 用户命中 B 自家政策是合法行为不是泄漏——判据必须能区分这两者）。一般化=判据强度随语料
     几何定，世界变了判据要跟着换，否则绿灯先于代码腐烂。趋势：两轮 off-topic 分数双双上涨
     （0.19→0.209、0.3131→0.334）——语料越密离题查询语义近邻越多，**分离窗随语料增长单调收窄**；
     「优惠券」距阈 0.016 是正在消耗的余量（M4.5 挂钩；窗破时动阈值还是权重→题 211"一对"）。
     锚：scripts/calibrate_retrieval_threshold.py:8-21、36-61）

## M3 全量复盘 · 站 6 意图路由（2026-07-28 出题；`apps/support/intent.py` 140 行 + `prompts.py` 30 行）

218. ⬜ `classify` 失败就地兜成 `Intent.AGENT`，`build_classifier` 的分类器失败却抛 `ValueError` 交给上层——
     两个几乎逐行同构的分类器，为什么失败处置相反？判据是什么？
     （判据=**失败能不能在返回类型里诚实表达**。`Intent` 有 `AGENT` 这个值，语义就是"没判出来，走通用路"，
     就地 fail-open 零信息损失；`Suspicion` 三值 none/medium/high **全是断言**，没有"不知道"——把失败洗成
     NONE 就是"把不可靠输出洗成可靠裁决"，只能抛给能表达它的类型（`EntryVerdict.classifier_error` 多带一
     个字段）。一般化：**fail-open 落点必须是类型内的合法值，不能是某个正常值的僭越**。与站 5 口径⑴连读：
     站 5 答"失败语义归消费边界"，本题答"边界能不能就地吞"。锚：intent.py:98-106、guardrails.py:239-242/289-293）

219. ⬜ 分诊失败为什么落 AGENT（最慢最贵的路）而不是 FAQ（最便宜的路）？fail-open 的方向怎么选？
     （**方向必须是"更慢更贵但更正确"**：主 Agent 带历史/检索/工具/六道闸门，答案质量不降只是成本升。
     若落 FAQ 就是拿正确性换成本，且换来的错误形态恰是客服最伤信任的"自信地答非所问"。C34"降级到确定性
     兜底"没说往哪降，这一题补上判据。顺带解释"为什么不重试"：**已有一条等价正确的出路时，重试是拿确定
     的延迟换不确定的收益**。锚：intent.py:30/98-105）

220. ⬜ 你说意图分类"绝不重试"，那网关的重试与档位 fallback 算什么？
     （口径分层：`gw.calls == 1` 钉的是 **L3 侧**；L1 内部首块前的受控重试与 fast 档 flash→turbo fallback 照常
     发生且对 L3 不可见。ADR-002 的"一次调用"= **一次 `LLMRequest`**，不是一次 HTTP。两层各自的重试语义
     不叠加也不互相知情。锚：intent.py:74-80、tests/apps/test_intent.py::test_classify_gateway_error_goes_agent_and_never_retries）

221. ⬜ `_parse_intent` 为什么是"恰含词表一词"而不是"命中即取第一个"？三行代码里有几个独立决策？
     （三个：strip+lower（格式归一）／子串扫描（救"分类：faq"/"faq。"加料）／`len(hits)==1`（拒歧义）。
     ②放宽"什么算命中"、③收紧"什么算裁决"，合起来把**命中词个数当输出可靠性的代理**——模型加料越多越
     容易撞多词、越倾向落 AGENT，**宽容解析的失败方向是保守的**。隐式前提：四词互不为子串（未被断言，
     加第五类若含包含关系会恒落 AGENT）。锚：intent.py:47-63）

222. ⬜ 恰一词判据防住了歧义，防不住什么？四个词的误判代价一样吗？
     （防不住**否定与引用语境**——子串扫描判的是"提及"不是"断言"，`"用户没有要求 handoff"` → 恰 1 命中 →
     HANDOFF。代价差三个量级：rag/tool 误判**零代价**（同走主 Agent）；faq 误判被 M3.8 守卫钳制且是质量
     缺陷；**handoff 误判有真副作用**（建工单+转人工事件，不可回退）。缓冲恰好写在话术里——
     `HANDOFF_REPLY_TEMPLATE` 末句"您也可以继续补充说明"。v1 不修=概率极低（prompt 要求只输出单词）。
     观察 ㉕。锚：intent.py:51-63、prompts.py:29）

223. ⬜ v1 里这个"四分类器"实际在做几分类？它真正的权力是什么？
     （**两分类**：M3.8 拍板Ⅲ 后 RAG/TOOL/AGENT 三值走完全相同的路（00 §7.3 原话"RAG/TOOL 区分退化为分类
     语义"），所以它真正决定的只有"**要不要绕过主 Agent**"（FAQ 直答 / HANDOFF 直通）。两个推论：①容错面
     极大（词表外幻觉、RAG↔TOOL 互错全部零代价）②风险面极集中——它唯一能造成实质后果的动作，就是把请求
     送出主 Agent 的保护范围（历史层/检索/工具/六道闸门/出口守卫）。FAQ 盲窗与题 222 是这条推论的两次现形。
     RAG/TOOL 当前是"为未来保留的分辨率"。锚：intent.py:26-30、00 §7.3 M3.8 行）

224. ⬜ `Intent` 用 `StrEnum` 安全，M2.8 的 `Suspicion` 用 `StrEnum` 却埋了字典序陷阱——同一个类型选择，
     判据是什么？
     （**枚举值之间有没有序关系**。Intent 四路平权，全部用法只有相等比较与子串匹配；Suspicion 有档位序、
     要 `max()` 取严，裸 max 走字典序（"high" < "medium" < "none"）→ 修为 `_SEVERITY_ORDER` 显式序。
     选型不看类型名，看**有没有人会对它做比较运算**。锚：intent.py:23-30、guardrails.py `_SEVERITY_ORDER`）

225. ⬜ `answer_faq` 一个 `try` 都没有（异常裸传播），而消费侧 `_faq_direct` 最终还是 fail-open 回落主
     Agent——那机制侧不兜图什么？
     （题 218 判据的第二例：`answer_faq` 的返回类型是**文本流**，里面没有"不知道"。它能自兜的形态只有吐空流
     （合法但错误的值，被伪装成正常）或吐自造兜底话术（机制函数开始定政策）。而调用方手上有一张它不可能
     有的牌——`_run_main`，**换一条同样正确且更强的路**。一般化：**谁能给出"同样正确的另一条路"，处置权
     就归谁**；没有那个能力时，诚实抛出比自作主张兜底更有价值。三站连读=站 5 口径⑴（归消费边界）→ 题 218
     （能否就地吞）→ 本题（吞不了时抛给谁）。锚：intent.py:124、service.py:227-233）

226. ⬜ FAQ 直答是"先跑完流再一次性写事件"，而 executor 是"先写 `tool_call` 再执行"——同一个项目里两种
     相反的顺序，判据是什么？
     （**副作用能不能靠重跑抹平**。工具调用有外部副作用、崩溃后必须有证据才能分诊 → write-ahead；直答只产
     文本、重跑无害 → 后写，换来"失败零事件残留、回落不双写"。代价被注释老实写了："已推段作废是通道现实
     （流式代价）"。同族追问=站 7 题 232（下游为什么能更进一步做到单事务）。锚：service.py:215-249、executor.py 生命周期④）

227. ⬜ prompt 为什么不进库、非要走代码提交？
     （理由写在 prompts.py 第一行：M4.3 的"**prompt 变更 PR 必须附重录 diff**"这道门依赖它可 diff。进库＝改一行
     没有 diff、没有 review、不触发重录——prompt 是模型行为的一半，把它挪出版本控制等于让一半的行为变更不可
     追溯。反面配套=租户侧 FAQ digest **确实**在库里，判据见题 230。锚：prompts.py:1-2）

228. ⬜ M2.6 决定"cassette 匹配键不含 prompt 哈希"，当时看像不够严格。它在 M3.12 兑现成什么？
     （**严格性 ↔ 可演进性的取舍在还账**：M3.12 规则 3 具体化是冻结后首次改 prompt，按纪律附五盘重录（实付
     ¥0.006），而既有回放测试**一条没红**——因为匹配键是 `(session_id, scope, 道内序号)`。若当初把 prompt 哈希
     做进匹配键，形式上更严，代价是每改一个字全部 cassette 测试变红，且**无法区分"prompt 变了"与"行为回归了"**。
     锚：replay.py 匹配键（C10/D2）、commit `8cc58ba`）

229. ⬜ FAQ 直答的模型输出过 `OutputGuard`，而 HANDOFF/FALLBACK 话术直接出帧不过守卫——判据是什么？
     反向推论是什么？
     （守卫防的是**模型把不该说的说出来**（system 片段/工具名/他人 PII）；系统话术是自己写死的确定性字符串，
     过守卫零收益、纯误杀风险（如 ticket_id 撞模式）。反向推论才是要记的那半：**任何"看着像我们写的、实际
     经过模型"的文本都必须过守卫**——FAQ 直答就是那个反例（system 是租户配置、输出是模型生成），故 M3.8
     拍板Ⅳ 把守卫补在这条通道上。锚：service.py:208-226 vs 270/349）

230. ⬜ 平台 SYSTEM_PROMPT 不进库、租户 faq_digest 却在 `tenants.config` 里——同样是进模型的 system 内容，
     判据是什么？这个判据的代价是什么？
     （判据是**谁是它的作者**：平台规则的作者是我们（PR+review+重录门），租户 FAQ 的作者是租户（要求租户改
     FAQ 得发版是荒谬的，#21 治理路径=种子即初始化入口、运行期只读）。代价=租户侧 prompt **不在"定了不动"
     纪律与 M4.3 重录门覆盖面内**：digest 改了没有任何机制知道，且 L3 cassette 录的是旧 digest、匹配键又不含
     prompt → **回放照绿=假绿**。观察 ㉗。锚：intent.py:120-121、seed_demo.py:52-55/66-69）

231. ⬜ M3.12 兜底率 R1 的真编造（赠品品牌/供应商）为什么改 prompt 有效，而原来的"绝不编造答案"无效？
     （**抽象禁令对模型无效**——它不认为自己在编造，它认为自己在用常识。修法是把禁令**具体化到事实品类**：
     "对品牌、供应商、赠品、活动、日期、价格等具体事实，凡知识库与工具给不出依据的，一律按『没有找到相关
     信息』处理，禁止凭常识或行业惯例推测作答"。三轮闭环 60→80→100（R2 的 20% 是判据漏报「暂未/暂无」合法
     变体，属信号集问题不是模型问题——**真编造 vs 判据漏报的判准=回答里有无语料外具体事实断言**）。
     残余缺口见题 244。锚：prompts.py:17-19、commit `8cc58ba`）

## M3 全量复盘 · 站 7 模拟业务系统（2026-07-28 出题；`mock_backend/{models,app,client}.py` 302 行 + 迁移 `f4b8d2a97c31`）

232. ⬜ executor 是"write-ahead 留证据、崩溃后分诊"，mock 下游却能做到"单事务、崩溃零中间态"——
     同一条哲学两种实现，判据是什么？
     （**副作用在不在同一个事务边界内**。L2 的"执行"是跨进程 HTTP 调用，数据库回滚不了它，只能退而求其次
     留证据；下游的"执行"就是同库 UPDATE，于是可以升级到最强形态：claim 与结果快照要么同时可见要么都不在。
     推论：**X1"结果不明"只存在于 L2**——下游内部没有不明，不明是跨边界通信的产物。
     锚：app.py:85-111、executor.py 生命周期④、题 226 同族）

233. ⬜ `_claim_and_execute` 里校验失败（409）会连 claim 行一起回滚——"失败不烧钥匙"违反了幂等键的严格
     定义（同键同结果），为什么这是对的？
     （真正需要幂等保护的是"**执行成功但响应丢失**"——那种情况 claim 已提交，重发拿 `duplicate:True` 回放，零
     双写；而 409 意味着**零副作用**，固化它没有任何安全收益，只有"业务状态变了却退不了款"的麻烦。更要命的
     反例：若失败也烧钥匙，一次瞬时校验故障就把这个 `tool_call_id` **永久毒化**，而该键不可再生（它是事件 id）。
     口径：**只对有副作用的成功路径固化钥匙**。锚：app.py:88-94/107-111、refunds.py:32-34）

234. ⬜ `mock_write_ops` 为什么把幂等键做成**主键**，而不是 `id` 自增 + 幂等键唯一索引？
     （把业务不变量编码进主键，**仲裁权就交给数据库**：去重不需要"先查再写"（TOCTOU），一次
     `INSERT ... ON CONFLICT DO NOTHING` + `rowcount` 判定就是全部算法；并发同键由唯一索引阻塞仲裁，应用层零锁。
     配套的物质基础是"台账跨崩溃存活"——M2.10 的恢复语义"半截工具＝幂等键安全重发"若配内存字典，重启即忘
     ＝等于没有去重。锚：models.py:47-61、app.py:97-106）

235. ⬜ 租户过滤做在 mock 内、用户归属校验做在工具里——这条分界线的现实依据是什么？
     （**外部业务系统本来就按商户分区**（它知道这是哪家店的单），但它**不知道你的登录态**（不可能替你判这个
     用户能不能看这单）。所以读端点老实把 `user_id` 交出来，判定权留给工具——"防线不从工具漂到 mock"。
     价值在 mock 的**忠实度**：假系统必须模拟真系统的**无知**；把归属校验塞进 mock，等于在演示里假设外部系统
     替你做了授权，而那正是真实世界最常见的越权成因。偏差(40) 就是这条收窄。锚：app.py:6-7/149-162、_shared.py:21-35）

236. ⬜ M3.3 的 `ALTER DEFAULT PRIVILEGES` 已经让未来表自动带 DML 授权，为什么每张新表的迁移还要自己
     `ENABLE RLS` + 建策略？
     （**RLS 不隐式继承**——DEFAULT PRIVILEGES 只管 GRANT（DML 授权），行级安全是表自身属性，新表默认是关的。
     所以 M3.3 登记了"前置义务"：每张带 `tenant_id` 的新表在自己的迁移里自补，M3.4（documents/chunks）第一次
     兑现、M3.7（mock 两表）第二次。策略写 `USING`+`WITH CHECK` 双子句：站 1 探针证明缺 WITH CHECK 时写侧会
     **回落到 USING**（故"只写 USING 就能越权写"是错的），双写的真价值在 USING 将来放宽时写侧不会静默跟着放宽。
     锚：migrations/f4b8d2a97c31:51-57、c895f9007bf7）

237. ⬜ `f4b8d2a97c31` 的 downgrade 直接 drop 两张表，而 M3.3 那份迁移的 downgrade 却**保留** `aegis_app` 角色——
     判据是什么？
     （**对象的生命周期范围**：表是本迁移创建的私有对象，删了只影响自己；角色是**集群级共享对象**，删了会波及
     同集群的别的库/别的迁移链。策略与索引随表删除，不用单独写。锚：f4b8d2a97c31:60-63 vs c895f9007bf7 downgrade）

238. ⬜ 进程内 ASGITransport 省掉了网络，为什么说它**没有**省掉语义？举三样它保住的东西。
     （①**请求头**：`Idempotency-Key` 走 header 才能模拟"下游按 header 去重"，换成函数参数就模拟不出来；
     ②**状态码分层**：400/404/409/503 各司其职，工具侧"409 回 dict 不进连败账"、"503 走 ERROR"这些分诊规则
     才有真实判据；③**异常家族**：#43 那条"发出前 ConnectError 可改道 / 发出后 HTTPError 转 TimeoutError 交 X1"
     是 **httpx 异常树上的事实**，只有真 httpx 栈才有。口径：**假的边界要假到能复现真边界上的失败分类**。
     锚：app.py:1-8、_shared.py:38-51）

239. ⬜ mock 为什么"绝不挂载到主 app"（拍板Ⅱ）？这个不变量今天靠什么维持？
     （mock 的 `tenant_id`/`user_id` 是**裸参数**（无认证无授权无归属校验，这是它模拟外部系统的必要形态）——
     挂上主 app 就是开了一个**未认证的水平越权入口**：任何人 `POST /refunds {"tenant_id":"别家"}` 就能退别人的钱。
     "信任内部调用方"这个假设，只在**外部到不了它**时成立。今天靠 grep 可核（11 个 `create_mock_api` 调用点零
     `app.mount`），但**无 CI 钉子**（观察 ㉞，一条断言即可）。锚：app.py:3-6、client.py:3-4）

240. ⬜ 【用户追问】worker 每次任务直接 `httpx.AsyncClient(transport=ASGITransport(app=create_mock_api(参数)))`
     不就行了？为什么还要一个 `set_mock_client` 函数？
     （**造得对 ≠ 送得到**，是两个问题。worker 确实就是这么造的（hitl.py:141-143），但工具走的是
     `AgentRuntime → AgentLoop → ToolExecutor → 工具函数 → _shared → mock_client()` 五层，**中间没有一层带 client
     参数**——不安装的话那个局部变量无人读取，工具照样调 `mock_client()` 拿到进程单例。想把 client 传下去只有
     四条路且全撞墙：加进工具签名（进 LLM 可见 schema）／加进 `ToolContext`（L2 冻结契约，分层倒挂）／
     `AgentRuntime`+`AgentLoop`+`ToolExecutor` 逐层加参（L2 冻结面，且只是第一层）。**模块全局是唯一零签名改动
     的通道**，`set_mock_client` 就是它的写入口。类比：worker 换了新手机，工具那本通讯录上只有一个号码
     `mock_client()`——不改通讯录，它们打的还是老号码。也答"为什么不干脆每次新建"：每次工具调用重建整个
     FastAPI 应用，且 `app.state.tickets` 每次清零。锚：client.py:29-36、hitl.py:140-156、_shared.py:28/47）

241. ⬜ 【用户追问】迁移里建的 RLS 策略，用 owner session 连接时会检查吗？
     （**一层都不过**。三重豁免任一成立即绕过（站 1 探针实测）：superuser ✅／`BYPASSRLS` 属性 ✅／**表 owner +
     `force_rls=false`** ✅（9 表全 `f`）。第三条最易漏：PG 默认让表 owner 豁免自己表上的 RLS，除非显式
     `FORCE ROW LEVEL SECURITY`。所以 owner 连接下 `current_setting('app.tenant_id')` 根本不被求值。三种后果：
     ①测试世界没有第 4 层（#47）②反方向的 app 引擎在 `tenant_context` 外读＝**静默空集**（M3.12 对账面归零）
     ③mock 第二层在不在取决于注入什么工厂（观察 ㉚）。**豁免不是缺口而是 D4 维护面的必要条件**（reaper 跨租户
     扫描/种子/对账必须看得见全部）；不开 FORCE 的取舍=用两条引擎物理分离表达"谁该看全部"，比 FORCE 的
     "谁都不许看"更贴意图。锚：db.py:32-71、站 1 探针⑵）

242. ⬜ 【用户追问】`mock_backend/app.py` 为什么不用 `tenant_context(tenant_id)` 包一层？
     （**因为它是叶子，叶子自设租户上下文＝用参数冒充身份**。合法设身份的封闭名单五处，共同点是 tenant_id
     都不是"调用方随口给的参数"：auth 裸 set（已验签 JWT，auth.py:144）／worker 任务内胆 with（任务参数+库里
     归属）／usage（403 判定通过后的显式特批）／approvals（库里的单据）／脚本 main（自宣告）。而 mock 的
     tenant_id 是**它无从验证的字符串**。若包上，`app.tenant_id` 与 WHERE 用**同一个输入** → RLS 从独立的第二道
     退化成 WHERE 的复读机（＝站 5 偏差(32) 叶子自冒充的同型）。不包，则 RLS 用**最外层建立的真身份**、WHERE 用
     参数，两者必须同时命中才可见＝**交叉核验**；工具被诱导传别家 tenant_id → 空集 404，失败得干净。
     口径：**要取什么可以由参数说了算，你是谁只能由边界说了算**。ASGITransport 同上下文让 ContextVar 天然穿透
     是白拿的红利；真独立部署时正解是"mock 自己做认证"，而不是"mock 自己 set 上下文"。锚：app.py:70-79、
     tenant_ctx.py:29-44、auth.py:144）

243. ⬜ 注入器最坏的危害是什么？为什么 `_no_mock_injection_in_prod` 必须炸在启动期？
     （最坏的不是"造故障"，是造出**你分辨不出来源的**故障——config.py:92 原话"故障与真实上游故障不可区分"，
     排障时你会去查上游而病因在自己的配置里。与 `parse_routes`/`_no_fault_injection_in_prod`/
     `_lease_renew_shorter_than_ttl` 同一哲学：**配置错误在启动时炸，不在凌晨的流量里炸**。运行期任何时刻发现
     都太晚。锚：config.py:86-103）

244. ⬜ 跨 event loop 单例陷阱在本项目出现过三次，三次修法都不同。约束怎么决定修法？还缺什么？
     （①M2.9 `get_redis()`：**30 个构造点** → 构造点显式传（`lock=None` 直通）；②M3.4② embedding `shared_client`：
     消费方是 `build_embedding_client(...)` **有装配期** → 工厂参数直通；③M3.9④ `mock_client()`：消费方是被
     registry 调用的工具函数、**没有装配期** → 安装缝。**判据=消费方有没有一个"你能塞参数进去"的时刻**。
     缺的是共性防线：三次都靠 docstring 警告，没有任何机制能在第四次提前报警（最小形态=单例记录创建时
     `get_running_loop()`，不一致就抛人话异常，而不是等 keep-alive 炸出裸 RuntimeError）。观察 ㉝。
     锚：client.py:1-7、redis.py、gateway/factory.py）

245. ⬜ "影子库工艺"解决的是哪一类漏检？为什么日常开发库跑绿不够？
     （**增量迁移绿 ≠ 裸库自举绿**。开发库是一路 upgrade 上来的，`alembic upgrade head` 成功只证明"从上一版到
     这一版"可行；而真实部署（CI service container / M4.7 容器化）是**空库跑全链**——迁移间的隐式顺序依赖、
     `CREATE EXTENSION` 缺失（M3.4 踩过）、conftest `create_all` 兜底掩盖问题，都只在裸库现形。M3.7① 首次引入
     `aegis_shadow` 空库七级迁移链全量重放，此后成为迁移类交付标配，且同时充当交付稿排练场（抓出过
     `AgentEvent.type` 误写、多余 aclosing、PS1 无 BOM）。锚：plans 14g 交付①、14h/14i 各次排练记录）

246. ⬜ `normalize_events`（C31）只别名化两样，为什么 `ticket_id` 会成为 M4.3 的阻塞点？修向选哪个？
     （C31 只别名化事件 `id`（e1..eN）与 `payload["approval_id"]`（a1..aM），**payload 其余字段原样进比对**。
     `ticket_create` 的 `ticket_id=uuid4().hex` 同时出现在 HANDOFF 事件 payload 与话术正文
     （`工单号 {ticket_id}`）——所以只要 M4.3 回放集含转人工会话，逐事件比对**必然两处 diff**。
     修向：**给 mock 加确定性 id 注入缝**（计数器/时钟注入）＞ 给 C31 加别名——因为别名化的是 payload 的**键**，
     够不到 `content` 里那串字符，而注入缝让 payload 与话术同时变确定、C31 一行不用改。观察 ㉜，挂 M4.3 开工核对。
     锚：replay.py:311-325、app.py:171-175、service.py:264/268）

## M3 全量复盘 · 站 8 工具五件（2026-07-28 出题；`tools/_shared.py`+五工具 193 行，#6/#38/#43）

247. ⬜ "订单不存在"与"订单不是你的"为什么必须逐字节同话术？统一话术堵的是哪个 oracle？
     （区分两者＝给出一个**订单号有效性预言机**：攻击者用任意单号去探，回"无权"就说明该单真实存在。而演示
     单号形如 `AZ-20260701-0042`——**日期+序号结构可枚举**，一个 oracle 就能测出租户的订单量、下单节奏、编号
     规律。与站 3 `_ensure_session`"不泄露存在性"（404 而非 403）是同一纪律的两次实装；#46 则是这条纪律在 RLS
     之后被**意外破坏**（500 vs 200 成了新 oracle）——同一纪律两次成功一次翻车。锚：_shared.py:16-18/21-35）

248. ⬜ 同一个工具里，归属不过 `return {"error": ...}`、503 却 `raise_for_status()` 裸抛——判据是什么？
     选错会怎样？
     （**能构成"答案"的失败回 dict，不能构成答案的失败抛异常**。归属不过是一次**成功的观察**（系统正常工作，
     答案是"不行"），该进 `tool_result` 让模型看见并改口；503 是**工具故障**，该进 `tool_error` 并**计入连败账**
     （闸门 #4，连续 N 次禁用该工具）。选错的后果：把业务拒绝抛成异常 → 正常的"不行"污染健康度统计 → 最终
     把好工具禁掉。锚：_shared.py:29-34、orders.py:17-18、refunds.py:32-35）

249. ⬜ 为什么"归属校验 fail-closed（对抗③）"这种话必须写成函数体注释，不能写进 docstring？
     （因为 `@tool` 把 docstring 抽成 `ToolDef.description`，而它**逐字进入每一次 LLM 请求的 tool schema**：
     ①每轮多烧常驻 token；②把内部防线告诉模型（无收益，违反最小知情）。所以约定是 **docstring 只写模型需要
     知道的（干什么、参数什么意思），机制/防线/横切编号一律写函数体内注释**，五个工具无一例外。配套：
     `ToolDef.__post_init__` 强制 description 非空——"空说明书=盲选工具"。锚：orders.py:13-15、tools.py ToolDef 校验）

250. ⬜ #43 为什么把"发出后传输错"转成 `TimeoutError`，而不是新造一个异常类型？
     （**当一个新故障与既有故障"物理上不可区分"时，正确做法是映射到既有类型而不是新增类型**——新类型意味着
     所有下游都要学会处理它。executor 已有成熟的 X1 路径（`except TimeoutError` + WRITE → RESULT_UNKNOWN +
     "禁止重试该操作，请先用查询类工具确认"），转过去即复用，**executor 零改动**＝修案(a) 的全部价值；修案(b)
     加新分支要动 L2 冻结面而语义完全一样。分界线本身是"副作用可能性"：连接未建立=零副作用可改道／已发出=
     结果不明须封死重试。锚：_shared.py:38-51、executor.py:187-199）

251. ⬜ 写工具"绝不自动重试"有两层保险，分别在哪？为什么要两层？
     （类型层：`ToolDef.__post_init__` —— 写工具 `retries > 0` 直接 `ValueError`（注册期炸）；执行层：
     `attempts_allowed = 1 + (tool.retries if READ else 0)` —— 即便类型层被绕过（比如手工构造 ToolDef），写也只跑
     一次。两层的意义：**一层是"写不出来"，一层是"写出来也没用"**；重试写操作会生成新幂等键，下游去重当场
     失效。锚：tools.py ToolDef 校验、executor.py:178）

252. ⬜ 归属校验通过之后到写请求发出之间有一个窗口，下游只兜状态不兜归属。为什么普通调用接受这个窗口，
     HITL 却必须重校验？
     （**判据是窗口时长，不是窗口是否存在**——窗口总是存在的。普通工具调用毫秒级 → 接受；HITL 批准间隔可达
     `approval_ttl_s=3600` → 必须重校验，这正是 M3.9 `revalidate`（快照业务新鲜度）+ 批准执行期 handler 以真实
     ctx 重做归属的正当性来源。真实系统的第三种处置=让下游也校验归属，或带着校验结论的令牌去写。观察 ㉟。
     锚：refunds.py:24-31、app.py:70-79（下游只按 tenant 过滤）、revalidate.py）

253. ⬜ `RiskPolicy` 的签名是 `(args, tenant_config) -> bool`，**没有 ctx**。这是遗漏还是设计？硬理由是什么？
     （设计，且硬理由不是"分工整洁"而是 executor.py:148 那行 `if not approved and tool.risk_policy is not None`——
     **闸门可以被一次人工批准整段跳过，权限不可以**。若谓词能拿到 ctx，迟早有人在里面写
     `order.user_id == ctx.user_id`：①越权请求从"拒绝"降级成"挂起等审批"（安全事件变工作流事件）；②坐席点
     批准 → `approved=True` → 闸门跳过 → **越权被执行**。一般化：**能被推翻的判定与不能被推翻的判定必须住在
     不同函数里，且后者的输入不能出现在前者签名上**。锚：tools.py `RiskPolicy`、refunds.py:13-17、executor.py:146-156）

254. ⬜ 风险闸门在 write-ahead **之前**（生命周期 ④ 在 ⑤ 之前），这个顺序有哪三个后果？
     （①命中审批的调用**没有 tool_call 事件、没有幂等键**——键是批准后重走生命周期时才铸出来的；②因此"审批
     期间崩溃"在安全面零风险（从未铸键=从未 write-ahead=下游从未收到请求），这正是 #44"安全面 ✅、语义面 ⚠️"
     的结构来源；③恢复重执行必须带 `approved=True` 豁免闸门，否则**必再命中 → 无限挂起**。
     锚：executor.py:146-172）

255. ⬜ 恢复执行时闸门被豁免、参数校验却要重跑——判据是什么？
     （**人批准的是"这件事"，不是"这段字节"**：风险闸门是"人已经对这件事表过态了，再问一次是死循环"；参数
     合法性是这件事本身的属性，与谁批准无关，故回炉重验。executor 注释原话："参数校验①不豁免（回炉重验）"。
     锚：executor.py:146-147）

256. ⬜ M2.3 的注册期防呆已经保证"写工具必须有 risk_policy 或 risk_exempt"，为什么还要
     `test_declarations_ledger` 这张清单测试？
     （**防呆只保证"非空"，不保证"正确"**——把五个工具全标 `risk_exempt=True` 一样过防呆，而所有审批闸门就此
     蒸发、没有任何红灯（评审 C15 担心的"批量豁免糊弄过防呆"）。清单测试逐个点名每个工具的三元组，改声明就
     **必须同时改测试**＝把一次静默的配置改动变成必须进 diff、必须过 review 的显式动作。口径：**机器能判定的
     （形状合法）交给防呆，人必须看见的（决策本身）交给清单测试**。锚：tests/apps/test_tools_contract.py:21-32）

257. ⬜ 工具参数 `amount: float`（LLM schema 只有 number），钱又"绝不过 float"——这条链上精度损失点有几个？
     （**一个，且在外部约束那一侧**。进门第一行 `Decimal(str(amount))` 而非 `Decimal(amount)`——后者会把 float 的
     二进制误差吸进来（`Decimal(0.1)` = 0.1000000000000000055511…）。完整链路：LLM float → `str()` → Decimal →
     `str(dec)` → JSON → 下游 pydantic `Decimal(gt=0)` → `Numeric(12,2)`，此后全程无损。两端都守住，中间那段
     JSON 才有意义（站 7 是下游侧的同一条纪律）。锚：refunds.py:23/29、app.py:48-55、models.py:42）

258. ⬜ `refund_needs_approval` 缺省 200、`coupon_needs_approval` 缺省 0——同族闸门的缺省失败方向相反，
     哪个对？为什么这算缺陷？
     （coupon 的 0 是 **fail-closed**（缺键＝任意正面额都挂审批）且注释明写；refund 的 200 是 **fail-open**（缺键＝
     200 元以下静默直接退款，无审批无告警无痕迹），而 00 §2.2 口径是"安全闸门 fail-closed"。病灶不是数值选错，
     是**失败方向从未进入议程**——200 只是把演示值搬进了缺省位。可达性不低：#21 治理路径是"种子即初始化入口"，
     新租户开通漏配一个键是现实运维事故，症状是闸门静默降级。修向：缺省改 0（与 coupon 对齐）或**缺键即启动炸**
     （与 `build_agent_spec` 对未知工具名的处置同款，更合本项目哲学）。观察 ㊲，建议 M4.0 顺手。
     锚：refunds.py:13-17 vs coupons.py:13-16、agent.py:39-42）

## M3 全量复盘 · 站 9 主 Agent 装配与服务层（2026-08-02 出题；`apps/support/agent.py` 47 + `handoff.py` 49 + `service.py` 324 行，含 M3.10 流式化面）

259. ⬜ `build_agent_spec` 把配置分成三级（平台常量 / 租户 config / 调用方参数），判据是什么？
     为什么 `owned_values` 走 keyword 参数而不是从 `tenant.config` 读？
     （判据＝**谁有权改它、改错了谁受伤**：改 prompts.py 波及全部租户且要付重录费（M4.3）→ 平台级写死在代码；
     改 tenant-a 的 tools 只伤 A → 租户级走 config；`owned_values` 是**用户级**数据（本人 PII 允许清单 C23），
     同一租户里每个用户都不同，放进租户 config 在数据模型上就是错的。三级分层直接刻在签名上。
     锚：agent.py:29/43-55）

260. ⬜ 为什么不给租户 B 装退款工具"反正闸门会拦"？两层理由。
     （⑴ **闸门可被一次批准整段跳过**（executor 的 `if not approved`，站 8 口径⑵）——装上等于把"坐席误批一次"
     铺到本不该有退款能力的租户；权限判定与风险闸门是两道防线，不能拿后者当前者。⑵ **工具 schema 会进 prompt**，
     装上就等于告诉模型"你有这个能力"，幻觉调用与社工诱导的表面积当场变大。不装＝物理上不可能，是唯一不依赖
     任何运行期判定的防线。锚：agent.py:39-45、§4.8 陷阱 2）

261. ⬜ 租户 config 里写了未知工具名，为什么选"炸"而不是"忽略"？
     （两种错误方向**症状不对称**：多给＝越权（危险但显眼），少给＝功能缺失（症状是"模型说我做不了"，排查者
     会依次怀疑 prompt、模型、工具实现，**最后才想到查 config 拼写**）。炸掉把配置错误变成自带"可用：[...]"
     清单的显式报错。同一哲学第三次出现：`parse_routes` 启动校验 / `build_classifier` 严格白名单 / 本处。
     锚：agent.py:40-42）

262. ⬜ `build_agent_spec` 收 `TenantRecord` 而不是 `tenant_id`——这个选择带来哪三个后果？
     （⑴ 装配器**无 IO、纯函数**，查库/缓存/租户行缺失合成的脏活全在 `ChatService.resolve_tenant`，脏活与纯函数
     的分界画在模块边界上；⑵ 测试零 DB（ORM 类不挂 session 就是普通对象）；⑶ **回放确定性**——M3.11 五盘 cassette
     的 spec 从种子常量构造，录制期与回放期共用同一装配器（I1 定义性同源），装配器若读时钟/随机/环境变量，回放
     就不可能。锚：agent.py:29、test_agent_assembly.py:20-21、test_l3_cassette_smoke.py:90/120）

263. ⬜ 为什么缺省值写 `LoopPolicy().session_token_budget` 而不是字面量 `50_000`？
     （单一事实源。反面教材是 08 §8 #10 那个挂点：`LoopPolicy.tool_step_timeout_s` 与 `ToolExecutor.default_timeout_s`
     两处各写 `30.0`、靠**巧合相等**维系，M2.7 总装时必须显式接线才关掉。M3.11 拍板 2 更进一步：`approval_ttl_s=3600`
     显式落种子，连缺省路径都不走。锚：agent.py:47-48、seed_demo TENANTS）

264. ⬜ `session_token_budget`（钱）给租户配，`model_tier`（也是钱）却硬编码 `"standard"`——判据是什么？
     （开放题。一种答法：预算是**租户自己的钱**（超了只伤自己），档位是**平台的成本/质量曲线**（各租户混跑同一批
     模型，改档影响容量规划与缓存命中面）。另一种答法：v1 只是没到那一步，两者同族，属配置居所判据（题 90）的
     未决边界。答题要能说出"放开会引入什么新问题"（租户全选 strong＝平台成本失控，必须配预算联动）。锚：agent.py:51）

265. ⬜ `dict.fromkeys` 去重与 `AgentSpec.__post_init__` 的重名防呆是两道同向防线，为什么都要？
     （分工不同：装配器这道是**消化**（config 重复写两遍 order_query 是无害手滑），spec 那道是**钉死**（真重名＝
     dispatch 表无法唯一路由必须炸）。一般化：**能被上游安全消化的输入畸形就消化掉，不能的才让下游炸**。
     锚：agent.py:45、spec.py:165-168）

266. ⬜ `entry_classifier` 按租户开关、缺省关，而两个演示租户都没配——这件事对外该怎么表述？
     （事实：M2.8 那 564 行护栏里的**入口 LLM 分类器在 L3 全程零消费、五盘 cassette 零覆盖**，生效的只有 14 条
     规则库底座。诚实表述＝"分类器按租户开通、v1 演示租户未开通，规则库是无条件底座"；拔高表述＝"入口有 LLM
     语义分类"（一问就穿）。观察 ㊴。锚：agent.py:54、spec.py:156-158）

267. ⬜ L2 已经给了 `text_sink` 这条缝，为什么 L3 还必须再解一次耦（队列 + 后台 task）？
     （因为**回调式产出与生成器式消费天然不同步**：`handle` 只有在消费者调 `__anext__` 时才有执行权，而
     `async for event in runtime.run(...)` 期间控制权在 run 手上，此时 `text_sink` 被调用也无处 `yield`（yield 只能
     发生在 `__anext__` 的调用栈里）。中间必须有缓冲。M3.8 的同步汇合点形态下首 token 延迟＝整个 run 时长。
     锚：service.py:159-169、loop.py:505-511）

268. ⬜ "消费者断连不取消生产者"在机制上靠什么成立？反例的代价是什么？
     （机制：`handle` 是 async generator，断连→`_relay` 停止迭代→生成器 `aclose()`→`GeneratorExit` 在 `yield frame`
     处抛出→while 被撕开→**`await produced` 那一行根本不执行**；生产者是独立 task 不受影响。反例代价要说具体：
     断连即取消＝用户网络抖一下，正在执行的退款工具被 cancel 在半路——而 X1"结果不明"整套 write-ahead/幂等键/
     reaper 分诊就是为避免这种半截。**为省一点内存把生产掐死，等于把恢复机制的适用面无谓扩大一倍**。
     锚：service.py:167-169、chat.py:109-118）

269. ⬜ 帧队列为什么必须无界（`asyncio.Queue()` 默认 maxsize=0）？
     （有界的话断连后没人取帧，生产者阻塞在 `put` 上＝观察者离场把事实生产掐死，与 ADR-007 断线语义正相反。
     代价是帧堆内存，上界＝一次 run 的帧数。锚：service.py:161）

270. ⬜ `_BACKGROUND.add(task)` 与 `task.add_done_callback(_reap_producer)` 各防什么？
     （**入池防 GC**：`create_task` 返回的 task 事件循环只持弱引用，无强引用可能在跑完前被回收（CPython 文档明载）。
     **出池防泄漏**：只进不出会让模块级 set 单调增长，每个滞留 task 牵着整张引用图。回调第二件事是 `task.exception()`
     **取回异常**——断连路径下 `await produced` 不执行、无人取回，GC 时会打 `Task exception was never retrieved` ERROR；
     先判 `cancelled()` 因为对已取消 task 调 `.exception()` 会抛 CancelledError。**两件事都不能写在 `_produce` 的
     finally 里**：异常由 task 对象持有，协程自己取不回自己。锚：service.py:64-74/165-166）

271. ⬜ `_TokenEmitter` 为什么必须是一个类、且每请求新建一个？
     （L2 只肯给一个 `Callable[[str], Awaitable[None]]`，而 L3 收到每段文本要同时做三件事（入帧队列 / 写 msgbuf /
     本轮记账）——**对外是函数（`emitter.emit` 是绑定方法）、对内握三份状态**。而 `ChatService` 是进程级单例，
     per-request 状态上 `self` 会导致甲的 token 累进乙的 `_acc`、乙的 `mark_turn` 清零甲的记账，并发越高越像
     "偶发灵异"。锚：service.py:77-113/126-127、main.py:87-94）

272. ⬜ `_TokenEmitter` 的三份状态各是什么口径、各由谁读、什么时候读？
     （`_queue` 存**增量**→本请求 `handle` 立刻读；`_acc` 存**请求内全量**→落 Redis，读者是**另一个 HTTP 请求**
     （GET /stream）可能在另一进程、可能永不读；`turn_text` 存**轮内全量**（llm_call 清零）→本请求 `_run_main` 在
     assistant_message 事件到达时读。三者跨进程/跨请求/跨时刻都对不齐，且队列是消耗型的（get 即出队），所以不能
     共用。线索：只有 `turn_text` 不带下划线——**下划线在这里是读面声明**。锚：service.py:85-105、stream.py:142、service.py:315）

273. ⬜ "先写 msgbuf 后入帧"是什么形式的契约？反序会出现什么用户可见现象？谁兑付它？
     （契约＝"**消费到帧 ⇒ 缓冲一定可见**"，保证任何时刻断线，GET 侧能重推的不少于用户已见。反序则"重连后半句话
     往回退"。兑付点在 GET 通道：回放完事件、接活尾之前读一次 msgbuf 发 `message_reset`。**用最弱的假设（一个写序）
     换够用的保证**。锚：service.py:96-105、stream.py:138-146）

274. ⬜ 主 Agent 路 user_message 先落盘（write-ahead），直答路却"先答后写"——同一系统里两种相反顺序怎么都对？
     （判据＝**这条路有没有副作用**。主路后面要执行工具，事实必须先于副作用；直答路整条零副作用，"失败零残留"
     更值钱——回落主 Agent 时不双写 user_message。代价是崩溃窗形态翻转：从"系统记了但用户没看到"变成"**用户看到了
     但系统不知道**"（观察 ㊷）。锚：loop.py:221、service.py:249/274-282）

275. ⬜ FAQ 直答守卫三个条件各挡什么？为什么判据落在 messages 投影计数上而不是"让分类器判自足性"？
     （三条件：分类＝FAQ（概率）∧ 租户配了 faq 摘要（确定）∧ **无历史**（确定，承重）。分类器的自足性判断不可验证
     且 M3.6 实录已证会误判「一般要多久？」；"是不是第一条消息"是确定性事实，恰是盲窗的**充分条件**。用 messages
     投影还有红利：**直答轮自己也写投影（D7），故第二轮起守卫自动关闭，不需要额外状态**。锚：service.py:178/187-195）

276. ⬜ prompt 侧限定（INTENT_PROMPT 加"仅当不依赖上文"）与代码侧守卫，为什么两半都做？
     （prompt 那半是"尽量别判错"，守卫这半是"判错了也不致命"。真正判据是**保证的可验证性**——prompt 侧只能靠实测
     抽样，守卫侧是能进 CI 的断言。一般化：能用确定性事实钳住的，绝不交给模型自觉。
     锚：intent.py:41、tests/apps/test_service.py:94-105）

277. ⬜ "兜底路径的依赖必须比主路径更少"——本项目哪里违反了？三种失败形态各是什么？
     （违反处＝兜底路径②**必须成功调通一次外部 HTTP 建单**，而主路径不需要 mock 后端。三形态：⑴预算类终止（首帧前
     就拦下）→`HTTPStatusError` 不在 chat.py except 阶梯→**HTTP 500 空响应**，信息量比不兜底还少；⑵循环类（已推
     token）→error 帧收尾；⑶建单成功后进程死→**孤儿工单**，且 `/tickets` 不读幂等键、重试必重复建单。观察 ㊻。
     锚：service.py:341-350、handoff.py:48-57、mock_backend/app.py:140-147/171-175）

278. ⬜ `FALLBACK_LOOP_LIMIT` 里"（已生成工单）"五个字如何约束了修法空间？
     （**话术即契约**：这句话已把"必须先建单成功"写进流程，所以"建单失败也照发这句"不是免费选项——那是对用户说谎。
     修法因此必须成对：加一条不承诺工单的话术（方案 a），或让建单本身可靠（方案 c：走 `post_write` + `/tickets` 上
     `_claim_and_execute`）。两者正交。锚：prompts.py:25-27）

279. ⬜ 兜底轮"替换非叠加"的代价：POST 用户 / GET 重连 / 坐席工单 / M4.3 比对，四个下游各看到哪一句？
     （POST 看 `FALLBACK_LOOP_LIMIT`（`queue.put` **绕过 emitter 故不进 msgbuf**）；GET 重连看 loop 写的
     `FALLBACK_MAX_ITERATIONS`/`FALLBACK_BUDGET`（stream 把 assistant_message 直译成 token）；坐席工单走摘要第二档
     时也是 loop 那句；M4.3 同理。**用户唯一看到的那句既不在事件流、不在 msgbuf、不在任何重放面**；事件流那句从未
     到达用户。观察 ㊼。锚：service.py:341-352、stream.py:52-53、loop.py:692-693）

280. ⬜ `create_handoff` 为什么不写 HANDOFF 事件？
     （单写者纪律：一次 run 一个 EventWriter，写入权归**持有写者的那一层**。机制函数只负责"在下游开单并交出结果"，
     对事件流一无所知——这也让它能被三处调用方复用。计划原签名里的 `summary` 参数被删也是同一取向。
     锚：handoff.py:1-6/40-59、store.py:290-295）

281. ⬜ 转人工摘要三档（`sessions.summary`→末三条 messages→固定占位）的顺序判据？第三档为什么不能是空串？
     （顺序＝**信息密度递减**：滚动摘要是压缩过的全局视角，末三条是局部原文，占位是"什么都没有"。第三档不能空，
     因为**兜底值的作用是消除歧义不是填格子**——空 detail 让坐席以为系统坏了，"（无历史消息）"让他知道这是刚开口
     就要转人工的用户。另注：末三条用 `id.desc()` 倒查再 `reversed`（自增 id 单调、无同秒歧义）。锚：handoff.py:20-37）

282. ⬜ `sessions.summary` 在 M2 复盘时被登记为"零读方预留"，它的第一个读方是谁？
     （**转人工工单的摘要第一档**（handoff.py:23），不是 ContextBuilder——后者从事件流重建上下文、不读该投影列
     （context.py:267 D5）。M2.5 写的滚动摘要投影，首个消费者出现在 M3.8。锚：handoff.py:20-26）

283. ⬜ 帧译表只把 `assistant_message` 译成 token 帧，但"用户看得见的文本"来源不止它——列出差集。
     （差集＝**tools 轮的 `turn.text`**（调工具前的过渡语"好的，我帮您查一下"）：它经 text_sink 推给了用户，但
     loop 的 tools 分支只把它放进工作序列，**不写 ASSISTANT_MESSAGE 事件**（全文只落在 `llm_result.payload["text"]`）。
     后果：run 结束 `emitter.clear()` 后，任何重放都比用户当时看到的少一段；附带 tools 轮不调 `_finish_text`，guard
     尾窗残句从未 flush。两份译表同病。观察 ㊾。锚：loop.py:414-415/403-412、service.py:313-316、stream.py:52-53）

284. ⬜ `tool_result` 事件里没有 `tool_name`，帧译靠 `last_tool` 跨事件携带——前提是什么？什么时候塌？
     （前提＝**工具串行执行**。并行工具一旦支持，`last_tool` 立刻错配，且**两份译表（service/stream）会同时错、
     无测试会红**。投影层不受影响（靠 `tool_call_id` 配对）——这是"帧协议比投影协议更弱"的一处。观察 ㊿。
     锚：service.py:317-323、stream.py:54-60、store.py:229-236）

285. ⬜ 确定性话术（HANDOFF 回复模板、FALLBACK 系列）为什么不过 OutputGuard？反向推论是什么？
     （守卫防的是"模型输出泄漏受控字面量"，这些话是我们自己的常量，过守卫只引入误杀风险（工单号撞规则）。
     **反向推论：凡是过守卫的，都是我们不完全信任的来源**。锚：service.py:270 注释、M2.8 豁免口径）

286. ⬜ `pending` 判据 `content != emitter.turn_text` 在守卫两种命中形态下表现相反——为什么？暴露了什么耦合？
     （流中命中：事件 content = `visible + SAFE_REPLY`，而 `_push_text(SAFE_REPLY)` 也推给了 sink→两者逐字相等→
     不押 pending，**正确**。终局命中：SAFE_REPLY 照推，但事件 content 被 D11 **整条替换**→两者不等→押 pending→
     终局再补发→**用户看到两遍 SAFE_REPLY**（站 9 缺陷候选①）。暴露的耦合：`pending` 判据默认了"事件内容＝用户
     看到的内容"，而 `final_check` 的存在意义恰恰是打破这个等式。锚：loop.py:638-646 vs 647-655、service.py:313-316/351-352）

287. ⬜ 入口守卫为什么只有 `AgentLoop.run` 一个挂点？出口守卫被复制到了服务层，入口没有——两次选择的判据分别是什么？
     （事实：FAQ 直答与 HANDOFF 直通都不进 loop，故**两条路的入口守卫都缺席**；而 M3.10 拍板Ⅳ 专门在服务层重建了
     出口守卫。丢失的是 14 条规则库 HIGH 拒答、MEDIUM 打标、以及入口 `GUARDRAIL_TRIGGERED` 审计事件（**入口攻击在
     直答路完全不可观测**，M4.2 统计缺样本）。诚实读法：不是论证后决定不做，是没被想起来。修向最便宜一档：直答前
     调一次 `Guardrails().check_input`——**未注入分类器时是纯规则库、零 LLM 调用、对 cassette 零冲击**，HIGH 命中
     复用既有"回落 `_run_main`"通路。观察 ㊴ 合并条。锚：loop.py:225/196、service.py:206-212）

288. ⬜ `OutputGuard` 的片段集来自"构造参 `system_prompt`"而非"实际发给模型的 system"——哪条路上恰好正确、哪条路上空转？
     （主 Agent 路：构造参就是实际 system（loop 只额外拼 UNTRUSTED_NOTICE），**正确**。FAQ 直答路：传的是
     `spec.system_prompt`，而模型实际看到的 system 是 `faq_digest`——**片段族在防一段模型无从泄漏的文本**；工具名族
     同理近乎空转（直答轮无工具）。三族里真正在岗的只有 PII 族，对外表述须收窄到这个精度。顺带核实：演示语料的客服
     热线 `400-800-1234` 不匹配 `phone_cn`（要求 `1[3-9]` 开头恰 11 位、前后无数字），不会被误杀。观察 (51)。
     锚：guardrails.py:414-435/339-357、service.py:206-212）

289. ⬜ `config = dict(tenant.config)` 这一行，不写会怎样？
     （**今天行为完全一样、一个测试都不会红**——它是防御性快照。它防的是这条别名链：`spec.tenant_config` →
     `TenantRecord.config` → `TenantDirectory` 缓存的**那个 ORM 实例本身**→全进程共享 60 秒。深层理由：`AgentSpec`
     是 frozen dataclass，但 **frozen 只冻到引用层**——挡得住重新赋值，挡不住 `spec.tenant_config["x"] = y`。
     `tools`/`owned_values` 用 tuple 把内容层也冻住，dict 没有不可变版本只能做副本——同一构造调用里三个字段三种
     写法、同一意图。边界：**只拷一层**（观察 ㊶），且**无 CI 证人**（钉子＝一行 `is not` 断言）。
     锚：agent.py:38/45/52-53、tenancy.py:96、spec.py:139-140）

290. ⬜ 断线之后 `_TokenEmitter` 的三份状态分别发生了什么？
     （`_queue`：生产者继续 put（无界不阻塞），没人 get，帧堆内存直到 run 结束；`_acc`→msgbuf：**继续更新**——这正是
     重连能补收的原因；`turn_text`：继续记账，`pending` 判据照常工作。**观察者离场后三条线全在跑**，只有第一条的
     产物没人取。锚：service.py:96-105/161-169）

291. ⬜ `final_check` 检查的是已经流出去的文本，"话说出去收不回"，那它还有什么用？
     （改变三样**不在那块屏幕上**的东西：⑴ **事实**——事件里的 `assistant_message` 被整条替换成 SAFE_REPLY，泄漏物
     不进 messages 投影→不进滚动摘要→不进转人工工单→不进 M4.3 回放→不进 M4.4 评测；**"泼出去的水收不回"只对那一屏
     成立，不写进事实源是防止它被无限次重放**；⑵ **可修正的重放**——GET 通道重放的是事件，用户刷新/重连即看到修正版；
     ⑶ **审计**——`GUARDRAIL_TRIGGERED(stage="final")` 是这次泄漏唯一的痕迹。深层：流式×零泄漏×确定性三者不可兼得，
     选了流式就必须放弃零泄漏（类 docstring：**"守卫的保证是止损不是零泄漏"**），`final_check` 是为这个放弃付的补偿，
     同时是 v1 唯一能做语义级检查（需看全文）的**座位**。另注 `feed` 并非逐 delta 裸放行：攒够整句/伪句、扫描通过
     才 release。锚：guardrails.py:403-412/448-493、loop.py:647-655/620-621）

292. ⬜ `final_check` 命中时事件被替换了，msgbuf 呢？
     （**没被替换**——`emitter._acc` 里仍是未经修正的原始流（含泄漏物）。正常路径 `emitter.clear()` 会删掉它，窗口很短；
     但进程若在命中与 clear 之间死掉，泄漏物在 Redis 留存 TTL 3600 秒，且 GET 重连会当 `message_reset` 整条推出——
     正好抵消"刷新即校正"的收益。根问题：**msgbuf 的定位是"通道的副本"（该保留原样）还是"事实的投影"（该跟着改）？
     这个定位从未被论证过**。观察 (52)。锚：service.py:96-105/353、stream.py:138-146）

## M3 全量复盘 · 站 10 HITL 业务闭环（2026-08-02 出题；`apps/support/revalidate.py` 97 + `api/approvals.py` 120 + `runtime.py` #44 分诊支 +118 + `workers/hitl.py` 212 行）

293. ⬜ `PrecheckHook` 的签名是 `(tool_name, args)` 没有 ctx。M3.0 开工核对预告的两条出路（闭包捕获身份 / 自查 sessions）
     最后一条都没走——为什么正解是"归属重校验根本不在这层做"？
     （因为归属是**权限**判定，权限的输入必须是运行时注入、模型不可控的身份，而唯一持有真实身份的是 `ToolContext`
     （executor 在 write-ahead 时构造）。批准执行走 `executor.execute(..., approved=True)` **全程**，handler 内
     `fetch_owned_order(ctx, order_id)` 双比对 tenant+user 照常跑——`approved=True` 只豁免生命周期③ 的闸门
     （`if not approved and tool.risk_policy is not None`），不豁免生命周期⑤ 的 handler。在 precheck 里再造一份，
     等于用更弱的身份重复一件下游会用更强身份再做一次的事，而且两份判定会漂移。锚：runtime.py:60-62、
     executor.py:148/167-173/186、_shared.py:21-35）

294. ⬜ #44 的三个崩溃窗里，只有"从未执行"那一窗跑 precheck，另两窗刻意不跑。为什么？
     （**precheck 的语义是"执行前"，write-ahead 之后它就失去了语义**：`tool_call` 事件一旦落盘，副作用可能已在下游
     生效——校验通过就重执行（原键安全），校验拒绝也阻止不了已发生的事，反而会把"结果不明"错记成"没执行"。
     窗口三（已有终局）重跑还会误拒一件已经成功的操作。锚：runtime.py:552（窗口一唯一调用点）/574-586）

295. ⬜ `_as_positive_decimal` 的注释说"快照字段不可信"。可这份快照已经被 pydantic 校验过、还过了一次风险闸门，
     为什么还不可信？
     （三个来源：⑴ 它的原始形态是 LLM 生成的 `arguments_json`；⑵ 它在 `approvals.args` 这个 jsonb 列里往返过一次，
     **类型在往返中不守恒**；⑶ executor 的参数校验产物是 `args_model` 实例，而写进 approvals 的是
     `model_dump(mode="json")` 的字典——校验器面对的是"曾被校验过的东西的 JSON 投影"，不是那个对象本身。
     另注 `Decimal(str(value))` 先 str 再 Decimal 是"钱不过 float"那条线的延伸。锚：revalidate.py:32-38、loop.py:575）

296. ⬜ `Revalidator` 为什么返回 `str | None` 而不是 `bool`？
     （拒因文本是**要回填给模型**的（D19 否决不终止），不是给日志看的。返回 bool 就必须在别处再造一张
     "工具名→话术"表，那张表会和判定逻辑分家漂移——**"判定"和"为什么"必须同一处产出**。锚：revalidate.py:28-29、
     runtime.py:77/556/683）

297. ⬜ 批准后的校验为什么直读数据库，不走 mock API？
     （⑴ 故障注入不该误伤批准后的校验——`mock_error_rate` 随机 503 会让 precheck 随机拒绝已批准的操作，而
     **注入器模拟的是"业务系统抖动"，precheck 不是业务动作、是我方的安全判定**；⑵ 躲开 `mock_client` 进程单例的
     跨 loop 面（worker 侧复用同一模块）；⑶（未写出的第三条）**安全闸门的依赖必须比它守护的操作更少**——写必须
     走 API（下游要去重要落台账），读若也走 API 就等于让我方判定依赖对方在线。第三条与站 9 口径⑵"兜底路径的依赖
     必须比主路径更少"是同一条原理。锚：revalidate.py:8-9、mock_backend/app.py:140-147）

298. ⬜ 校验器比下游更严、比下游更松，哪个更贵？为什么口径定成"以下游为准"而不是"从严从紧"？
     （更松→放行→执行时下游 409→回 dict 话术→模型改口，**下游兜住了**；更严→批准后白拒→坐席明明批了却没生效，
     **无人可兜**。所以在有下游兜底的位置，多拦一道比少拦一道更贵。`_revalidate_coupon` 刻意不看订单状态，正因为
     mock 的 `_execute_coupon` 也不看。锚：revalidate.py:64-72、mock_backend/app.py:125-128）

299. ⬜ `REVALIDATORS` 为什么恰好两枚，这个"恰好"为什么可以被 CI 检查？
     （能走到 precheck 的必是挂过审批的工具，能挂审批的必是带 `risk_policy` 的工具——所以**登记面 ≡ 带 risk_policy
     的工具集**，是一个可机器检查的等式。五工具实况：order/logistics=READ 不过闸门，ticket_create=risk_exempt，
     refund_apply/coupon_grant 带 policy。`test_registry_pins_gated_write_tools` 一行 `set(REVALIDATORS) == {...}`
     钉死，两个方向后果都写在注释里：少一枚=高危写批准后裸奔进 fail-closed 拒绝，多一枚=给不过审批的工具白造校验器。
     手法与 #38 声明清单同源。锚：revalidate.py:75-80、test_revalidate.py:110-113）

300. ⬜ 未登记工具是运行时 fail-closed 拒绝，而未知工具名（`build_agent_spec`）是启动即炸。同为配置错误，
     为什么处置不同？
     （因为 `REVALIDATORS` 与工具货架分属两个模块，**没有一个自然的启动时刻能把两者对上**。于是把这道防线挪到了
     更早的座位——CI：契约测试代替启动炸。"启动炸 → CI 红"是同一条防线换座位，不是放弃。锚：revalidate.py:83-97、
     agent.py 白名单点名）

301. ⬜ revalidate 的 `_load_order` 只按 `id` 查，既没有租户维度也没有用户维度。生产上安全吗？安全边界精确到哪一层？
     （**租户维安全、用户维不安全**。租户维靠 RLS——三条调用路径逐一核过：审批 API 在 `tenant_context(approval.tenant_id)`
     内走 app 引擎（`get_session_factory` = app 引擎 + `install_tenant_guard`）；worker 崩溃恢复与对账踢单共用
     `_resume_in_context`，在 `tenant_context(tenant.id)` 内走任务局部 app 引擎 + guard。但 **RLS 策略是 tenant_id 级
     的，不是 user 级**，所以同租户跨用户读得到。对照组：mock 侧同名 `_load_order` 是"WHERE tenant_id 第一层 + RLS
     第二层"，这里只剩一层——站 7 ㉙"交叉核验退化成单层"的第二例（观察 (54)）。锚：revalidate.py:41-45、
     mock_backend/app.py:70-79、db.py:32-43、approvals.py:113、hitl.py:169/136-137）

302. ⬜ 【缺陷候选②】precheck 的拒因怎么绕过了对抗③的统一话术？为什么执行面仍然是安全的？
     （链路：模型对同租户他人订单发起 `refund_apply(amount=500)` → **闸门在 handler 之前**（executor.py:148 vs :186）
     所以归属还没被检查就挂了审批单 → 坐席批准（v1 单据只显示 tool_name+args，看不出归属问题）→ precheck 无 user 维度
     读到他人订单 → 拒因 `"退款金额超过可退上限 300.00"` → 按 SYSTEM_PROMPT **规则 4「如实转达系统给出的说明」**
     被模型复述给用户。四种拒因彼此可区分＝存在性 oracle（不存在／已退款／存在且实付 N／放行），而 M3.7 的
     `DENIED_TEXT` 三路逐字节同话术正是为抹平这个区分而设。**执行面安全**：放行后 handler 的 `fetch_owned_order`
     照样挡住回 `DENIED_TEXT`——站 8 口径⑵ 完全兑现；漏的是**信息面**（同租户跨用户，不跨租户）。修向 (a) 拒因
     粗粒度化、细节只进 logger 与事件 payload（建议，M4.0 与 ㊲ 同批）；(b) 给 hook 加 ctx＝破 L2 冻结面；
     (c) 归属提到闸门前＝违反站 8 口径⑵ 且丢审计痕迹。锚：executor.py:148/186、prompts.py:20、
     _shared.py:16-18/33、revalidate.py:60）

303. ⬜ "一个拿不到身份的层，它的输出必须对所有身份都安全"——这句话为什么是 (302) 的**根因**而不是症状？
     （因为 `build_precheck` 的闭包里只有 factory，签名里只有 `(tool_name, args)`，**连 session_id 都没有**——
     这层在结构上无从知道"谁在退款"，因此它对任何以身份为条件的信息**不可能**做访问控制。docstring 说"本层只管
     快照的业务新鲜度"是对的，但漏了下半句：**"业务新鲜度"的表述本身携带了受保护的数据**。所以无 ctx 的正解
     "不做归属判定"是对的，它只是没有同时推出"也不要说出只有 owner 该看到的事实"。）

304. ⬜ veto 路径不回填 `event_id`，于是该单永远满足 `_find_unattached_approved` 的认领判据——每次崩溃恢复都会
     重新认领、重新校验一次。为什么这不是缺陷？
     （因为**校验无副作用，重跑幂等**。代价只在审计视图：veto 过的单与"批准了但从未兑现"的单长得一模一样。
     M3.9 拍板Ⅳ 已登记为已知边界（题 138/139）。锚：runtime.py:553-556/407-426）

305. ⬜ precheck 抛异常（比如 DB 抖动）会发生什么？这层为什么一个 `except` 都不写？
     （方向正确：安全闸门不许 fail-open（C34 分野左边）。后果链：异常穿过 `_resume_locked` → 生成器死 → 会话锁释放
     但**租约不释放**（无 finally）→ 会话卡 RUNNING → 租约过期 → reaper steal → `_recover_locked` a+ 支窗口一 →
     precheck 重跑。自洽（校验无副作用故重跑安全），但要诚实说出：**这层分不清"校验拒绝"与"校验器坏了"**——
     前者产出话术，后者进恢复循环，反复失败最终 C9 置 failed。属未登记行为。）

306. ⬜ 审批端点的授权查读 `_load_approval` 为什么必须走 owner 引擎、主动绕开 RLS？代价是什么？
     （因为 operator 在自己的租户上下文里查他租单据，RLS 会把那行过滤掉 → 只能回 404 → **"存在但你无权"与
     "根本不存在"物理上不可分辨**，而对抗④ 要的恰恰是"越界被点名"。一般化：**有些判定天生要求平台视角，
     RLS 越强它越做不了**——这是 #46 教训（加防线改变可达路径）的镜像：那里 RLS 让比对分支变死代码，
     这里 RLS 让 403 判定结构上不可能。代价=跨租户防线从"数据库强制"降级为"应用层一个 if"，
     必须有 CI 证人替补（test_approvals_api + test_adversarial）。锚：approvals.py:49-52/109、
     main.py:97、db.py:54-64）

307. ⬜ 同一个项目，工具面拼命不泄露存在性（`DENIED_TEXT` 三路同话术），审批端点却显式 403 泄露"他租有这张单"。
     两条判据是什么？
     （⑴ **标识符可不可猜**：订单号业务可见、可能从别处得知；`approval_id = uuid4().hex`——持有一个有效 id
     本身就意味着泄露已发生在别处，再隐身收益极小。⑵ **调用方可信度**：工具面输入受 LLM 与终端用户影响（半敌对），
     审批端点调用方是持 staff 凭证的坐席（半可信）——对半可信方，"越界被点名"的运维价值 > 存在性隐身的安全价值。
     锚：loop.py:573、_shared.py:16-18、approvals.py:109-111）

308. ⬜ `tenant_context(approval.tenant_id)` 与站 5 偏差(32) 的"叶子自冒充"形状几乎一样——都是从手边数据取
     tenant_id 设上下文。为什么一个是缺陷一个是正确？
     （判据不是"值从哪个变量来"，而是 **"这个值有没有经过一次独立于它自身的核验"**。Retriever 的 tenant_id 是
     纯函数参数，无任何独立核验 → RLS 交叉核验塌成 WHERE 的复读机；approvals 的单据租户在 operator 路径刚经过
     `principal.tenant_id == approval.tenant_id` 核对（docstring 称"本租等值覆盖"），admin 路径经过角色授权
     （特批冒充，故进封闭名单第五处：auth 裸设／任务内胆／脚本 main／usage 特批／本处）。锚：approvals.py:109/113-116）

309. ⬜ `_drain` 的三层 except 顺序为什么是承重的（而不只是风格）？
     （因为四个异常**全是 `RuntimeError` 子类**：`SessionLockHeld`(locks.py:32)、`EventStoreUnavailable`(store.py:179)、
     `EventWriteFenced`(store.py:183)、`LeaseLost`(store.py:522)。把兜底的 `except RuntimeError` 挪到最前面，
     三种事实源故障就会被静默译成 409，客户端会去重试一个重试不好的东西。与 chat._collect 逐条同构，
     两处注释互相指认＝单一事实源写法。锚：approvals.py:55-64、chat.py:87-96）

310. ⬜ 事实源三类（`EventStoreUnavailable`/`EventWriteFenced`/`LeaseLost`）为什么裸穿成 500，而不译 409？
     （409 的含义是"现在冲突，稍后重试可能成功"。PG 挂了＝重试无用；围栏与租约旁落是**终态**（所有权已旁落，
     绝不退避重试）——译 409 等于骗客户端。**状态码是承诺，不是分类**。）

311. ⬜ `decide` 的 CAS 输家为什么回 409，而不是"幂等地"回 200？
     （因为"已处理"有四种含义完全不同的原因：另一坐席批了／另一坐席**拒了**／用户撤回／超时。回 200 等于告诉坐席
     "你的批准生效了"，而真相可能是"你同事刚拒了"。**幂等友好 ≠ 诚实**：当重复请求背后可能藏着一个相反的裁决时，
     幂等回成功就是编造。另注 WHERE 用 `func.now()`＝DB 时钟，与 expires_at 写入时钟同源。锚：store.py:431-448）

312. ⬜ worker 侧明明已有整套任务局部装配和 `_kick`，审批端点为什么还自己同步消费 resume？
     （⑴ 坐席要立刻知道结果（`_summary` 三态就是答案），异步只能回 202 + 自己去查；⑵ **崩溃窗有另外两条路兜底**
     （a+ 分诊支 + 对账扫描），所以同步路径不必自己保证可靠性——**同步路径可以只管快乐路径，因为它不是唯一的路径**；
     ⑶ 与 chat 取消路径同形，前端不必学两套模型。）

313. ⬜ `_summary` 为什么需要 `awaiting_approval` 这一态？
     （因为**同一次续跑里可以再撞上下一道闸门**：批准 A 之后 Agent 继续跑，又调了一个高危写工具 → 新开单挂起。
     判定顺序 terminated → approval_requested → 兜底，三态各自对应"跑完了／又挂起了／什么都没发生"。
     零事件态 `resumed` 的账诚实（events=0）但词乐观——真实含义是"决策已落、续跑归 T3 赢家"。锚：approvals.py:67-89）

314. ⬜ 项目里建立租户上下文有两种写法——`with tenant_context(...)`（set+reset）与裸 `set` 不 reset。
     它们各自匹配什么消费方式？这条配对写在哪？
     （`with`＝身份只在块内有效，**块内必须把全部库操作干完**（approvals／worker 任务内胆／usage 特批）；
     裸 set 不 reset＝身份必须**活过端点函数**（`current_principal`，因为 chat 返回 StreamingResponse，真正的库操作
     发生在 return 之后）。**这条配对只以注释形式散落两处、无任何机制保证**（观察 (58)）。具体地雷：若把审批端点
     改成流式（4.4 的两个修向都指这个方向），`with` 会在 return 时 reset，流内每一次库操作静默落进 RLS 空集——
     无异常无红灯。锚：approvals.py:113、auth.py:142-145、tenant_ctx.py:29-36）

315. ⬜ 观察 (56)：为什么说审批端点是全项目**最花钱**却唯一没挂入站限流的端点？
     （一次 POST 触发一次完整 Agent 续跑（工具执行＋多轮 LLM＋计量落账），而 `rate_limited` 只挂在 `POST /v1/chat`。
     站 1-3 观察⑥ 登记该缺口时点名的是 kb 与 stream，审批端点当时还不存在（M3.9）。缓解面要说清：需 staff 凭证；
     同一单 CAS 只赢一次故不能靠重放放大；真实攻击面＝坐席账号被盗后批量批准，上界＝该租户 pending 单数量。
     锚：chat.py:44 vs approvals.py:92-98）

316. ⬜ 观察 (57)：审批端点的 HTTP 响应时长等于什么？M3.10 的哪条实录侧面证实了它？
     （等于一次完整 Agent run（`_drain` 消费完整条事件流），无流式无上界。M3.10 实录"批准后续跑帧**瞬时推达页面**
     （早于批准 HTTP 响应返回）"——GET 流早看到结果，坐席的 POST 还在等。M3.10 只把 chat 做了 SSE，审批端点没跟。
     断连后服务端是否跑完＝未实测，不下结论。修向 (a) 只 drain 首帧（要重新论证 409 契约）／(b) 202 + 引导看 GET 流。）

317. ⬜ 端点里 404 排在 403 之前，且 403 只对 OPERATOR 生效。admin 跨租户批准是合法的——它会用谁的预算、
     落谁的账本？
     （02 §7.1 矩阵给 admin 的是无限定 ✅，故不设租户比对。执行时 `tenant_context(approval.tenant_id)` 内跑，
     所以 LLM 续跑走**该单据租户**的预算与账本——业务上正确（那本就是那个租户的会话），
     但它意味着一次平台侧动作会消耗租户配额。锚：approvals.py:107-116）

318. ⬜ #44 的缺陷本体是一句什么话？为什么说它是"安全但不正确"的标本？
     （**`_recover_locked` 的分诊全程不查 approvals 表**。于是那个未配对的 tool_call 声明走到 `_rebuild_working`
     最后一段被补上 `_DISCARDED_NOTE`（"等待人工审批期间未执行"）——批准被当弃置。安全面 ✅ 零副作用零双花，
     语义面 ⚠️ 批准丢失／孤儿 approved 单／坐席白批一次。**所有不变量都成立，只是做错了事**。
     发现于 M2 复盘站 12 追问：两条各自正确的路径，交界处没人走过。锚：runtime.py:201-203/76）

319. ⬜ 批准到审计链闭合之间的四个崩溃窗，库里各留下什么？W0 为什么 reaper 结构上看不见？
     （W0=decide 后未消费：awaiting_approval + **无租约**（租约在 T3 之后才 acquire）；W1=T3 后：running+租约，
     事件到 approval_requested 为止；W2=write-ahead 后：多一条 tool_call 无终局；W3=tool_result 后、attach 前。
     **reaper 扫的是"租约过期且 running"，W0 两个条件都不满足** → 不是疏忽，是扫描维度决定的结构性不可见 →
     必须另开一条扫描路（对账 sweep）。锚：runtime.py:653-661、reaper.py 扫描面）

320. ⬜ #44 的前案（在 ResumeHook 里查到 approved 单就改调 `resume(approval_id=X)`）为什么废？
     （⑴ **W1/W2 必打空**：`_resume_locked` 第一件事是 T3 CAS `expected=AWAITING_APPROVAL`，而崩溃现场会话已是
     `running` → CAS 打空 → 安静零事件 → 什么都没修且**无红灯**；⑵ **W3 是真双写**：`execute` 生命周期④ 会再写
     一条 tool_call = **新幂等键** → 下游 PK 去重当场失效 → 同一笔退款真退两次；⑶ 隐性代价=恢复策略的知识从 L2
     漏进 worker，反了 reaper"自己不 import 业务"的设计。锚：runtime.py:653-656、executor.py:158-166/226-234）

321. ⬜ 一般化：什么时候该"换一个入口"，什么时候该"在原入口加一支"？
     （**取决于新情况需不需要看见旧入口看不见的事实**。W1/W2/W3 的分辨要看 tool_call/tool_result 的在场与否——
     那是 `_recover_locked` 的视野（它手上有全会话事件），不是 `resume(approval_id)` 的视野（它只有一个 id）。
     判定权必须留在唯一读得懂那些事实的地方。）

322. ⬜ 为什么用 `event_id IS NULL` 当"批准未兑现"的凭证，而不是新加一个 `resumed_at` 标记字段？
     （因为 `attach_event` 的 CAS 是 `WHERE id=? AND event_id IS NULL`——**回填恰一次**，天然的一次性标记；
     而且这个字段**同时是审计链**：它指向那条 tool_call 事件，事件 id 又是下游幂等键，一个字段串起
     "批准→执行→下游去重"三段（#6 钥匙链的最后一环）。加纯标记字段会让"标记已置但事件不存在"成为可能＝两个事实源。
     **但它有第二种为空的理由——见题 330**。锚：store.py:484-496、runtime.py:407-426）

323. ⬜ 三个窗口为什么不能统一成一种处置？
     （统一成"重执行"→ 窗口三双写；统一成"不执行"→ 窗口一批准永远不兑现。**三个窗口在事件流里留下的痕迹不同，
     所以正确处置必然不同**——崩溃点可以从事实里推断，不需要额外状态字段，这是事件溯源相对状态机存储的直接红利。）

324. ⬜ 窗口一为什么要**重跑** precheck？"恢复=重放"这个直觉错在哪？
     （恢复不是重放，是"**重新走一遍执行前该走的路**"。TOCTOU 窗口在崩溃期间还在继续变大，不重校验等于把 #8 的
     防线在恢复路径上挖掉。同理 `decided` 事件缺失时补写——"谁在什么时候批的"不能因为一次崩溃就消失，
     `operator_id` 从单据取不是编的。锚：runtime.py:541-556）

325. ⬜ 窗口二为什么必须走 `reexecute` 而不是 `execute`？
     （`reexecute` 跳过生命周期①–④、复用⑤⑥⑦，以**原 write-ahead 事件 id** 当幂等键——**绝不产生第二把钥匙**。
     参数是事实源里当年校验过的快照故不再"不信"；终局事件以原 id 写入，投影 `_finish_invocation` 恰好闭合原
     RUNNING 行。b 支语义被整个并进认领分支，区别只在事后要不要 attach。锚：executor.py:226-252）

326. ⬜ 窗口三为什么"绝不重执行"，只补 attach？取回结果的口径是什么？
     （操作已完成、结果已落盘，重执行＝新钥匙＝真双写。取回口径与 `_rebuild_working` 逐字一致：`injected` 优先，
     否则 `json.dumps(result, ensure_ascii=False, default=str)`——**X4"事件恒存原文、injected 是收缩产物"在恢复
     路径上的第二次消费**。代价：这段逻辑被复制了一份，两处口径无机制保证（观察 (59)）。
     锚：runtime.py:578-585 vs :186）

327. ⬜ 同在 a+ 支里，"单在事件不在"降级留痕，"悬挂工具与认领单不匹配"却响亮 RuntimeError。判据是什么？
     （前者＝事实源被外力动过，系统对它没有正确处置 → 降级到更保守的路径 + 留证据；后者＝**单写者不变量被破坏**，
     而整个恢复算法（含"悬挂 tool_call 至多一个"的断言）都建立在那条不变量上。
     **建立在不变量上的算法，遇到不变量被破必须停，不能继续推理。** 锚：runtime.py:522-525/538-540/487-490）

328. ⬜ a+ 支为什么必须排在 b 支之前？（提示：不是性能问题）
     （b 支只看"有 write-ahead 无终局"，窗口二恰好也长这样。若 b 先跑，窗口二会被 reexecute 正确执行，
     但**不会 attach_event** → 单据仍是孤儿 → 下次恢复又来一遍。**是信息完整性问题：a+ 知道这次执行属于哪张单，
     b 不知道。** 锚：runtime.py:509-511/600-608）

329. ⬜ 缺陷修复类交付里"先红后绿"为什么不可省？M3.9③ 的 5 红 1 绿各是什么？偏差(49) 的回旋镖是什么？
     （它证明这些测试真的在测那个缺陷，而不是在测一个恰好成立的性质。五红全是断言红＝"恢复把已批准调用弃置、
     直接 LLM 续跑"＝#44 症状原样现形；1 绿＝a 支优先序回归钉（现行本就成立）。偏差(49)：W3 测试的夹具**预翻了
     T3**，真实 resume 的 T3 CAS 被打空安静返回、根本崩不到 attach → DID NOT RAISE。教训＝**崩溃模拟夹具的预置
     状态必须与被模拟的崩溃点逐一对表，多预置一步就把被测路径短路成 no-op**。）

330. ⬜ 【缺陷候选③】precheck veto 过的单据永远满足 `approved ∧ event_id IS NULL`。把它和 #44 的认领判据放在一起，
     会发生什么？
     （**跨 run 错误认领**。veto 后 run 正常终止、会话回 idle，库里稳定留一张 unattached approved 单
     （demo_hitl 段 D 亲手断言过这个状态）。此后任意一次**无悬挂工具**的崩溃恢复：`_find_unattached_approved`
     无 run 维度无时间窗 → 捞到陈旧单 → `claim_req_index` 在全会话 rows 里找得到它的 approval_requested →
     进入 a+ 认领。**确定后果**：收尾用 `_load_suspension(X)` 定位到几轮之前的旧 run，`user_input` 与 `working`
     全取旧 run——**用户刚问的话被完全忽略，Agent 回去重答旧问题**。**低概率后果**：窗口一重跑 precheck 若这次通过
     → 执行一次本轮从未请求的写操作。**加重情节**：`call_row` 取"第一个同名同参 tool_call"，可能匹配到新 run 里
     不相干的调用 → 审计链挂错。**部分自然防线**：崩溃时若有悬挂 tool_call，一致性检查会响亮抛错——所以可达条件
     精确为"崩在无悬挂工具时"（LLM 半截/干净缝，恰是最常见形态）。**精确表述：`event_id IS NULL` 被当作"批准未
     兑现"的代理，实际是"没有执行事件可挂"的代理**；docstring 说"更老的孤儿（若因历史缺陷存在）"——它不是历史缺陷，
     是 veto 边界在正常运行中稳定生产的产物。修向 (a) 认领前查"该 approval_requested 之后是否已有 loop_terminated"
     （最小、只读事实、无新字段，建议）／(b) veto 时给单据终结标记（改表与状态机）／(c) 时间窗（最脆）。
     锚：runtime.py:407-426/511-521/589-593/553-556）

331. ⬜ 观察 (60)：`lease.acquire` 到 `_pump_with_lease` 之间没有任何续租任务在跑。a+ 支往这段里塞了什么？
     （全会话事件扫描 → `_find_unattached_approved` → 可能的 decided 补写 → precheck（DB 往返）→ **工具执行
     （上限 `tool_step_timeout_s=30s`）** → attach_event → `_load_suspension`（第二次全会话扫描）。
     而 `lease_ttl_s=60.0` → **安全边际约 2×，且该段耗时上界从未被论证**。租约在此过期 → 另一 reaper 可 steal →
     两个恢复者同走 a+（第二个会被 attach CAS 或 EventWriteFenced 挡，但**挡在副作用之后**）。
     结构本身是 M2.9 就有的（`_resume_locked` 同款），a+ 只是把它拉长。锚：runtime.py:447/382、config.py:66、spec.py:65）

332. ⬜ a+ 支与 `_resume_locked` APPROVED 分支"同构"，同在哪、差在哪？
     （**收尾三步完全相同**：`_load_suspension` → `_rebuild_working(fill_*)` → `resume_run` 续跑；三个窗口只是各自
     算出一个 `claimed_content`。差异全部集中在"这次批准走到哪一步了"：APPROVAL_DECIDED（无条件写 vs 缺则补）、
     precheck（跑 vs 仅窗口一跑）、执行（execute vs reexecute vs 不执行）、attach 的 event id 来源。
     锚：runtime.py:587-595 vs :691-698）

333. ⬜ `sweep_once` 第一句就调 `expire_due` 翻转到期单，然后**不用它的返回值**。为什么？
     （`expire_due` 返回的是"**本轮新翻的单**"，而真正要处理的是"**所有已决但未被消费的单**"——两者的差集恰好
     是崩溃窗产物：上轮翻了 expired 没来得及 kick 就崩，这轮返回值里根本没有它；W0（decide 后未消费）从来就不在
     任何一轮返回值里。**自愈型扫描的定义性特征：不信任何"本轮发生了什么"的增量信号，每轮从当前状态重推全集**
     （同族＝M3.4 摄取的 `IS NULL 谓词即进度`、reaper 的 `list_expired`）。锚：hitl.py:62-72、store.py:464-482）

334. ⬜ "最新单已决"这个判据防的是哪一种误杀？把它换成"任意已决单"会发生什么？
     （防**旧 EXPIRED + 新 PENDING**：会话第一次挂起超时 expired、用户重新发起产生第二张 pending 单，此刻会话仍是
     awaiting。若按任意已决单去踢，`resume(旧expired单)` 走拒绝族 → T3 把 awaiting 翻 running → 写
     loop_terminated(cancelled) → T4 归 idle → **那张正在等人批的新单连同用户的等待被一次好意的对账掐死**。
     取最新一张则自动躲开：最新是 pending → continue。锚：hitl.py:63-71/96-97）

335. ⬜ 同样是"从一堆历史单据里挑一张"，`sweep_once` 与 `_find_unattached_approved` 的写法差在哪？
     （sweep：**挑选判据与状态判据分离**——先 `order by created_at desc limit 1` 取最新一张（不管状态），
     再用"是否 pending"决定动不动；认领：**把状态判据塞进了挑选条件**（`status=approved ∧ event_id IS NULL`
     再取最新），于是"最新的 approved-unattached 单"未必是"当前相关的单"→ 缺陷候选③。
     **同一个问题，两种写法，一个对一个错**——这是站 10 最好的一处对照。）

336. ⬜ 为什么对账扫描不并进 reaper，而要单开一条 beat？
     （**扫描维度完全不同**：reaper 扫"租约过期 ∧ running"，对账扫"run_state == awaiting_approval"；
     恢复入口也不同（`approval_id=None` → `_recover_locked` ／ `approval_id=X` → `_resume_locked`）。
     W0 的会话在 T3 之前**没有租约可过期**，对 reaper 结构上不可见。**扫描器按谓词切分，不按"都是恢复"切分。**）

337. ⬜ `_kick` 为什么走 `resume(approval_id=X)` 而不是崩溃分诊的 `None`？
     （W0 的会话是 `awaiting_approval`，从来没有开始过恢复 run；`_recover_locked` 的分诊假定"上一个 run 崩在半路"。
     走 `_resume_locked` 才对——它的第一步 T3 CAS `awaiting → running` 恰好是为这个状态设计的。）

338. ⬜ worker 跨 event loop 的受控缝有三种形态，判据是什么？各举一例。
     （判据＝**消费方有没有"你能塞参数进去"的时刻**（站 7 ㉝ 登记）。①**配置源提取**：`new_redis_client()`/
     `new_http_client()`——单例与任务局部实例共用唯一配置源，超时重试口径不漂移；②**工厂参数化**：
     `build_gateway(*, session_factory, redis, client)`/`build_session_lock(*, redis, engine)`——消费方有装配时刻，
     缺省 None＝现行为零改动；③**安装缝**：`set_mock_client()`——`tools/_shared` 里是 `mock_client()` 裸调用，
     穿参会改 L3 工具契约，故**装缝不改面**，前提是 `--pool=solo` 串行（线程池不支持）。
     锚：redis.py:12-28、base.py:34、factory.py:29-38、locks.py:282-292、client.py:29-36）

339. ⬜ 恢复钩子为什么用 import 副作用注册，而且为什么放在 `hitl.py` 而不是 `celery_app.py`？
     （⑴ `reap_expired_leases` 是 Celery 任务壳、签名由框架定死，`_reap_fresh()` 拿不到参数——**全局
     `_resume_hook` 是"签名被框架锁死的函数"的最后一种参数传递方式**；⑵ 放 celery_app 会让它 import 业务，
     反了 reaper"自己不 import 任何业务、恢复全在钩子后面"的设计；而 `include` 已点名 hitl，worker 启动必然加载；
     ⑶ 不外溢到 API 进程靠层契约 `aegis.api | aegis.workers` 互不 import，由 import-linter 在 CI 强制——
     **架构约束顺带成了副作用的隔离墙**。锚：hitl.py:209-212、celery_app.py:19-21、reaper.py:44-54/153）

340. ⬜ `resume_session(session_id, lease_owner, lease_generation)` 只用了第一个参数，另两个只进日志。为什么不用？
     （`(owner, generation)` 是 steal 的凭据快照，而 runtime 内部会以**同一个 owner 重入续接**
     （`LeaseStore.acquire` 的同 owner 分支）——steal → 钩子 → resume 是**同进程交接**，凭据不需要跨函数传递，
     只需要在日志里能对上。锚：hitl.py:175-180）

341. ⬜ 观察 (61)：`sweep_once` 一轮的工作量上界是多少？隔壁有什么先例？
     （**无上界**：`select(...).where(run_state==awaiting)` 无 limit ＋ 串行 for ＋ 每项一次完整 Agent 续跑，
     一轮 N 个会话＝`1+2N` 个引擎创建销毁（sweep 自己一个＋每次 kick 的 `_tenant_of_session` owner 引擎
     ＋`_task_runtime` app 引擎）。先例：`LeaseStore.list_expired(*, now, limit=100)` 有 limit。
     **且与复盘补丁一新增的不变量"任务时长 ≪ visibility_timeout(3600s)"直接相关**——而"worker 长期停摆后重启"
     恰恰同时是 N 变大与这个扫描最该工作的时刻。修＝加 limit，自愈扫描天然支持分批。
     另两条轻量：`SweepReport` 无 failed 计数（M4.2 统计对账失败率结构上拿不到，同族站 6 ㉓）；
     `latest is None` 静默 continue 无留痕（对比 a+ 支同族不可能态有 warning——**不可能态的留痕纪律不一致**）。）

342. ⬜ 观察 (62)：把 `hitl.py:212` 的 `register_resume_hook(resume_session)` 删掉，测试会红吗？为什么？
     （**不会红**。`reap_once` 把 `resume` 做成显式参数、测试注入 spy；全局 `_resume_hook` 的**唯一读点**是生产薄壳
     `_reap_fresh`（reaper.py:153）。全仓测试目录里 `register_resume_hook` **零处调用**。删掉的唯一症状是生产日志
     一行"reaper 抢租未恢复（无钩子）"，然后会话 recovery_count 递增到上限被 C9 置 failed——**一条静默失效的恢复
     能力**。钉子极便宜：`import aegis.workers.hitl; assert reaper._resume_hook is not None`。
     **更大的一般化**：`_sweep_fresh`/`_reap_fresh`/`_task_runtime`/`_kick`/`_tenant_of_session`——
     **worker 整条生产装配链在 CI 里没有任何证人，唯一证人是手工的 demo_hitl.ps1**（交付④ docstring 已诚实写明）。
     与 #47"测试跑在无 RLS 世界"同形态：**CI 见到的是逻辑，真实链路只有人肉见过**。）

343. ⬜ 观察 (63)：`_task_runtime` 的 finally 有什么问题？
     （`set_mock_client(None)` 后五个串行 `await`（mock/http/redis/engine）**没有各自的保护**——任何一个 aclose 抛
     异常，后面的全部不执行 → 资源泄漏，而 worker 是长驻进程、每 60s 一轮、泄漏会累积。同族＝M2.12 偏差 #7
     （`_pump_with_lease` finally 次生异常顶掉原始异常，已挂 M4.0）——**两处都是"清理段没有为自己的失败做准备"**，
     建议同批。锚：hitl.py:155-160）

344. ⬜ 观察 (64)：`_task_runtime` 与 `create_app` 的"四件逐件对应"是什么保证的？它已经被破过一次吗？
     （**只是一句人肉承诺，无任何机制保证**。`AgentRuntime` 新增注入参时两处必须同步更新，漏掉 worker 侧＝
     "恢复路径行为与请求路径不同"且无红灯。**已经发生过一次**：M3.10 的 `text_sink` 只加在 API 侧——这一次是
     **有意的**（worker 无对外流），但机制上区分不了"有意不加"和"忘了加"。具体后果链：worker 侧恢复既无 text_sink
     也无 msgbuf（ChatService 只在 API 侧装配）→ 一次由 sweep/reaper 驱动的续跑，用户在 GET 通道看到的是
     **整段一次性出现**，而同一次续跑走审批 API 则是逐 token 推送——最终一致 ✓ 实时性不对称 ⚠ 且从未登记。
     修＝装配契约测试（两点参数集合差集必须是显式白名单）或至少写进 docstring。锚：hitl.py:146-153 vs main.py:75-79）

345. ⬜ worker 的恢复为什么"只消费不转发"（`async for _event in ...: pass`）？
     （**事实源是事件流，worker 只需要驱动它前进**；worker 无对外流，用户经 GET 通道从事件流取回真相——
     M3.10"观察者不改变事实"的又一次兑现。锚：hitl.py:163-172）

346. ⬜ `_task_runtime` 里 `create_mock_api(settings, app_factory)` 传的是哪个工厂？这对站 7 观察 ㉚ 意味着什么？
     （传的是 **app 工厂**（`database_url_app` + `install_tenant_guard`）→ mock 的"RLS 第二层由调用侧环境承担"
     在 worker 侧**真的在场，而且是显式做对的**（不是靠缺省）。㉚ 说"生产缺省 app 引擎＝在场／测试全注入 owner＝
     不在场／CI 里无人作证"——**worker 这一侧是 ㉚ 的正面样本**。锚：hitl.py:136-142）

## M3 全量复盘 · 站 11 SSE 双通道（2026-08-02 出题；单元 A＝L2 逐 token 受控缝 `loop.py` 三处 + `runtime.py` +71）

347. ⬜ 逐 token 输出为什么必须由 L2 开一条缝？通道层自己从事件流里拿不到吗？
     （**拿不到**：`TextDelta` 在 `_llm_step` 内部被 `parts.append` 聚合消化（loop.py:467-468），事件粒度是"步"
     不是 token（events.py 契约：`assistant_message` 一次一整段）。通道层订阅事件流最细只能拿到"整段一次性出现"。
     14j 核对实况⑴ 就是这条：**要么改事件粒度（污染事实源、破坏 C31 回放与幂等），要么开缝**。选缝＝
     把"实时性"定性为**观察需求**而非事实需求。锚：loop.py:466-473、00 §2.2 C31）

348. ⬜ `text_sink` 为什么是 keyword-only 且缺省 None？开这条 additive 缝时撞到了哪两类既有测试面？
     （keyword-only＝**位置参数签名是 M2 的对外契约**（runtime.py:240 docstring），additive 只许往后加不许挤位；
     缺省 None＝"缺省即原行为"，既有 792 个测试零改动全绿本身就是等价性证明。两类冲击（偏差51，用户跑门抓出）：
     ⑴`test_runtime` 的 `inspect.signature` 快照钉——契约演进后**改钉不删钉**（新钉＝位置前缀锁死 + text_sink
     必须 KEYWORD_ONLY 且缺省 None）；⑵M3.9 的 `_SpyRuntime.resume` 覆写因基类签名扩展变成 Liskov 不兼容，
     mypy `[override]` 抓获。教训＝**开 additive 缝先 grep 签名快照测试与测试替身覆写**）

349. ⬜ `_llm_step` 里的 `OutputGuard` 为什么是"sink 在场才建"？sink 缺席时守卫在哪？
     （sink 缺席＝**零守卫零推送**，守卫留在 `_finish_text` 里以聚合模式建（loop.py:625-631）——这样 M2.7 形态
     逐字节不变。sink 在场才建的理由：流式守卫的存在意义只有一个——**决定哪些字符可以放行给观察者**；没有观察者
     时它不产生任何决策价值，却会改变 guard 实例数与生命周期。锚：loop.py:449-458）

350. ⬜ "观察者不改变事实"这条不变量，在干净路径上靠什么保证？在守卫命中路径上靠什么保证？两者强度一样吗？
     （**不一样，这是本单元最值钱的一处读法**。干净路径：事件写的是 `turn.text`（loop.py:659）＝**模型原文，
     根本不经过 guard 的输出**——两模式写同一个值是**结构保证**，与不变量无关。命中路径：事件写
     `visible + SAFE_REPLY`（loop.py:644），而 `visible` 在聚合模式＝`feed(turn.text)+flush()`、在流式模式＝
     逐帧累加的 `_stream_visible + tail`——**两者相等完全依赖 OutputGuard"逐字符 feed ≡ 整段 feed"不变量**
     （guardrails.py:406-408）。结论：**那条不变量只在命中路径上承重**，钉死它的
     `test_feed_granularity_deterministic` 是这条缝的地基而不是装饰）

351. ⬜ `_push_text` 遇到 sink 抛异常为什么把 `self._text_sink` 置 None 而不是上抛？降级的作用域是什么？
     （上抛＝**观察者杀死事实生产**，正是 M3.10 要否掉的方向（客户端断连是常态，不是 run 失败的理由）。置 None＝
     本 run 作用域自废通道（AgentLoop 每 run 一实例），warning 留痕，事件流照常跑完。连锁效果是自洽的：
     下一次 `_llm_step` 见 `text_sink is None` → 不建 guard → `_finish_text` 自动回落聚合模式。锚：loop.py:502-511）

352. ⬜ sink 在流中途死掉，已经放行的那半句会不会从事件里丢？
     （**不会**。放行段先累加 `self._stream_visible`（loop.py:472）**再** `_push_text`（473）——顺序即承诺。
     这是同一条纪律的第三处现形：M3.10② `_TokenEmitter` 先写 msgbuf 后入帧、M3.7 write-ahead 先落事件后发请求、
     此处先记可见文本后送观察者。**一般化：凡"事实 + 副本"成对出现，事实一定先落**）

353. ⬜ `_finish_text` 的流式分支为什么只 `flush()` 不 `feed()`？
     （文本在 `_llm_step` 里已经逐帧 feed 过了，`turn.text` 是同一批字符的聚合体——再 feed 一次＝内容翻倍。
     流式分支要做的只有两件：把守卫缓冲里**还没到句界的尾窗**吐出来（`tail`），以及把累计可见文本
     交给终局检查。锚：loop.py:632-637）

354. ⬜ 守卫的 `max_hold` 尾窗缓冲，在一个 tools 轮里由谁来 flush？
     （**没有人**。`_finish_text` 只在 `kind == "text"` 分支被调用（loop.py:403-404），tools 轮直接进
     `_run_tools`。所以工具轮前置文本（"我帮您查一下…"）的**最后一个未成句片段永远不会到达用户**——
     站 9 观察 ㊾"尾窗残句不 flush"在代码层坐实。它不是 bug 而是"通道只承诺尽力"的一处诚实边界，
     但从未写进任何 docstring）

355. ⬜ 承 354：如果 tools 轮的前置文本里守卫**命中**了，会发生什么？（站 11 新观察 (66)）
     （**通道静默止损、事件面零留痕**：`feed` 命中后恒返空串（命中即终态），后续片段不再放行；但
     `guard.hit` 只在 `_finish_text` 里被检查，而 tools 轮不走那里 → 既不发 `GUARDRAIL_TRIGGERED`
     也不发 `SAFE_REPLY`，下一轮 `_llm_step` 直接换新 guard 实例，命中被遗忘。
     后果＝**"守卫命中必留审计"这条声明在 tools 轮上不成立**；用户侧表现为前置文本说到一半忽然停住。
     可达性不高（前置文本触发 PII/工具名族），但属结构性审计缺口。锚：loop.py:403-404 vs 638-656）

356. ⬜ `_stream_guard`/`_stream_visible` 为什么是"当前 LLM 调用"作用域而不是"本 run"作用域？
     （守卫的语义单位是**一个纯文本回复出口**（guardrails.py:411），一个 run 可能有多轮 LLM 调用，
     跨轮共用实例会让上一轮的缓冲/命中态污染下一轮。故 `_llm_step` 每次进入无条件重置两者
     （loop.py:458-459）——包括把 guard 置回 None，这也是 sink 死后自动回落聚合模式的机制。
     对照：`_violations`/`_tokens_used`/`_repeat_streak` 才是 run 作用域）

357. ⬜ 站 9 缺陷候选①：终局守卫命中时，用户为什么会看见两次 SAFE_REPLY？三个下游各看到什么？
     （链路已两侧逐行确认：`_finish_text` 终局支先 `_push_text(SAFE_REPLY)`（loop.py:650）→ 通道侧
     `turn_text = visible + SAFE_REPLY`；事件 content 被 D11 **整条替换**成 `SAFE_REPLY`（654）→
     service.py:315 的 `content != emitter.turn_text` 成立 → 押 `pending` → 351-352 再补发一次。
     三下游三种视图：**POST 实时**＝`visible + SAFE + SAFE`；**GET 重放**＝只有 `SAFE`（事件面）；
     **msgbuf/message_reset**＝`visible + SAFE + SAFE`（终局替换不覆盖缓冲＝站 9 观察 (52)）。
     对照组＝流中命中支两者逐字相等故正确（638-645）。危害纯体验＋泄漏物在 msgbuf 里留 TTL；
     证实形态＝造"流中不命中、终局命中"剧本，断言 token 帧里 SAFE_REPLY 恰一次）

358. ⬜ `text_sink` 被穿透了四条路径（`_run_locked`/`_recover_locked`/`_resume_locked` 及其共用的 `_assemble`），
     生产上真正带着非 None sink 跑的有几条？
     （**一条**。全仓 `text_sink=` 实参只有 `service.py:306`（`_run_main` 走 `runtime.run`）。三处
     `resume` 调用点——`api/approvals.py:119`（坐席批准）、`api/chat.py:144`（用户显式取消）、
     `workers/hitl.py:171`（超时踢单）——**全部不传**。故 resume 侧的穿透在生产上是结构性空转，
     只有 `test_resume_continuation_streams_through_sink` 在替它作证。这不是缺陷（见 359），
     但"缝开了四条、生产走一条"这件事从未登记＝站 11 新观察 (65)）

359. ⬜ 那么 M3.10 五幕验收里那句"批准后续跑帧瞬时推达页面"，帧到底是怎么推达的？
     （**走 GET 通道的事件译帧，不是 text_sink**：批准 → `approvals.py` 同步消费 resume（无 sink）→
     事件落库 → `AFTER INSERT` 触发器 `pg_notify` → `EventNotifier` 唤醒 → `stream.py._translate`
     把 `assistant_message` 译成**一个整段 token 帧**。所以"瞬时"是真的（事件驱动、早于 HTTP 响应返回），
     "逐 token"是假的。**这构成对站 10 观察 (64) 的更正**：(64) 写"worker 侧整段一次性出现，与走审批 API
     的逐 token 推送实时性不对称"——实测两条路都是整段一次性，不对称不存在，真正的分界是
     **首轮问答（POST，有 sink，逐 token）vs 任何续跑（无 sink，整段）**）

360. ⬜ `TextSink` 类型别名为什么住在 `runtime.py` 而不是 `spec.py` 或通道层？
     （它与 `PrecheckHook` 并排（runtime.py:60-67）＝**同一族：L3 往 L2 注入的挂点类型**。判据是
     "谁定义这个契约"：`AgentSpec` 里的字段是**租户策略**（每租户一份、进回放匹配面），而 sink/precheck 是
     **每请求物**（一次调用一个，不该挂进 spec，也不该挂进进程级构造——14j 拍板Ⅱ 的"钩子侧不可行"推演）。
     居所判据同族＝题 90「配置居所：平台物理学 vs 租户策略」）

### 单元 B＝事实推送机制（迁移 `d41be6a90c27` 44 行 + `api/notify.py` 99 行）

361. ⬜ 跨副本事件通知为什么选 PG LISTEN/NOTIFY 而不是 Redis pub/sub？两条理由分别是什么？
     （⑴**事务性**：NOTIFY 在 COMMIT 时投递，通知与事实同一个事务边界——"通知到了但行还看不见"和
     "行提交了但通知丢了（进程死在 commit 与 publish 之间）"两种错位**结构上不存在**；应用层 publish
     无论放在 commit 前还是 commit 后都会踩其中一个。⑵**不给 Redis 加新降级面**：Redis 已经背着锁/缓存/
     限流/msgbuf 四条降级路径，再加一条＝多一个"部分可用"的组合态；而 PG 挂了事件流本身就没了，
     **通知通道与事实源同生死＝没有独立的失效态需要设计**。锚：00 §2.2 C22 行、迁移 upgrade docstring）

362. ⬜ 通知的 payload 为什么只是 `session_id:seq` 这样一个路由键，而不是事件内容？
     （**因为消费方一律重查**（notify.py:56-57、74 注释）。由此同时买到三条性质：**伪唤醒无害**（醒来查
     一次没有增量就继续等）、**丢通知无害**（超时也会醒来重查）、**乱序无害**（游标是 seq，不是通知顺序）。
     附带好处：payload 不受 pg_notify 8000 字节上限约束，也不会把事件内容（含 PII）广播到所有副本。
     一般化＝**通知只做"可能有事"的提示，不做数据通道**）

363. ⬜ `_on_notify` 为什么用 `payload.rsplit(":", 1)[0]` 而不是 `split(":")[0]`？
     （**session_id 是客户端可控的**（M3.2 `_ensure_session` 首见建行，id 来自请求体），可以含冒号。
     `rsplit(..., 1)` 只切最后一个冒号，seq 段永远是最后一段——所以 `a:b:c:7` 正确还原成 `a:b:c`。
     用 `split` 会把 session 名截断成前缀，唤醒**错误的会话**（且是可构造的：故意起名
     `victim:1` 就能蹭 `victim` 的唤醒）。这行一个词的差别是安全相关的。锚：notify.py:74）

364. ⬜ LISTEN 为什么必须自己开一条原生 asyncpg 连接，不能从 SQLAlchemy 池里借？
     （**LISTEN 绑定物理连接**：连接一旦归还池子/被复用/被 reset，监听就没了（且不报错，是**静默失聪**）。
     池连接的生命周期由事务决定，而 LISTEN 需要的是与进程同寿的常驻连接——两种生命周期不兼容。
     §7 陷阱 7 就是这条。附带正确性：这条连接**从不读业务数据**，所以它不挂 tenant guard、不进 RLS
     讨论面，也因此可以放心用最低权角色 `database_url_app`（main.py:59）。锚：notify.py:3-4）

365. ⬜ "通知永远不会早于事实可见"这句话靠什么机制成立？
     （PG 把 NOTIFY 排在事务的提交队列里，**提交成功才投递**；监听端收到后发起的是一次全新查询
     （新快照），必然看得见那一行。反例：应用层若在 commit 之前 publish，订阅者可能查到旧快照＝
     "通知到了行没到"；若在 commit 之后 publish，进程在两步之间死掉就永久丢通知。
     我们的兜底（超时重查）能救第二种，但**第一种是无法用重试补救的语义错误**——这才是选型的硬理由）

366. ⬜ `wait_for` 在"未启动/断连"时为什么是 sleep 一个轮询节拍就返回，而不是抛异常或直接等满超时？
     （返回＝把控制权交还给调用方去**重查**——降级形态下 `stream.py` 就从"事件驱动"退化成"2s 轮询"，
     功能不变只是延迟变大（C22 兜底＝after_seq 轮询）。抛异常会把观察者的故障升级成流的故障；
     等满 25s 则让降级形态比正常形态慢一个数量级。**测试形态天然走这条路**：ASGITransport 不跑
     lifespan → notifier 从未 start → `_conn is None` 恒成立，所以全部 SSE 测试实际验证的是降级路径，
     真 LISTEN 只有 `test_wait_for_wakes_on_notify` 一条集成测在作证。锚：notify.py:58-60、main.py:51-52）

367. ⬜ 连接在某个等待者**已经挂上之后**才断掉，这个等待者会被唤醒吗？（站 11 观察 (67)）
     （**不会**。`_run` 的 finally 只把 `self._conn = None`，**不遍历 `_waiters` 把它们叫醒**。
     于是：新来的 `wait_for` 立刻走降级 2s 节拍，而已在途的等待者要熬满 `_WAIT_TIMEOUT_S=25s` 才醒来重查。
     后果是一次断连给在途的流最多加 25s 静默（正确性不受损，重查一定发生）。
     修＝finally 里 `for bucket in self._waiters.values(): for e in bucket: e.set()` 两行。
     一般化＝**降级开关只对"之后来的人"生效，是降级设计的常见半拉子**）

368. ⬜ `while not self._stopped and not conn.is_closed()` 这条守连循环能发现什么样的断连、发现不了什么样的？
     （能发现**显式关闭**（服务端重启/被 kill 会发终止包，asyncpg 标记 closed）；发现不了**网络黑洞**
     （TCP 无回应但未收到 FIN/RST）——没有心跳查询、没有配 TCP keepalive，OS 级超时可达数分钟。
     黑洞期间 `_conn` 仍非 None → `wait_for` 走"信任通知"分支 → 每次熬满 25s。
     **失效模式（25s）比设计好的降级模式（2s）慢 12.5 倍，且静默**（站 11 观察 (68)）。
     修向＝守连循环里定期 `SELECT 1`（或 asyncpg 的 `conn.execute` 探针），失败即翻降级）

369. ⬜ `poll_interval_s` 一个参数同时充当"降级轮询节拍"和"重连退避间隔"，问题在哪？
     （**两个用途的优化方向相反**：想让降级形态更灵敏就该调小（面向延迟），想让 DB 挂掉时不被重连风暴
     淹没就该调大（面向负载）。合成一个旋钮＝拧任何一边都会误伤另一边，且这件事从未被论证过。
     同族＝站 5 口径⑵「**能被单独拧的旋钮不该与别的旋钮有隐式耦合**」（那里是重排权重 0.7/0.3 与阈值的
     绑定）。当前默认 2.0 对两个用途碰巧都合理，所以它是一处**潜伏**而非现行缺陷。锚：notify.py:34、59、99）

370. ⬜ 触发器为什么 `RETURN NULL`？为什么没有 `WHEN` 子句？由此通知量等于什么？
     （AFTER 触发器的返回值被忽略，`RETURN NULL` 是惯例写法（BEFORE 触发器返回 NULL 才有"取消本行"的语义）。
     无 WHEN＝**每一条 events 插入都发一次通知**，而 GET 通道只把其中一个子集译成帧——所以
     **通知量 ≡ 事件量，不是帧量**（一轮工具调用会发 llm_call/tool_call/tool_result/llm_result… 好几次）。
     代价：唤醒后重查可能译出零帧但游标照常前进（正确）；收益：不需要在 SQL 里维护"哪些事件类型
     值得通知"这份与 `_translate` 重复的知识——**过滤知识只留一份，在 Python 那边**）

371. ⬜ 迁移里函数用 `CREATE OR REPLACE FUNCTION`、触发器用裸 `CREATE TRIGGER`——这个不对称是有意的吗？
     （无据可考、大概率是顺手。后果：这条迁移**函数幂等、触发器不幂等**，重复执行会 `already exists` 报错。
     alembic 版本表在管所以实际不可达，但与 M3.3 那条**刻意全幂等**的手写迁移（角色/GRANT 都写了幂等形态）
     纪律不一致。PG14+ 已支持 `CREATE OR REPLACE TRIGGER`，一处一词即可对齐。属"小到不值得单独修、
     下次碰这个文件时顺手"的一类）

372. ⬜ `test_events_insert_trigger_in_place` 为什么只查 `pg_trigger` 断言触发器在位，不直接测"插一行收到通知"？
     （**SAVEPOINT 夹具下事务永不提交，而 NOTIFY 只在提交时投递**——直测必然永远收不到，是夹具前提与
     被测语义的冲突。所以分工：**分发机制**用真原生连接 + `pg_notify` 直发测（`test_wait_for_wakes_on_notify`）、
     **触发器在位**用元数据查询测、**端到端"插入→通知→推帧"**只有真实链路验收（五幕）作证。
     同族＝偏差(49) 崩溃模拟预置状态与崩溃点对表、偏差(53) SAVEPOINT 夹具不支持测试内并发协程——
     三次都是**"夹具的隐含前提必须与被测形态逐一对表"**）

373. ⬜ 单频道 `aegis_events` 广播给所有副本，这算跨租户信息流动吗？
     （算，但在 v1 是**已知且可接受的边界**：payload 只有 session_id 与 seq，且每个 API 副本本来就服务全部租户
     （无按租户分片），所以没有"本不该知道的进程知道了"。真正的代价是**扩展性**：通知量随全局事件量增长，
     每个副本都要收全量再本地过滤。升级路径＝按租户分频道（`aegis_events_{tid}`）——但那要求
     LISTEN 端知道自己关心哪些租户，与"任意副本服务任意租户"冲突，故 v1 不做。属 atlas 已知边界一条）

### 单元 C＝重订阅端点与审计读面（`api/stream.py` 160 行 + `api/events_view.py` 67 行）

374. ⬜ GET 通道第一批为什么是"先回放事件、再发 message_reset、然后才进活尾"？这个位置为什么是唯一正确的？
     （msgbuf 里装的是**当前 run 累计流出、但还没落成 `assistant_message` 事件**的那段文字
     （`_TokenEmitter._acc` 全量覆盖写，run 收尾 `clear()`）。所以它在时间轴上恒**新于**任何已落盘事件：
     放在回放之前，客户端会先看到新文字再被旧事件盖掉；放在活尾之后，中间到达的实时帧会被它整条覆盖。
     只有"回放之后、活尾之前"这一格是对的。语义是**覆盖不是追加**——客户端断线前看到了这段的多少字
     是不可知的，所以只能整条重写。锚：stream.py:136-147、service.py:96-105）

375. ⬜ msgbuf 到底是"通道私有副本"还是"事实投影"？（站 9 观察 (52) 在此裁决）
     （**写它的时候当副本，读它的时候当事实**——这就是 (52) 的病根。证据三条：⑴只有 POST 路径
     （有 `text_sink` 的那条）会生产它，worker 驱动的续跑不写，于是那种场景重连**没有 message_reset**；
     ⑵它不经单写者 `EventWriter`、没有 seq、不进 C31 归一化；⑶但 GET 通道——**另一条通道**——
     把它当权威内容推给用户。再加上终局守卫替换只覆盖事件面不覆盖它（(52) 本体），
     结论是：**它是一个只有一条路径生产、却被另一条路径当事实消费的第三方状态**。
     两个正解方向：要么承认它是通道副本（那 GET 就不该读它，代价＝断线丢半句），
     要么升格为事实（那就要过单写者与守卫，代价＝每 token 一次写事件，不可接受）。v1 选了中间态并接受后果）

376. ⬜ 关流为什么必须是两条判据？只留其中一条各会怎样？
     （判据一＝本批见到 `loop_terminated`；判据二＝会话已归 idle/failed **且**本批无增量。
     只留判据一：**FAQ 直答类会话根本没有 `loop_terminated` 事件**（直答不走 loop）→ 永远不关流。
     只留判据二：`loop_terminated` 与 `run_state→idle` 是两次写（loop.py:697 vs 699），
     二者之间存在窗口——落在窗口里就要多熬一个 25s 等待周期才关。所以判据一还是**"不依赖两个事实的更新顺序"**
     的保险。锚：stream.py:148-157、loop.py:692-702）

377. ⬜ `awaiting_approval` 为什么不在关流状态集里？
     （**因为审批挂起时流必须留着**——这条通道的定位就是"断线重连与审批后续跑的统一入口"。
     挂起期间 run_state 既不是 idle 也不是 failed，于是循环继续每 25s 醒一次；
     坐席一批准，续跑事件落库、触发器发通知、这条流立刻推出后续帧（M3.10 五幕验收那句"瞬时推达"）。
     代价＝一条挂起会话最长可挂 `approval_ttl_s`＝3600s 的连接，每 25s 一次空查。锚：stream.py:154）

378. ⬜ 每次等 25 秒的时候，这条流占着数据库连接吗？为什么这件事重要？
     （**不占**。`async with factory() as s` 只包住那一次查询，`await notifier.wait_for(...)` 在**所有会话之外**。
     反例形态（把整条流包在一个 session 里）＝N 个并发 SSE 客户端就锁死 N 条池连接，
     几十个用户就能把连接池吃干——而 SSE 连接的特点恰恰是**长时间在线且大部分时间无事可做**。
     这是"长连接端点"的第一条纪律：**连接的生命周期不能跟着流的生命周期走**。锚：stream.py:124-131、150-153、158）

379. ⬜ `stream._translate` 与 `service._run_main` 这两份译表的差集有哪些？（站 9 观察 ㊾ 的完整版）
     （四条：⑴**逐 token vs 整段**——POST 的 token 帧来自 `text_sink` 一个字一个字，GET 的 token 帧来自
     `assistant_message` 事件**一次一整段**；⑵**工具轮前置文本**（"我帮您查一下…"）POST 看得见、GET 永远看不见
     （它没有事件，㊾）；⑶**兜底话术互换**（见题 380）；⑷**`user_message` 两边都不译**（见题 382）。
     共同点也要记：`last_tool` 跨事件携带的"工具串行"前提两份都有（㊿），并行工具一到两处同时错且无红灯）

380. ⬜ 一次"循环达上限"的兜底，POST 用户和 GET 用户看到的文字为什么不一样？
     （**代码级坐实 ㊼**：L2 的 `_terminate` 先把兜底话术写成 `assistant_message` 事件（loop.py:692-693）
     再写 `loop_terminated`；L3 的 `_run_main` 则把它**替换**成 `FALLBACK_LOOP_LIMIT`（"已为您生成工单…"）出帧
     （service.py:341-349，"替换非叠加"定案）。于是：**POST 实时**＝L3 话术、**GET 重放**＝L2 话术
     （`_translate` 照译那条 `assistant_message`）、**事件流/M4.3 回放**＝L2 话术、**坐席工单**＝第三种描述。
     一句话：**用户唯一看到的那句话不在任何可重放面里，而可重放面里那句话从没到过用户**）

381. ⬜ 两个通道的 `done.usage` 口径一样吗？
     （**不一样**。POST 的累计范围是 `runtime.run(...)` 这一次 run（service.py:309-312）；
     GET 的累计范围是 **`after_seq` 之后回放到的所有 `llm_result`**（stream.py:75-78），
     `after_seq=0` 重入一条老会话时，`done.usage` 是**整条会话历史的合计**。
     同名字段两套口径、无人声明——站 9"四下游各看一句"的又一例。站 11 观察 (72)。
     修向＝译表按 `run_id` 分段清零（事件行有 `run_id` 列，成本很低））

382. ⬜ `_translate` 为什么没有 `user_message` 分支？重入一条老会话时后果是什么？
     （对"断线重连回到同一次问答"的场景无害（用户自己那句还在屏幕上），但 M3.10 偏差(56) 已经把
     **"重入既有会话＋重放"定为标配件**（sid 输入框去 readonly 就是为这个）——在那个场景下，
     用户粘一个旧 sid 拉回来的是**只有半边的对话**：全是助手的回答，没有任何提问。
     `user_message` 明明在事件流里（loop.py:221 恒为首事件）。站 11 观察 (73)，修≈译表加一个分支）

383. ⬜ stream 端点 docstring 写的"admin 平台级"是真的吗？
     （**不是**。`_ensure_owned` 用的是常规 app 工厂（stream.py:39-40），而 `sessions` 表带 tenant_id
     **在 RLS 名单里**，auth 又对**所有角色**（含 admin）无差别 `current_tenant_id.set(principal.tenant_id)`
     （auth.py:144）→ admin 读他租会话时行**根本不可见** → `row is None` → 404「会话不存在」。
     代码里"只对 USER 做归属校验、admin 不校验"的写法说明作者**意图**是放行，是 RLS 把它悄悄拦了。
     性质＝fail-closed（不泄漏，只是功能不可用），但**能力声明与实际不符**。
     这是 #46「加防线会改变上层代码的可达路径」**家族第二例**——同族第一例是 `_ensure_session` 里
     `row.tenant_id != principal.tenant_id` 变成死代码。站 11 观察 (71)）

384. ⬜ 承 383：同一个提交 `d1d2275` 里的 `events_view.py` 为什么就没这个问题？
     （因为它**显式走了 owner 查读缝**（`app.state.approvals_lookup`，M3.9② 建的平台视角工厂，
     events_view.py:38-40），拿到行之后再用代码做租户判定。也就是说：**同一次交付里的两个兄弟端点，
     对"staff 跨租户查读要不要平台视角"给了两个不同答案**——一个想到了、一个没想到，
     而没想到的那个不会报错只会 404。这正是 #47「业务代码 × RLS 交互面在 CI 里没有证人」的具体形状：
     两个端点的测试都是绿的，因为测试连的是 owner 引擎，**RLS 根本不在场**）

385. ⬜ events_view 对 operator 跨租户返 **403 点名**，stream 对 user 跨租户返 **404 不解释**——两个相反的选择，判据是什么？
     （判据是**"存在性本身对这个身份是不是秘密"**。对终端用户，"这个 session id 存在"是可枚举的信息资产
     （#19 定的调子：不泄露存在性），所以统一 404。对 staff，同组织内"存在一个属于别家租户的会话"不是秘密，
     而**明确告诉他"你越租了"**比让他以为 id 打错更有运维价值——与 M3.9 对抗④审批端点跨租 403 同一口径。
     一般化：**对外不解释、对内说清楚**）

386. ⬜ events_view 有 `_MAX_EVENTS=1000` 上限，stream 的第一批回放为什么没有任何上限？
     （无据可考。stream 第一批是 `.where(seq > cursor)` 全量 `.all()`——一条跑了很久的会话重入
     （`after_seq=0`）会一次性把全部事件读进内存再逐帧编码。v1 会话短所以够用，
     但**流式端点里藏着一个无界查询**，与隔壁 1000 上限的谨慎不对称。同族＝站 10 (61)
     `sweep_once` 工作量无上界、隔壁 `list_expired` 有 limit=100 的先例——
     **"同一个仓库里，有上限的和没上限的写法并存且无人裁决"已经是第三次**。站 11 观察 (74)）

387. ⬜ events 端点的审计留痕落在哪里？这个"最小落地"的代价是什么？
     （一行 `logger.info`（events_view.py:55-62，02 §7.3 最小落地，事件化/落表/PII masker 归 M4.1）。
     代价：**留痕落在 v1 唯一没有归集的地方**——账本在 PG、事件在 PG、指标要等 M4.2，
     而进程日志在 Windows 本地开发形态下就是控制台。所以"谁看过谁的 trace"这件事目前
     **写下来了但取不出来**。诚实的表述是"已留痕、未可查"）

388. ⬜ 为什么终端用户被完全挡在 `GET /events` 之外（403），哪怕是自己的会话？
     （trace 是**内部视图**：`llm_call` 里有完整 prompt（含 SYSTEM_PROMPT 四规则与 UNTRUSTED_NOTICE）、
     `tool_call` 里有内部工具名与参数、`guardrail_triggered` 里有命中的规则名与打码片段——
     开给用户等于**把出口防护（OutputGuard 的工具名族/system 片段族）整条绕过去**：
     守卫拦的东西在 trace 里原样躺着（X4 事件存原文）。所以这条 403 不是权限洁癖，
     **它是出口防护的一部分**。锚：events_view.py:3-4）

389. ⬜ `limit=max(1, min(limit, _MAX_EVENTS))` 这个夹逼在防什么？
     （防两头：`limit=0` 或负数 → SQL `LIMIT -1` 在 PG 是报错、`LIMIT 0` 是静默空集（**查询参数能把
     "无权限"和"没数据"变成同一个响应**）；`limit=10**9` → 上限被绕过。夹逼一行同时把
     "客户端传什么都不会让服务端出非预期形状"钉死——同族纪律＝M3.4 `split_text` 的窗口下界、
     M2 各处 `max(0, …)`。**凡外部可控的数值直接进 SQL/切片，必须先夹逼**）

### 单元 D＝前端与装配收口（`aegis/web/chat.html` 232 行 + `api/main.py` 增量）

390. ⬜ 两个通道为什么都用 `fetch` 手写 SSE 解析，而不用原生 `EventSource`？代价是什么？
     （**原生 EventSource 不能带自定义请求头**，也就带不了 `Authorization: Bearer`——原生用法只剩
     "JWT 进 URL 查询串"一条路，而"凭证不进 URL/日志"是安全底线（URL 会进 access log、Referer、浏览器历史）。
     代价＝自己实现分帧（`\n\n` 切块、`id:/event:/data:` 前缀取行）与重连循环，约 20 行（ADR-007 后果栏
     "几十行"就是它）。**服务端协议一行没改**（照发 `id:`、照收 `Last-Event-ID`），
     所以将来换成 cookie 认证可以无损切回原生 EventSource——**折衷落在客户端，不落在协议上**）

391. ⬜ 为什么 POST 流断了必须"整段重建"，而 GET 流断了可以"无缝续传"？
     （**因为只有 GET 的帧能寻址到事实**。GET 每帧带 `id:=events.seq`，客户端记住 `lastSeq`，
     重连时 `after_seq` 一送就精确接上；POST 的 token 帧**没有 seq 也不可能有**——它是流中文本的瞬时切片，
     根本不对应任何一行已提交的事实（那时 `assistant_message` 事件还没写）。
     所以断点在 POST 流里**不可表达**，唯一正确的恢复方式是"忘掉本地状态，从事实源重画"＋
     `message_reset` 盖住那半句。一句话：**可续传性 = 帧能不能寻址到事实**。锚：chat.html:168-169、196-197）

392. ⬜ 客户端怎么知道"这次挂起去等审批了"？
     （靠 **`approval_pending` 出现过 且 `done` 没出现过**（chat.html:137/151-158）——因为服务端挂起时
     **刻意不发 done**（service.py:337-339 清缓冲直接 return）。也就是说：**"没有发什么"也是协议的一部分**。
     判到这个组合就自动换轨到 GET 通道等续跑（"🔀 挂起：切换到重订阅通道"）。
     这是帧协议里唯一一处用"缺席"传递信息的地方，值得在 ADR-007 里写明——否则第二个客户端实现必踩）

393. ⬜ `lastSeq` 为什么只认 GET 帧的 `id:`？POST 帧会不会污染游标？
     （不会：`encode_frame` 只在 `frame.seq is not None` 时才写 `id:` 行，而 service 层产的帧一律不带 seq
     （seq 字段是 M3.10② 给 GET 回放加的）。所以 `if (f.id !== null && f.id > lastSeq)` 天然只被 GET 帧触发。
     两侧同一个约定、各自守住一半——**协议里"字段何时缺席"和"字段是什么值"一样重要**）

394. ⬜ POST 断线后点【断线重连】，面板被清空重建——**用户自己刚发的那句话去哪了**？
     （**永久消失**。`resubscribe(true)` 先 `$("pane").innerHTML = ""`（chat.html:173），
     而重放来的帧里**没有任何 user 侧内容**（`_translate` 不译 `user_message`——站 11 观察 (73)）。
     所以这不是"重入旧会话"才会遇到的边角场景：**它在 M3.10 验收幕 D 的标准路径上就会发生**，
     只是当时所有人都盯着 assistant 那半句有没有被 `message_reset` 盖上。
     这条把 (73) 从"重入场景的缺陷"升级为"标准演示路径的缺陷"）

395. ⬜ 助手气泡的边界靠什么信号？一条 FAQ 直答很多的会话，重放时会长什么样？
     （靠 **`done` 帧**——`handleFrame` 只在 `done`/`error` 时 `bubble = null`（chat.html:121/125），
     其余 token 帧一律往当前气泡里追加。主 Agent 会话每个 run 以 `loop_terminated` 收尾，所以 done 恰好
     兼任了消息分隔符。**但直答类会话没有 `loop_terminated`**（不走 loop）→ 重放时 N 条直答的
     `assistant_message` 会被**连成一个气泡**，中间既无分隔也无提问（题 394）。
     根因＝**帧协议没有"消息边界"这个概念，是 done 在兼职**；直答路径不发 done，兼职就落空了。
     站 11 观察 (75)。修向＝译表在每条 `assistant_message` 后补一个边界帧，或让 token 帧带 event_id）

396. ⬜ 页面为什么从头到尾用 `textContent` 而不是 `innerHTML`？
     （因为气泡里装的是 **LLM 生成的、且可能包含用户与工具回传内容的文本**——用 `innerHTML` 就等于
     把模型输出当 HTML 执行，一次提示注入即可拿到页面上的 Bearer token（它就在 DOM 里）。
     `textContent` 让这条路彻底关闭。**这是站 8 前瞻边界的对照组**：那里说"工单标题是 LLM 可控自由文本，
     一旦进坐席界面渲染就是标准存储型注入面"——聊天页这一侧做对了，M4/M5 做坐席页时必须照抄这条纪律）

397. ⬜ Bearer token 放在 `<textarea>` 里、不进 localStorage，刷新就得重新粘——这是 bug 还是取舍？
     （取舍，而且是对的一侧：localStorage 可被任意 XSS 读取，把长效凭证放进去等于给注入面配钥匙
     （尤其页面还要渲染模型输出）。代价是演示不便——**M3.10 偏差 (56)「页面刷新丢会话」的根因其实有两半**：
     sid 每次随机新生成（已修＝输入框去 readonly）与 token 不持久（未修，也不该修）。
     诚实的表述是"会话身份可携带了，凭证仍需手工带"）

398. ⬜ 真实网络断线与点【断线重连】按钮，页面行为差在哪？服务端"断连不取消生产者"这个设计被兑现了吗？
     （**差在自动不自动**：`simulateDrop()` 会主动 `resubscribe(true)` 换轨（chat.html:198-201）；
     而真实断线走的是 `send()` 的 catch 分支——只 `sys("⚠️ POST 流异常")` 然后恢复按钮，**不换轨**
     （chat.html:159-163）。可是服务端此刻**仍在继续跑这次 run**（M3.10② 拍板：断连不取消生产者，
     就是为了让客户端回来补收）。结果：服务端为重连做好了全部准备，客户端在真实场景里没有兑现它——
     用户看到一行警告，然后一切停住，除非他手动点按钮。站 11 观察 (77)。
     修≈catch 分支里调一次 `resubscribe(true)`，与演示按钮同一条路）

399. ⬜ `create_app` 有十个注入参，它们的组合空间里实际被验证过的是哪几个？
     （只有两个角：**全缺省**（生产链）与**测试常用的那几组**。中间组合会静默降级，已知两个实例：
     ⑴注入 `runtime` 但不注入 `chat_service` → ChatService 拿到 `lock=None`（站 1-3 观察⑤，直答/转人工无互斥）；
     ⑵注入 `runtime` 但不注入 `msg_redis` → `msg_redis` 的缺省赋值在 `if runtime is None` 分支**里面**
     （main.py:80-81）→ ChatService 拿到 `redis=None` → 无 msgbuf → GET 重连**静默丢半句**。
     两次都是"注入了 A 就顺带关掉了 B"，且都无告警。站 11 观察 (76)。
     docstring 只警示了"注入 runtime 不给 gateway＝聊天不可用"这一条最响的）

400. ⬜ 为什么 `EventNotifier` 在 `if runtime is None` **之外**构造，而 `msg_redis` 在**里面**？
     （notifier 是**端点自己的依赖**（GET 通道要用），任何形态的 app 都得有一个（哪怕没 start＝恒降级轮询）；
     msg_redis 是**生产链的一环**（ChatService 的缓冲），测试形态注入 runtime 时通常不想要真 Redis。
     判据是"**这个资源属于端点还是属于装配链**"。副作用见题 399⑵——判据本身合理，落点造成了一个隐式耦合）

401. ⬜ 站 10 观察 (64) 举的例子是"`text_sink` 只加在 API 侧、worker 侧漏了"——这个例子举对了吗？
     （**没举对**。`text_sink` 从来就不是装配参数：它是**每请求物**，由 `service._run_main` 在调用点传入
     （service.py:306），`create_app` 与 `_task_runtime` 两边都没有它，谈不上"漏"。
     (64) 的**主张**（"装配面逐件对应只是人肉承诺、机制上区分不了有意与遗忘"）成立，
     但**证据**要换成 `msg_redis`：worker 侧没有 `_TokenEmitter` 故不写 msgbuf → worker 驱动的续跑期间
     重连**收不到 message_reset**，而 API 侧收得到。这条真不对称与单元 C 对 (52) 的裁决同源）

402. ⬜ `/chat` 为什么必须由后端同源出页（`FileResponse`），直接双击打开 html 文件不行吗？
     （`file://` 打开的页面向 `http://localhost:8000` 发请求是**跨源**，会撞 CORS 预检；而项目**刻意不加
     CORS 中间件**（最小攻击面）。由后端同源出页 = 零中间件解决问题。锚：main.py:109-111。
     顺带：`_CHAT_PAGE` 用 `Path(__file__).resolve().parents[1]` 锚定，不依赖 cwd——07 §4 第 7 条）

403. ⬜ lifespan 只管 `EventNotifier` 的起停，Redis 客户端与数据库引擎为什么不管？
     （因为它们是**进程级手动 global 单例**（00 §2.2 数据访问行："值用 lru_cache，资源手动 global"），
     生命周期与进程同寿、由 OS 回收；而 notifier 持有一条**必须显式 LISTEN/取消的后台任务**，
     不停会留下悬挂 task 与未关连接。判据＝**这个资源有没有"进程还活着但它该停"的时刻**——
     有则进 lifespan，没有就别加仪式。对照＝worker 侧 `_task_runtime` 的 finally 五连 await（站 10 (63)），
     那里资源是**任务局部**的，所以必须显式关）

---

## M4.0 治理层开工（M4.0①② 产出，2026-08-03）

404. ⬜ `approved ∧ event_id IS NULL` 被用作"批准已落锤但未兑现"的判据。这个代理为什么会出错，
     以及"用一个字段的空代理一件事没发生"要先证明什么？
     （**必须先证明这个字段没有第二种为空的理由**。`event_id` 确实是"批准已兑现"的唯一凭证
     （`attach_event` CAS 恰一次），但它为空有**两种**成因：⑴ 崩在批准与兑现之间（要认领）；
     ⑵ **precheck 否决**——无执行事件可挂，单据合法地停在该状态（14i 拍板Ⅳ 登记的已知边界）。
     两义相撞的后果：veto 孤儿单**永远**满足该谓词，于是此后任意一次"无悬挂工具"的崩溃恢复
     都会把它捞进 a+ 认领支——本该走 c 支作废重发的新 run 被劫持。M4.0① 探针实测两个后果：
     分诊走错支；**precheck 此刻若放行，会执行一次本轮从未请求的写操作**。
     同族对照＝站 10 口径⑵ 的一般化）

405. ⬜ 修候选③ 时为什么判据选"该单 approval_requested 之后是否已有 loop_terminated"，
     而不是加时间窗或给审批单加 run_id 列？
     （**时间窗要选阈值，选多长都是猜**——这与 M2.10 否决"beat 超时扫描重投"是同一条推理：
     超时启发式必然误判"慢而未死"，而状态事实不会。加 `run_id` 列则是**给已经能推出的事实
     新增冗余存储**，还要配迁移与回填。选中的判据只读 `rows`（本就是全量事件按 seq 排序、
     `claim_req_index` 本就算好了）——**零新字段、零新查询、零迁移**。
     它不误伤真认领的原因也值得说：W1/W2/W2.5/W3 四个真崩溃窗的**共同特征恰是
     `loop_terminated` 没写成**（崩在它之前），所以新判据对它们全部放行）

406. ⬜ precheck 的拒因为什么必须粗粒度化？它和 `_shared.DENIED_TEXT` 的三路同话术是什么关系？
     （**风险闸门在 handler 之前**（executor.py:148 vs :186）——这是全链唯一一处"没有
     `fetch_owned_order` 把关、却能读到订单事实并说出口"的路径：越权+超阈值会先挂审批单，
     坐席批准后 `_load_order`（无 user 维度）读到同租户他人订单，拒因经 SYSTEM_PROMPT
     **规则 4「如实转达」**复述给用户。四种拒因彼此可区分＝存在性+状态+金额的 oracle，
     而 `DENIED_TEXT` 三路同话术**正是为抹平它而设计的**——precheck 是这条设计的旁路。
     反证：`refund_apply` 自己的 409 路径**不需要改**，因为 `fetch_owned_order` 在
     `post_write` 之前，他人订单根本走不到 409，那条 detail 里的金额是说给单主自己听的。
     根因口径＝站 10 口径⑴：**拿不到身份的层，输出必须对所有身份安全**）

407. ⬜ 粗粒度化为什么只针对"订单派生拒因"，而"退款金额非法（须为正数）"可以保持具体？
     （因为后者是**参数事实**不是订单事实——它只复述模型自己给出的参数形状，不泄露任何人的数据。
     这条分界线让修复不至于矫枉过正：把所有反馈一律抹平会让模型失去自我纠错的依据（它连
     "我参数写错了"都不知道），而那部分信息本来就没有安全代价。
     **判据＝这句话的内容来自谁**：来自被查询的对象→统一话术；来自请求者自己→可以具体）

408. ⬜ 修候选④ 时，为什么只把 `_ensure_owned` 换成 owner 查读缝是不够的？
     （因为 `stream` 端点里有**两处** `SessionRecord` 读：归属校验 + 关流判据
     （`run_state`）。只换前者的结果是"流开了立刻关"——关流判据读不到行会拿到 `None`，
     而 `None` 恰好落在 `(IDLE, FAILED, None)` 这个"可以关流"的集合里。
     这是**加防线改变可达路径**（#46 家族）的第二重表现：不仅 if 分支会变死代码，
     `scalar_one_or_none()` 的 `None` 分支还会**恰好撞进另一个语义正确的集合**里，
     不报错、不留痕。顺带：事件读**不用换**——`events` 无 `tenant_id` 列、不在 RLS 名单
     （P5：仅带 tenant_id 列的表），这也是为什么兄弟端点 `events_view` 只换了会话读那一处）

409. ⬜ 同族的两个风险闸门 `refund_needs_approval`（缺省 200）与 `coupon_needs_approval`
     （缺省 0）对"租户 config 少一个键"给出了相反的行为。为什么这本身就是缺陷信号？
     （因为**同一类闸门对同一种故障的失败方向必须一致且被论证过**（站 8 口径⑶ 的邻题）。
     这里只有 coupon 那条写了理由（"缺省 0 = 任意正面额都挂审批——安全闸门 fail-closed 缺省"），
     refund 的 200 是**从业务示例值（01 §5 租户 A 的阈值）顺手滑进缺省值的**——它冒充了一个
     业务阈值，让"漏配"看起来像"配了 200"。后果：新租户漏配 → 200 元以下**静默直退**，
     无审批无告警无痕迹，与 00 §2.2「安全闸门 fail-closed」直接冲突。可达性不低：
     #21 治理路径下"种子即初始化入口"，漏配是现实运维事故。
     未选"缺键即启动炸"的理由：`build_agent_spec` 是**每请求**装配（观察㊵），在那里炸的
     后果是 500 空流而非启动期失败，比 fail-closed 更糟）

410. ⬜ `_task_runtime` 的 finally 里五个串行 `await` 不加保护，具体会烂在哪里？
     （**一件抛则其余全部跳过**：长驻 worker 每执行一次任务就泄漏一条 HTTP 连接池／Redis
     连接／DB 引擎，累积成"跑了一天之后 worker 打不开新连接"——而这个故障现场离病根
     隔了几千次任务。第二层伤害：清理期的次生异常会**顶掉 try 体内真正的首因**
     （M2.12 偏差 #7 同族），排障时看到的是"mock 关闭失败"而不是那个真正让任务崩掉的异常。
     修法用 `(名字, 可调用)` 元组表驱动而非四个 try 块，是为了让"**顺序即协议**"一眼可读；
     `set_mock_client(None)` 留在循环外，因为它是纯内存赋值不会抛、且必须先于 `mock.aclose()`）

411. ⬜ M4.0① 的四枚候选此前全是读码推断，为什么"定级前必须实测"这条纪律值钱？
     （因为实测**推翻了其中一条的危害描述**：候选③ 原述"用户刚问的话被完全忽略"不成立——
     `_rebuild_working` 带的是全量事件，新消息仍在 prompt 里。危害的**方向**说偏了，
     但结论不变，而且实测顺带挖出更重的 3b 支（执行一次从未请求的写操作）。
     另一例：候选① 实测发现 sink 累计 248 字 vs 事件 content 42 字——比"双发话术"更值钱的是
     **终局守卫在有通道模式下止损能力≈0**（已推流不可撤回，D11 显式接受），
     这条该进 atlas 已知边界而不是当 bug 修。
     一般化：**读码推断给的是"哪里可能有问题"，实测给的是"问题到底是什么形状"**——
     定级、排期、修向三件事都依赖后者）

412. ⬜ 密钥扫描为什么必须**阻断式**且**扫全历史**？只扫最新提交漏掉了什么？
     （**阻断式**：非阻断的扫描等于"记录一下你泄漏了"，而密钥的特性是**泄漏瞬间即失效**——
     一旦进过公开历史就只能作废换 key，事后知道不能挽回任何东西。这与 lint 不同：
     lint 红了改代码就行，密钥红了改代码没用。
     **扫全历史**（`fetch-depth: 0`）：只扫最新提交回答的是"这次有没有带进来"，
     漏掉的恰是唯一不可逆的情形——**"密钥曾经在某次提交里出现过、后来被删掉了"**。
     它在工作区看不见、在 diff 里看不见，但 `git log -p` 里永远在，任何人 clone 都拿得到。
     位置也是判据的一部分：扫描放在 checkout 之后**第一道**，因为后面每一步
     （装依赖、跑测试、打日志）都可能把仓库内容打进 Actions 日志）

413. ⬜ `.gitleaks.toml` 的 allowlist 为空时，为什么仍然要保留这个文件？
     （让"**加豁免**"这个动作必须显式发生在版本历史里。若没有配置文件，第一次需要豁免时
     人们倾向于就地加 `continue-on-error` 或删掉这一步——那是把门整个关掉；有了文件，
     豁免变成一次带 diff、带理由注释、要过 review 的提交。
     一般化：**安全配置的默认形态应该让"放松"比"收紧"更费力**，
     而不是相反。同款设计=`.gitleaks.toml` 里每条豁免旁边强制写"为什么它不是真密钥"）

414. ⬜ `alembic check` 补上的是哪个洞？为什么"CI 先 alembic 后 create_all"这个组合本身不报错？
     （洞＝**ORM 改了但没生成迁移**。为什么无人报错：CI 跑 `alembic upgrade head` 建库，
     而 conftest 的 `create_all` 是本地兜底且**对已存在的表是 no-op**——
     于是"迁移链建出的表"与"ORM 声明的表"不一致时，两条路径都安安静静：
     迁移路径按老 schema 建好了，create_all 看见表已存在就跳过，**新加的列静默缺失**。
     真相要到某个测试恰好用到那列才炸，而且炸在离病根很远的地方。
     `alembic check` 的位置也是判据：必须在 `upgrade head` **之后**——
     它比对的是"迁移链建出的库"与"当前 ORM 元数据"，没有库就无从比对）

415. ⬜ M3.4 的注释说"autogenerate 不认识 `USING hnsw`，故 HNSW 索引一律手写"。
     这句话在 M4.0③ 被修正成了什么？为什么这个区分重要？
     （修正为：**只对"生成"面成立，不对"比对"面成立**。autogenerate 确实不会自动
     *写出* `CREATE INDEX ... USING hnsw`（所以当初手写迁移的决定依然正确），
     但只要 ORM 侧用 `postgresql_using` + `postgresql_ops` 声明了，它**认得**并能正确比对
     （scratchpad 探针用 `compare_metadata` 实证：补声明后差异归零）。
     区分之所以重要：不做这个区分就会得出"HNSW 与 alembic check 天然不兼容"的错误结论，
     进而选择 `include_object` 把该索引排除在 check 视野外——那是**用"让门看不见"换"门变绿"**，
     索引将来被误删也无人报警。补声明才让"ORM 是事实源"这句话真的成立。
     附带教训：探针脚本只 import 了部分模型时会报出一堆 `remove_table` 假差异——
     **读 autogenerate 差异前必须先确认 metadata 装载完整**）

416. ⬜ `_ensure_session` 的 `IntegrityError` 分支里，404 为什么用 `raise ... from None` 而不是 `from e`？
     （因为 `IntegrityError` 在这里**不是错误，是预期内的并发信号**——"另一个请求刚好先建了这行"
     是设计中的正常路径（首见建行的竞态），而 404 是给客户端的正常答复。
     挂上异常链会让每一次正常的跨租户撞键都在日志里留一段 DB traceback，
     既是噪音又暗示"这里出了故障"。语义上它也与同函数下方那条 404（非 except 块内、
     天然无链）对齐——同一个答复不该因为走到它的路径不同而带上不同的因果尾巴。
     反过来说，若 except 捕的是真正的意外（比如连接断了），那就该 `from e` 保留链）

417. ⬜ `task_acks_late=True` 到底保证了什么、**没有**保证什么？为什么它单独不足以构成"至少一次投递"？
     （它只保证**消息不在任务执行前被 ack**——崩溃时消息留在 broker 的 unacked 集合里，
     即"不丢"。但把 unacked 消息**放回队列**是另一件事：在 kombu 的 Redis transport 里，
     那是 `restore_visible` 干的，判据是消息进入 unacked 的时间超过 `visibility_timeout`
     （默认 **3600s**）。所以完整的"至少一次"= `acks_late`（不丢）× `visibility_timeout`
     到期（回队）× **有人定时触发 restore**（下题）。M4.0④b 实录之前，本项目只做到第一项，
     却在文档里写成了"至少一次投递"——**配置改了 ≠ 行为验证了**，这正是补 kill -9 实录的理由）

418. ⬜ 为什么 Windows 上的 Celery worker 永远等不到 unacked 消息重投？这个结论对 pool 敏感吗？
     （kombu 把恢复挂在 event loop 上：`loop.call_repeatedly(10, cycle.maybe_restore_messages)`
     （kombu/transport/redis.py:1382），而这行只在 `Transport.register_with_event_loop` 里执行；
     celery 的 `WorkController.should_use_eventloop()` 是
     `detect_environment()=='default' and transport.implements.asynchronous and **not app.IS_WINDOWS**`
     ——**Windows 恒 False → 走 `synloop` 无 hub → 那行永不注册**。
     **对 pool 不敏感**：不是 solo 的问题，solo/threads/gevent 在 Windows 上一样；
     Linux + prefork 走 `asynloop` 才正常。
     诊断方法值得记：先查 broker 实际状态（消息在 unacked 还是队列）→ 再读 transport 源码
     找恢复机制 → 再**手动调一次** `restore_visible` 分离"逻辑坏了"与"没人调用"。
     手动调用立刻恢复，就把问题从"为什么不工作"缩小成了"为什么没人调它"）

419. ⬜ kill -9 实录要跑真 worker、真 broker，但 M4 的真实调用口径只允许 M4.4/M4.6 花钱。怎么两全？
     （抓住**配置项就是注入缝**这一点：`build_embedding_client` 读的是
     `settings.dashscope_base_url`（factory.py:87），把它指向本地假服务即可——
     **生产任务体一字不改**，跑的是完整的 `ingest_document → _ingest_fresh → ingest_once`。
     假服务必须按真协议面应答，因为 `EmbeddingClient._post_once` 有三重形状校验
     （条数 / `index` 归位 / 维度）且都是 fail-loud 的，糊弄不过去——
     **这恰恰说明那三道校验有价值：它让"假下游"也必须是诚实的假**。
     对照 M3.7 的 mock_backend：同一条哲学"假边界要假到能复现失败分类"）

420. ⬜ 实录里把 `visibility_timeout` 从 3600s 调到 60s、并手动触发 restore，这算不算"测了个假东西"？
     （不算，但**必须写清替换了什么**。被替换的只有"谁来定时调用"这一环；
     超时判定（`ceil = time() - visibility_timeout`）与 restore 逻辑本身仍是生产实现，
     幂等消费、`IS NULL` 续传、账本记账也全是真的。这与 M2.9 审批超时用注入时钟、
     M2.10 用可注入 clock 是同款手法：**改的是实验装置的时间尺度，不是被测逻辑**。
     纪律在于凭证里必须显式印出差异与未覆盖面（本实录末行就是那句"未覆盖：定时器自动触发
     restore……挂 M4.7 Linux 复验"）——**实验的价值等于它诚实声明的边界**）

421. ⬜ 实录结果里"假服务调用 2→4 批、账本 embedding 行=3、理论批数=3"——这三个数字各说明什么？
     （25 块 = 3 批。**调用 4 批**＝理论 3 批 + 崩溃当批重做 1 次，正好落在
     "重复成本上界 = 一批 `EMBED_BATCH_SIZE`"上——上界来自"每批独立事务"+`IS NULL` 谓词
     让已回填行天然出队（重投不会从头再来）。
     **账本只有 3 行**比上界还好：崩溃当批的计量随那个未提交的事务一起回滚了，
     故**零重复计费**——这说明"每批独立事务"的红利比设计时预期的更大（不仅限制重做量，
     还让重做不产生重复账）。
     反过来读：若账本出现 4 行，也仍在可接受范围（计量是 fail-open 的软路径），
     但那会意味着计量与回填不在同一事务边界内——**这三个数字合起来是一次事务边界的体检**）

422. ⬜ M4.0 一步之内四道"已经装好的门"被逐个拆验，两道有洞两道完好。
     把这四次合起来看，"配置改了 ≠ 行为验证了"具体分几种失败形态？
     （**形态一·开关空转**（#48）：`task_acks_late=True` 配了、CI 还有断言钉着它，
     但真正把消息放回队列的定时器挂在 event loop 上，而 celery 在 Windows 上恒不用 hub
     → 开关是真的、语义只兑现一半。**症状是"什么都没发生"**，最难发现。
     **形态二·门从没扫过东西**（#24）：gitleaks 步骤绿了很多次，但 action 对 push 只扫
     增量 commit，而历史里那 6 处从来不在范围内。**绿灯是真的，只是它什么也没说**。
     **形态三·探针本身无效**（红绿验证）：`AKIAIOSFODNN7EXAMPLE` 撞 gitleaks 自带 stopword
     → 即使门在工作也不会红。**这是最危险的一种：假阴性伪装成通过**，
     你会拿着一个绿灯宣布"验证过了"。
     **形态四·门是好的**（`alembic check`、#29 粘滞化）——但也只有验过才知道。
     统一的纪律：**任何"防线"都要有一次故意触发它的实录**；红绿验证的探针
     **必须先本地实证会被抓再推上去**，否则那个绿零信息量）

423. ⬜ 为什么 M3 复盘的 77 条观察要单独建 §10.1-bis 账本，而不是并进 §10.1 主表？
     （因为**账本和主线是两种东西**：§10.1 追的是跨里程碑的遗留主线（几十条、每条都有
     独立来源与归位），77 条观察一次性涌入会让它膨胀三倍并把主线彻底淹没——
     读者从此再也不能靠扫一遍 §10.1 知道"项目还欠什么"。
     拆开后 §10.1 只留一行指针（#51），账本自带里程碑归位。
     顺带一条纪律：**结案不等于"没问题"，等于"已论证过不做"**——理由必须写下，
     否则日后翻案时没人记得当初为什么放过它。
     归位分布本身也是信息：M4.7 积压 18 条说明"容器化"那一步的真实范围
     远超 00 §8.1 标的 S→M，届时必须重估）

424. ⬜ 做 `alembic downgrade base → upgrade head` 往返，验的是 `alembic check` 验不到的什么？
     （`check` 只比对"当前库 vs 当前 ORM"，走的是**正向**且只看终态。往返验的是
     **反向可达性**：8 个迁移里有 4 个是手写 DDL（RLS 角色与策略／EXTENSION+HNSW／
     mock 两表／NOTIFY 触发器），它们的 `downgrade()` 分支在此之前**一次都没执行过**——
     手写的东西没人替你检查对称性。M4.7 容器化的回滚预案正依赖这条能力。
     附带产出两项：坐实 08 记的"迁移链 9 个"实为 8（列举漏了 M1 首个迁移），
     以及一条成本教训——**"数据可重建"不等于"重建免费"**：清库让摄取幂等失效，
     种子重建全量重走了一次 embedding（20 行 / 2955 token / ¥0.001481），
     这是 M4.0 唯一一次计划外真实调用，已记账）

## M4.1 · trace 查询 API（obs 底座/端点升级/PrecheckVeto，2026-08-03）

425. ⬜ 为什么自研 trace 而不接 OpenTelemetry？两者的关系是什么？
     （04 C37 背稿：本项目的 trace 单位是"会话/run/事件"这一**业务语义层**——我要看的是
     token、工具序列、终止原因，不是跨服务 RPC 树；单体+Celery 的拓扑里 collector/exporter
     的运维负担大于收益。两者不互斥：映射已清晰（session=trace、run=root span、事件=span
     event），obs 查询 API 是稳定接口，v2 加 OTel 导出器不动调用方。一句话：**"我需要的是
     LLM 语义的可观测，先做业务 trace；OTel 是导出格式问题，不是设计问题。"**）

426. ⬜ `aegis.obs` 为什么放在与 `aegis.apps` 同层互不 import，而不是 M4.0 时建议的
     "runtime 之下、gateway 之上"？
     （低位方案经实测三连否决：①obs 够不到 `guardrails.PII_RULES_V1` 与 store ORM——
     "masker 与出口守卫共用同一张表"的单点被迫退化成复制常量或动 M2 冻结件；②M4.2 已裁
     "runtime/gateway 不许 import obs"（进程内指标只在 api 层打、DB 派生指标 scrape 现算），
     低位的唯一潜在收益（让下层用 obs）为零；③同层 `|` 语义把"业务永不依赖可观测"变成
     import-linter 强制而非口头纪律。**决策方法**：先列这个包要 import 谁、谁会 import 它，
     再看契约语义——层位是这两张清单的交集，不是审美。锚：pyproject.toml:74-80）

427. ⬜ PII 脱敏为什么绝不做在 events 写路径，只做在展示出口？
     （events 是**恢复的唯一事实源**（02 §7.3）：脱敏的事件流会让恢复后的上下文与崩溃前
     不一致——物流工具需要真实手机号，打了码的号码恢复后寄不了件。代价是 events 表纳入
     PII 管控（仅 operator+ 可访问且留审计——矩阵与审计行 M3.10/M4.1 兑现）。
     对照测试形态：`test_payload_masked_in_view_but_raw_in_store`——同一条事件，
     视图打码、库里原文，一条测试钉两面。**"存原文"是主动选择的取舍，要能讲**）

428. ⬜ TraceAssembler 查账本为什么必须包 `tenant_context(会话租户)`？不包会怎样？
     （usage_ledger 在 RLS 名单内，而 auth 对**所有角色**无差别把 ContextVar 设为
     **观察者**的租户（auth.py:144）。admin 跨租看 trace 时"观察者租户≠数据归属租户"，
     不显式覆盖，RLS 把账本 SUM 过滤成空集且**零报错**——"有账变没账"的静默降级
     （观察池 (58) 家族，usage.py:65 先例）。CI 证人必须住在 RLS 在场的世界
     （test_rls M4.1 增量节）：owner 夹具对这类缺陷天然失明（#47）。收口时做了反向实证：
     影子里拆掉包裹，测试立刻红在 `usage.requests 0==1`——**证人必须先证明自己会响**）

429. ⬜ PrecheckHook 的返回值为什么要从 `str | None` 升级成 `PrecheckVeto | None`？
     （单一 str 在 M4.0② 之后同时承担两个职责：模型观察（必须统一话术抹 oracle）与
     审计内容（必须具体可诊断）——两个方向相反的需求挤在一个字段里，细节无处安放，
     结果是 precheck 否决在事件流**零留痕**，坐席看到"批准了却什么都没发生"的哑谜。
     拆成 observation（模型面）+detail（审计面，随 precheck_vetoed 事件落盘、经 trace API
     仅 operator/admin 可读）。分离的测试形态：detail 断言**出现在事件 payload、
     不出现在 prompt_blob**——一条测试钉死信息流向。同型判据＝站 10 口径⑴
     "拿不到身份的层说出口的话必须对所有身份安全"，现在补全下半句：
     **说不出口的话，给有身份的面留个去处**）

430. ⬜ 加第 17 类事件 `precheck_vetoed` 走了哪些流程？为什么不复用 `guardrail_triggered`？
     （扩枚举流程是 M2.5 拍板 4 预定义的三处联动：03 §5 表加行 → 快照测试**先红**
     （"再加成员先让这里红、过口径再改"）→ C31 归一化核对。本次 C31 零改动——
     `normalize_events` 对任意事件顶层 `approval_id` 通用别名化（replay.py:320-324），
     新类型天然被覆盖；`_rebuild_working` 正向匹配对未知类型自动忽略；11 盘 cassette
     无 veto 场景零重录费。不复用 guardrail_triggered：其 payload 契约（stage/disposition/
     kind/rule/excerpt）没有 approval_id 槽位，语义是 M2.8 三挂点——**复用会让 M4.3 的
     行为断言面被迫在一个类型里区分两族语义**。判据：payload 形状与消费方都不同时，
     新类型比过载便宜）

431. ⬜ llm 耗时断言为什么不能"append 两条事件然后断言差值>0"？测试里怎么做的？
     （savepoint 夹具把所有会话绑在一个外层事务上，而 PG `now()` 是**事务开始时间**——
     测试世界里所有 created_at 冻结同值，墙钟差恒 0（生产不冻结：EventWriter 每 append
     独立事务）。就算不冻结，"差值>0"也是时序敏感断言（红线 5 不进 CI）。做法：append 走
     真实写路径后，显式 `UPDATE events SET created_at=:t` 构造已知时钟，断言
     `duration_ms == 1500` 精确值——**测配对算法，不测测试机的调度延迟**。
     顺带钉死配对语义：连发两条 llm_call（半截作废重发 D10），result 配**最近**一条（1s
     而非 11s）——pop 一次配对用掉，杜绝隔步错配。锚：tests/obs/test_trace_assembler.py）

432. ⬜ 收口凭证 `m4_trace_sample.json` 的会话是回放重建的——为什么不跑一次真实 demo？
     （M4.0④b 的 downgrade 往返清了演示库（"数据可重建"教训的续集）。重跑真实 demo=
     计划外真实调用，M4 口径只许 M4.4/M4.6 花钱（红线 1）；而 l3 cassette 回放=FakeGateway
     扮演 LLM（录制内容是 M3.11 的**真实模型输出**）+ mock 后端**真执行**（工具 latency
     是本次实测），零 token 重建出与真实链路同构的事件流。凭证里 usage 全零不是缺陷，
     是"回放不过计量"的直接体现——诚实标注即可。这本身就是"确定性回放"卖点的自证：
     **演示库可以随时清掉，因为会话可以从磁带上长回来**）

## M4.2 · Prometheus 指标 + /metrics（双源/中间件/观察池批，2026-08-03）

433. ⬜ 指标为什么是"双源架构"？为什么不给 runtime/gateway 打点？
     （进程内观测（Counter/Histogram）只覆盖 api 层看得见的东西；其余全部 scrape 时从
     DB 现算（Gauge）——事实源就是账本与事件表，与"events 即 trace 源"同一哲学。
     不给 L1/L2 塞 metrics：①层契约反向非法（runtime import obs = lint-imports 红）；
     ②更深的理由是**事实已经落盘了**——终止原因/token/工具终局全在表里，再打一遍点
     等于维护两本账，漂移是时间问题。推论：**能从事实源派生的指标绝不在代码路径上
     重复计数**；只有"落不了盘的瞬时量"（HTTP 计数、延迟）才配进程内打点）

434. ⬜ /metrics 的 DB 刷新为什么必须走 owner 维护面工厂？计划伪码错在哪？
     （计划写 `refresh(get_session_factory())`——app 工厂。但 /metrics 无认证无租户身份，
     ContextVar 没人设，RLS 把 sessions/usage_ledger/tenants/documents 全过滤成**空集且
     零报错**：十一个族安静导出零，仪表盘"一切正常"。这是 (58) 家族第三例（usage.py
     admin 跨租/TraceAssembler 账本/本条），且**首次埋在计划伪码里**——计划写作早于
     RLS 落地，"未来事实"被先落地的步骤改变（plans/README 消费规则的实证）。
     正解=平台级聚合是维护面读（D4：报表/对账），走 approvals_lookup 平台查读缝）

435. ⬜ HTTP 计数中间件为什么用纯 ASGI 而不用 FastAPI 的 @app.middleware("http")？
     （后者=BaseHTTPMiddleware：把下游包进 task-group、response 换壳——对 chat/stream
     的 SSE 长流（等待窗 25s）平添缓冲与取消语义的变数。纯 ASGI 形态只包一层
     `send` 窥 `http.response.start` 拿状态码，每个 body 帧原样透传，**对流零改写**；
     影子全量回归（含全部 SSE 测试）照绿是实证。附两个小决策：状态码初值 500
     （响应头没发出去就炸=异常也是流量，不数=盲区）；计数放 finally（挂了也计））

436. ⬜ path label 为什么必须用路由模板？未匹配的请求怎么办？
     （真实路径含 session id/document id——**外部可控值进 label=基数爆炸**，Prometheus
     每个 label 组合一条时序，内存事故。路由模板（`/v1/sessions/{session_id}/events`）
     把基数钉死在路由表大小。未匹配路由（404 探测）连模板都没有→统一归并
     `"unmatched"`——否则攻击者扫路径就能给你造无限时序。一般化：**label 值必须来自
     封闭集合**（路由表/枚举/租户表），永不来自请求原文）

437. ⬜ "chat 首 token 延迟"的观测点为什么是首个 token 帧而不是首帧？t0 为什么在 handler 入口？
     （首帧可能是 tool_status（工具轮先行）——按首帧算会把"模型还没吐字"记成"已出字"，
     与 M3.12/M5.2 的"首块"口径错轴。t0=进入 handler=用户视角的等待起点（含准入、
     intent 分类、检索、循环装配全部编排开销）——这是"平台开销+模型延迟"的端到端口径，
     与 M5.2 压测口径①要拆的"平台自身开销"互为整体与部分。全程时长记 finally：
     error 收流的请求也是延迟样本，**只统计成功请求=幸存者偏差**）

438. ⬜ CI 空库红那次（cache 指标 delta 断言）到底错在哪？为什么影子门没抓住？
     （`aegis_cache_requests` 是唯一无租户维度的共享 label 族。DB 派生 Gauge 的刷新
     只 set 查询结果里**在场**的 label——空库首刷零行=不触发 set=保留**上一个测试
     世界**的旧值，delta 基线错位。本机 dev 库常驻真实账本行，两刷都有行可 set，
     所以影子门全量绿——**影子门与 CI 的分岔不在代码在数据**（M2.11"环境依赖测试"
     的镜像版：那次 CI 绿本机红，这次本机绿 CI 红）。修=断言前 clear() 共享 child。
     一般化：**跨用例共享的可变全局（registry/单例/缓存），断言要么先复位、要么找
     与初值无关的不变量**）

439. ⬜ #23 预算比 gauge 与月度预算闸门怎么保证"永不对不上"？
     （不是"两边口径写得一样"，是**分子共用同一个实现**：gauge 直接调
     `MeteringRecorder.month_spend`（月窗=DB 端 date_trunc、cached 排除、复合索引路径
     三个细节全继承）。对不上在物理上不可能，而不是靠 review 保证。构造上有个小噱头：
     MeteringRecorder 要价目表而 month_spend 不花钱——空表构造+cast 形状相容，
     注释声明"这不是糊弄类型检查，是声明事实"。凭证实拍闭环：3 轮演示
     ratio 0.0008→0.0031 肉眼上升，告警面与拦截面同一把尺的活证）

440. ⬜ (74) 的修法为什么是"分批"而不是像 events_view 那样"截断"？(61) 的 LIMIT 为什么要配 ORDER BY？
     （两个端点语义不同：events_view 是调试面，截断+声明即可；stream 是**全量重放**
     语义——少一条事件=用户面板永久缺一段，所以 `_REPLAY_BATCH` 只分批不截断：
     批满立刻续扫，**终止判据与 message_reset 都等存量排空**（跨批的 loop_terminated
     若提前判会早退丢事件——`first_batch` 语义升级为 `replay_done` 正为此）。
     (61) 的 LIMIT 无 ORDER BY=数据库自由挑行，**每轮随机领批**——积压时某些会话
     可能连续几轮都轮不到（挨饿）；`ORDER BY id` 让余量必然轮到。一般化：
     **加 LIMIT 必须同时回答"剩下的什么时候轮到"**——silent cap 纪律的下半句）

441. ⬜ 回放回归为什么断言"行为轨迹"而不是逐事件全等？逐事件全等（M2.12）与它各测什么？
     （M2.12 的逐事件全等测的是**确定性本身**——同一 cassette 中断恢复前后归一化流
     相等，回答"回放机器可信吗"；M4.3 的行为轨迹四键（终止原因/工具序列/禁词/必现
     事件）测的是**管线语义**——代码改了之后同一录制还走不走同一条路，回答"行为
     漂移了吗"。逐事件全等做回归门会把 latency/usage/id 这些"合法波动域"全变噪声，
     C31 豁免救不了语义无关的顺序抖动；行为四键则把断言面收在"用例设计当初承诺
     的行为"上——期望能先于录制写出来，正是因为断言面=设计承诺而非实现快照）

442. ⬜ manifest 期望值"先于录制推导，不许抄实际输出"——凭什么说抄了就退化成快照？
     （快照测试固化的是"现状"，回归测试守护的是"承诺"。抄输出时你无法区分输出里
     哪些是设计意图、哪些是当天的偶然（甚至是 bug）——tool_loop 盘期望执行 2 次而
     盘内意图 4 次，就是推导与抄写的分水岭：抄会写 4（把"模型想调 4 次"当行为），
     推导写 2（闸门 #4 承诺第 3 次打断第 4 次触杀）。完整性三向（盘面≡manifest≡
     DRIVERS）保证没有盘能绕过这道"先想清楚再录"的流程）

443. ⬜ forbidden_output 扫描面为什么要剔 digest/input_tokens_est？"259"这类禁词的红绿本来取决于什么？
     （禁词是数字串时，扫描面里任何高熵十六进制/估算整数都可能撞上——64 字符 hex
     含任意指定 3 字符的概率 ≈1.5%/个，一盘几个 hex 就是百分之几的**恒定假阳性**
     （同内容同 hash，不是 flaky 是恒红或恒绿的抽签）。隔离断言的红绿不许押注在
     哈希巧合上，故 _dump_text=C31 归一化（豁免 usage/latency+id 别名化）再剔机械
     噪声键；且只滴 payload 顶层（D12）——result 原文里的语义"259"照样能红。
     一般化：**文本禁词断言必须先定义"语义域"，机械域进扫描面=把断言交给运气**）

444. ⬜ token_burn 盘为什么不断言工具序列？"断得越死越安全"错在哪？
     （该盘的调用次数取决于估算尺 C25 的具体数值——预算 2000 除以每轮估算量，钉死
     序列=把断言绑在"尺的刻度"上，合法调参（改进估算精度）会恒红，红灯从此不再
     意味着行为坏了=信噪比崩塌（红线 5"没人信红灯"的变体）。终止原因
     token_budget_exceeded 已锁住行为本体（预算先于轮数）。红绿验证恰好补证了这条：
     阈值×10 后 burn 盘仍绿（预算仍先触发=行为没变，门不误报）、budget 盘响亮红
     （行为真变了）。**断言面要绑承诺，不绑实现参数**）

445. ⬜ 红绿有效性验证的改坏点，为什么"注释检索 WHERE tenant_id"是无效选项？
     （改坏点必须落在**被测世界真正执行的语句**上。回放/CI 世界无 DASHSCOPE_API_KEY，
     检索恒 fail-open 空集——那条 WHERE 根本不参与执行路径，注释它任何回放用例都
     不会红，"验证通过"零信息量。这是 M4.0④b"探针必须先本地实证会被抓再推"在
     回放门的重演：门的有效性凭证，前提是探针对门可见。选中的候选②（预算×10）
     红在 CassetteMismatch 而非终止断言——闸门弱化后管线试图真调 LLM、空盘立刻
     失配，**响亮失配比语义断言红得更早**=C10 设计的直接回报）

446. ⬜ (73) 修复里"POST 侧刻意不发 user_message 帧"——为什么不对称反而是对的？
     （两通道对"用户消息"的知情状态不同：POST 流的消费者就是刚发消息的那个页面
     （本地已 addBubble），再发一遍=重复气泡；GET 重放的消费者可能是清空重建的
     面板（resubscribe(true)）或全新客户端——事件流是它唯一的事实源，不译
     user_message 就永远半边对话。同一张译表因消费者知情状态不同而产生合法差集；
     真正的缺陷不是差集本身，是差集**从未被写下**——修复的另一半就是把它钉进
     两处 docstring。一般化：**协议不对称要么消除、要么声明，不许沉默**）

447. ⬜ (62) 的"零证人"结论后来被推翻——复盘方法论上这次失准暴露了什么？
     （站 10 登记"register_resume_hook 全仓测试零处调用"，M4.3 核对发现注册面证人
     test_module_import_registers_real_hook 早在 M3.9④ 就有。失准根因=复盘拍板
     "免测试段"（生产代码逐类讲透、测试只点名）——省时间的代价是**复盘对测试面的
     断言天然不可信**。教训：复盘可以不讲测试，但凡要下"无证人/零覆盖"这类关于
     测试面的否定性结论，必须回测试面 grep 实证；否定性结论的举证成本比肯定性
     结论高（要证明"不存在"），恰是免测试段最容易破产的地方）

448. ⬜ 评测用例为什么"定义源在 repo、运行事实源在表"两个都要？seed 脚本的更新列为什么排除 enabled？
     （repo 里的 cases.json 管"用例是什么"（版本化、PR 可审、判据变更有 diff），表管
     "运行时哪些参赛"（enabled 运营开关：控费收窄冒烟批次）。两者职责不同：若只有表，
     判据变更无评审面；若只有文件，临时关停一条要走提交。幂等 upsert 的更新列**排除
     enabled/created_at**——否则重跑种子会把运营员手工关停的开关冲掉：**运营态永远不该
     被定义源的重放覆盖**（与"重录不覆盖 manifest 期望"同族：两个世界各管各的字段））

449. ⬜ EvalVerdict 为什么是三态？judge 崩了记 fail 会怎样？
     （error=执行/judge 异常，**不算 fail**。若混进 fail：通过率虚低且不可归因——你看到
     80% 通过率，分不清是回答变差还是 judge 服务抖动；修 rubric 还是修网络，方向会选错
     （M3.12"改 prompt 还是改判据"的判定问题在评测层的重演）。三态让异常显式可见、
     逐条人工归因，质量信号保持纯净）

450. ⬜ eval_runs.judge_model 为什么记 API 回显名而不是配置名"strong"？
     （strong 是路由链不是模型：qwen3.7-max→qwen-plus fallback，judge 可能中途换模。
     记配置名=历史行全写 strong，某天分数漂移根本查不到是模型换了还是回答变了。
     记回显名（UsageChunk.model）后：报告按 judge_model 分组看趋势、跨模型分数不直接
     比较（rubrics §4 明文）。C36 的完整落地——回显名是事实，配置名是意图）

451. ⬜ 三类用例的判定权分配：为什么 adversarial 的 pass 不依赖 judge、retrieval 压根不调 judge、只有 e2e 让 judge 定判？
     （判定权跟着"机器能不能判"走：retrieval 是集合成员判定（top-5 命中）零语义歧义，
     花 judge 钱只引入噪声；adversarial 的核心是禁现字面与拒绝形态——同样机器可判，
     且**判定不依赖 judge 是同族偏差的结构性缓解**（Qwen 评 Qwen 的分数不碰安全结论）；
     e2e 的"回答质量"才真需要语义评价，judge ≥4=pass，且机器硬断言先行——fail 的
     不再花 judge 的钱（预算纪律与判定纯度双赢））

452. ⬜ M4.4④ 冒烟首炮：judge 调用为什么炸 42501？这条口径行当天落档当天被踩中说明什么？
     （judge 是全项目**第一个 tenant_context 之外的网关调用点**——网关自动计量写
     usage_ledger（RLS 名单表），WITH CHECK 查 current_setting 未设即拒。之前没炸是因为
     所有网关调用都活在被包裹的 run 里；评测引入了新的出边界调用形态。同日恰好落档的
     §2.2 配对纪律口径行（(58)）说的正是"每个新的出边界调用点必查上下文"——写下当天
     被自己人踩中，防线价值自证。另一半收获：计量"绝不拖垮请求"的兜底首次真实验证
     ——批次照跑，只是账缺行，症状与设计完全一致）

453. ⬜ 首个基线 20/20 全过、judge 判分 15 条全 5 分——这是好消息吗？怎么向面试官讲这个数字？
     （通过率 20/20 是真的（机器断言面：禁现字面零命中、兜底全触发、检索全命中——
     种子集是 M3.12 调优后的行为面，全过合理）；但判分全 5 说明 **judge 打分维度当前
     零区分度**——它没提供任何机器断言之外的信息。诚实的表述："质量信号目前全部来自
     机器断言；judge 曲线要出区分度靠扩集加难例与 spot-check 人工对照"。这比"评测
     100% 通过"可信得多——后者一句"判据是不是太松"就被戳穿）

454. ⬜ 行成本对账时"最终批行合计恰好等于账本全量"为什么是最响的警报？
     （两个本应不同的数字恰好相等=几乎必有集合关系错误（子集算成了全集）。根因：
     `LIKE 'eval-<case>-%'` 无批次维度，三批同 case 的花销全被计入最终批的行。修=judge
     与被评共用**唯一** sid、精确匹配。一般化：对账断言优先找"必然不等"的量对
     （本批 ⊂ 全量），相等时先怀疑查询而不是庆祝对上了）

455. ⬜ 评测 runner 对挂起的审批单主动拒绝再续跑——这算绕过审批防线吗？
     （不算，这是**第二层防线的正确剧本**。iso-06 的金额超阈值触发 risk_policy 挂单
     （闸门在 handler 之前——站 8 口径⑵：闸门可被批准跳过而权限不可），真实世界里
     坐席看到跨用户补券申请就该拒。runner 扮演坐席 decide(False)+resume 收尾（cancelled），
     approvals_rejected 计入 denied/fallback 绊线——"挂起被拒"与"工具统一话术拒绝"
     都是"未泄漏未执行"的合法形态。若 runner 批准它，那才是用评测剧本绕过了防线）

456. ⬜ 兜底信号集从 10 词到 13 词冻结的四轮反哺史——为什么第五轮不再加词而是改架构？
     （okb-02「未在知识库中提供」/okb-08「暂不支持」/okb-05「不掌握」——模型每批换措辞，
     词面追逐是猫鼠游戏。第四轮后停手的判据：README 早宣称"信号集只做绊线不做裁判、
     语义终裁归 judge"，而 machine_verdict 把绊线不中直接判 fail=**实现与架构宣称矛盾**
     ——三轮漏报是同一错位的三次现形。修=e2e 绊线不中交 judge 终裁（绊线归位召回器）、
     adversarial 保持机器 fail（安全面判定权不外放）。一般化：**同一类 bug 修到第三次，
     该怀疑的不是词表不全，是架构位置放错了**）

457. ⬜ iso-12 的「1–3个工作日」为什么既是漏判又是取证？
     （en-dash（U+2013）绕过连字符禁词=归一化尺的字符形态盲区（机器假 pass）；但同一
     字符差异恰好证明**不是缓存/检索把 A 的内容复制过来**——复制会保留 A 原文的连字符
     形态，en-dash 是模型自己的书写风格 → 缓存租户隔离没破，是强先验独立编造撞值。
     judge 判「严重合规泄漏」方向对（fail）但定性重了（编造≠泄漏）。一般化：**字面
     匹配失败的形态本身携带信息流证据**——判据修盲区、取证留档案，一次失败两份收获）

458. ⬜ 评测基线 38/40 比 40/40 更硬——这个口径怎么向面试官讲？
     （四轮批次迭代：34/40→39/40→假绿修正 38/40→稳定 38/40。两条已知失败有名有姓：
     okb-07 发票 90 天、iso-12 退款时效——都是"训练先验强于 prompt 禁令"的稳定编造
     样本（品类清单点名了期限时效仍编）。100% 通过率一句"判据是不是太松"就被戳穿；
     **95% 且能逐条说出那 5% 是什么、为什么修不掉、监控它的机制是什么**（M4.6/M5
     复测追踪）——这是评测体系成熟度的证明，不是质量缺陷的坦白）

459. ⬜ spot-check 委托 AI 复评后，凭证怎么保住可信度？
     （三条口径如实写进凭证：复评者=Claude 与 judge 异族（rubrics 声明的同族自我偏好
     在复评侧不存在——比同族人工预填多一个独立维度）；非严格盲评（复评者归因环节接触
     过部分 judge 分）——缓解=逐条独立理由可审计；用户保留分歧点终裁权（最小人工环节）。
     **凭证的可信度不在流程完美，在口径诚实**——"AI 异族复评、±1 一致率 100%、4 条
     分歧全在颗粒度层"比伪装成人工盲评的同样数字可信得多）

460. ⬜ l3 重录把评测搞红了（nor-03）——两个"都对"的流程怎么撞出一个 fail？
     （重录脚本真实执行 AZ-1002 退款（自检断言"订单落 refunded"）；评测用例假设种子
     状态=delivered；mock 对 refunded 单如实回"物流终止"；模型如实转达；judge 对照
     期望判事实错误——**五个环节全部诚实，错在两个流程共享可变种子且无复位纪律**。
     修的不是任何一环，是环境契约：跑批前 seed_demo 复位（README §5）。一般化：
     集成环境的失败归因先问"是谁的状态假设被谁改了"，再问"谁的代码错了"）

461. ⬜ 成本对照数字怎么做到「没法被质疑是评测集凑出来的」？（00 §8 面试考点原题）
     （五道防线叠加：①问题集与评测集**字面零交集**且由 CI lint 钉死（谁想偷偷混入
     评测题让数字变好看，测试先红）；②实验①用**全唯一集**（80 条零重复）——重复率
     是缓存的功劳不是路由的功劳，唯一集把两种降本物理隔离；③集合构成公开（分布
     24/32/16/8 写进文件、lint 钉住、报告引用）；④**全部数字可由 usage_ledger 复算**
     ——报告附聚合 SQL 与精确 sid 清单，面试官可以自己 SUM；⑤**不预设目标值**（04 M4
     删掉「≥40%」类预设）——先定目标再凑数字的嫌疑从源头拆除。一句话：可疑点不是
     数字大小，是「构成能不能审计」）

462. ⬜ 实验①为什么要双基线（vs-strong 与 vs-standard 两个数字）？
     （单基线的死穴：「你把基线选成最贵的 strong，降本当然高」——评审一句话就拆穿。
     双基线讲两个不同的故事：vs-strong=「不做分档、全用最强模型求稳」的保守实现，
     这是很多团队的真实起点；vs-standard=「不做分档、全用中档」的朴素实现，它压掉了
     基线虚高的水分。两个数字一起给，路由的价值区间就有了上下界——降本大头来自
     「贵题不再全走贵档」，小头来自「FAQ/闲聊直答连中档都不用」。附带每档调用分布表，
     数字的来路全透明）

463. ⬜ 为什么 B 组的 fast 分诊调用必须计入 B 组成本？
     （分诊不是免费的：每条消息先花一次 fast 调用才知道走哪条路。不入账=报告的降本%
     虚高一截，面试被拆穿的经典点（计划 §7 陷阱 5 预言的作弊形态）。实装上这笔账
     **想赖都赖不掉**：分诊调用带同一 session_id 走网关，计量自动入账——「按 sid 精确
     分账」的设计红利是诚实不需要自觉，账本结构替你诚实。深挖一层：分诊成本是路由
     方案的固定开销，问题越简单占比越高——这正是 FAQ 直答也用 fast 档的原因，分诊+
     直答两笔 fast 加起来仍远低于一次 standard 主 Agent 往返）

464. ⬜ 两个成本实验为什么必须口径分开、不能一个脚本「顺便都测」？
     （因为两个降本机制的**污染方向相反**：路由实验里若流量含重复问题，缓存/模型对
     重复题的处理会把「路由的功劳」和「重复率的功劳」搅在一起——所以实验①用全唯一集
     且缓存关闭（双保险）；缓存实验里降本幅度几乎完全由复述率决定——复述率是**流量
     分布假设**不是系统性质，所以实验②把 30% 显式声明成假设、固定种子可重放，数字
     只在该假设下成立。合并测得到的是一个「既依赖构成又依赖重复率」的数字，两头都
     解释不清（00 §8.0 加粗「口径分开」的原因））

465. ⬜ 组间分账为什么用「精确 sid 清单」而不是计划原案的「每组一个租户」？
     （开工核对推翻计划的实锚：`mock_orders.id` 是**全局主键**（无租户维度）——三组
     若各占一个租户，订单号无法跨租户克隆同号，工具题题面被迫每组不同，「三组同题」
     这个最重要的控制变量就破了。而 M4.4④ 冒烟对账已立过「LIKE 前缀跨批撞账→共用
     唯一 sid 精确对账」的先例——sid 清单进报告，聚合 SQL 用 `= ANY(sids)`，审计精度
     不降反升。一般化：**分账单位应该选「实验设计的最小控制单元」**（这里是一次驱动
     =一个会话），租户只是其中一种恰好可用的聚合键，不是唯一正解）

466. ⬜ 缓存 key 不哈希 session_id 的设计（M1.10），在实验②里兑现了什么红利？
     （实验②每条请求都开新会话（sid 全不同），复述请求照样命中——因为 key 只哈希
     语义本体 {tier, messages, tools, temperature, max_tokens}（cache.py:38-42），
     request_id/session_id/deadline 这些「每次必变的身份字段」被排除在外。当初的理由
     是「混入则永不命中且静默烧钱」；今天它让「跨会话的重复问题」成为可命中面——
     客服场景里复述恰恰来自不同会话（不同用户问同一个问题），这个排除决定就是精确
     缓存在真实流量里有降本空间的全部前提。反面推论：若当年把 session_id 混进 key，
     实验②的降本%将恒等于 0%，而且没有任何报错提示你为什么）

467. ⬜ 实验②的命中率自检为什么按「请求级全命中」而不是「调用级命中率」？
     （一条请求在管线里是多笔 LLM 调用（fast 分诊 + 主 Agent 1–2 笔 / 或分诊+直答），
     调用级命中率是个稀释过的平均数——60% 的调用命中可能意味着「所有请求各命中一半」
     （管线非确定性，坏）也可能是「六成请求全命中」（好），同一个数字两种病情。
     请求级全命中（该 sid 全部账行 cached=true 才算 1）是**管线确定性的证明**：复述
     请求应恰好 60/200 全命中、首现请求应 0 命中——任何偏差都精确指向某个非确定性面
     （上下文里混进了时间戳？检索排序不稳定？）。自检对不上=先修 bug 再报数（计划 §3），
     防的是「带着管线 bug 报出一个碰巧好看的降本%」）
