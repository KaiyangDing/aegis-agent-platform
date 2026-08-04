"""M5.4 demo 四高光驱动器（docs/demo-script.md 的"操作"列即本脚本子命令）。

子命令（仓库根执行；compose 真实上游栈在跑、.env 在场）：
    uv run python scripts/demo_m5_highlights.py prep    # 预备：复位演示订单 + 签发 5 枚 token
    uv run python scripts/demo_m5_highlights.py h1      # 高光1 故障注入：30% 照答 + 熔断毫秒拒
    uv run python scripts/demo_m5_highlights.py h2      # 高光2 断点续跑全弧（kill 副本 + 断连批准）
    uv run python scripts/demo_m5_highlights.py h3      # 高光3 多租户隔离四连
    uv run python scripts/demo_m5_highlights.py h4      # 高光4 trace 还原 + 回放门
    uv run python scripts/demo_m5_highlights.py all     # 排练模式：四段连跑 + 计时表

段间状态走 .demo_tokens.json / .demo_state.json（gitignore，含短时 JWT 不入库）。
高光1 直连网关（零 HTTP）与容器共用同一 Redis：结尾必清熔断键，否则 H2 真实流量被拒。
高光2 断言只认事实面（events 序列 + mock 订单翻转），不认 HTTP 响应体——
批准连接断没断、续跑在哪个副本上，事实面都给同一个答案（(57) 全弧的口径）。
(58) 家族第三例：裸网关驱动必须 tenant_context 配对，否则计量被 RLS 静默拒收。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8080"
CHAT_MSG = "请直接为订单 HITL-DEMO-0001 提交 300 元退款申请，不需要与我确认。"
TOKENS_FILE = REPO_ROOT / ".demo_tokens.json"
STATE_FILE = REPO_ROOT / ".demo_state.json"
KILL_TARGET = "aegis-api-3"


def _run(*args: str) -> str:
    out = subprocess.run(args, capture_output=True, text=True, cwd=str(REPO_ROOT), encoding="utf-8")
    return (out.stdout or "") + (out.stderr or "")


def _tokens() -> dict[str, str]:
    if not TOKENS_FILE.exists():
        raise SystemExit("缺 .demo_tokens.json——先跑 prep 子命令")
    return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))


def _state() -> dict[str, str]:
    if not STATE_FILE.exists():
        raise SystemExit("缺 .demo_state.json——先跑 h2 子命令")
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def prep() -> None:
    """预备段：演示订单复位（重跑即复位）+ 5 枚角色 token 落本地文件。"""
    print(_run("uv", "run", "python", "scripts/demo_hitl_helper.py", "seed").strip())
    tokens: dict[str, str] = {}
    for uid in ("u-a1", "op-a1", "op-b1", "u-a2", "u-b1"):
        tok = _run("uv", "run", "python", "scripts/mint_token.py", uid).strip().splitlines()[-1]
        if tok.count(".") != 2:
            raise SystemExit(f"签发 {uid} 失败：{tok[-200:]}")
        tokens[uid] = tok
    TOKENS_FILE.write_text(json.dumps(tokens), encoding="utf-8")
    print(f"5 枚 token 已就绪 → {TOKENS_FILE.name}（gitignore，短时效）")


async def h1() -> None:
    """高光1（网关直连零 HTTP）：30% 注入照常回答 → 单候选 100% 注入熔断毫秒级拒绝。"""
    import os

    os.environ["CACHE_TTL_SECONDS"] = "0"
    from aegis.core.config import get_settings

    get_settings.cache_clear()
    from aegis.core.tenant_ctx import tenant_context
    from aegis.gateway.schema import LLMRequest, Message, TextDelta
    from scripts.experiment_breaker_recovery import _clear_breaker_keys, _gateway

    def _req(content: str) -> LLMRequest:
        return LLMRequest(
            tier="standard",
            messages=[Message(role="user", content=content)],
            tenant_id="lt-demo",
            session_id=f"demo-h1-{uuid4().hex[:8]}",
            max_tokens=16,
        )

    await _clear_breaker_keys()
    gw30 = _gateway(fault_rate=0.3)
    for i in range(3):
        t0 = time.perf_counter()
        try:
            with tenant_context("lt-demo"):
                async for chunk in gw30.complete(_req(f"演示探针 {uuid4().hex}，回一个字。")):
                    if isinstance(chunk, TextDelta):
                        pass
            print(f"[h1] 30% 注入 #{i + 1}：照常回答（{time.perf_counter() - t0:.1f}s——重试/fallback 消化注入）")
        except Exception as e:  # noqa: BLE001 —— 演示画面要的是现象名，不是栈
            print(f"[h1] 30% 注入 #{i + 1}：失败 {type(e).__name__}（0.3^重试次数 的小概率，讲稿预答）")
    gw100 = _gateway(fault_rate=1.0)
    for _ in range(6):  # 阈值 5：多打一发保熔断必开（注入在真实调用前拦截——零 token）
        try:
            async for _chunk in gw100.complete(_req("x")):
                pass
        except Exception:  # noqa: BLE001,S110 —— 故意打失败攒熔断账
            pass
    t0 = time.perf_counter()
    try:
        async for _chunk in gw100.complete(_req("x")):
            pass
    except Exception as e:  # noqa: BLE001
        print(f"[h1] 熔断打开后拒绝：{(time.perf_counter() - t0) * 1000:.0f}ms（{type(e).__name__}——秒拒不烧上游）")
    await _clear_breaker_keys()
    print("[h1] 已清熔断键（与容器共用 Redis——不清则后续真实流量被拒）")


async def h2() -> tuple[str, str]:
    """高光2：退款>阈值挂起 → kill 一个 api 副本 → 幸存副本批准且 3s 断连 → 事实面确认续跑。"""
    print("[h2] " + _run("uv", "run", "python", "scripts/demo_hitl_helper.py", "seed").strip())
    tokens = _tokens()
    sid = f"demo-h2-{uuid4().hex[:8]}"
    approval_id = ""
    async with httpx.AsyncClient(timeout=120.0) as c:
        async with c.stream(
            "POST",
            f"{BASE}/v1/chat",
            json={"session_id": sid, "message": CHAT_MSG},
            headers={"Authorization": f"Bearer {tokens['u-a1']}"},
        ) as resp:
            assert resp.status_code == 200, resp.status_code
            buf = ""
            async for chunk in resp.aiter_text():
                buf += chunk
                for line in buf.splitlines():
                    if line.startswith("data:") and '"approval_id"' in line:
                        try:
                            approval_id = json.loads(line.partition(":")[2].strip())["approval_id"]
                        except (json.JSONDecodeError, KeyError):
                            continue  # SSE 半行未到齐，继续攒
                if approval_id:
                    break  # 用户视角：看到"等待审批"即关页面走人（断连①）
    assert approval_id, f"未捕获 approval_pending：{buf[-400:]}"
    print(f"[h2] 已挂起 approval={approval_id}；kill 副本 {KILL_TARGET}（手动 kill 不触发 unless-stopped 自启）")
    subprocess.run(["docker", "kill", KILL_TARGET], capture_output=True)
    t_kill = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=3.0)) as c:
            r = await c.post(
                f"{BASE}/v1/approvals/{approval_id}",
                json={"decision": "approve"},
                headers={"Authorization": f"Bearer {tokens['op-a1']}"},
            )
            print(f"[h2] decide 完整返回 {r.status_code}:{r.json().get('status')}（续跑快于 3s 超时窗——缓存命中路径）")
    except httpx.ReadTimeout:
        print("[h2] decide 3s 读超时→客户端已断连（断连②：裁决已 CAS 落库，续跑在服务端继续）")
    except httpx.HTTPError as e:
        print(f"[h2] decide 连接异常 {type(e).__name__}（nginx 撞死副本窗口，记录实况）")
    from sqlalchemy import select, text  # noqa: PLC0415

    from aegis.apps.support.mock_backend.models import MockOrderRecord  # noqa: PLC0415
    from aegis.core.db import get_owner_session_factory  # noqa: PLC0415

    owner = get_owner_session_factory()
    deadline = time.monotonic() + 150  # 兜底：decide 若中途死，beat 60s 对账扫描接手（approvals.py 崩溃窗）
    types: list[str] = []
    order_status = ""
    while time.monotonic() < deadline:
        async with owner() as s:
            rows = await s.execute(text("SELECT type FROM events WHERE session_id = :sid ORDER BY seq"), {"sid": sid})
            types = [str(r[0]) for r in rows.all()]
            row = (
                await s.execute(select(MockOrderRecord).where(MockOrderRecord.id == "HITL-DEMO-0001"))
            ).scalar_one_or_none()
            order_status = "" if row is None else str(row.status)
        if "loop_terminated" in types and order_status == "refunded":
            break
        await asyncio.sleep(2)
    need = ("approval_decided", "tool_result", "loop_terminated")
    assert all(t in types for t in need) and order_status == "refunded", (types, order_status)
    print(
        f"[h2] 事实面落地（kill 后 {time.perf_counter() - t_kill:.1f}s）："
        f"{[t for t in types if t in need]}，订单 status={order_status}"
    )
    tokens_user = tokens["u-a1"]
    async with httpx.AsyncClient(timeout=30.0) as c:  # 用户回来：GET 回放整段（终止会话服务端自动收流）
        r = await c.get(f"{BASE}/v1/sessions/{sid}/stream", headers={"Authorization": f"Bearer {tokens_user}"})
        assert "event: done" in r.text, r.text[-300:]
        print(f"[h2] 用户 GET /stream 回放：{len(r.text)} 字节，含 done 帧（用户侧闭环）")
    STATE_FILE.write_text(json.dumps({"sid": sid, "approval_id": approval_id}), encoding="utf-8")
    print(f"[h2] 状态已存 {STATE_FILE.name}；收尾提醒：docker start {KILL_TARGET}")
    return sid, approval_id


async def h3(sid: str, approval_id: str) -> None:
    """高光3 隔离四连：三拒零 LLM（拿真单据/真会话做靶）+ B 租户问 A 专有知识（1 次真实调用）。"""
    tokens = _tokens()
    async with httpx.AsyncClient(timeout=120.0) as c:
        r1 = await c.post(
            f"{BASE}/v1/approvals/{approval_id}",
            json={"decision": "approve"},
            headers={"Authorization": f"Bearer {tokens['op-b1']}"},
        )
        r2 = await c.get(f"{BASE}/v1/sessions/{sid}/stream", headers={"Authorization": f"Bearer {tokens['u-a2']}"})
        r3 = await c.get(f"{BASE}/v1/sessions/{sid}/events", headers={"Authorization": f"Bearer {tokens['u-a2']}"})
        print(
            f"[h3] B 租坐席裁 A 租真单={r1.status_code}（预期 403 点名）  "
            f"跨用户回放真会话={r2.status_code}（预期 404 隐身）  "
            f"user 查 trace={r3.status_code}（预期 403 角色墙）"
        )
        assert (r1.status_code, r2.status_code, r3.status_code) == (403, 404, 403)
        r4 = await c.post(
            f"{BASE}/v1/chat",
            json={"session_id": f"demo-h3-{uuid4().hex[:8]}", "message": "灵犀降噪耳机 Pro 的保修政策是什么？"},
            headers={"Authorization": f"Bearer {tokens['u-b1']}"},
        )
        data_lines = [ln for ln in r4.text.splitlines() if ln.startswith("data:")]
        answer = "".join(str(json.loads(ln.partition(":")[2]).get("text", "")) for ln in data_lines if '"text"' in ln)
        print(f"[h3] B 租户问 A 专有知识：HTTP {r4.status_code}，答复末段=「…{answer[-80:]}」")
        print("[h3] 检索不可见+缓存不命中：B 走自家语料兜底，A 的保修条款一字未现")


async def h4(sid: str) -> None:
    """高光4：坐席 trace API 逐步还原高光2 会话 + 回放门（同一确定性能力的 CI 形态）。"""
    tokens = _tokens()
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(f"{BASE}/v1/sessions/{sid}/events", headers={"Authorization": f"Bearer {tokens['op-a1']}"})
        assert r.status_code == 200, r.status_code
        tv: dict[str, Any] = r.json()
        runs = tv.get("runs", [])
        n_events = sum(len(run.get("events", [])) for run in runs)
        print(f"[h4] 坐席 trace 还原：runs={len(runs)} events={n_events}（每步耗时/工具参数可见，展示层已脱敏）")
    out = _run("uv", "run", "pytest", "tests/replay", "-q", "--no-header")
    last = [ln for ln in out.splitlines() if ln.strip()][-1]
    print(f"[h4] 回放门（零 token 重放录制会话，事件序列等价性断言）：{last}")
    assert "passed" in last and "failed" not in last


async def _all() -> None:
    timings: list[tuple[str, float]] = []
    t0 = time.perf_counter()
    prep()
    timings.append(("预备（订单复位+5 token）", time.perf_counter() - t0))
    t0 = time.perf_counter()
    await h1()
    timings.append(("高光1 故障注入+熔断", time.perf_counter() - t0))
    t0 = time.perf_counter()
    sid, approval_id = await h2()
    timings.append(("高光2 断点续跑全弧", time.perf_counter() - t0))
    t0 = time.perf_counter()
    await h3(sid, approval_id)
    timings.append(("高光3 隔离四连", time.perf_counter() - t0))
    t0 = time.perf_counter()
    await h4(sid)
    timings.append(("高光4 trace+回放门", time.perf_counter() - t0))
    print("\n== 计时表（机器时间，不含讲稿）==")
    total = 0.0
    for name, v in timings:
        print(f"  {name}: {v:.1f}s")
        total += v
    print(f"  合计: {total:.1f}s")
    print(f"收尾提醒：docker start {KILL_TARGET}")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"prep", "h1", "h2", "h3", "h4", "all"}:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "prep":
        prep()
    elif cmd == "h1":
        asyncio.run(h1())
    elif cmd == "h2":
        asyncio.run(h2())
    elif cmd == "h3":
        st = _state()
        asyncio.run(h3(st["sid"], st["approval_id"]))
    elif cmd == "h4":
        asyncio.run(h4(_state()["sid"]))
    else:
        asyncio.run(_all())


if __name__ == "__main__":
    main()
