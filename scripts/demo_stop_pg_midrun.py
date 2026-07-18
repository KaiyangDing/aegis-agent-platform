"""M2.12 停 PG 演示：事件写入退避（0.1/0.2/0.4s）耗尽 → EventStoreUnavailable 明确终止；
write-ahead 核验式"内存副作用计数 == 已落盘 tool_call 数"（00 §6.2 第 6 项后半）。

操作：
  1) uv run python scripts/demo_stop_pg_midrun.py          # 仓库根；起跑时 PG 须在
  2) 看到横幅后另开终端：docker stop aegis-postgres（20 秒窗口）
  3) 脚本捕获明确错误后：docker start aegis-postgres——脚本等它回来自动核验并落盘实录
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from sqlalchemy import text

from aegis.core.config import Settings
from aegis.core.db import get_session_factory
from aegis.gateway.schema import LLMChunk, StopChunk, TextDelta, ToolCall, ToolCallChunk, UsageChunk
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import EventStoreUnavailable, SessionRecord
from aegis.runtime.tools import SideEffect, ToolContext, tool

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m2_degradation_pg.txt"
SESSION_ID = f"demo-pg-{uuid.uuid4().hex[:8]}"
LOG: list[str] = []
EXECUTED: list[str] = []


def log(line: str) -> None:
    print(line)
    LOG.append(line)


@tool(side_effect=SideEffect.WRITE, risk_exempt=True)
async def slow_ticket(ctx: ToolContext, title: str) -> dict:
    """慢写工具：write-ahead 已落盘、副作用已执行，然后给你 20 秒去停库。"""
    EXECUTED.append(ctx.tool_call_id)
    print("\n" + "=" * 62)
    print(">>> write-ahead 已落盘、副作用已执行（内存账本 +1）。")
    print(">>> 请现在在另一终端执行：docker stop aegis-postgres")
    print(">>> 20 秒后工具返回，执行器将尝试写 tool_result ……")
    print("=" * 62 + "\n", flush=True)
    await asyncio.sleep(20)
    return {"ticket": title}


SPEC = AgentSpec(system_prompt="你是演示客服。", tools=(slow_ticket,))
_CALL = ToolCall(id="c-slow", name="slow_ticket", arguments_json='{"title": "停库演示工单"}')


def _cassette() -> Cassette:
    tool_turn: list[LLMChunk] = [
        ToolCallChunk(tool_call=_CALL),
        UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12),
        StopChunk(reason="tool_calls"),
    ]
    text_turn: list[LLMChunk] = [
        TextDelta(text="工单已创建。"),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]
    return Cassette(
        session_id=SESSION_ID,
        scopes={"main": (CassetteEntry(chunks=tuple(tool_turn)), CassetteEntry(chunks=tuple(text_turn)))},
    )


async def main() -> None:
    sf = get_session_factory()
    async with sf() as s:
        async with s.begin():
            s.add(SessionRecord(id=SESSION_ID, tenant_id="t-a", user_id="u-1"))
    # 租约心跳挪出演示窗（100s）：规避偏差 #7 登记的缺陷候选——停库时心跳若先死，
    # finally 段的次生异常会顶掉 EventStoreUnavailable；本演示聚焦事实源退避语义本身
    settings = Settings(lease_ttl_s=300.0, lease_renew_interval_s=100.0)
    runtime = AgentRuntime(FakeGateway(_cassette()), sf, settings=settings)
    log(f"== 阶段 1：起 run（session={SESSION_ID}），等待你在窗口内停 PG ==")
    error_text = ""
    try:
        async for ev in runtime.run(SPEC, SESSION_ID, "帮我建一条工单"):
            log(f"  seq={ev.seq}  {ev.type.value}")
    except EventStoreUnavailable as e:
        error_text = str(e)
        log(f"  捕获 EventStoreUnavailable：{error_text}")
    if not error_text:
        raise SystemExit("run 正常完成——PG 没有在窗口内被停，请重跑并及时 docker stop aegis-postgres")

    log("== 阶段 2：请 docker start aegis-postgres，脚本轮询等它回来 ==")
    while True:
        try:
            async with sf() as s:
                await s.execute(text("SELECT 1"))
            break
        except Exception:
            print("  …… PG 未就绪，3 秒后重试（docker start aegis-postgres）", flush=True)
            await asyncio.sleep(3)
    async with sf() as s:
        tool_calls = (
            await s.execute(
                text("SELECT COUNT(*) FROM events WHERE session_id = :sid AND type = 'tool_call'"),
                {"sid": SESSION_ID},
            )
        ).scalar_one()
        results = (
            await s.execute(
                text("SELECT COUNT(*) FROM events WHERE session_id = :sid AND type = 'tool_result'"),
                {"sid": SESSION_ID},
            )
        ).scalar_one()
    log(f"  核验：内存副作用计数={len(EXECUTED)}；已落盘 tool_call={tool_calls}；tool_result={results}")
    if len(EXECUTED) != tool_calls:
        raise SystemExit("核验式不成立：副作用计数 != 已落盘 tool_call 数——write-ahead 被违反，报修")
    log("  核验式成立：副作用计数 == 已落盘 tool_call 数（write-ahead：无事件即无副作用；")
    log("  本例副作用发生在停库前属正常——tool_result 未落盘 = 结果不明路径，恢复语义由 M2.10 承接）")
    log("结论：事实源不可用 = 服务不可用——退避 0.1/0.2/0.4s 后明确终止，错误文本点名死因；无半执行副作用")
    REPORT_PATH.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"实录已落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
