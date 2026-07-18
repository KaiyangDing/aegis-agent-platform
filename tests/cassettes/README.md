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
| L3 隔离/预算行为用例 | ——（跨租户隔离、预算行为） | 真实录制 | **M3.11（明确不在本步，届时在本表追加）** |
