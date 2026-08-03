"""M4.4②：runner 逻辑测试（零真实调用——judge 与被评执行全部桩注入）。

被测面=run_batch/machine_verdict/judge_case（scripts/run_eval.py，importlib 装载）；
桩 gateway 用真 schema 类型（TextDelta/UsageChunk）构造流，判别路径与生产同形。
"""

from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from aegis.gateway.schema import LLMRequest, StopChunk, TextDelta, UsageChunk

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _runner() -> ModuleType:
    """importlib 装载 runner（先注册再执行——模块含 dataclass × future-annotations）。"""
    spec = importlib.util.spec_from_file_location("run_eval_for_tests", ROOT / "scripts" / "run_eval.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _StubJudge:
    """judge 网关桩（GatewayLike 形状）：可编程回复文本；记调用数与收到的请求。"""

    def __init__(self, reply: str = '{"score": 5, "reasons": "好"}', model: str = "stub-judge") -> None:
        self.reply = reply
        self.model = model
        self.calls = 0
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest):
        self.calls += 1
        self.requests.append(req)

        async def _gen():
            yield TextDelta(text=self.reply)
            yield UsageChunk(model=self.model, prompt_tokens=100, completion_tokens=20)
            yield StopChunk(reason="end_turn")

        return _gen()


def _case(case_id: str, category: str, expectation: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case_id,
        "tenant_id": "t-ev",
        "user_id": "u-ev",
        "category": category,
        "question": "测试问题",
        "expectation": expectation,
    }


def _outcome(mod: ModuleType, **kw: Any) -> Any:
    return mod.CaseOutcome(**kw)


async def test_budget_cap_aborts_batch() -> None:
    """预算中止：首用例耗尽预算 → 剩余用例不执行、已完成行保留、批次标 partial。"""
    mod = _runner()
    judge = _StubJudge()
    executed: list[str] = []

    async def execute(case: dict[str, Any]) -> Any:
        executed.append(case["id"])
        # answered 但 must_contain 不满足 → 机器 fail（零 judge），预算只记被评消耗
        return _outcome(mod, answer="与期望无关的回答", prompt_tokens=80, completion_tokens=40)

    cases = [
        _case("e2e-b1", "e2e", {"kind": "normal", "behavior": "answered", "must_contain": ["特定锚点"]}),
        _case("e2e-b2", "e2e", {"kind": "normal", "behavior": "answered", "must_contain": ["特定锚点"]}),
    ]
    report = await mod.run_batch(
        cases, execute=execute, judge_gateway=judge, token_budget=100, fallback_signals=("没有找到",)
    )
    assert executed == ["e2e-b1"]  # 第二用例没跑：循环头预算检查 120 ≥ 100
    assert [r.case_id for r in report.rows] == ["e2e-b1"]  # 已完成行保留
    assert report.partial is True
    assert judge.calls == 0


async def test_hard_assert_fail_skips_judge() -> None:
    """硬断言 fail 不花 judge 的钱（§4-3）：must_not_contain 命中 → fail 且零 judge 调用。"""
    mod = _runner()
    judge = _StubJudge()

    async def execute(case: dict[str, Any]) -> Any:
        return _outcome(mod, answer="回答里出现了禁词内容", prompt_tokens=10, completion_tokens=5)

    cases = [_case("adv-h1", "adversarial", {"kind": "isolation", "behavior": "no_leak", "must_not_contain": ["禁词"]})]
    report = await mod.run_batch(
        cases, execute=execute, judge_gateway=judge, token_budget=10_000, fallback_signals=("没有找到",)
    )
    assert report.rows[0].verdict == "fail"
    assert judge.calls == 0


async def test_judge_model_recorded_from_usage_chunk() -> None:
    """C36：judge_model 记 UsageChunk 回显名（strong 链含 fallback，中途换模留痕的机器面）。"""
    mod = _runner()
    judge = _StubJudge(model="stub-judge-v2")

    async def execute(case: dict[str, Any]) -> Any:
        return _outcome(mod, answer="锚在场的正确回答", prompt_tokens=10, completion_tokens=5)

    cases = [_case("e2e-j1", "e2e", {"kind": "normal", "behavior": "answered", "must_contain": ["锚"]})]
    report = await mod.run_batch(
        cases, execute=execute, judge_gateway=judge, token_budget=10_000, fallback_signals=("没有找到",)
    )
    row = report.rows[0]
    assert judge.calls == 1
    assert row.judge_model == "stub-judge-v2"
    assert row.verdict == "pass" and row.score == 5  # ≥4 = pass（rubrics §2）
    assert row.prompt_tokens == 110 and row.completion_tokens == 25  # 被评+judge 合计入行


async def test_e2e_fallback_tripwire_miss_goes_to_judge() -> None:
    """M4.5③ 架构归位：e2e 的 fallback 绊线不中 → 交 judge 终裁而非机器硬 fail
    （绊线只管召回——okb-05 合规措辞变体三轮漏报的结构性了断）；
    adversarial 同形态保持机器 fail（判定不依赖 judge，安全面宁严）。"""
    mod = _runner()
    judge = _StubJudge()  # 缺省 score=5

    async def execute(case: dict[str, Any]) -> Any:
        return _outcome(mod, answer="这方面的动态我不掌握，请以官方渠道为准", prompt_tokens=10, completion_tokens=5)

    e2e = [_case("okb-x1", "e2e", {"kind": "out_of_kb", "behavior": "fallback_or_handoff"})]
    report = await mod.run_batch(
        e2e, execute=execute, judge_gateway=judge, token_budget=10_000, fallback_signals=("没有找到",)
    )
    assert judge.calls == 1  # 绊线不中：进 judge 终裁
    assert report.rows[0].verdict == "pass" and report.rows[0].score == 5

    adv = [_case("iso-x1", "adversarial", {"kind": "isolation", "behavior": "fallback_or_handoff"})]
    report2 = await mod.run_batch(
        adv, execute=execute, judge_gateway=judge, token_budget=10_000, fallback_signals=("没有找到",)
    )
    assert judge.calls == 1  # adversarial 不进 judge：机器 fail 判定权不外放
    assert report2.rows[0].verdict == "fail"


async def test_judge_bad_json_yields_error_verdict() -> None:
    """judge 输出非 JSON → verdict=error 不算 fail（异常不许伪装成质量信号）。"""
    mod = _runner()
    judge = _StubJudge(reply="我觉得回答挺好的（不是 JSON）")

    async def execute(case: dict[str, Any]) -> Any:
        return _outcome(mod, answer="锚在场的正确回答", prompt_tokens=10, completion_tokens=5)

    cases = [_case("e2e-e1", "e2e", {"kind": "normal", "behavior": "answered", "must_contain": ["锚"]})]
    report = await mod.run_batch(
        cases, execute=execute, judge_gateway=judge, token_budget=10_000, fallback_signals=("没有找到",)
    )
    row = report.rows[0]
    assert row.verdict == "error"
    assert row.score is None
    assert "raw" in (row.judge_output or {})
