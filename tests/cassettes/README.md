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
   **手写类资产不重录**，按第 1 节格式手改；
3. 落盘后自查：`Select-String -Path tests\cassettes\*.json -Pattern "sk-"` 必须零命中；
4. **PR 必须附重录 diff**（00 主计划 M4.3 行要求）。

## 4. diff 审查清单

- 各道**条目数**变化是否与 prompt 变更预期一致？条目数变化 = 行为轨迹变化，审查者必须能说出为什么；
- chunk 文本变化是否限于预期的道？
- `prompt_sha256` 变化仅作定位参考（哪条请求变了）；
- usage 数字变化**不阻塞**（C31 等价断言同样豁免 usage 类字段）。

## 5. 命名约定

`<用途>_<场景>.json` 小写下划线，如 `minimal_demo.json`、`long_dialog_40turns.json`。
