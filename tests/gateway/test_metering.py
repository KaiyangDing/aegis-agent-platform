from decimal import Decimal

from sqlalchemy import select

from aegis.gateway.metering import MeteringRecorder, PriceTable, UsageRecord, compute_cost
from aegis.gateway.schema import LLMRequest, Message, UsageChunk


def make_record(request_id: str) -> UsageRecord:
    return UsageRecord(
        request_id=request_id,
        tenant_id="t1",
        tier="fast",
        provider="bailian",
        model="qwen-flash",
        prompt_tokens=10,
        completion_tokens=5,
        cached=False,
        cost=Decimal("0.000123"),
    )


async def test_usage_record_roundtrip(db_session):
    rec = make_record("req-roundtrip")
    db_session.add(rec)
    await db_session.flush()  # 发 INSERT 拿自增 id，但不 commit（夹具最终会回滚）
    await db_session.refresh(rec)  # 回读服务端填充的列（created_at 是数据库的钟给的）
    assert rec.id is not None
    assert rec.created_at is not None
    got = (
        await db_session.execute(
            select(UsageRecord).where(UsageRecord.request_id == "req-roundtrip")
        )
    ).scalar_one()
    assert got.cost == Decimal("0.000123")  # Decimal 无损往返——用 float 这里会开始出鬼


async def test_rollback_isolation_first(db_session):
    # 与下一个测试插入完全相同的 request_id：两个都过 = 回滚夹具真的在工作
    db_session.add(make_record("iso-proof"))
    await db_session.flush()


async def test_rollback_isolation_second(db_session):
    db_session.add(make_record("iso-proof"))
    await db_session.flush()


PRICES: PriceTable = {"qwen-flash": (Decimal("0.00015"), Decimal("0.0015"))}


def test_compute_cost_known_model():
    cost = compute_cost("qwen-flash", 1000, 2000, cached=False, prices=PRICES)
    assert cost == Decimal("0.00315")  # 1k×0.00015 + 2k×0.0015


def test_compute_cost_cached_is_free():
    assert compute_cost("qwen-flash", 1000, 2000, cached=True, prices=PRICES) == Decimal("0")


def test_compute_cost_unknown_model_zero_but_loud(caplog):
    cost = compute_cost("gpt-999", 1000, 1000, cached=False, prices=PRICES)
    assert cost == Decimal("0")
    assert "价目表" in caplog.text  # 静默记零是财务事故，必须喊


def make_req(**kw) -> LLMRequest:
    kw.setdefault("tier", "fast")
    kw.setdefault("tenant_id", "t-meter")
    return LLMRequest(messages=[Message(role="user", content="x")], **kw)


async def test_recorder_writes_priced_row(db_session_factory):
    rec = MeteringRecorder(db_session_factory, PRICES)
    req = make_req(session_id="s1")
    await rec.record(
        req, "bailian", UsageChunk(model="qwen-flash", prompt_tokens=1000, completion_tokens=2000)
    )
    async with db_session_factory() as s:
        from sqlalchemy import select

        row = (
            await s.execute(select(UsageRecord).where(UsageRecord.request_id == req.request_id))
        ).scalar_one()
    assert row.cost == Decimal("0.00315")
    assert (row.provider, row.tier, row.session_id) == ("bailian", "fast", "s1")


async def test_recorder_cached_row_costs_zero(db_session_factory):
    rec = MeteringRecorder(db_session_factory, PRICES)
    req = make_req()
    await rec.record(
        req,
        "cache",
        UsageChunk(model="qwen-flash", prompt_tokens=1000, completion_tokens=2000, cached=True),
    )
    async with db_session_factory() as s:
        from sqlalchemy import select

        row = (
            await s.execute(select(UsageRecord).where(UsageRecord.request_id == req.request_id))
        ).scalar_one()
    assert row.cost == Decimal("0")
    assert row.cached is True


async def test_month_spend_counts_only_real_calls_of_this_tenant(db_session_factory):
    rec = MeteringRecorder(db_session_factory, PRICES)
    await rec.record(
        make_req(tenant_id="t-x"),
        "bailian",
        UsageChunk(model="qwen-flash", prompt_tokens=1000, completion_tokens=2000),
    )
    await rec.record(  # 缓存回放：不计入预算
        make_req(tenant_id="t-x"),
        "cache",
        UsageChunk(model="qwen-flash", prompt_tokens=500, completion_tokens=500, cached=True),
    )
    await rec.record(  # 别的租户：不计入
        make_req(tenant_id="t-y"),
        "bailian",
        UsageChunk(model="qwen-flash", prompt_tokens=9000, completion_tokens=0),
    )
    assert await rec.month_spend("t-x") == 3000
