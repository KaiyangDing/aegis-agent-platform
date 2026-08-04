# 对照学习：如果 M0/M1 用 LangChain 写，代码长什么样

> **性质**：学习对照物，不是迁移方案。与 `retro-m0-m1.md` 对照阅读。
> API 以 langchain-core 0.3 世代为准（`langchain-openai` / `langchain-anthropic` 集成包），
> 代码写到"能跑的形状"但未实测——重点是**结构与语义对比**，不是逐行可复制。
> 结论先行：**约 700 行被替代（schema+两个适配器+部分重试），约 1000 行原样保留
> （限流/熔断/计量/缓存/闸门），另新增约 150 行"翻译进框架"的胶水。**

---

## 0. M0 的变化：几乎没有

| M0 交付 | LangChain 版 |
|---|---|
| uv 工程 | `uv add langchain-core langchain-openai langchain-anthropic`——多三个直接依赖（及其传递依赖 openai/anthropic SDK） |
| 分环境配置 | **原样**（pydantic-settings 与框架无关） |
| docker-compose | **原样** |
| CI 六道门 | **原样**；import-linter 契约不变（langchain 属第三方，不在分层图里） |

唯一实质变化：依赖面扩大——openai/anthropic SDK 回来了（我们现版刻意不用它们），
langchain 系的版本 churn 进入你的 `uv.lock`。

---

## 1. `models.py` —— 替代 `schema.py` + `providers/` 三个文件（约 600 行 → 45 行）

```python
"""LangChain 版"适配器层"。

原 openai_compat.py 里的 SSE 解析、[DONE] 哨兵见证、tool-call 按 index 组装、
流内 error 事件——全部消失在 langchain_openai 集成包内部。
省下 600 行的代价：这些细节从"我写的、我可断言的"变成"我信任的黑盒"。
"""

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from aegis.core.config import Settings


def build_chat_models(s: Settings) -> dict[str, BaseChatModel]:
    """key 与现版 Candidate 的 'provider:model' 对齐，路由表零改动。"""
    common = dict(
        # ！！全场最重要的一行：SDK 自带重试（openai 默认 max_retries=2），
        # 必须归零——重试权威只能有一个（我们的外壳）。不关的话 429 时
        # SDK 重试 × 我们重试 × fallback 三层相乘（ADR-003 v1.2 的问题在框架下更隐蔽）
        max_retries=0,
        # 三段超时的前两段还能表达（connect/read=块间空闲）；
        # 但"首块 25s"与 deadline 传播在框架参数里没有位置——仍靠我们的外壳
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
        stream_usage=True,  # 等价于我们手写的 stream_options.include_usage
    )
    models: dict[str, BaseChatModel] = {}
    for name in ("qwen-flash", "qwen-turbo", "qwen-plus", "qwen-max", "deepseek-v3"):
        models[f"bailian:{name}"] = ChatOpenAI(
            model=name,
            base_url=s.dashscope_base_url,
            api_key=s.dashscope_api_key.get_secret_value(),
            **common,
        )
    models["anthropic:claude"] = ChatAnthropic(
        model="claude-sonnet-5",
        api_key=s.anthropic_api_key.get_secret_value(),
        max_retries=0,
        timeout=30.0,
    )
    return models
```

**对照点**：
- 统一协议不再是我们的 `LLMRequest/LLMChunk`，而是 langchain 的消息类型
  （`HumanMessage/AIMessage/ToolMessage`，流式产出 `AIMessageChunk`）；
- 方言翻译（我们 M1.4 写了三四天的 tool-call 双向映射）由集成包内部完成；
- **共享 httpx 客户端没了**：每个 ChatOpenAI 实例自建客户端——"三处连接池"之一
  失去显式控制（可传 `http_async_client=` 找回来，又是一行胶水）。

---

## 2. `errors_lc.py` —— 翻译表换了输入端（新增文件，约 40 行）

我们的六类契约（对 L2）**必须原样保留**——L2 的降级/恢复语义建立在它上面。
变化只是翻译源：从"httpx 状态码"变成"SDK 异常类型"。

```python
"""SDK 异常 → 我们的分类异常。替代 base.py 的 raise_for_status 翻译表。"""

import anthropic
import openai

from aegis.gateway.errors import (
    AuthError,
    BadRequestError,
    ProviderServerError,
    ProviderTimeoutError,
    RateLimitedError,
)


def classify(provider: str, e: Exception) -> Exception:
    if isinstance(e, (openai.RateLimitError, anthropic.RateLimitError)):
        # Retry-After 藏得更深了：要从 e.response.headers 里挖，
        # 且 HTTP-date 格式解析（base.py::parse_retry_after）还得留着
        ra = None
        resp = getattr(e, "response", None)
        if resp is not None:
            from aegis.gateway.providers.base import parse_retry_after
            ra = parse_retry_after(resp.headers.get("retry-after"))
        return RateLimitedError(provider, str(e)[:200], retry_after=ra)
    if isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError,
                      anthropic.AuthenticationError)):
        return AuthError(provider, str(e)[:200])
    if isinstance(e, (openai.APITimeoutError, anthropic.APITimeoutError)):
        return ProviderTimeoutError(provider, str(e)[:200])
    if isinstance(e, (openai.BadRequestError, anthropic.BadRequestError)):
        return BadRequestError(provider, str(e)[:200])
    if isinstance(e, (openai.APIError, anthropic.APIError)):
        return ProviderServerError(provider, str(e)[:200])
    return ProviderServerError(provider, f"未分类: {e!r}"[:200])
```

**对照点**：`sanitize_error_text` 的源头消毒逻辑仍然需要（SDK 异常文本同样可能
回显 key 片段）；`GatewayOverloadedError`（PoolTimeout 单独分类）在 SDK 抽象下
**很难再区分**——本地池排队和上游超时都变成 `APITimeoutError`，"三个不"待遇丢失。

---

## 3. `resilience_lc.py` —— 形状全保留，内核换成 astream（改约 20 行）

**这是最有学习价值的一段**：langchain 的 `.with_retry()` 不能用——它重试的是
"整次调用"，没有"首块之前才安全"的概念，流式场景下会造成重复输出。
我们 M1.5 的首块安全窗口是框架没有的语义，所以 `complete_with_retry` 的
骨架一行不改，只换"流从哪来、异常怎么翻译"：

```python
async def complete_with_retry_lc(
    model: BaseChatModel,          # ← 原来是 Provider 协议
    provider_name: str,
    messages: list[BaseMessage],   # ← 原来是 LLMRequest
    policy: RetryPolicy | None = None,
    *,
    deadline: float | None = None,
) -> AsyncGenerator[AIMessageChunk]:
    policy = policy or RetryPolicy()
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        stream = model.astream(messages)          # ← 原来是 provider.complete(req, model)
        try:
            first_wait = policy.first_chunk_timeout
            if deadline is not None:
                first_wait = min(first_wait, max(0.0, deadline - time.monotonic()))
            try:
                async with asyncio.timeout(first_wait):
                    first = await anext(stream)
            except TimeoutError as e:
                await stream.aclose()
                raise ProviderTimeoutError(provider_name, f"首块超时 >{first_wait:.1f}s") from e
        except StopAsyncIteration:
            return
        except Exception as raw:                   # ← 多一步：SDK 异常先翻译再分拣
            e = raw if isinstance(raw, GatewayError) else classify(provider_name, raw)
            if not isinstance(e, RETRYABLE_ERRORS) or attempt >= policy.max_attempts:
                raise e from raw
            delay = compute_backoff(attempt, policy, getattr(e, "retry_after", None))
            now = time.monotonic()
            if now - start + delay > policy.total_timeout:
                raise e from raw
            if deadline is not None and now + delay + policy.min_attempt_budget > deadline:
                raise e from raw
            await _sleep(delay)
            continue
        async with aclosing(stream) as inner:
            yield first
            async for chunk in inner:
                yield chunk
        return
```

**对照点**：三条铁律、双闸取小、预算裸抛真实死因、退避满抖动+Retry-After 优先——
**全部是我们的，框架给不了**。唯一变化：异常入口多了一次 `classify()` 翻译。

---

## 4. 原样保留的文件（一行不改或只改类型签名）

| 文件 | 命运 | 原因 |
|---|---|---|
| `ratelimit.py` | **原样** | langchain 的 `InMemoryRateLimiter` 是进程内、无 provider/租户维度、无 Lua 原子性——玩具与工业件的差距 |
| `breaker.py` | **原样** | 框架无熔断概念；`.with_fallbacks()` 是无记忆的钝器——每个请求都要在坏供应商上撞一次墙才转身，没有"deny 秒拒"、没有半开互斥 |
| `metering.py` | **原样** | 账本、Decimal、月度聚合、预算闸门全是我们的。数据源小改：token 用量从 `AIMessageChunk.usage_metadata` 读（`{"input_tokens":…,"output_tokens":…}`），字段名翻译两行 |
| `cache.py` | **保留主体，改 key 函数** | langchain 的全局 LLM 缓存（`set_llm_cache`）**key 里没有租户概念**，且无"完整流才入库"守卫——头号安全卖点在框架缓存上直接翻车。保留 ExactCache，`_key` 改为序列化 `(tier, messages, tools)` 的 canonical JSON |
| `core/config.py` `core/tokens.py` | **原样** | 与框架无关 |
| 六类异常契约 `errors.py` | **原样** | L2 的世界观，谁也动不了 |

### 4.1 cache 的 key 函数改版（展开）

```python
# value 侧（get/put/完整性守卫）逐字节不变——方案 A 下 buffer 里仍是我们的 LLMChunk。
# 只有 _key 重写：langchain 消息带非语义字段（id 每条随机/response_metadata/
# usage_metadata），混入哈希 = 永不命中 + 静默烧钱——"request_id 混入"事故的框架变体。

_SEMANTIC_FIELDS = ("type", "content", "tool_calls", "tool_call_id", "name")

def _canonical_message(m: BaseMessage) -> dict:
    d = m.model_dump()
    return {f: d[f] for f in _SEMANTIC_FIELDS if d.get(f)}   # 空值不进哈希

def _key(self, req: GatewayRequest) -> str:
    essence = {
        "tier": req.tier,
        "messages": [_canonical_message(m) for m in req.messages],
        "tools": [t.model_dump() for t in req.tools],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
    }
    blob = json.dumps(essence, sort_keys=True, ensure_ascii=False)
    return f"aegis:cache:v1:{req.tenant_id}:{hashlib.sha256(blob.encode()).hexdigest()}"
```

**学习点**：① 现版对自有类型用**黑名单** exclude（可行但 M2.0 加 deadline_s 时
差点翻车——评审 X4）；第三方类型必须**白名单**——langchain 升级新增元数据字段时，
黑名单会静默漏进哈希导致全量 miss。口诀：自己的类型黑名单可用，别人的类型必须白名单。
② 不用框架 `set_llm_cache` 的根本原因：它缓存"最终答案"（generate 路径，对 astream
无感），我们的缓存是"流回放器"（存 chunk 序列+盖章+记零成本账）——对象都不一样。
③ 若选方案 B，value 侧也得用 langchain 的 dumpd/load 序列化——框架类型渗进 Redis
持久化数据，升级可能让存量缓存集体解析失败。

---

## 5. `router_lc.py` —— 总装九步全保留，候选从 Provider 变 Runnable

```python
class LLMGatewayLC:
    """九步旅程与现版 router.py 逐步对应——对照着读，看变的只有 ⑦ 的内层。"""

    async def complete(self, req: GatewayRequest) -> AsyncGenerator[LLMChunk]:
        # ① 路由防御 ② deadline 换算 —— 原样
        # ③ 精确缓存 —— 原样（key 函数见 §4）
        # ④ 月度预算闸门 ⑤ 单请求闸门 —— 原样（估算器数消息文本，多一个
        #    "langchain 消息 → 纯文本"的 3 行适配）
        # ⑥ 租户出站限流 —— 原样
        ...
        for cand in candidates:                       # ⑦ 候选环：结构原样
            # deadline 预检 / 熔断闸门 / 供应商限流 —— 原样，一行不改
            ...
            model = self._models[f"{cand.provider}:{cand.model}"]
            if req.tools:
                model = model.bind_tools(req.tools)   # ← 方言翻译：框架代劳
            lc_messages = to_lc_messages(req.messages) # ← 新胶水（约 20 行）

            try:
                async with aclosing(complete_with_retry_lc(
                    model, cand.provider, lc_messages, policy, deadline=deadline,
                )) as rs:
                    async for chunk in rs:
                        yielded = True
                        # ← 新胶水：AIMessageChunk → 我们的 LLMChunk（约 40 行）
                        #    如果不翻译，langchain 类型就会漏进 L2 契约——见 §6 的抉择
                        for out in from_lc_chunk(chunk):
                            if isinstance(out, UsageChunk):
                                usage_seen = out
                            buffer.append(out)
                            yield out
                # ⑧ 成功收尾：on_success / 缓存写入 / 记账 —— 原样
                ...
            except _BREAKER_COUNTED as e:
                # ⑨ 异常三待遇与终局三段 —— 原样，一行不改
                ...
```

**对照点**：被替代的只有两处——`bind_tools`（方言）和 `astream`（传输）。
熔断记账、半截不换路、budget_out → rejected → exhausted 终局、故障注入
（FaultInjector 从"包装 Provider"变成"包装 async 生成器"，逻辑不变）——全部原样。

---

## 6. 绕不开的抉择：L2 契约用谁的类型？

这是整个对照实验最深的一课。`from_lc_chunk` 那 40 行胶水存在的原因：

- **方案 A（上面展示的）**：L2 契约维持我们的 `LLMChunk`——那么"适配器"并没有被
  消灭，只是从"翻译 SSE 线格式"退化成"翻译 langchain 类型"，600 行变 60 行；
- **方案 B**：L2 直接消费 `AIMessageChunk`——胶水归零，但 langchain 类型从此
  渗透进 AgentLoop、EventStream 的 payload、回放 cassette 格式……**框架升级 =
  全栈事件格式迁移**。事件溯源系统最怕的就是把第三方类型焊进事实源。

方案 B 就是 ADR-003 说的"对抗框架的抽象"的具体形态；方案 A 则说明：
**只要你想保住自己的契约边界，"用框架"省掉的代码远比宣传的少。**

---

## 7. 语义保真度总表（M1 每个卖点在 LangChain 版下的命运）

| M1 卖点 | LangChain 版命运 |
|---|---|
| 统一协议 + 方言抹平 | ✅ 框架代劳（真省事的部分） |
| tool-call 按 index 组装 / [DONE] 哨兵 / 流内 error | ⬛ 黑盒化——省 400 行，失去可断言性（respx 级别的 24 个适配器测试无处安放） |
| 首块安全窗口重试 | 🟨 **必须自己保留**（`.with_retry` 无此语义） |
| Retry-After 优先 + 满抖动 | 🟨 自己保留（`.with_retry` 只有指数抖动，不读服务端指令） |
| 熔断（三键 + 半开互斥 + deny 秒拒） | 🟥 框架无此物，原样保留 |
| 分布式多维限流（Lua + Redis TIME） | 🟥 同上 |
| 租户隔离缓存 + 完整性守卫 | 🟥 框架缓存无租户概念，原样保留 |
| Decimal 账本 + 三级预算闸门 | 🟥 原样保留（数据源字段名小改） |
| 超时两阶段 + deadline 传播 | 🟨 connect/idle 能配，首块与 deadline 自己保留 |
| PoolTimeout 单独分类（三个"不"） | ❌ SDK 抽象下丢失 |
| 六类异常契约 | 🟨 保留，翻译源换成 SDK 异常（新增 classify 表） |
| 故障注入三模式 | 🟥 原样保留（包装对象换个类型） |
| 双重重试防线 | ⚠️ 从"不引 SDK 天然免疫"变成"必须记得 max_retries=0"——防线从结构保证退化为纪律保证 |

图例：✅ 框架提供 ｜ ⬛ 黑盒化 ｜ 🟨 形状保留内核换 ｜ 🟥 与框架无关原样保留 ｜ ❌ 丢失

---

## 8. 这次对照的三个学习结论

1. **框架替掉的是"传输与格式"，替不掉"策略与状态"**——而这个项目的简历价值
   全在后者。行数上：~700 行被替代、~1000 行原样、+150 行新胶水，净省 ≈550 行，
   占网关的三分之一，且恰是测试最好写、面试最不被问的三分之一；
2. **契约边界是主权问题**：§6 的抉择说明"用不用框架"的真正代价不在写代码时，
   而在框架类型是否渗进你的事实源（事件、缓存、回放格式）；
3. **最值得偷的是机制不是依赖**：langchain 的 `@tool`（inspect+Pydantic）、
   `InjectedToolArg`（注入参数剔除）与我们 M2.3 的设计殊途同归——读它的源码
   印证自己的设计，比 import 它更有面试价值（ADR-003 的辩证答法有了实证）。
