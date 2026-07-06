"""事件循环的一课：三个'SSE 流' + 一个同步阻塞的反派。盯着时间戳看。"""

import asyncio
import time

START = time.perf_counter()


def now() -> str:
    return f"{time.perf_counter() - START:5.2f}s"


async def sse_stream(user: str) -> None:
    """模拟一个用户的对话流：每 0.5s 从'上游'等到一块 token，推送给用户。"""
    for i in range(1, 7):
        await asyncio.sleep(0.5)  # 模拟等待上游吐块（真实世界是网络 IO）
        print(f"{now()}  [{user}] 推送第 {i} 块")


async def villain() -> None:
    """反派：1.2s 后执行一次同步阻塞——模拟误用了同步数据库驱动。"""
    await asyncio.sleep(1.2)
    print(f"{now()}  [反派] 开始同步阻塞 2 秒（time.sleep，没有 await！）")
    time.sleep(2)  # ← 罪魁祸首：线程站住，事件循环停摆
    print(f"{now()}  [反派] 阻塞结束")


async def main() -> None:
    await asyncio.gather(sse_stream("用户A"), sse_stream("用户B"), sse_stream("用户C"), villain())


asyncio.run(main())
