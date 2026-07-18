"""M2.12 HITL 挂起-恢复端到端演示（必保路径；零真实调用——FakeGateway 回放）。

时间线：超阈值退款 → 风险闸门开审批单 → approval_requested → run 干净挂起（无
loop_terminated=进程可下线）→ 坐席 decide 批准（CAS：第二次翻转恰返 False）→
恢复单入口续跑 → 工具凭幂等键真执行 → 终答 → loop_terminated(completed)。

    uv run python scripts/demo_hitl_suspend_resume.py     # 仓库根；需 PG 在跑（Redis 可停）
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select

from aegis.core.db import get_session_factory
from aegis.gateway.schema import LLMChunk, StopChunk, TextDelta, ToolCall, ToolCallChunk, UsageChunk
from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, CassetteEntry, FakeGateway
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec
from aegis.runtime.store import ApprovalRecord, ApprovalStore, SessionRecord
from aegis.runtime.tools import SideEffect, ToolContext, tool

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "reports" / "m2_hitl_demo.txt"
SESSION_ID = f"demo-hitl-{uuid.uuid4().hex[:8]}"
LOG: list[str] = []
EXECUTED: list[str] = []


def log(line: str) -> None:
    print(line)
    LOG.append(line)


def _needs_approval(args: Any, tenant_config: Mapping[str, Any]) -> bool:
    return bool(args.amount > tenant_config.get("approval_threshold", 200))


@tool(side_effect=SideEffect.WRITE, risk_policy=_needs_approval)
async def refund_apply(ctx: ToolContext, order_id: str, amount: int) -> dict:
    """退款（超租户阈值走人工审批——演示场景：租户 A 阈值 200，00 §1）。"""
    EXECUTED.append(ctx.tool_call_id)
    return {"refunded": amount, "idempotency_key": ctx.tool_call_id}


SPEC = AgentSpec(
    system_prompt="你是数码商城客服，按平台规则处理退款。",
    tools=(refund_apply,),
    tenant_config={"approval_threshold": 200},
)
_REFUND = ToolCall(id="c-demo", name="refund_apply", arguments_json='{"order_id": "A-350", "amount": 350}')


def _cassette() -> Cassette:
    tool_turn: list[LLMChunk] = [
        ToolCallChunk(tool_call=_REFUND),
        UsageChunk(model="qwen-plus", prompt_tokens=30, completion_tokens=12),
        StopChunk(reason="tool_calls"),
    ]
    text_turn: list[LLMChunk] = [
        TextDelta(text="退款已提交，预计 1-3 个工作日到账。"),
        UsageChunk(model="qwen-plus", prompt_tokens=20, completion_tokens=7),
        StopChunk(reason="end_turn"),
    ]
    return Cassette(
        session_id=SESSION_ID,
        scopes={"main": (CassetteEntry(chunks=tuple(tool_turn)), CassetteEntry(chunks=tuple(text_turn)))},
    )


async def _run_state(sf: Any) -> str:
    async with sf() as s:
        return (await s.execute(select(SessionRecord.run_state).where(SessionRecord.id == SESSION_ID))).scalar_one()


async def main() -> None:
    sf = get_session_factory()
    async with sf() as s:
        async with s.begin():
            s.add(SessionRecord(id=SESSION_ID, tenant_id="t-a", user_id="u-1"))
    log(f"== 阶段 1：起 run 至挂起（session={SESSION_ID}）==")
    runtime = AgentRuntime(FakeGateway(_cassette()), sf)
    events = [e async for e in runtime.run(SPEC, SESSION_ID, "帮我退 350 元")]
    for e in events:
        log(f"  seq={e.seq}  {e.type.value}")
    aid = next(e for e in events if e.type is EventType.APPROVAL_REQUESTED).payload["approval_id"]
    async with sf() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    log(f"  审批单：id={aid} status={row.status} tool={row.tool_name} args={row.args} expires_at={row.expires_at}")
    log(f"  run_state={await _run_state(sf)}（awaiting_approval）；run 已干净返回、无 loop_terminated")
    log("  —— 进程此刻可下线：恢复段用全新 Runtime/网关实例模拟重启 ——")

    log("== 阶段 2：坐席决策（decide CAS）==")
    approvals = ApprovalStore(sf)
    log(
        f"  decide(approved=True, operator=op-demo) -> "
        f"{await approvals.decide(aid, approved=True, operator_id='op-demo')}"
    )
    log(
        f"  第二次 decide 同单 -> {await approvals.decide(aid, approved=True, operator_id='op-late')}（CAS 赢家恰一个）"
    )

    log("== 阶段 3：恢复单入口续跑 ==")
    resume_rt = AgentRuntime(FakeGateway(_cassette(), start_cursors={"main": 1}), sf)
    resumed = [e async for e in resume_rt.resume(SPEC, SESSION_ID, aid)]
    for e in resumed:
        log(f"  seq={e.seq}  {e.type.value}")
    log(f"  终止原因={resumed[-1].payload['reason']}；工具真执行幂等键={EXECUTED}")
    async with sf() as s:
        row = (await s.execute(select(ApprovalRecord).where(ApprovalRecord.id == aid))).scalar_one()
    log(f"  审批单终态：status={row.status} operator_id={row.operator_id} event_id={row.event_id}（审计链回填）")
    log(f"  run_state={await _run_state(sf)}（idle 归位）")
    log("结论：挂起→审批→恢复全链闭合；审批回调只翻状态、恢复统一走单入口（必保路径，00 §6.2 第 5 项）")
    REPORT_PATH.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    print(f"实录已落盘：{REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
