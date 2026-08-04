"""跨 event loop 单例防线（M4.7 ㉝）：三次现形、三种修法之后的共性机制。

三次实锚：M2.9 `get_redis` 跨 loop 炸（修=30 个构造点显式传参）／M3.4 `shared_client`
keep-alive 绑死创建 loop（修=工厂参数直通）／M3.9 `mock_client`（修=安装缝）。三次都
只靠 docstring 警告——本模块把"发现"机制化：**首次在运行中 loop 里被使用即绑定**
（连接是惰性建立的，首用 loop 就是 keep-alive 连接的归属 loop），此后换 loop 复用时
给出**带定位的人话**，而不是等连接在调用栈深处炸出裸
`RuntimeError: ... attached to a different loop`。

两档处置（M4.7 偏差登记）：`strict=True` 抛异常（mock_client——其契约本就禁止跨 loop
复用，测试替身经对象身份重绑定天然豁免）；`strict=False` 响亮 warning（get_redis/
shared_client——既有测试装置面广，直接抛会把"曾经侥幸可用"的路径一刀切死，先警告
观察一个里程碑再议升级）。对象被替换（`set_mock_client`/monkeypatch 装替身）即重新
绑定——防线盯的是"同一实例跨 loop"，不是"换了新实例"。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class LoopBoundGuard:
    """单例的 loop 归属哨兵：`check(obj)` 在每次取用单例时调用。"""

    def __init__(self, what: str, *, hint: str, strict: bool) -> None:
        self._what = what
        self._hint = hint
        self._strict = strict
        self._obj: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def check(self, obj: object) -> None:
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            return  # 同步上下文取用：连接尚未绑定任何 loop，无从判定也无需判定
        if self._obj is not obj:
            self._obj = obj
            self._loop = running
            return
        if running is not self._loop:
            message = (
                f"{self._what} 是进程级单例、其连接已绑定另一个 event loop——"
                f"跨 loop 复用会在调用栈深处炸裸 RuntimeError。{self._hint}"
            )
            if self._strict:
                raise RuntimeError(message)
            logger.warning("%s", message)
            self._loop = running  # 非严格档：警告后跟随新 loop，不重复刷屏
