"""#48 Linux 复验（M4.7-E，00 §10.1 #26 追加验收义务）：unacked 由 kombu 定时器**自动** restore。

本地 Windows 实录（M4.0④b）已证一半：消息不丢 ✅，但 celery `should_use_eventloop`
显式排除 Windows → 恒走 synloop 无 hub → `loop.call_repeatedly(10, maybe_restore_messages)`
从不注册 → **永不自动重投**（须手动 restore_visible）。补丁一的"至少一次"因此在本地
只兑现一半——本脚本在**容器 Linux（prefork/asynloop）**里补上另一半的凭证。

形态=#26 原文"复用 experiment_kill9_ingest.py 但去掉手动 restore 那一步"：
种子/状态/账本/broker/清理件全部 importlib 复用原脚本（DOC_ID 装载时新铸）；
worker 换成 aegis-app 镜像容器（scripts/ 只读卷挂载跑 scripts.kill9_celery_app，
visibility_timeout=60s 实验尺度同款）；kill -9 = `docker kill -s KILL`（SIGKILL 全进程树）。

四断言：①崩溃现场=PROCESSING+部分回填；②消息不丢仍在 unacked；
③**零人工干预**——越过 visibility_timeout 后 kombu 定时器自动重投、重新消费至 DONE
且 chunk_count 正确（本脚本从头到尾不调 restore_visible）；④账本重复 ≤1 批。
凭证：reports/m4_kill9_ingest_linux.txt。

前置（仓库根执行）：aegis-app 镜像已构建（deploy compose up --build）、PG/Redis 容器在跑、
零真实调用（假 embedding 服务顶替上游，DASHSCOPE_BASE_URL 指向宿主 host.docker.internal）。
脚本自己会：停 compose worker/beat（防生产 worker 抢走消息）→ 起假服务与 kill9 容器 →
实验 → 清理并恢复 worker/beat。
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

REPORT = REPO_ROOT / "reports" / "m4_kill9_ingest_linux.txt"
COMPOSE = ["docker", "compose", "-f", str(REPO_ROOT / "deploy" / "docker-compose.yml")]
KILL9_CONTAINER = "aegis-kill9-worker"
FAKE_PORT = int(os.environ.get("FAKE_EMBED_PORT", "8799"))
LINES: list[str] = []


def say(line: str) -> None:
    print(line)
    LINES.append(line)


def _load_base() -> ModuleType:
    """importlib 装载原实验脚本（I1：断言件单一事实源；装载即新铸 DOC_ID）。"""
    spec = importlib.util.spec_from_file_location(
        "kill9_base_for_linux", REPO_ROOT / "scripts" / "experiment_kill9_ingest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def _spawn_fake_server() -> subprocess.Popen[bytes]:
    env = dict(os.environ)
    env["FAKE_EMBED_DELAY_S"] = "3"  # 每批 3s：给 kill 留窗口（原实录同参）
    env["PYTHONUTF8"] = "1"
    return subprocess.Popen(
        [sys.executable, str(REPO_ROOT / "scripts" / "fake_embedding_server.py")],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _start_kill9_container() -> None:
    _docker("rm", "-f", KILL9_CONTAINER)
    run = _docker(
        "run",
        "-d",
        "--name",
        KILL9_CONTAINER,
        "--network",
        "aegis_default",
        "--add-host",
        "host.docker.internal:host-gateway",  # Linux 引擎兜底；Docker Desktop 本就内置
        "-v",
        f"{REPO_ROOT}\\scripts:/app/scripts:ro",
        "-e",
        "DATABASE_URL=postgresql+asyncpg://aegis:aegis@postgres:5432/aegis",
        "-e",
        "DATABASE_URL_APP=postgresql+asyncpg://aegis_app:aegis_app@postgres:5432/aegis",
        "-e",
        "REDIS_URL=redis://redis:6379/0",
        "-e",
        f"DASHSCOPE_BASE_URL=http://host.docker.internal:{FAKE_PORT}",
        "-e",
        "DASHSCOPE_API_KEY=fake-key-for-kill9-linux",
        "aegis-app:latest",
        "celery",
        "-A",
        "scripts.kill9_celery_app",
        "worker",
        "-l",
        "info",
    )
    if run.returncode != 0:
        raise SystemExit(f"kill9 容器启动失败：{run.stderr.strip()}")


async def main() -> None:
    base = _load_base()
    say(f"# M4.7 #48 Linux 复验（{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%SZ')}）")
    say(f"文档 {base.DOC_ID}；visibility_timeout=60s（实验尺度，生产默认 3600s——口径随数字走）")

    say("[0] 停 compose worker/beat（防生产 worker 抢走实验消息；结束后恢复）")
    subprocess.run([*COMPOSE, "stop", "worker", "beat"], capture_output=True)
    if base.CALL_LOG.exists():
        base.CALL_LOG.unlink()  # 假服务调用账从零起算
    fake = _spawn_fake_server()
    try:
        for _ in range(50):
            try:
                httpx.get(f"http://127.0.0.1:{FAKE_PORT}/", timeout=1.0)
                break
            except Exception:
                await asyncio.sleep(0.2)
        await base._cleanup()
        await base._seed()
        say("[1] 种子就绪；启动容器 worker（Linux prefork——asynloop 世界）")
        _start_kill9_container()
        await asyncio.sleep(6)  # 容器 celery 就绪窗

        from scripts.kill9_celery_app import celery_app

        celery_app.send_task(base.INGEST_TASK_NAME, args=[base.DOC_ID, base.TENANT])
        say("[2] 任务已投递，等首批打到假服务后 kill -9")
        deadline = time.monotonic() + 90
        while base._calls_now() < 2 and time.monotonic() < deadline:
            await asyncio.sleep(0.5)
        if base._calls_now() < 2:
            raise SystemExit("首两批未到达假服务——容器 worker 没在干活，实验中止")
        _docker("kill", "-s", "KILL", KILL9_CONTAINER)
        status, _ = await base._doc_status()
        total, filled = await base._chunk_counts()
        say(f"[3] 崩溃现场：status={status} 块 {filled}/{total} 已回填（断言①=PROCESSING+部分回填）")
        assert status == "processing" and 0 < filled < total, "断言① 失败：kill 未落在中段"
        unacked, queued = base._broker_state()
        say(f"[4] broker：unacked={unacked} queued={queued}（断言②=消息不丢仍在 unacked）")
        assert unacked >= 1, "断言② 失败：unacked 为空——消息丢了"

        say("[5] 重启容器 worker，**全程零人工 restore**——等 kombu 定时器自动重投")
        _docker("start", KILL9_CONTAINER)
        t0 = time.monotonic()
        done_status = ""
        chunk_count = None
        while time.monotonic() - t0 < 240:
            done_status, chunk_count = await base._doc_status()
            if done_status == "done":
                break
            await asyncio.sleep(5)
        elapsed = time.monotonic() - t0
        assert done_status == "done", f"断言③ 失败：{int(elapsed)}s 内未自动恢复至 DONE（自动重投没发生）"
        total2, filled2 = await base._chunk_counts()
        assert chunk_count == total2 == filled2, "断言③ 失败：chunk_count 与回填数不一致"
        say(f"[6] 断言③ PASS：重启后 {int(elapsed)}s 自动恢复至 DONE（{filled2}/{total2} 块；未调 restore_visible）")
        unacked2, queued2 = base._broker_state()
        say(f"    收尾 broker：unacked={unacked2} queued={queued2}")

        ledger = await base._ledger_rows()
        batches = (total2 + base.EMBED_BATCH_SIZE - 1) // base.EMBED_BATCH_SIZE
        say(f"[7] 账本 embedding 行={ledger}，理论批数={batches}（断言④=重复 ≤1 批）")
        assert ledger <= batches + 1, "断言④ 失败：重复计费超过 1 批上界"
        say("四断言全 PASS——Windows 实录缺的那一环（定时器自动 restore）在 Linux 容器世界闭合。")
    finally:
        _docker("rm", "-f", KILL9_CONTAINER)
        fake.kill()
        await base._cleanup()
        subprocess.run([*COMPOSE, "start", "worker", "beat"], capture_output=True)
        say("[8] 清理完成：kill9 容器已删、假服务已停、实验数据已清、compose worker/beat 已恢复")
    REPORT.write_text("\n".join(LINES) + "\n", encoding="utf-8", newline="\n")
    print(f"凭证落盘：{REPORT}")


if __name__ == "__main__":
    asyncio.run(main())
