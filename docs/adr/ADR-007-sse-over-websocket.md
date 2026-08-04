# ADR-007 · SSE 而非 WebSocket 做流式响应

**状态**：Accepted（v1.1 评审修订）　**日期**：2026-07

## 背景

LLM 逐 token 生成，等全部生成完再返回的体验不可接受（数十秒白屏），必须流式推送。
候选协议：SSE（Server-Sent Events）与 WebSocket。
额外约束：HITL 挂起可持续数小时，"审批通过后续跑的输出从哪条连接送达客户端"必须有答案。

## 决策

**双通道 SSE**：
1. `POST /v1/chat` 返回 `text/event-stream`——发消息与接收本轮流式回复；
   事件帧：`token` / `tool_status` / `approval_pending` / `done`(trace_id+usage) / `error`；
2. `GET /v1/sessions/{id}/stream?after_seq=N`——**重订阅通道**，
   断线重连与 HITL 审批后续跑输出的统一入口。该端点是 GET，可用浏览器原生
   EventSource（自动重连 + 自动携带 Last-Event-ID）；客户端收到 `approval_pending`
   后关闭 POST 流、改挂这条订阅。

## 理由

1. **通信模式匹配**：对话是"请求→流式响应"的单向下行，用户下一条消息就是下一个 HTTP 请求；
   WebSocket 的双向长连接在这里是闲置的复杂度；
2. **仍是普通 HTTP**：省掉 WebSocket 的 Upgrade 握手、心跳保活、水平扩展下的连接亲和三类问题。
   **但不是"零特殊配置"**——反向代理要 `proxy_buffering off`（否则 token 被攒批，流式失效）
   并调大 `proxy_read_timeout`（默认 60s 会掐断长回复），这两个坑写进部署清单；
3. **与事件溯源对齐（评审后的诚实表述）**：SSE 的事件 id 模型与事件流 seq 天然同构，
   重订阅通道用 `after_seq` / Last-Event-ID 实现事件级续传。
   **注意两个边界**：(a) POST + fetch 流没有任何"原生"重连——EventSource 的自动重连
   只属于 GET 端点，这正是重订阅通道存在的理由之一；(b) 续传单位是**事件帧不是 token**，
   进行中的 assistant 消息由服务端在 Redis 缓冲已生成部分，重连后**整条重推**
   （前端用消息重置帧覆盖半句话）；
4. **行业惯例**：OpenAI/Anthropic 的 API 本身就是 SSE，链路上下同构。

## 备选方案

- **WebSocket**：真正的双向实时需求出现时才引入——即"坐席实时接管对话"场景，列 v2
  （v1 转人工 = 创建工单 + 上下文摘要，见路线图 v2 展望）；
- **长轮询**：实现最简但延迟与连接开销都差，仅作为不支持 SSE 的客户端兜底。

## 后果

- 收益：实现、部署、调试全链路最简；curl 就能演示流式；HITL 挂起数小时不需要挂着长连接；
- 代价：POST 流的解析要用 fetch 手写（几十行）；双通道意味着前端要处理通道切换逻辑；
  纯单向，坐席接管留给 v2。

## 面试深挖点

- "为什么不用 WebSocket"标准答案：按通信模式选协议——单向下行选 SSE，真双向才上 WS；
  反例意识：实时协作白板用 SSE 就是错的；
- "断线重连怎么做"：分通道答——POST 流断了不重连（该轮结果走重订阅通道补收），
  GET 通道原生 EventSource 重连 + after_seq 续传；半条消息整条重推；
- "审批挂起三小时，用户怎么收到结果"：重订阅通道 + （可选）前端在 approval_pending 后降级轮询；
- Nginx 两个坑：proxy_buffering、proxy_read_timeout；
- HTTP/1.1 浏览器每域 6 连接上限对 SSE 是真约束，HTTP/2 多路复用后不是问题。

## 实装注记（M3.10 收口回填，2026-07-26）

1. **消息重置帧定名 `message_reset`**（U5 缺口补齐）：GET 通道回放之后、活尾之前，
   若 Redis 缓冲存在进行中 assistant 半条，服务端发 `message_reset`（data=`{"text": 整条现状}`），
   前端整条覆盖当前气泡——"半条消息整条重推"的帧名与时序落地（plans §4.10 D11）。
2. **"原生 EventSource"的 Bearer 认证折衷**：EventSource 无法携带 Authorization 头，
   原生用法只剩"JWT 进 URL 查询串"一条路（违安全底线：凭证不进 URL/访问日志）。
   v1 演示页双通道均以 fetch 手写 SSE 解析、自记 Last-Event-ID、手动重连；
   **服务端 `id:`/`Last-Event-ID` 协议原样**，未来切 cookie 认证即可回到原生 EventSource
   （本文"自动重连+自动携带 Last-Event-ID"的描述在 cookie 形态下依然成立）。
