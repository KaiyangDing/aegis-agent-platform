"""签发演示 token（P7 拍板：v1 无登录端点，本脚本即凭证发放口）。

角色与租户从 users 表读（先跑 seed_demo），TTL 按角色取 user/staff 档。
在仓库根执行（.env 相对 cwd 加载，需含 JWT_SECRET）：

    uv run python scripts/mint_token.py u-a1
"""

import asyncio
import sys

from aegis.api.auth import issue_token
from aegis.core.config import get_settings
from aegis.core.db import get_session_factory
from aegis.core.tenancy import Role, TenantDirectory


async def main(user_id: str) -> None:
    settings = get_settings()
    user = await TenantDirectory(get_session_factory()).get_user(user_id)
    if user is None:
        raise SystemExit(f"用户 {user_id} 不存在——先跑 uv run python scripts/seed_demo.py")
    role = Role(user.role)
    ttl_s = settings.jwt_user_ttl_s if role is Role.USER else settings.jwt_staff_ttl_s
    token = issue_token(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=role,
        ttl_s=ttl_s,
        secret=settings.jwt_secret.get_secret_value(),
    )
    print(token)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("用法：uv run python scripts/mint_token.py <user_id>（种子用户如 u-a1/op-a1/admin-a1）")
    asyncio.run(main(sys.argv[1]))
