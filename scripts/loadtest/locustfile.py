"""locust SSE 虚拟用户（M5.1 交付②；口径与指标定义在此，报告照抄）。

指标口径：**TTFT = POST 发出到首个 token 帧**（事件名 chat_first_token）；
**平台开销 = TTFT − 800ms**（LatencyModelProvider 注入的固定首 token 延迟——口径①专用）；
错误三类分开计数：HTTP 非 200（chat_http_error）/ error 帧（chat_error_frame）/
done 前断流（chat_truncated）。总耗时事件 chat_total。

纪律（plans/m5 D3-D7）：不 import aegis（gevent monkey-patch 与 asyncio 互相污染 T2）；
`iter_content` 喂纯函数解析器、绝不 `iter_lines`（T3）；每虚拟用户一个会话、串行发消息
（同会话并发第二条会 409——会话互斥）；prompt 带 uuid 唯一化+压测环境关缓存（T4 双保险）；
`test_start` 后 30s `stats.reset_all()`=预热后稳态计窗（D6，复盘补丁二口径）。

用法（M5.2 交付②；容器全栈 + nginx 之后）：
    $env:AEGIS_LOADTEST_TOKEN = (uv run python scripts/mint_token.py u-a1 | Select-Object -Last 1)
    uv run locust -f scripts/loadtest/locustfile.py --headless -u <档位> -r 5 -t 120s -H http://127.0.0.1:8080
"""

from __future__ import annotations

import json
import os
import time
from uuid import uuid4

import gevent
from locust import HttpUser, between, events, task
from locust.env import Environment

from scripts.loadtest.sse_client import iter_sse_frames

WARMUP_S = 30.0
"""预热窗（D6）：首 30s 含冷启动/连接池预热/故障检测延迟，reset 后才是稳态计窗。"""

FIRST_TOKEN_BASELINE_MS = 800.0
"""口径①的注入首 token 延迟（LatencyModelProvider first_token_s=0.8）——平台开销的减数。"""


@events.test_start.add_listener
def _arm_steady_state_window(environment: Environment, **kwargs: object) -> None:
    def _reset() -> None:
        gevent.sleep(WARMUP_S)
        if environment.runner is not None:
            environment.runner.stats.reset_all()
            print(f"[稳态窗] {WARMUP_S}s 预热段已剔除，统计从此刻起算（D6）")

    gevent.spawn(_reset)


class AegisChatUser(HttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self) -> None:
        token = os.environ.get("AEGIS_LOADTEST_TOKEN", "")
        if not token:
            raise RuntimeError("缺 AEGIS_LOADTEST_TOKEN——先用 scripts/mint_token.py 签发（§0-5）")
        self._headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._session_id = f"lt-{uuid4().hex[:12]}"  # D5：每虚拟用户一个会话，串行发消息

    @task
    def chat_turn(self) -> None:
        prompt = f"压测探针 {uuid4().hex}，请简短回复。"  # D5：唯一化防缓存命中
        t0 = time.perf_counter()
        first_token_ms: float | None = None
        saw_done = False
        saw_error_frame = False
        with self.client.post(
            "/v1/chat",
            data=json.dumps({"session_id": self._session_id, "message": prompt}),
            headers=self._headers,
            stream=True,
            name="chat",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                self._fire("chat_http_error", t0, RuntimeError(f"HTTP {resp.status_code}"))
                resp.failure(f"HTTP {resp.status_code}")
                return
            for frame in iter_sse_frames(resp.iter_content(chunk_size=1024)):  # T3：绝不 iter_lines
                if frame.event == "token" and first_token_ms is None:
                    first_token_ms = (time.perf_counter() - t0) * 1000
                    self._fire("chat_first_token", t0, None, response_time_ms=first_token_ms)
                elif frame.event == "error":
                    saw_error_frame = True
                elif frame.event == "done":
                    saw_done = True
                    break
            total_ms = (time.perf_counter() - t0) * 1000
            if saw_error_frame:
                self._fire("chat_error_frame", t0, RuntimeError("error 帧"), response_time_ms=total_ms)
                resp.failure("error 帧")
            elif not saw_done:
                self._fire("chat_truncated", t0, RuntimeError("done 前断流"), response_time_ms=total_ms)
                resp.failure("done 前断流")
            else:
                self._fire("chat_total", t0, None, response_time_ms=total_ms)
                resp.success()

    def _fire(self, name: str, t0: float, exc: Exception | None, *, response_time_ms: float | None = None) -> None:
        # locust 2.46 统一事件签名（T1：落笔前已 Read event.py 核实字段名）
        self.environment.events.request.fire(
            request_type="SSE",
            name=name,
            response_time=response_time_ms if response_time_ms is not None else (time.perf_counter() - t0) * 1000,
            response_length=0,
            exception=exc,
            context={},
            response=None,
        )
