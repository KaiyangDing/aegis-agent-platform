"""M4.7 ㉝：跨 event loop 单例防线——LoopBoundGuard 四判据（零真实依赖，纯 asyncio）。

三次现形三种修法之后的共性机制：首用即绑定 loop、同实例跨 loop 严格档抛人话/
非严格档响亮警告、实例被替换（set_mock_client/monkeypatch 替身）即重绑定豁免。
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from aegis.core.loopcheck import LoopBoundGuard


def _run_in_fresh_loop(coro_fn, *args):
    """在独立新 loop 里跑一段——模拟 worker 每任务 asyncio.run 的世界。"""
    return asyncio.run(coro_fn(*args))


def test_same_loop_reuse_is_silent() -> None:
    guard = LoopBoundGuard("试件", hint="用工厂现建。", strict=True)
    obj = object()

    async def use_twice() -> None:
        guard.check(obj)
        guard.check(obj)  # 同 loop 同实例：静默

    _run_in_fresh_loop(use_twice)


def test_cross_loop_same_object_raises_in_strict_mode() -> None:
    guard = LoopBoundGuard("试件", hint="用工厂现建。", strict=True)
    obj = object()

    async def bind() -> None:
        guard.check(obj)

    async def reuse() -> None:
        guard.check(obj)

    _run_in_fresh_loop(bind)
    with pytest.raises(RuntimeError, match="试件"):
        _run_in_fresh_loop(reuse)  # 换 loop 复用同实例：人话异常而非深处裸炸


def test_cross_loop_same_object_warns_in_lenient_mode(caplog) -> None:
    guard = LoopBoundGuard("试件", hint="用工厂现建。", strict=False)
    obj = object()

    async def bind() -> None:
        guard.check(obj)

    async def reuse() -> None:
        guard.check(obj)

    _run_in_fresh_loop(bind)
    with caplog.at_level(logging.WARNING, logger="aegis.core.loopcheck"):
        _run_in_fresh_loop(reuse)
    assert any("试件" in r.message for r in caplog.records), "非严格档必须响亮警告"


def test_replaced_object_rebinds_without_complaint() -> None:
    """替身安装（set_mock_client/monkeypatch）＝新实例：重绑定豁免，防线盯的是
    "同一实例跨 loop"，不是"换了新实例"。"""
    guard = LoopBoundGuard("试件", hint="用工厂现建。", strict=True)

    async def use(obj: object) -> None:
        guard.check(obj)

    _run_in_fresh_loop(use, object())
    _run_in_fresh_loop(use, object())  # 不同实例跨 loop：静默


def test_sync_context_is_exempt() -> None:
    """同步上下文取用（如 create_app 装配期）：连接尚未绑定任何 loop，无从判定也不判定。"""
    guard = LoopBoundGuard("试件", hint="用工厂现建。", strict=True)
    obj = object()
    guard.check(obj)
    guard.check(obj)
