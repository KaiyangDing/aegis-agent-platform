"""成本对照实验共享底座（M4.6 交付①；00 §8.1 M4.6 行）。

三件事集中一处，两实验脚本与 lint 测试同源消费（I1 单一事实源，样式沿 seed_demo）：
1) 实验数据面常量——exp-route / exp-cache 两租户的 tenants/users/orders 种子形状。
   拍板 P3：每实验一个租户、组间按精确 sid 清单分账（M4.4④ LIKE 跨批撞账后的对账正解）；
   弃「每组一租户」的实锚=mock_orders.id 是全局主键（models.py:38，无租户维度），
   跨租户克隆同号必撞 PK，三组题面将被迫发散。
   拍板 P6：工具面只读——tools 只点名 order_query/logistics_query，写工具物理不在场
   （写操作会挂审批混入 HITL、且改变环境状态破坏组间可比性与复述命中确定性）。
2) 题库装载 load_questions()——evals/cost_questions.json 双节（routing 80 / cache 唯一池 140），
   双节零交集、与评测集零交集由 tests/obs/test_cost_traffic.py 钉死。
3) 缓存流量生成器 build_cache_traffic()——纯函数、固定种子，流量可精确重放（计划 §4）。

订单号前缀 EXPR-/EXPC- 避开种子段（AZ-/BF-）、演示自清理段（mo-demo-*）与
M2.11 cassette 埋点（AZ-20260701-0042）。数据面是 tenant-a 的镜像：同名、同 faq
digest、语料同源 data/corpus/tenant-a（摄取归实验脚本种子步）——组间唯一变量是档位。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "evals" / "cost_questions.json"
EXP_CORPUS_DIR = ROOT / "data" / "corpus" / "tenant-a"

ROUTE_TENANT_ID = "exp-route"
CACHE_TENANT_ID = "exp-cache"
ROUTE_USER_ID = "u-expr-1"
CACHE_USER_ID = "u-expc-1"

# tenant-a config 的镜像面：faq digest 逐字节同源（FAQ 直答行为一致）；
# tools 只读两件=P6；token_budget_monthly=0（#22：≤0 闸门关闭，不白查账本）
# ——预算闸不设限是 §3 控制变量，防 BudgetExceeded 混入实验结果。
_EXP_FAQ = (
    "云杉数码商城常见问题：营业时间 9:00-18:00（周一至周日）；"
    "客服热线 400-800-1234；支持 7 天无理由退货（详情请查询退货政策）。"
)
_EXP_CONFIG: dict[str, Any] = {
    "approval_ttl_s": 3600,
    "tools": ["order_query", "logistics_query"],
    "faq": _EXP_FAQ,
}

EXP_TENANTS: list[dict[str, Any]] = [
    {"id": ROUTE_TENANT_ID, "name": "云杉数码商城", "config": _EXP_CONFIG, "token_budget_monthly": 0},
    {"id": CACHE_TENANT_ID, "name": "云杉数码商城", "config": _EXP_CONFIG, "token_budget_monthly": 0},
]

EXP_USERS: list[dict[str, Any]] = [
    {"id": ROUTE_USER_ID, "tenant_id": ROUTE_TENANT_ID, "role": "user", "display_name": "成本实验用户"},
    {"id": CACHE_USER_ID, "tenant_id": CACHE_TENANT_ID, "role": "user", "display_name": "成本实验用户"},
]


def _orders(tenant_id: str, user_id: str, prefix: str, count: int) -> list[dict[str, Any]]:
    """只读订单批量构造：状态在 paid/shipped/delivered 轮转（物流轨迹是状态的确定性派生，
    app.py _TRACKS——refunded 刻意不出现在实验面：它是写路径的产物）。"""
    statuses = ("paid", "shipped", "delivered")
    skus = ("灵犀降噪耳机 Pro", "R68 Pro", "Type-C 快充数据线", "桌面收纳支架")
    rows: list[dict[str, Any]] = []
    for i in range(count):
        rows.append(
            {
                "id": f"{prefix}-{1001 + i}",
                "tenant_id": tenant_id,
                "user_id": user_id,
                "status": statuses[i % len(statuses)],
                "paid_amount": f"{59 + i * 40}.00",
                "items": {"sku": skus[i % len(skus)], "qty": 1 + i % 2},
            }
        )
    return rows


EXP_ORDERS: list[dict[str, Any]] = _orders(ROUTE_TENANT_ID, ROUTE_USER_ID, "EXPR", 8) + _orders(
    CACHE_TENANT_ID, CACHE_USER_ID, "EXPC", 14
)


def load_questions() -> dict[str, list[dict[str, str]]]:
    """题库整档装载：双节缺一即炸（脚本消费面 fail-loud；细则校验归 lint 测试）。"""
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    if set(data) != {"routing", "cache"}:
        raise ValueError(f"cost_questions.json 顶层键须为 routing/cache，得到 {sorted(data)}")
    return data


def question_strings(section: str) -> list[str]:
    """某节的问题字面序列（保文件序——routing 三组同序驱动、cache 作唯一池）。"""
    return [row["question"] for row in load_questions()[section]]


def build_cache_traffic(questions: list[str], *, replay_ratio: float = 0.3, seed: int = 42) -> list[str]:
    """把唯一问题池扩成含历史复述的模拟流量（计划 §4 签名）。

    构造保证（tests/obs/test_cost_traffic.py 逐条钉）：
    - 总长 = round(唯一数 / (1 - replay_ratio))：140 条 @0.3 → 恰 200；
    - 复述条数 = 总长 - 唯一数（@0.3 恰 60）——分布假设精确成立，不是近似；
    - 复述槽位随机散布（首位恒唯一），每个复述从已流出前缀均匀重抽——
      同一问题可被复述多次（真实流量亦然）；
    - random.Random(seed) 全程独占：同 seed 逐条相等，流量可精确重放。
    复述必须逐字节同串（缓存 key 只哈希语义本体，cache.py:38-42）——从前缀
    原样取值，绝不改写标点（计划 §7 陷阱 1）。
    """
    if not 0.0 < replay_ratio < 1.0:
        raise ValueError(f"replay_ratio 须在 (0,1) 内，得到 {replay_ratio}")
    if not questions:
        raise ValueError("唯一问题池为空")
    rng = random.Random(seed)
    total = round(len(questions) / (1.0 - replay_ratio))
    replay_slots = set(rng.sample(range(1, total), total - len(questions)))
    fresh = iter(questions)
    traffic: list[str] = []
    for i in range(total):
        traffic.append(rng.choice(traffic) if i in replay_slots else next(fresh))
    return traffic
