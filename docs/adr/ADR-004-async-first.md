# ADR-004 · 全栈 asyncio 并发模型

**状态**：Accepted　**日期**：2026-07

## 背景

LLM 应用的并发特征极端：单个请求在"等待上游 token"上挂起数秒到数十秒，
是极端 IO 密集负载；同时存在少量 CPU 密集环节（文档解析、embedding、重排）。

## 决策

1. API 进程**全栈 asyncio**：FastAPI + httpx.AsyncClient + SQLAlchemy 2.0 async
   （asyncpg 驱动）+ redis-py async。整条请求链路零同步阻塞调用
   （CI 中用 blockbuster 类工具检测事件循环阻塞）；
2. CPU 密集任务**不进事件循环**：文档摄取流水线（解析/切块/embedding）全部走
   Celery worker（独立进程池，绕开 GIL）；API 进程内偶发 CPU 活用 `run_in_executor`；
3. 水平扩展用**多进程副本**（uvicorn worker / compose --scale），不是多线程。

## 理由（面试标准答案——评审后把绝对化断言换成经得起追问的版本）

- **资源效率差一个数量级，而不是"线程不可行"**（Java 线程模型服务端跑了二十年，
  Python 线程在 IO 等待时也释放 GIL、同样能做 IO 并发——真实差异是成本）：
  1000 并发下每线程需要独立栈 + 内核调度，协程只是 KB 级堆对象；
  SSE 万级长连接场景下两者的内存与切换成本差距被进一步放大；
- **GIL 的准确表述**：GIL 限制的是**纯 Python 字节码**的多线程 CPU 并行——
  numpy/tokenizer 等 C 扩展段会释放 GIL。所以 CPU 密集走多进程（Celery），
  不是因为"线程毫无贡献"，而是不依赖"恰好是 C 扩展"的侥幸；
- SSE 流式响应本身就是 async generator，token 逐个到达逐个推送，与 asyncio 天然同构；
- async 的真实代价：一处同步阻塞（如误用同步 requests、同步 DB 驱动）就会卡死整个
  事件循环拖累所有请求——所以"全栈 async"是纪律而不是偏好，混搭是最差选择。

## 备选方案

- **同步 + 线程池（Flask/gunicorn sync worker）**：模型简单，但并发容量差一个数量级，
  流式推送实现别扭；
- **Go/Java**：并发模型更强，但 AI 生态（SDK、embedding、文档解析）Python 断层领先，
  且本项目瓶颈在上游 LLM 延迟，语言运行时性能不是瓶颈。

## 后果

- 收益：单副本高并发容量；流式链路自然；
- 代价：全team（此处即个人）必须懂 async 陷阱——阻塞检测进 CI；调试栈比同步深。

## 面试深挖点

- "async 万能吗？"——不能，CPU 密集会饿死事件循环，答出 run_in_executor / 独立 worker 分流；
- "GIL 和 asyncio 什么关系？"——GIL 限制的是线程级 CPU 并行；asyncio 是单线程协作调度，
  根本不与 GIL 冲突，它解决的是 IO 等待的并发不是 CPU 并行；
- "怎么发现事件循环被阻塞？"——压测时 P99 整体抬升 + asyncio debug 模式的慢回调告警 +
  blockbuster 在测试中断言。
