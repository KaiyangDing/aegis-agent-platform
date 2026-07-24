"""演示数据种子（M3.1 起步版：tenants/users；M3.11 扩全——订单/语料/摄取触发）。

种子即初始化入口（00 §10.1 #21 / D12 拍板）：tenants.config 运行期只读，
变更 = 改本脚本重跑。upsert 语义：跑两遍不重复不报错（M3.11 有幂等测试）。
在仓库根执行（.env 相对 cwd 加载——08 §9.1 运行前提）：

    uv run python scripts/seed_demo.py
"""

import asyncio
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from aegis.core.db import get_session_factory
from aegis.core.tenancy import Role, TenantRecord, UserRecord

# 01 §5 两租户设定；approval_threshold=200 是租户 A 的配置项不是平台常量。
# token_budget_monthly=2_000_000：M3 开发调试走真实调用的月度兜底（plans/m3-detailed §3.1）。
# tenant-b 的 coupon_threshold 等键随 M3.7/M3.11 定值后补。
TENANTS: list[dict[str, Any]] = [
    {
        "id": "tenant-a",
        "name": "云杉数码商城",
        "config": {"approval_threshold": 200},
        "token_budget_monthly": 2_000_000,
    },
    {
        "id": "tenant-b",
        "name": "云杉生鲜超市",
        "config": {},
        "token_budget_monthly": 2_000_000,
    },
]

# 每租户 user×2（跨用户订单对抗需要两个）+ operator×1 + admin×1（02 §7.1 三档）
USERS: list[dict[str, Any]] = []
for t in ("a", "b"):
    USERS += [
        {"id": f"u-{t}1", "tenant_id": f"tenant-{t}", "role": Role.USER.value, "display_name": "演示用户一"},
        {"id": f"u-{t}2", "tenant_id": f"tenant-{t}", "role": Role.USER.value, "display_name": "演示用户二"},
        {"id": f"op-{t}1", "tenant_id": f"tenant-{t}", "role": Role.OPERATOR.value, "display_name": "演示坐席"},
        {"id": f"admin-{t}1", "tenant_id": f"tenant-{t}", "role": Role.ADMIN.value, "display_name": "演示管理员"},
    ]


async def main() -> None:
    async with get_session_factory()() as s:
        async with s.begin():
            for row in TENANTS:
                stmt = insert(TenantRecord).values(**row)
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[TenantRecord.id],
                        set_={
                            "name": stmt.excluded.name,
                            "config": stmt.excluded.config,
                            "token_budget_monthly": stmt.excluded.token_budget_monthly,
                        },
                    )
                )
            for row in USERS:
                stmt = insert(UserRecord).values(**row)
                await s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[UserRecord.id],
                        set_={
                            "tenant_id": stmt.excluded.tenant_id,
                            "role": stmt.excluded.role,
                            "display_name": stmt.excluded.display_name,
                        },
                    )
                )
    print(f"种子完成：tenants={len(TENANTS)} users={len(USERS)}（upsert，可重复执行）")


if __name__ == "__main__":
    asyncio.run(main())
