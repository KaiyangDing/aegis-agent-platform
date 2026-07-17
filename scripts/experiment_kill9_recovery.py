"""kill -9 崩溃恢复实录（M2.10 交付④，P5 拍板默认做）。

时序敏感 → 不进 CI（00 §2.2 测试纪律）；凭证落 reports/m2_kill9_recovery.txt
（简历数字纪律：没实测不写数字）。双模式：
  主模式  python scripts/experiment_kill9_recovery.py
  子模式  （主进程自动拉起）--child <session_id>：跑到慢速写工具执行中被 kill。
四断言：副作用恰一次（幂等键账本）/ seq 连续 / 合法终止 / recovery_count 归零。
路径一律 Path(__file__) 锚定仓库根（记忆教训：脚本落盘不依赖 cwd）。
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from aegis.core.config import get_settings  # noqa: E402
from aegis.gateway.schema import (  # noqa: E402
    LLMChunk,
    LLMRequest,
    StopChunk,
    TextDelta,
    ToolCall,
    ToolCallChunk,
    UsageChunk,
)
from aegis.runtime.events import EventType  # noqa: E402
from aegis.runtime.runtime import AgentRuntime  # noqa: E402
from aegis.runtime.spec import AgentSpec  # noqa: E402
from aegis.runtime.store import EventRecord, RunState, SessionRecord  # noqa: E402
from aegis.runtime.tools import SideEffect, ToolContext, tool  # noqa: E402
from aegis.workers.reaper import reap_once  # noqa: E402

LEDGER = REPO_ROOT / "reports" / "kill9_ledger.jsonl"
"""假下游账本：按幂等键（ctx.tool_call_id）记账——恢复重执行复用原键，按键去重后恰一次。"""


@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def slow_refund(ctx: ToolContext, order_id: str, amount: int) -> dict:
    """慢速写工具：child 模式睡 15s（kill 窗口），恢复模式睡 0；账本按幂等键去重。"""
    await asyncio.sleep(float(os.environ.get("KILL9_SLOW_S", "0")))
    LEDGER.parent.mkdir(exist_ok=True)
    seen = set()
    if LEDGER.exists():
        seen = {json.loads(line)["key"] for line in LEDGER.read_text(encoding="utf-8").splitlines() if line}
    if ctx.tool_call_id not in seen:  # 幂等下游：同键第二次到达不再产生副作用
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": ctx.tool_call_id, "order": order_id, "amount": amount}) + "\n")
    return {"refunded": amount, "idempotency_key": ctx.tool_call_id}


class _ScriptedGateway:
    def __init__(self, scripts: Sequence[Sequence[LLMChunk]]) -> None:
        self._scripts = scripts
        self._i = 0

    async def complete(self, req: LLMRequest) -> AsyncGenerator[LLMChunk]:
        script = self._scripts[self._i]
        self._i += 1
        for chunk in script:
            yield chunk


def _tool_turn() -> list[LLMChunk]:
    call = ToolCall(id="c-k9", name="slow_refund", arguments_json='{"order_id": "K9-1", "amount": 80}')
    return [
        ToolCallChunk(tool_call=call),
        UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12),
        StopChunk(reason="tool_calls"),
    ]


def _text_turn(text: str) -> list[LLMChunk]:
    return [
        TextDelta(text=text),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]


def _spec() -> AgentSpec:
    return AgentSpec(system_prompt="你是演示客服。", tools=(slow_refund,))


def _engine():
    return create_async_engine(get_settings().database_url, poolclass=NullPool)


async def _child(session_id: str) -> None:
    """子进程：建行 → run 到慢工具执行中（等着被 kill）。"""
    engine = _engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        async with s.begin():
            s.add(SessionRecord(id=session_id, tenant_id="t-a", user_id="u-1"))
    runtime = AgentRuntime(_ScriptedGateway([_tool_turn(), _text_turn("退款已提交。")]), factory)
    async for _ in runtime.run(_spec(), session_id, "帮我退 80 元"):
        pass
    await engine.dispose()


async def _main() -> int:
    session_id = f"kill9-{int(time.time())}"
    if LEDGER.exists():
        LEDGER.unlink()
    print(f"== kill -9 崩溃恢复实录  session={session_id} ==")

    env = os.environ | {"KILL9_SLOW_S": "15", "PYTHONUTF8": "1"}
    proc = subprocess.Popen([sys.executable, __file__, "--child", session_id], env=env, cwd=REPO_ROOT)
    engine = _engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # 等 write-ahead 落盘（tool_call 事件出现 = 工具执行中），随即 kill -9
    for _ in range(200):
        async with factory() as s:
            n = (
                await s.execute(
                    select(func.count())
                    .select_from(EventRecord)
                    .where(EventRecord.session_id == session_id, EventRecord.type == EventType.TOOL_CALL.value)
                )
            ).scalar_one()
        if n:
            break
        await asyncio.sleep(0.1)
    else:
        print("FAIL: 等不到 tool_call 事件，子进程没跑起来")
        proc.kill()
        return 1
    proc.kill()  # Windows 上 Process.kill == TerminateProcess，等效 kill -9
    proc.wait(timeout=10)
    print(f"子进程已被 kill（pid={proc.pid}），工具执行中、副作用未落账")

    async with factory() as s:
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one()
    ok_stuck = row.run_state == RunState.RUNNING.value
    print(f"[断言0] 会话卡在 running（尸体形态）: {'PASS' if ok_stuck else 'FAIL'}")

    # reaper 认领（注入未来时钟，不真等 60s TTL）+ 演示恢复钩子（走 resume 单入口续跑）
    os.environ["KILL9_SLOW_S"] = "0"
    async with factory() as s:
        db_now = (await s.execute(select(func.now()))).scalar_one()
    from datetime import timedelta

    hook_errors: list[BaseException] = []

    async def resume_hook(sid: str, owner: str, generation: int) -> None:
        # owner 必须与 reap_once 同串（default_lease_owner）：resume 内 acquire 走同 owner 重入
        rt = AgentRuntime(_ScriptedGateway([_text_turn("退款已提交，请留意到账。")]), factory)
        try:
            async for _ in rt.resume(_spec(), sid, None):
                pass
        except BaseException as e:  # P6 会把异常吞进日志——脚本要响亮，自己收集再抛
            hook_errors.append(e)
            raise

    from aegis.runtime.store import default_lease_owner

    report = await reap_once(
        factory,
        owner=default_lease_owner(),
        lease_ttl_s=get_settings().lease_ttl_s,
        recovery_limit=get_settings().recovery_limit,
        resume=resume_hook,
        now=db_now + timedelta(minutes=2),
    )
    print(f"reaper 认领：recovered={report.recovered} abandoned={report.abandoned}")
    if hook_errors:
        print(f"FAIL: 恢复钩子异常：{hook_errors[0]!r}")
        await engine.dispose()
        return 1

    # 四断言
    async with factory() as s:
        rows = (
            await s.execute(
                select(EventRecord.seq, EventRecord.type, EventRecord.payload)
                .where(EventRecord.session_id == session_id)
                .order_by(EventRecord.seq)
            )
        ).all()
        row = (await s.execute(select(SessionRecord).where(SessionRecord.id == session_id))).scalar_one()
    ledger_lines = LEDGER.read_text(encoding="utf-8").splitlines() if LEDGER.exists() else []
    keys = [json.loads(line)["key"] for line in ledger_lines if line]
    call_ids = [r.payload.get("tool_call_id") or "" for r in rows if r.type == EventType.TOOL_RESULT.value]
    ok_once = len(keys) == 1 and len(set(keys)) == 1
    ok_seq = [r.seq for r in rows] == list(range(1, len(rows) + 1))
    ok_end = rows[-1].type == EventType.LOOP_TERMINATED.value and rows[-1].payload.get("reason") == "completed"
    ok_reset = row.recovery_count == 0 and row.run_state == RunState.IDLE.value
    print(f"[断言1] 副作用恰一次（账本键 {keys}，tool_result 键 {call_ids}）: {'PASS' if ok_once else 'FAIL'}")
    print(f"[断言2] 事件 seq 连续 1..{len(rows)}: {'PASS' if ok_seq else 'FAIL'}")
    print(f"[断言3] 合法终止（loop_terminated/completed）: {'PASS' if ok_end else 'FAIL'}")
    print(f"[断言4] recovery_count 归零且 run_state=idle: {'PASS' if ok_reset else 'FAIL'}")
    resume_seq = next((r.seq for r in rows if r.type == EventType.TOOL_RESULT.value), "?")
    print(f"事件总数 {len(rows)}；恢复段起点 seq={resume_seq}")
    # 自清理：本次演示行不留库——失败残留（running+过期）会污染 reaper 测试的全库扫描
    from sqlalchemy import text as _text

    async with engine.begin() as conn:
        for table in ("events", "messages", "tool_invocations"):
            await conn.execute(_text(f"DELETE FROM {table} WHERE session_id = :sid"), {"sid": session_id})
        await conn.execute(_text("DELETE FROM sessions WHERE id = :sid"), {"sid": session_id})
    await engine.dispose()
    all_pass = ok_stuck and ok_once and ok_seq and ok_end and ok_reset
    print(f"== 结论：{'全部 PASS —— 断点续跑成立，无重复副作用' if all_pass else '存在 FAIL，见上'} ==")
    return 0 if all_pass else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--child":
        asyncio.run(_child(sys.argv[2]))
    else:
        raise SystemExit(asyncio.run(_main()))
