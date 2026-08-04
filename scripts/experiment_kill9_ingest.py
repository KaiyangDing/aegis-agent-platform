"""摄取链路 kill -9 实录（M4.0④b，00 §10.1 #48 的"kill -9 实录待补"）。

**为什么必须做**：复盘补丁一（`944e5ee`）只改了两个配置开关（`task_acks_late=True` +
`task_reject_on_worker_lost=True`），CI 钉子 `test_delivery_is_at_least_once` 也只是
**纯配置断言**——"配置改了 ≠ 行为验证了"。本脚本验的是真链路：真 Redis broker、
真 Celery worker、真 kill -9、真重投。

**零真实调用**（M4 口径 00 §8.0：只有 M4.4/M4.6 花钱）：`DASHSCOPE_BASE_URL` 指向
`scripts/fake_embedding_server.py`，生产任务体一字不改（`build_embedding_client` 读的
就是这个配置项，factory.py:87）。

**首跑实测推翻了一处设计前提，四断言据此改造（2026-08-03）**：
`task_acks_late=True` 只保证"消息不在执行前 ack"；真正把 unacked 消息放回队列的是
kombu Redis transport 的 `restore_visible`，而它挂在 **event loop** 上
（`loop.call_repeatedly(10, cycle.maybe_restore_messages)`，kombu/transport/redis.py:1382）。
Celery 的 `WorkController.should_use_eventloop()` 含 `not self.app.IS_WINDOWS`——
**Windows 上恒走 synloop 无 hub（与 pool 无关）→ unacked 消息永不自动重投**。
实测印证：kill 后重启 worker 等满 150s 无恢复；手动调一次 `restore_visible`
两条消息立刻回队列（restore 逻辑本身完好，只是无人调用）。

故本实录在 Windows 形态下把"自动重投"这一环**显式替换为手动触发**，并如实登记：
  0. 崩溃现场：文档卡 PROCESSING、部分块已回填向量（"半截"确实存在）；
  1. **消息不丢**：kill 后消息仍在 `unacked`（acks_late 兑现的那一半）；
  2. **超时判定 + restore 正确**：等过 visibility_timeout 后触发 restore，消息回队列，
     worker 重新消费到最终 DONE 且 chunk_count 正确（幂等消费收敛）；
  3. 账本重复 embedding 行 ≤1 批（重复成本上界＝一批 EMBED_BATCH_SIZE，
     "每批独立事务"的红利——IS NULL 谓词让已回填行天然出队）。
**未覆盖面（挂 M4.7 Linux 容器复验）**：定时器自动触发 restore 这一环。

**时序敏感 → 不进 CI**（00 §2.2 测试纪律）；凭证落 reports/m4_kill9_ingest.txt。
路径一律 Path(__file__) 锚定仓库根（记忆教训：脚本落盘不依赖 cwd）。

前置（三个窗口，仓库根）：
  ① docker compose -f deploy/docker-compose.yml up -d
  ② $env:FAKE_EMBED_DELAY_S="3"; uv run python scripts/fake_embedding_server.py
  ③ uv run python scripts/experiment_kill9_ingest.py     ← 本脚本，自动拉起/杀死 worker
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from aegis.apps.support.rag.ingest import INGEST_TASK_NAME  # noqa: E402
from aegis.apps.support.rag.models import ChunkRecord, DocumentRecord, IngestStatus  # noqa: E402
from aegis.core.config import get_settings  # noqa: E402
from aegis.core.tenancy import TenantRecord  # noqa: E402
from aegis.gateway.embeddings import EMBED_BATCH_SIZE  # noqa: E402
from aegis.gateway.metering import UsageRecord  # noqa: E402
from scripts.kill9_celery_app import VISIBILITY_TIMEOUT_S  # noqa: E402

REPORT = REPO_ROOT / "reports" / "m4_kill9_ingest.txt"
CALL_LOG = REPO_ROOT / "reports" / "fake_embed_calls.jsonl"
FAKE_PORT = int(os.environ.get("FAKE_EMBED_PORT", "8799"))
FAKE_URL = f"http://127.0.0.1:{FAKE_PORT}"

TENANT = "t-kill9"
DOC_ID = f"kill9-doc-{int(time.time())}"
CHUNKS_WANTED = 25  # > 2 批（EMBED_BATCH_SIZE=10）：保证 kill 落在"部分回填"的中段
LINES: list[str] = []


def say(line: str) -> None:
    print(line)
    LINES.append(line)


def _owner_factory():
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _long_text() -> str:
    """造 ≥25 块（>2 批）：kill 才能落在"部分回填"的中段。

    算术（split_text 口径）：target_tokens=400、CJK 恰 1 token/字（C25 护栏尺）——
    每段 ≈102 字 → 每块聚 ≈4 段 → 需 ≈100 段才够 25 块。首版按 40 段只切出 10 块
    （=1 批），kill 窗口不成立：**批次边界是这个实验的物质基础，块数必须先算后写**。
    """
    para = "这是用于崩溃恢复实录的演示文本，内容无意义但长度足够成块。" * 3
    return "\n\n".join(f"第 {i} 段。{para}" for i in range(100))


async def _seed() -> None:
    engine, factory = _owner_factory()
    try:
        async with factory() as s:
            async with s.begin():
                tenant = (await s.execute(select(TenantRecord).where(TenantRecord.id == TENANT))).scalar_one_or_none()
                if tenant is None:
                    s.add(TenantRecord(id=TENANT, name="kill9 实录租户", config={}, token_budget_monthly=10_000_000))
                s.add(
                    DocumentRecord(
                        id=DOC_ID,
                        tenant_id=TENANT,
                        source="kill9-experiment",
                        text=_long_text(),
                        status=IngestStatus.PENDING.value,
                        meta={},  # NOT NULL 无 default——照 api/kb.py:76 生产建行方式
                    )
                )
    finally:
        await engine.dispose()


async def _doc_status() -> tuple[str, int | None]:
    engine, factory = _owner_factory()
    try:
        async with factory() as s:
            row = (await s.execute(select(DocumentRecord).where(DocumentRecord.id == DOC_ID))).scalar_one()
            return row.status, row.chunk_count
    finally:
        await engine.dispose()


async def _chunk_counts() -> tuple[int, int]:
    """(总块数, 已回填向量的块数)。"""
    engine, factory = _owner_factory()
    try:
        async with factory() as s:
            total = (
                await s.execute(select(func.count()).select_from(ChunkRecord).where(ChunkRecord.document_id == DOC_ID))
            ).scalar_one()
            filled = (
                await s.execute(
                    select(func.count())
                    .select_from(ChunkRecord)
                    .where(ChunkRecord.document_id == DOC_ID, ChunkRecord.embedding.is_not(None))
                )
            ).scalar_one()
            return total, filled
    finally:
        await engine.dispose()


async def _ledger_rows() -> int:
    """本租户 embedding 计量行数——重复回填会多记，用于断言 3 的上界核对。"""
    engine, factory = _owner_factory()
    try:
        async with factory() as s:
            return (
                await s.execute(
                    select(func.count())
                    .select_from(UsageRecord)
                    .where(UsageRecord.tenant_id == TENANT, UsageRecord.tier == "embedding")
                )
            ).scalar_one()
    finally:
        await engine.dispose()


async def _cleanup() -> None:
    engine, factory = _owner_factory()
    try:
        async with factory() as s:
            async with s.begin():
                await s.execute(delete(ChunkRecord).where(ChunkRecord.document_id == DOC_ID))
                await s.execute(delete(DocumentRecord).where(DocumentRecord.id == DOC_ID))
                await s.execute(delete(UsageRecord).where(UsageRecord.tenant_id == TENANT))
    finally:
        await engine.dispose()


def _spawn_worker() -> subprocess.Popen:
    """拉起真 Celery worker（--pool=solo，06 §4 第 1 坑）。环境里钉假 embedding 端点。

    `-A scripts.kill9_celery_app`：复用生产 celery_app 与全部生产任务体，只把
    `visibility_timeout` 从默认 3600s 调到 60s——**否则 unacked 消息要等一小时才重投**
    （`acks_late` 只管"不提前 ack"，放回队列的是这个超时；首版脚本只等 180s 故必然卡死，
    而这条不变量恰恰是 #48 自己论证过的）。
    """
    env = dict(os.environ)
    env["DASHSCOPE_BASE_URL"] = FAKE_URL
    env["DASHSCOPE_API_KEY"] = "fake-key-for-kill9-experiment"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "scripts.kill9_celery_app", "worker", "--pool=solo", "-l", "info"],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _kill9(proc: subprocess.Popen) -> None:
    """Windows 无 SIGKILL：taskkill /F /T 是等价物（/T 连子进程一起，solo 形态本无子进程）。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()
    proc.wait(timeout=15)


def _calls_now() -> int:
    if not CALL_LOG.exists():
        return 0
    return sum(1 for line in CALL_LOG.read_text(encoding="utf-8").splitlines() if line.strip())


def _broker_state() -> tuple[int, int]:
    """(unacked 条数, celery 队列长度)——投递语义的直接观测面。"""
    import redis

    r = redis.from_url(get_settings().redis_url, decode_responses=True)
    try:
        return r.hlen("unacked"), r.llen("celery")
    finally:
        r.close()


def _restore_visible() -> int:
    """手动触发 kombu 的 unacked 恢复，返回回到队列的条数。

    这一步在 Linux 上由 `loop.call_repeatedly(10, cycle.maybe_restore_messages)` 自动做；
    Windows 无 event loop（celery `should_use_eventloop` 显式排除）故须手动替代——
    **被替代的只是"谁来定时调用"，超时判定与 restore 逻辑仍是生产实现**。
    """
    from scripts.kill9_celery_app import celery_app

    before = _broker_state()[1]
    with celery_app.connection_for_read() as conn:
        chan = conn.default_channel
        chan.qos.restore_visible(num=chan.unacked_restore_limit)
    return _broker_state()[1] - before


async def main() -> None:
    settings = get_settings()
    # 前置核查：假服务在不在（不在就别浪费一轮）
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            health = (await c.get(f"{FAKE_URL}/healthz")).json()
    except Exception as e:
        print(f"假 embedding 服务未启动（{FAKE_URL}）：{e!r}\n先在另一窗口跑：")
        print('  $env:FAKE_EMBED_DELAY_S="3"; uv run python scripts/fake_embedding_server.py')
        sys.exit(1)
    if float(health.get("delay_s", 0)) < 1:
        print(f"假服务延迟={health.get('delay_s')}s 太短，kill 窗口不可控。请以 FAKE_EMBED_DELAY_S=3 重启它。")
        sys.exit(1)

    await _cleanup()
    CALL_LOG.unlink(missing_ok=True)
    await _seed()
    say(f"== 摄取链路 kill -9 实录  document={DOC_ID} ==")
    say(f"假 embedding 端点 {FAKE_URL}（每批延迟 {health['delay_s']}s）；broker={settings.redis_url}")
    say(
        f"实验尺度：visibility_timeout={VISIBILITY_TIMEOUT_S}s（生产取 Redis transport 默认 3600s）"
        "——acks_late 只管不提前 ack，放回队列的是这个超时；调小仅为可观测，"
        "仍远大于本实验任务时长 ≈9s（#48 的下限论证）"
    )

    from celery import Celery

    producer = Celery("aegis-kill9-producer", broker=settings.redis_url)

    worker = _spawn_worker()
    say(f"worker 已拉起（pid={worker.pid}），等待就绪…")
    time.sleep(12)  # celery 启动 + broker 连接
    producer.send_task(INGEST_TASK_NAME, args=[DOC_ID, TENANT])
    say("任务已投递，等待第一批向量落库…")

    # 等到"已回填 ≥1 批但未全部完成"——这就是 kill 窗口
    deadline = time.time() + 90
    while time.time() < deadline:
        total, filled = await _chunk_counts()
        if total and 0 < filled < total:
            break
        time.sleep(1)
    total, filled_at_kill = await _chunk_counts()
    calls_before_kill = _calls_now()
    _kill9(worker)
    say(f"worker 已 kill -9（pid={worker.pid}）；此刻 总块={total} 已回填={filled_at_kill}")

    status, chunk_count = await _doc_status()
    a0 = status == IngestStatus.PROCESSING.value and 0 < filled_at_kill < total
    verdict0 = "PASS" if a0 else "FAIL"
    say(f"[断言0] 崩溃现场 PROCESSING 且部分回填（status={status} {filled_at_kill}/{total}）: {verdict0}")

    unacked_n, queued_n = _broker_state()
    a1 = unacked_n >= 1 and queued_n == 0
    verdict1 = "PASS" if a1 else "FAIL"
    say(f"[断言1] 消息未丢，仍在 unacked（unacked={unacked_n} 队列={queued_n}）: {verdict1}")

    # 等过 visibility_timeout 再触发 restore——超时判定与 restore 都是生产实现，
    # 手动替代的只有"谁来定时调用"（Windows 无 event loop，见模块 docstring）
    wait_s = VISIBILITY_TIMEOUT_S + 5
    say(f"等待 {wait_s}s 越过 visibility_timeout，然后手动触发 restore（Linux 由定时器代劳）…")
    time.sleep(wait_s)
    restored = _restore_visible()
    say(f"restore 已触发：回到队列 {restored} 条")

    say("重启 worker，等待重新消费…")
    worker2 = _spawn_worker()
    deadline = time.time() + 150
    done = False
    while time.time() < deadline:
        status, chunk_count = await _doc_status()
        if status == IngestStatus.DONE.value:
            done = True
            break
        time.sleep(2)
    if not done:
        say("⚠️ 等满 150s 仍未 DONE——检查是否有别的 worker 抢走了消息")
    calls_after = _calls_now()
    total2, filled2 = await _chunk_counts()
    ledger_rows = await _ledger_rows()
    _kill9(worker2)

    a2 = done and chunk_count == total2 == filled2 and total2 > 0 and calls_after > calls_before_kill
    verdict2 = "PASS" if a2 else "FAIL"
    calls2 = f"假服务调用 {calls_before_kill}→{calls_after} 批"
    detail2 = f"status={status} count={chunk_count} 块={total2} 回填={filled2} {calls2}"
    say(f"[断言2] restore 后重新消费至 DONE 且 chunk_count 正确（{detail2}）: {verdict2}")
    # 重复成本上界：重投至多让"崩溃当批"重做一次，故账本行数 ≤ 理论批数 + 1
    expected_batches = -(-total2 // EMBED_BATCH_SIZE)  # ceil(total/批大小)
    a3 = ledger_rows <= expected_batches + 1
    verdict3 = "PASS" if a3 else "FAIL"
    say(f"[断言3] 账本重复 ≤1 批（embedding 行={ledger_rows}，理论批数={expected_batches}）: {verdict3}")

    all_pass = a0 and a1 and a2 and a3
    if all_pass:
        say("== 结论：全部 PASS —— 消息不丢 + restore 后幂等消费收敛 ==")
        say(
            "== 未覆盖：定时器自动触发 restore（Windows 无 event loop，celery "
            "should_use_eventloop 显式排除本平台）——挂 M4.7 Linux 容器复验 =="
        )
    else:
        say("== 结论：存在 FAIL，见上 ==")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    print(f"\n凭证已落盘：{REPORT}")
    await _cleanup()
    CALL_LOG.unlink(missing_ok=True)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":  # M4.7：补守卫——Linux 复验脚本 importlib 复用本件的种子/断言/清理件
    asyncio.run(main())
