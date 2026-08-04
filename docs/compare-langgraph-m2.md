# 对照学习：如果 M2 用 LangGraph 写，代码长什么样

> **性质**：学习对照物，不是迁移方案。与 `retro-m2.md` 对照阅读（retro 现为草稿，
> M2 毕业后定稿——毕业后补链）。姊妹篇：`compare-langchain-m1.md`（网关层对照）。
> **API 世代基准**：langgraph **1.0 世代**（2025-10 发布线：`create_react_agent` /
> `ToolNode` / `interrupt()`+`Command(resume=…)` / `PostgresSaver` checkpointer）；
> 写作者知识截面 2026-01，代码写到"能跑的形状"**未实测**——重点是结构与语义对比。
> **结论先行（行数为估算，C25 纪律）**：M2 运行时 ≈4300 行里，**约 600 行被替代**
> （循环骨架与分支调度 / @tool schema 生成 / 挂起-恢复的传输壳 / working 序列管理），
> **约 3300 行原样保留**（六道闸门 / 执行器七步中的六步 / 六层预算与滚动摘要 /
> Guardrails / EventStream 全家 / 锁+租约+reaper / 回放四道+C31 / 审批五态 CAS），
> 另需 **约 200 行胶水**（state schema、节点包装、interrupt↔审批单同步）。

---

## 1. `create_react_agent` vs AgentRuntime/AgentLoop——一道闸门对六道

LangGraph 版的"总装"确实只要几行：

```python
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=saver)
result = await agent.ainvoke(
    {"messages": [{"role": "user", "content": user_input}]},
    config={"configurable": {"thread_id": session_id}, "recursion_limit": 25},
)
```

M2.7 那 650 行 loop.py 消失了吗？逐道闸门问"框架有吗"：

| 我们的终止面（7 类 + gateway_rejected） | LangGraph 对应物 |
|---|---|
| #1 max_iterations（按 LLM 调用计） | 🟨 `recursion_limit`——但计的是**图超步**（节点执行数，工具轮也算），语义偏移；超限抛 `GraphRecursionError`，无兜底话术、无事件 |
| #2 单步双超时（LLM deadline 传播 / 工具 asyncio.timeout 取严） | ❌ 无。模型侧靠底层 SDK 超时（M1 对照 §3 的课重演），工具侧自己在 handler 里包 |
| #3 会话 token 预算（D8 种子从事件流重建） | ❌ 无。state 里的 messages 是"当前窗口"不是事实源，跨 run 累计口径无处安放 |
| #4 重复调用哈希窗口（canonical_json 规范形/打断不清零） | ❌ 无 |
| #5 协议违规纠错（空输出/幻觉名计数，2 次纠错） | ❌ 无。空输出在框架里就是"终答"，直接结束——我们判 violation 并给纠错机会 |
| #6 取消 / HITL 拒绝或超时 | 🟨 interrupt 可承载 HITL（见 §3）；取消信号检查点、拒绝/超时→CANCELLED 事件化自建 |
| gateway_rejected 零话术裸暴露（C6） | ❌ 异常语义分类是我们网关契约，框架不辨"确定性拒绝 vs 可降级" |

更根本的缺失是**"终止原因"作为一等事实**：我们的每次 run 以 `loop_terminated(reason=…)`
收尾进事件流，M4.3 的行为轨迹断言、C9 的恢复计数都踩在它上面；框架的终止是
"函数返回了"或"异常抛了"——审计面上什么都没留下。

---

## 2. `ToolNode` + LangGraph `@tool` vs ToolRegistry/ToolExecutor——七步留六步

schema 生成殊途同归（inspect + Pydantic，M1 对照 §8-3 已证；连"ctx 类参数不暴露给
模型"都有对应物 `InjectedToolArg`/`InjectedState`）。真正的对照在执行生命周期：

| M2.4 七步 | ToolNode 版命运 |
|---|---|
| ① 严格校验（lax 解析 + extra=forbid 口径自洽） | 🟨 Pydantic 校验有；forbid 口径、坏 JSON 的回填话术自己写（`handle_tool_errors` 只给"把异常变 ToolMessage"的钩子） |
| ② 权限三层（tenant/user/工具声明） | ❌ 无概念 |
| ③ 风险闸门 fail-closed（谓词崩溃=阻断）+ C15 注册期防呆 | ❌ 无。写工具裸奔在框架里不是错误 |
| ④ **write-ahead 幂等键**（事件 id 先落盘、经 ctx 透传下游） | ❌ **最关键缺失**：ToolNode 执行前不落任何事实——崩溃后"执行过没有"不可知，下游去重无键可用 |
| ⑤ 超时取严 / 读退避重试 / 写恒单次（类型不变量） | ❌ 自己在 handler 里包 |
| ⑥ 结果规范化（超预算 fast 档摘要 + injected 留痕 X4） | ❌ 无 |
| ⑦ 事件 + 审计投影（tool_invocations） | ❌ 无 |
| X1 结果不明（写超时→禁止重试引导查询） | ❌ 无——模型自发重试会生成新调用，正是我们防的去重失效 |
| 连败 2 次本轮禁用 | ❌ 无 |

结论：ToolNode 替代的是 dispatch 表 + "结果回填成 ToolMessage" 的约 30 行；
七步里的六步、两条恢复期安全性（④/X1）全部原样保留——它们是 M3.7 幂等闭环的前提。

---

## 3. `interrupt()` + `Command(resume=…)` vs 审批五态 CAS + 恢复单入口——最深的一问

LangGraph 的 HITL 形状：

```python
def refund_node(state):
    decision = interrupt({"tool": "refund_apply", "args": args})  # 抛出+checkpoint 落盘
    if decision["approved"]:
        return do_refund(args)          # 恢复后从节点头重放到这里
    ...
# 坐席批准后：
await agent.ainvoke(Command(resume={"approved": True}), config)
```

三处本质差异：

1. **恢复 = 重放节点函数**。`interrupt()` 之前的代码在恢复时**重新执行**——官方文档
   自己警告"interrupt 前不要放副作用"。也就是说，防重复副作用的责任被交还给
   "使用者把 interrupt 摆对位置"的自律；我们的答案是结构性的：write-ahead 幂等键 +
   `reexecute` 原键重执行 + 下游去重（评审 X1/C2 一族）。**这是本对照最值得在面试里
   讲透的一问：框架用"重放代码"恢复，我们用"重建事实"恢复（保事实不保字节，K2②）。**
2. **审批是值不是状态机**。`Command(resume=…)` 只是把一个值注入续跑；五态单
   （pending/approved/rejected/cancelled/expired）、`expires_at` 过期 fail-closed（C7）、
   双坐席并发 decide 的 CAS 恰一赢家（C11）、批准后前置校验重跑挂点（TOCTOU）——
   框架侧全部要自建，等于把我们的 ApprovalStore 原样搬过去。
3. **挂起-恢复的等价性不可证**。M2.12 交付①的"中断-恢复逐事件一致"强断言，前提是
   存在独立于运行时状态的事实源（事件流）可归一化比较；checkpoint 体系里"state 即
   真相"，恢复对不对只能靠终局输出体感——没有逐事件这个概念。

---

## 4. `PostgresSaver`（checkpoint 快照）vs EventStream（事件溯源）——M1 §6 的续篇

| 维度 | PostgresSaver | 我们的 events + 同事务投影 |
|---|---|---|
| 存什么 | 每超步的**全量 state 快照**（channel values，langchain 消息对象 serde） | 16 类**语义事件**增量，payload 存原文（X4） |
| 能恢复吗 | ✅（这是它的全部使命） | ✅（重放事件重建 working） |
| 能审计吗 | 🟨 只有"每步之后的状态"，"发生了什么"要靠相邻快照 diff 猜 | ✅ 事件即事实：谁调了什么工具、哪次审批谁批的、终止为什么 |
| 能投影吗 | ❌ messages 表/摘要列/工具审计另起炉灶 | ✅ 同事务派生（C8），报表裸 SQL 直查 |
| 回放/回归 | ❌ 无 cassette/归一化概念 | ✅ 四道计数回放 + C31 等价断言 + M4.3 CI 回归 |
| 并发互斥 | ❌ 无租约概念——两副本对同一 thread_id 并发恢复无围栏 | ✅ 会话锁 + lease_generation fencing + (session_id, seq) 物理兜底 |
| schema 主权 | 框架 serde 格式（langchain 类型焊进 PG）——升级=存量 checkpoint 迁移风险 | `schema_version` 自有，老事件永远可重放 |

M1 对照 §6 说"第三方类型焊进事实源"是缓存层的风险；到了 M2 这变成**审计与回放层**
的风险——而"确定性回放 + 中断-恢复等价"恰是本项目最稀缺的简历资产（评审 C33）。

---

## 5. 原样保留清单（与框架无关，一行不改）

六层预算编译与滚动摘要（框架有 message-trim/摘要辅件，但预算编译、`summary_updated`
事件化、C8 投影是我们的）；Guardrails 三挂点（入口规则库+分类器 fail-open、
wrap_untrusted、OutputGuard 确定性状态机与 C23 owned_values）；`core/locks.py`
（Redis 主 + PG advisory 降级 + 粘滞切换）；租约续租伴飞、reaper、恢复次数上限 C9；
`replay.py` 全家（cassette/四道/Recorder/`normalize_events`）；三级预算与 token 估算尺；
停 Redis / 停 PG 两条降级语义（M2.12 实录）；模型池路由/熔断/限流/计量（M1 层，
框架版对照见姊妹篇）。

---

## 6. 绕不开的抉择：图状态 schema 用谁的？

`create_react_agent` 的 state 是 `MessagesState`——langchain `BaseMessage` 列表。选它，
则 checkpoint（事实源）、interrupt payload、你补写的任何事件里都是框架类型：
框架升级 = 事实源迁移（M1 §6 方案 B 的运行时版，赌注从"缓存失效"升级为"审计作废"）。
保自有 `AgentEvent` 契约，则每个节点边界都要写"框架消息 ↔ 我们事件"的双向胶水，
且 checkpoint 与事件流**两套真相**要回答谁是权威、失同步怎么办——这份同步代码
框架不会替你写。M1 的结论在 M2 只会更重：**想保住契约边界，"用框架"省掉的
代码远比宣传的少；不保，省掉的代码会在第一次框架大版本升级时连本带利要回去。**

---

## 7. 逐卖点命运表（M2 每个卖点在 LangGraph 版下的命运）

| M2 卖点 | LangGraph 版命运 |
|---|---|
| 循环骨架 + working 序列管理 | ✅ 框架提供（真省事的部分） |
| @tool schema 生成 / 注入参数剔除 | ✅ 殊途同归（`InjectedToolArg`） |
| 挂起-恢复的传输壳 | ✅ `interrupt`/`Command(resume)` |
| 六道终止闸门（预算/重复/协议/双超时/取消） | 🟥 仅 recursion_limit 近似一道，其余原样保留 |
| 终止原因事件化（loop_terminated + cause 分层） | ❌ 框架终止无事实留痕 |
| write-ahead 幂等键 + X1 结果不明 + 下游去重契约 | 🟥 原样保留（interrupt 重放语义反而放大需求） |
| 审批五态 CAS + expires fail-closed + TOCTOU 挂点 | 🟥 原样保留 |
| 事件溯源 + 同事务投影 + schema_version | 🟥 PostgresSaver 是快照不是账本 |
| 会话锁 + lease 围栏 + reaper + C9 毒会话上限 | 🟥 框架无互斥/租约概念 |
| **中断-恢复逐事件一致（CI 强断言）** | ❌ 无独立事实源，不可证 |
| 确定性回放（cassette 四道 + C31 归一化） | ❌ 无对应物 |
| 六层预算编译 + 滚动摘要事件化（C8） | 🟥 辅件可借形状，内核自留 |
| Guardrails 三挂点 + OutputGuard 确定性状态机 | 🟥 原样保留 |
| 降级两条（锁换后端保互斥 / 事实源不可用明确终止） | 🟥 原样保留 |

图例：✅ 框架提供 ｜ ⬛ 黑盒化 ｜ 🟨 形状保留内核换 ｜ 🟥 与框架无关原样保留 ｜ ❌ 丢失

---

## 8. 这次对照的三个学习结论

1. **框架替掉的是"编排与传输"，替不掉"事实与约束"**。M2 约 4300 行里被替代的
   ≈600 行恰是最好写、缺陷最少的部分；六道闸门、write-ahead、审批状态机、事件溯源、
   锁与租约——简历上每一条能报数字的能力都在"原样保留"栏里（行数为估算）。
2. **主权问题从缓存层升级到事实源层**。M1 的抉择赌的是缓存失效；M2 的抉择
   （MessagesState/checkpoint serde 进 PG）赌的是审计与回放作废——事件溯源系统
   最不能让渡的就是事件格式的定义权。
3. **最值得偷的是机制不是依赖**：`interrupt` 的"checkpoint-before-raise"、ToolNode 的
   `handle_tool_errors` 回填思想、`InjectedToolArg` 的注入剔除，读源码印证自己的设计
   即可（#33 的复刻 spike 归 M4 后弹性窗）；反向也成立——框架用户终究要自建的
   （幂等、审批状态机、等价断言、围栏），正是这个项目已经实证过的部分。
