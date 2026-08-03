# tests/cassettes · 回放资产与重录流程（M2.6 定稿；M4.3 CI 回归的 PR 审查指引）

## 1. 格式速览

顶层三键：`format_version`（当前 1）· `session_id` · `scopes`。
`scopes` 的键只许四道（拼错载入期就炸，`aegis/runtime/replay.py` 的 `Cassette.load` 防呆）：

| scope | 调用源 | 接线方 |
|---|---|---|
| `main` | 主循环 | AgentLoop 调网关（M2.7） |
| `summary` | 滚动摘要 | ContextBuilder 摘要钩子（M2.5，M2.7 组装） |
| `guard` | 守卫分类 | 入口 fast 档可疑度分类（M2.8） |
| `tool_digest` | 结果摘要 | ToolExecutor 的 summarize 钩子 |

每道是条目数组，entry 两键：`request_digest`（诊断域，**不参与匹配**；手写资产允许任意键子集或空对象）
+ `chunks`（回放本体：`text_delta* → tool_call* → usage → stop`，必须以 `stop` 收尾）。
匹配键 = `(session_id, scope, 道内序号)`——**不是 prompt 哈希**，prompt 微调不会全量失配。

## 2. 敏感字段纪律（红线）

- request 侧只有摘要域四键（`tier / message_count / tool_names / prompt_sha256`），
  **prompt 原文（用户对话，潜在 PII）不落盘**——由 `request_digest()` 机械保证；
- chunk 文本只许**虚构演示数据**（云杉电商假租户）；禁止把真实用户对话、真实 API key 录进任何 cassette。

## 3. 重录流程（prompt 变更时）

1. 确认变更涉及哪几道：改 system prompt → `main` 道必变；改摘要提示词 → `summary`/`tool_digest` 道；
2. 真实录制类资产：跑 `scripts/record_long_dialog.py`（M2.11 交付，预算上限写死在脚本内）重新生成；
   **录制必须"干净"**——脚本六道自检全过才落盘（摘要≥2 / 覆盖含第 12 轮 / 五探针全中 /
   全轮 completed / 零护栏事件 / **零摘要 fail-open**——录制期辅助调用失败无痕，回放期
   FakeGateway 必然成功，触发点会错位消费 summary 道，cassette 从此不可忠实回放，
   plans/m2.11 偏差 #8）；**手写类资产不重录**，按第 1 节格式手改；
3. 落盘后自查：`Select-String -Path tests\cassettes\*.json -Pattern "sk-"` 必须零命中；
4. **PR 必须附重录 diff**（00 主计划 M4.3 行要求）。

## 4. diff 审查清单

- 各道**条目数**变化是否与 prompt 变更预期一致？条目数变化 = 行为轨迹变化，审查者必须能说出为什么；
- chunk 文本变化是否限于预期的道？
- `prompt_sha256` 变化仅作定位参考（哪条请求变了）；
- usage 数字变化**不阻塞**（C31 等价断言同样豁免 usage 类字段）。

## 5. 命名约定

`<用途>_<场景>.json` 小写下划线，如 `minimal_demo.json`、`long_dialog.json`
（真实录制类资产名**稳定不带日期/轮数**——M4.3 重录 diff 靠稳定名成为评审物，plans/m2.11 D1）。
**L3 五盘落 `l3/` 子目录**（M3.11 拍板：成组管理、M4.3 按目录消费），命名约定不变；
重录入口 `scripts/record_l3_cassettes.py`（自检先于落盘、五盘全过才统一落盘）。

## 6. M2 基准会话集登记表（M2.11 落定；04"录制基准会话集"收窄至此；M3.11 在本表追加 L3 行）

M4.3 CI 回归的输入范围以本表为准。逐行核对承载物存在且可复用（M2.11 核对结论：缺口 0）；
"内联夹具"形态是 D12 显式允许的——不强推既有用例重构成文件。

| 用例 | 覆盖（终止原因用枚举字面值） | 形态 | 承载物 |
|---|---|---|---|
| long_dialog | completed ×40 + 滚动摘要 ≥2 + 第 1-5 轮埋点召回 | 真实录制 | `long_dialog.json` + `tests/runtime/test_long_dialog_benchmark.py`（M2.11） |
| completed_tool_roundtrip | completed + 读工具两轮链（tool_call→tool_result→最终回复） | 手写 + 内联 | `minimal_demo.json`（M2.6）+ `tests/runtime/test_loop_flow.py`（M2.7） |
| gate1_max_iterations | max_iterations（诱导死循环对抗） | 手写 cassette | `adversarial_runaway_iterations.json` + `tests/runtime/test_loop_adversarial.py`；另 `test_loop_termination.py` 内联 |
| gate2_step_timeout | step_timeout（gateway_exhausted / gateway_overloaded 两 cause） | 内联存根（cassette v1 不承载异常条目，m2.6 D4） | `tests/runtime/test_loop_gateway_errors.py`（M2.7） |
| gate3_token_budget | token_budget_exceeded（L2 预检 + L1 两级 cause） | 手写 cassette + 内联 | `adversarial_token_burn.json` + `test_loop_adversarial.py` / `test_loop_termination.py` / `test_loop_gateway_errors.py` |
| gate4_repeated_calls | repeated_calls（同名同参 ×3，打断不清零） | 手写 cassette + 内联 | `adversarial_tool_loop.json` + `test_loop_adversarial.py` / `test_loop_termination.py` |
| gate5_protocol_violation | protocol_violation（空输出 / 幻觉工具名两源） | 手写 cassette + 内联 | `adversarial_empty_replies.json` + `test_loop_adversarial.py` / `test_loop_termination.py` |
| gate6_cancelled | cancelled（取消信号 + HITL 拒绝/撤回/超时三变体） | 内联夹具 | `tests/runtime/test_loop_termination.py`（M2.7）+ `tests/runtime/test_suspend_resume.py`（M2.9） |
| gateway_rejected | gateway_rejected（七类之外，零兜底话术 C6） | 内联存根 | `tests/runtime/test_loop_gateway_errors.py`（M2.7） |
| tool_seq_write_approval_resume | 写工具→NEEDS_APPROVAL→批准→单入口恢复续跑 | 内联夹具 | `tests/runtime/test_suspend_resume.py`（M2.9） |
| tool_seq_fail_streak_disable | 同一工具连败 2 次本轮禁用→改道 | 内联夹具 | `tests/runtime/test_executor_exec.py`（M2.4） |
| l3_isolation_cross_tenant_rag | completed + B 问 A 专有知识零泄漏（检索空集来源=阈值拒答，fail-open 空集不入带） | 真实录制 | `l3/isolation_cross_tenant_rag.json` + `tests/apps/test_l3_cassette_smoke.py`（行为断言主体 M4.3 接手） |
| l3_isolation_cross_user_refund | completed + 工具统一话术拒绝全程（对抗③；100 元刻意低于阈值走归属面非审批面） | 真实录制 | `l3/isolation_cross_user_refund.json` + 冒烟载入 |
| l3_budget_token_exceeded | token_budget_exceeded（L3 租户配置注入口径；main 道**零条目**=闸门 #3 预检零调用） | 真实录制（零 LLM 条目） | `l3/budget_token_exceeded.json` + 冒烟端到端回放 |
| l3_hitl_approve_resume | 挂起（无终止事件）→ decide → resume completed + 订单落 refunded | 真实录制 | `l3/hitl_approve_resume.json` + 冒烟载入（挂起/续跑双段条目形状） |
| l3_tool_roundtrip | completed + 工具序列恰 [order_query]（L3 生产装配正例） | 真实录制 | `l3/tool_roundtrip_order_query.json` + 冒烟全链回放（FakeGateway×mock 后端） |

## 7. 行为回归门与 PR 纪律（M4.3 起生效）

11 盘文件形态资产由 `tests/replay/test_behavior_regression.py` 逐盘行为断言
（终止原因必断；工具序列/禁词/必现事件按 manifest 键在场断言），期望登记在
`tests/replay/expectations.json`（manifest）。**完整性三向钉死**：盘面文件 ≡
manifest 条目 ≡ 驱动注册（DRIVERS），多录漏挂、条目悬空、驱动缺失都红。

**新录一盘 cassette 的四件事**：
1. 录制落盘（真实录制类走录制脚本，自检全过才落盘；手写类按 §1 格式）；
2. 挂 manifest 期望——**先于录制从用例设计推导，不许跑一遍把实际输出抄成期望**
   （抄输出是快照不是回归，坏行为会被固化）；
3. 挂 DRIVERS 装配（三族样板就在该文件内：M2 演示工具族/长对话族/L3 族）；
4. 若该盘不满足"四道全部耗尽"，进 EXHAUSTED_EXEMPT 必须带语义理由。

**PR 纪律（重录触发时）**：
1. 触发条件 = prompt 变更 **或** 调用结构变更（C10 并列口径，二者任一即触发）；
2. 跑对应录制脚本（预算上限写死在脚本内）重新生成；
3. `git diff --stat tests/cassettes` 确认变更盘与预期一致（§4 审查清单）；
4. PR 描述附：diff 摘要 + 本次录制 token/费用；
5. 评审人核对**期望行为是否需同步改 manifest**——条目数或行为轨迹变了，
   manifest 期望必须在同一 PR 里改，且审查者必须能说出为什么。

## 8. 断言边界声明（M4.3 定稿；"声明它比修它重要"）

行为断言的扫描面 = **事件流语义域**（C31 归一化豁免 usage/latency/墙钟并别名化
id，再剔机械噪声键 iteration/input_tokens_est/digest——哈希 hex 会撞数字禁词）。
以下四条边界是裁决过的差集，不是疏漏：

- **POST 帧面 / msgbuf / 工具轮前置文本不在扫描面**（观察 ㊾）：工具轮的前置
  文本（"我帮您查一下"）只存在于 llm_result.text 不落 assistant_message 事件，
  forbidden 断言扫不到它——若泄漏恰发生在该段，本门不报警；
- **兜底轮话术互换**（观察 ㊼）：兜底路径上用户实际看到的 FALLBACK_LOOP_LIMIT
  话术不在事件流里，事件流里那句从没到过用户——若未来录制兜底类 cassette，
  manifest 期望必须按**事件面**的话术写，并知道它与用户所见不同；
- **随机 id 不参与断言面**（观察 ㉜）：ticket_id=uuid4 之类随机值不进任何期望。
  触发条件：录制含 handoff/兜底的盘、或引入"同盘两跑逐事件全等"的确定性断言
  之前，**必须先给 mock 加确定性 id 注入缝**（别名化够不到 content 里的字符串）；
- **重录门覆盖面 = 代码内 prompt 常量**（观察 ㉗）：租户侧 prompt
  （`tenants.config["faq"]` 的 digest）不在"定了不动"纪律与本门覆盖面内——
  digest 改了无任何机制知道，且 FAQ 直答路径当前**零 cassette 覆盖**，本门对
  "FAQ 直答质量"既不绿也不红。该面的质量评测归 M4.4（与 ㉖ 直答守卫缺口同批裁决）。
