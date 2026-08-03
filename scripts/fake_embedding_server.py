"""确定性假 embedding 服务（M4.0④b 支撑件，#48 kill -9 实录用）。

**存在理由**：#48 要验的是"acks_late 让消息被重投、幂等消费收敛"这条**投递语义**，
不是向量质量——但要跑生产任务体（`ingest_document` → `_ingest_fresh` → `ingest_once`）
就必须有个 `/embeddings` 端点应答。M4 真实调用口径（00 §8.0）只允许 M4.4/M4.6 花钱，
故本服务顶替上游：`DASHSCOPE_BASE_URL` 指向它即可，**生产代码一字不改**
（`build_embedding_client` 读的就是这个配置项，factory.py:87）。

协议面按 `EmbeddingClient._post_once`（embeddings.py:105-145）逐条对齐：
- 请求 `{model, input, dimensions, encoding_format}`；
- 响应 `data[]` 每项含 `index` 与 `embedding`，**长度必须等于请求条数、维度必须等于
  dimensions**——三重形状校验是 fail-loud 的，糊弄不过去；
- `usage.total_tokens` 供计量记账（账本重复行断言的分母）。

慢速开关 `FAKE_EMBED_DELAY_S`：给 kill -9 留窗口。计数落 `reports/fake_embed_calls.jsonl`
（**跨进程可见**——worker 被 kill 后重启，重投是否发生要靠这份账来证）。

跑法（另开窗口，仓库根）：
    uv run python scripts/fake_embedding_server.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402

CALL_LOG = REPO_ROOT / "reports" / "fake_embed_calls.jsonl"
"""每批一行：跨进程账本——worker 被 kill 再重启后，这份账是"消息被重投"的物证。"""

PORT = int(os.environ.get("FAKE_EMBED_PORT", "8799"))
DELAY_S = float(os.environ.get("FAKE_EMBED_DELAY_S", "0"))


def _vector(text: str, dims: int) -> list[float]:
    """确定性伪向量：同文本恒得同向量（可重放），值域 [-1,1]，与真 embedding 无关。"""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = (digest * (dims // len(digest) + 1))[:dims]
    return [(b - 128) / 128.0 for b in raw]


app = FastAPI(title="fake-embeddings")


@app.post("/embeddings")
async def embeddings(body: dict[str, Any]) -> dict[str, Any]:
    batch: list[str] = list(body.get("input") or [])
    dims = int(body.get("dimensions") or 1024)
    CALL_LOG.parent.mkdir(exist_ok=True)
    with CALL_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "n": len(batch), "texts": [t[:24] for t in batch]}) + "\n")
    if DELAY_S:
        time.sleep(DELAY_S)  # 同步 sleep：确保这一批真的卡住，kill 窗口可控
    return {
        "data": [{"index": i, "embedding": _vector(t, dims), "object": "embedding"} for i, t in enumerate(batch)],
        "model": body.get("model", "text-embedding-v4"),
        "usage": {"total_tokens": sum(len(t) for t in batch), "prompt_tokens": sum(len(t) for t in batch)},
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "delay_s": str(DELAY_S)}


if __name__ == "__main__":
    print(f"假 embedding 服务：http://127.0.0.1:{PORT}  延迟 {DELAY_S}s  账本 {CALL_LOG}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
