from decimal import Decimal

from sqlalchemy import select

from aegis.gateway.metering import UsageRecord


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
