"""M2.11 长对话基准录制：一次性真实调用，产出回放 cassette 与录制凭证（真实调用例外①）。

口径（写死，凭证照抄；00 §6.0 / plans/m2.11 §3）：
- 40 轮纯文本客服对话（无工具，D2），第 1-5 轮埋入五个高熵事实，第 36-40 轮逐一探针追问；
- 预算三上限写死在常量区，任一超限立即停止且不落盘（已花费照报）；
- 自检先于落盘（D8）：滚动摘要 >=2、末次覆盖含第 12 轮（末个字面埋点/复述轮）、五探针全命中、
  每轮恰以 completed 终止、全程零护栏事件、录制期零摘要 fail-open——任一不满足即 exit 1，不产 cassette；
- 落盘走 M2.6 Cassette.save（原子写 + 固定键序），绝不自带 json.dumps（陷阱 13）。

    uv run python scripts/record_long_dialog.py     # 必须在仓库根执行（.env 相对 cwd，陷阱 2）

预计 3-6 分钟，按演示价目实际花费 <¥1（以账本为准）。需要 PG 与 Redis 在跑。
2026-07-16 模型池变更后首次真实调用（00 §10.1 #28）：凭证含 API 回显模型名与价目表 key 对照。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import NoReturn

from sqlalchemy import text

from aegis.core.config import get_settings
from aegis.core.db import get_session_factory
from aegis.core.redis import get_redis
from aegis.gateway.factory import build_gateway
from aegis.runtime.events import EventType
from aegis.runtime.replay import Cassette, Recorder
from aegis.runtime.runtime import AgentRuntime
from aegis.runtime.spec import AgentSpec, LoopPolicy, TerminationReason
from aegis.runtime.store import SessionFactory, SessionRecord

# 落盘路径锚定项目根（记忆教训：PyCharm cwd=脚本目录，相对路径会把资产写错位置）
ROOT = Path(__file__).resolve().parent.parent
CASSETTE_PATH = ROOT / "tests" / "cassettes" / "long_dialog.json"
REPORT_PATH = ROOT / "reports" / "m2_long_dialog_recording.txt"

SESSION_ID = f"bench-long-dialog-{uuid.uuid4().hex[:8]}"  # D10：每次录制唯一，绝不复用
TENANT_ID = "bench"
USER_ID = "bench-user"

# D5 预算三上限（2026-07-17 拍板）：token 与金额走账本实测（C25 账单侧）；
# 调用行数是第三道兜底——上游偶发缺 usage 时适配器合成 0 token（openai_compat.py:144），
# 前两道会失明，行数不依赖 usage 可信（陷阱 5）
MAX_TOTAL_TOKENS = 800_000
MAX_TOTAL_COST_YUAN = Decimal("3.00")
MAX_LLM_CALLS = 200

# 拍板 2（计划外必改，偏差块 #2）：闸门 #3 是会话级累计口径（D8 种子从全会话事件流重建），
# 默认 50_000 会在 ~12-18 轮触发 TOKEN_BUDGET_EXCEEDED 违反 I4；40 轮累计估算上界约 21 万，
# 取约 2 倍余量。交付③回放测试必须复用本 SPEC——预算变了摘要触发点就漂，道内序号会失配
SESSION_TOKEN_BUDGET = 400_000

# 埋点五值（D6 三性质：高熵唯一 / 不可改写 / 一问一答可点名；拍板沿用计划样例表）
FACT_MEMBER = "VIP-7749"
FACT_ORDER = "AZ-20260701-0042"
FACT_MODEL = "R68 Pro"
FACT_STREET = "青梧路 199 号"
FACT_TIME = "19:00"

# 偏差块 #3：复述地址只说街道门牌——防模型自行拼出"市+区+路+号"全链命中出口
# PII 规则 address_cn（guardrails.py:338-344），探针答案被截断替换即自检失败。
# 偏差块 #7：第三行"逐字复述确认"让登记信息在摘要输入源里天然出现两次（用户说+助手复读）
SYSTEM_PROMPT = (
    "你是云杉电商·数码商城的在线客服助手，服务态度友好专业。\n"
    "回答保持简洁，每次不超过三句话，不要主动扩展无关话题。\n"
    "用户提供会员号、订单号、型号、地址、联系时段等登记信息时，回复中逐字复述一遍以确认登记无误。\n"
    "用户请你确认此前提供过的信息时，照登记的原始写法逐字复述，不要改写。\n"
    "复述地址时只说街道与门牌号，不要自行补全省、市、区等行政区划。"
)

SPEC = AgentSpec(
    system_prompt=SYSTEM_PROMPT,
    policy=LoopPolicy(session_token_budget=SESSION_TOKEN_BUDGET),
)

# 40 轮剧本：1-5 埋点、11-12 复述强化（型号 / 会员号+地址）、6-35 推进、36-40 探针+收尾（D4）。
# 台词纪律（偏差块 #3/#7）：城市"杭州"只在第 23 轮单独出现，永不与街道同句；
# 第 12 轮之后用户台词不再出现任何字面埋点值（探针答案只能派生自压缩链路的前提）；
# 全部台词已逐条对照入口 14 条规则（guardrails.py:74-176），零命中
TURNS: tuple[str, ...] = (
    f"你好，我是你们商城的老会员，先帮我做登记：我的会员号是 {FACT_MEMBER}，之后报修换货的全部流程"
    f"都挂在这个号下面，工单一定要写对。我家的路由器最近老出问题，今天想正式报修。",
    f"先把设备对应的订单号发给你：{FACT_ORDER}，你核对一下能不能查到这笔订单。设备买了大概半年，"
    f"一直是我自己在家用，没摔过没进水，平时放在客厅电视柜上，使用环境正常。",
    f"设备型号是 {FACT_MODEL} 路由器，你记进工单，后面判断问题要用。故障是 5GHz 频段每天断流好几次，"
    f"每次断十几秒自己恢复，2.4G 从来不断，手机电脑连 5G 时最容易中招，体验很差。",
    f"顺便把收货信息也登记上：收货地址是{FACT_STREET}，之后换货的新机就寄这个地址，你复述确认一遍"
    f"别寄错；旧机上门取件也用同一个地址，这一点请一并写进备注，配送范围你也帮我看下。",
    f"我的诉求现在说清楚，请记进工单：我要换货不要退款，这台配置我用着顺手，退了重买太麻烦。"
    f"另外联系我一律安排在工作日 {FACT_TIME}后，白天上班不方便接电话，这个时段请你复述确认并写进备注。",
    "断流一般发生在晚上八九点，家里人都回来、连的设备一多就特别明显，白天家里没人时基本不断。"
    "我自己猜跟负载有关但拿不准，你们从售后角度看，这种带规律的断流一般指向什么原因？",
    "我已经试过重启路由器了，重启之后确实能安稳半小时左右，然后又开始断，表现跟之前一模一样，"
    "治标不治本。这种重启就好、过会儿又犯的情况，你们一般会让用户下一步排查什么？",
    "固件版本我在管理后台看过，是今年年初发布的版本，页面没有提示可升级的新版本，应该已经是最新。"
    "固件层面我理解可以排除了，你要是能查到官方最新版本号，帮我再确认一遍更稳妥。",
    "我把 5GHz 信道从自动改成 149 了，昨天白天确实稳定，一次都没断，但晚上高峰还是断了两次，"
    "每次十几秒。看起来信道干扰只是次要因素，主要问题在别处，我这个判断你觉得对吗？",
    "频宽我也从 160MHz 改到 80MHz 了，断流频率略降，但穿墙明显变差，卧室刷视频经常转圈，"
    "副作用挺难受。要是最后确认是硬件问题，这些无线设置我是不是都可以改回原样？",
    "家里连这台路由器的设备有二十多个：摄像头、音箱、扫地机挂 2.4G，手机、电脑、平板走 5G。"
    f"按你们 {FACT_MODEL} 标称的承载能力，这个数量算多吗？会不会就是负载把 5G 模块压垮了？",
    "对了帮我核对一下：这个报修工单挂的是我会员号吧？你把系统里登记的会员号和收货地址"
    "照原样念一遍给我，我怕前面登记时写错，后面查进度或者寄件对不上就麻烦了。",
    "我怀疑设备过热，下午专门摸了机身顶盖，烫手程度比刚买时明显得多。你们这个型号有没有类似的"
    "散热反馈？要真是通病我就不折腾了，直接走换货流程，省得来回耗时间。",
    "我把它从电视柜的封闭格子挪到了开放架子上，四周留了空隙，散热条件好了不少，温度确实降了些，"
    "但今天中午还是断了一次。散热改善了还断，过热这条线索是不是也能排除了？",
    "需要我把系统日志导出来发给你们吗？我在管理后台的诊断页看到一段红色报错，时间点就在断流前后，"
    "看着挺可疑。日志要是有用，你告诉我导出的入口和格式要求，我今晚就去弄。",
    "日志我翻了一遍，反复出现无线模块自动重启的记录，时间点跟我记的断流时间一条条都对得上，"
    "不像外部干扰，更像模块自身的问题。这个证据够不够支撑直接按硬件故障来处理？",
    "既然软件层面的排查都做完了还是这样，按你们售后的经验基本可以判定是硬件问题了吧？"
    "我不想再无限排查下去了，想直接进售后流程，你把现在可以走的处理方案给我列一列。",
    "走售后检测的话具体步骤是怎样？是我先把设备寄回检测中心，还是有工程师上门？两种方式周期分别"
    "多久？我居家办公全靠这台路由器，断网时间太长真的扛不住，这点你们要考虑进去。",
    "有没有先发新机、再回收旧机的置换服务？我记得你们会员权益介绍里提到过这一项。有的话我优先走"
    "这个，家里不断网体验最好，具体怎么申请、要什么条件，你一次跟我说全。",
    "太好了，就按先发后收来办。跟你确认两件事：第一，发来的新机必须全新原封，翻新机我不接受；"
    "第二，新机发出之前会不会有短信或站内通知？我好提前留意收货，别错过配送。",
    "旧机的包装配件要全部一起寄回吗？彩盒还在，电源线网线也都在，但说明书找不到了，会不会影响"
    "回收？缺一样要不要扣费？回收的验收标准你跟我讲清楚，我好提前把东西凑齐。",
    "电源适配器用了半年，外壳有点使用痕迹，谈不上损坏就是正常磨损，这会影响换货审核吗？要不要"
    "提前拍照留证？要拍的话告诉我拍哪些角度，我一次拍齐免得来回补材料耽误进度。",
    "对了我人在杭州，你们仓库要是有同城库存，调拨应该挺快吧？就不用等外地发货了。要是同城没货，"
    "从最近的仓发过来一般几天？你帮我查下库存，我心里好有个预期安排接收。",
    "换货申请是我自己在订单页发起，还是你后台直接帮我提交？哪种方式更快、留痕更全？我怕自己操作"
    "漏填字段，审核被打回重新走一遍反而更慢，所以想选最稳妥的那条路。",
    "那就麻烦你直接帮我提交吧，提交完把申请编号发我。之后的进度有短信通知吗？我平时不看邮件，"
    "重要节点请都走短信，这个通知偏好帮我写进备注里，免得漏接消息。",
    "审核一般要多久？今天周四，顺利的话赶得上周末前把新机发出来吗？赶不上的话大概什么时候能发？"
    "给我个大致时间范围就行，我好提前安排家里人在家收货，免得放代收点。",
    "换新机后序列号就变了，保修期是从签收新机那天重新计算，还是接着原来那台的剩余保修继续走？"
    "这两种差别挺大，你帮我确认清楚，最好把政策原文也发我看一眼，我心里有底。",
    "旧机里我配置了不少东西，端口转发、设备限速、访客网络一大堆规则，需要先手动备份吗？还是新机"
    "能一键迁移？迁移不了的话重配一遍挺费劲，你告诉我最稳妥的做法，我照着来。",
    "我已经把配置文件导出存到电脑里了，文件不大。新机到手后在同一个管理后台直接导入就能恢复吧？"
    "同型号之间导入会有版本兼容问题吗？有坑的话提前告诉我，我好绕开少走弯路。",
    "上门取旧机的是哪家快递？包装要我自己提前打好，还是师傅带材料现场打包？要自己打包的话纸箱"
    "尺寸有没有要求？我提前准备好，免得师傅到了现场再折腾半天耽误双方时间。",
    "取件时间能约在周末吗？工作日白天家里没人，只有晚上和周末有人在。要是只能约工作日，就按我"
    "之前登记的联系时段先电话确认，别白天打过来没人接，师傅也白跑一趟。",
    "还有个事要先问清楚：要是新机到手后还是同样的 5GHz 断流，还能再走一次换货吗？还是第二次只能"
    "修不能换？这关系到我要不要从第一天就留使用记录当证据，规则你给我讲明白。",
    "行，那我先用新机观察一段时间再说。你们售后的后续跟进是电话回访为主还是短信为主？回访的话"
    "备注里写清楚按我登记的时段来，别一到上班时间就打过来，我真的接不了。",
    "这次换货的处理进度我自己在哪里能查？给我指个入口，是订单详情页还是专门的售后页面？我不想"
    "每次都进来问人工，自己能查最省事，你把路径一步一步说给我，我记下来。",
    "好，那今天就把换货流程全部走起来，要我配合提供的材料我都会尽快给，进度我自己盯售后页面，"
    "剩下的等你们通知。这几天就麻烦你们跟进了，有异常第一时间按登记方式联系我。",
    "在等通知之前，顺便再帮我确认一下：我的会员号是多少来着？你们系统里登记的应该有，我自己"
    "念不准了，你照登记的原样报给我听一遍，我核对一下。",
    "还有，我最早报修时给你的那个订单号是哪个？我这边好几笔订单混在一起，自己都记不清了，"
    "你把工单里登记的那个号完整念一遍给我，我记到本子上。",
    "再确认一个：我这台报修的路由器是什么型号来着？我要在寄回的包装箱上把型号写清楚，"
    "免得仓库收错货，你照登记信息报给我就行。",
    "我的收货地址在哪条路？门牌号也一起念给我，我确认下你们登记的和我说的有没有出入，登记错了现在就改，免得新机寄丢。",
    "最后一个问题：我之前说过每天什么时间之后联系我比较方便？请按我原话复述一遍，我确认工单"
    "备注写对了没有。今天麻烦你了，谢谢。",
)

# D8 强化（首录复盘，偏差块 #7）：全部字面埋点在 1-5 轮、唯一复述强化在第 12 轮——要求末次
# 摘要覆盖 ≥12，且 12 轮后用户台词无任何字面埋点值，则此后对埋点值的一切提及都只能派生自
# 摘要链路，探针答案的来源可辩护（陷阱 10 的结构化封堵）
PROBE_COVER_TURN = 12

PROBES: tuple[tuple[int, str], ...] = (
    (36, FACT_MEMBER),
    (37, FACT_ORDER),
    (38, FACT_MODEL),
    (39, FACT_STREET),
    (40, FACT_TIME),
)

_NORM_STRIP = re.compile(r"[-\s]")
_SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}")


class SummarizeFailureTrap(logging.Handler):
    """捕获录制期的滚动摘要 fail-open（C34 只留 logger.warning——无事件无条目无账本行）。

    为什么这是录制致命项（偏差块 #8）：摘要触发判定是确定性的，回放时同一触发点必然复现，
    而 FakeGateway 不会失败——录制期"触发→失败→无痕"的点会让回放错位消费 summary 道，
    cassette 从此不可忠实回放。对录制器而言，"干净运行"是比"成功运行"更强的要求。
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.failures: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "滚动摘要失败" in message:
            self.failures.append(message)


def normalized(value: str) -> str:
    """召回判定两侧共用的归一化：全角冒号折半角 + 剔连字符与空白（确定性排版折叠）。

    "青梧路 199 号"与"青梧路199号"、"19：00"与"19:00"各是同一事实的排版变体，
    不许成为假阴性源；语义级改写（如"晚上7点"）仍判失败——D7 关键词断言的局限声明不变。
    """
    return _NORM_STRIP.sub("", value.replace("：", ":"))


def check_recall(transcript: dict[int, str]) -> list[str]:
    """五探针逐一核对（I1：本函数同时是录制自检与交付③ CI 断言的判据本体）。"""
    missed: list[str] = []
    for turn_no, keyword in PROBES:
        answer = transcript.get(turn_no, "")
        if normalized(keyword) not in normalized(answer):
            missed.append(f"第 {turn_no} 轮探针未命中 {keyword!r}；实际回答：{answer[:120]!r}")
    return missed


def self_check(
    transcript: dict[int, str],
    summaries: list[tuple[int, int]],
    guard_hits: list[str],
    summarize_failures: list[str],
) -> list[str]:
    """D8 六道判据，返回失败清单（空=全过）。判据变更须与交付③测试同步——两处是同一套。"""
    failures: list[str] = []
    if len(summaries) < 2:
        failures.append(
            f"滚动摘要仅 {len(summaries)} 次（要求 >=2）——加长台词或加轮数，"
            "绝不去调 ContextConfig 预算，那是在改被测物（陷阱 4）"
        )
    if summaries and summaries[-1][1] < PROBE_COVER_TURN:
        failures.append(
            f"末次摘要覆盖至第 {summaries[-1][1]} 轮（< {PROBE_COVER_TURN}）——"
            "字面埋点/复述轮尚在原文窗口，探针测不到压缩链路（陷阱 10）"
        )
    for item in summarize_failures:
        failures.append(f"录制期摘要 fail-open（回放分歧源，必须重录）：{item}")
    failures.extend(check_recall(transcript))
    failures.extend(guard_hits)
    return failures


def scan_secrets(blob: str) -> None:
    """落盘前扫密（I3 双保险之二；之一是 M2.6 request_digest 不落 prompt 原文）。"""
    if _SECRET_RE.search(blob):
        raise SystemExit("扫密失败：cassette 序列化文本含 sk- 模式——不落盘")
    key = get_settings().dashscope_api_key.get_secret_value()
    if key and key in blob:
        raise SystemExit("扫密失败：cassette 序列化文本含 API key 明文——不落盘")


async def preflight(sf: SessionFactory) -> None:
    """就绪检查，失败即 SystemExit：探针表自洽、key 非空、PG 可达、Redis 可达。"""
    if any(not 1 <= turn_no <= len(TURNS) for turn_no, _ in PROBES):
        raise SystemExit("PROBES 轮号超出 TURNS 范围——剧本与探针表不同步")
    if not get_settings().dashscope_api_key.get_secret_value():
        raise SystemExit("DASHSCOPE_API_KEY 为空——请在仓库根运行（.env 相对 cwd 解析，陷阱 2）")
    async with sf() as s:
        await s.execute(text("SELECT 1"))
    await get_redis().ping()


async def ensure_session_row(sf: SessionFactory) -> None:
    """P2：run 之前 sessions 行必须先存在（runtime.py:260 无行拒绝起跑；摘要投影同样要求）。"""
    async with sf() as s:
        async with s.begin():
            s.add(SessionRecord(id=SESSION_ID, tenant_id=TENANT_ID, user_id=USER_ID))


async def spend_of(sf: SessionFactory, session_id: str) -> tuple[int, Decimal, int]:
    """账本实测口径（C25 账单侧；报表用裸 SQL）：(token 总量, 费用元, 调用行数)。"""
    stmt = text(
        "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0),"
        " COALESCE(SUM(cost), 0), COUNT(*) FROM usage_ledger WHERE session_id = :sid"
    )
    async with sf() as s:
        row = (await s.execute(stmt, {"sid": session_id})).one()
    return int(row[0]), Decimal(str(row[1])), int(row[2])


async def models_of(sf: SessionFactory, session_id: str) -> list[str]:
    """账本 distinct 模型名（#28：模型池变更后首次真实调用，须与 model_prices key 对照）。"""
    stmt = text("SELECT DISTINCT model FROM usage_ledger WHERE session_id = :sid ORDER BY model")
    async with sf() as s:
        return [r[0] for r in (await s.execute(stmt, {"sid": session_id})).all()]


async def abort(sf: SessionFactory, why: str) -> NoReturn:
    """失败统一出口（I3：落盘是最后一步，走到这里必然没有半截 cassette）。已花费照报（D8）。"""
    tokens, cost, calls = await spend_of(sf, SESSION_ID)
    print(why)
    print(f"已花费（账本实测）：tokens={tokens} cost=¥{cost} calls={calls}")
    raise SystemExit(1)


def build_report(
    *,
    cassette: Cassette,
    tokens: int,
    cost: Decimal,
    calls: int,
    summaries: list[tuple[int, int]],
    transcript: dict[int, str],
    models: list[str],
) -> str:
    """凭证正文（D13）：数字全部来自账本与事件实测，口径注记随凭证本体（简历数字纪律）。"""
    prices = get_settings().model_prices
    unknown = [m for m in models if m not in prices]
    lane_counts = {scope: len(entries) for scope, entries in cassette.scopes.items()}
    lines = [
        "M2.11 长对话基准 · 真实录制凭证（真实调用例外①，00 §6.0；预算三上限写死本脚本）",
        f"录制时间：{datetime.now().isoformat(timespec='seconds')}",
        f"session_id：{SESSION_ID}（cassette 头部同值——同源同次录制，I2）",
        f"轮数：{len(TURNS)}（每轮均以 completed 终止）；探针轮：{[t for t, _ in PROBES]}",
        f"LLM 调用（账本行数）：{calls}；cassette 各道条目数：{lane_counts}",
        f"token 总量（账本 prompt+completion 实测）：{tokens}",
        f"费用（按 config.model_prices 演示价目计算）：¥{cost}（实际扣费以百炼控制台为准）",
        f"滚动摘要：{len(summaries)} 次；覆盖范围 (turn_from, turn_to)：{summaries}",
        "探针召回（判定=两侧剔 [-\\s] 归一后包含，判据与 CI 同一套）：",
    ]
    for turn_no, keyword in PROBES:
        answer = transcript.get(turn_no, "")
        lines.append(f"  第 {turn_no} 轮 关键词 {keyword!r} 命中；回答摘录：{answer[:60]!r}")
    lines += [
        f"账本 distinct 模型名：{models}；价目表 key：{sorted(prices)}",
        (
            f"#28 对照：以下模型名未命中价目表，本次成本按 0 记账，须回填实价后复算：{unknown}"
            if unknown
            else "#28 对照：全部模型名命中价目表（价目为演示值，实价以百炼价目页为准）"
        ),
        "口径注记：录制关缓存（CACHE_TTL_SECONDS=0，D9）；护栏用估算、账单用实测（C25）；",
        "  本凭证由 scripts/record_long_dialog.py 自检通过后生成——自检与 CI 断言同判据（I1）。",
        "",
    ]
    return "\n".join(lines)


async def main() -> None:
    # D9 关缓存（消除类别而非概率）。放 main() 首行即够早：Settings 在 get_settings()
    # 首调时才构造（config.py:83 lru_cache），本进程 import 期没有任何 get_settings 调用
    # ——比计划原文"import 前"晚，意图相同（偏差块 #5），换来本模块可被测试安全 import
    os.environ["CACHE_TTL_SECONDS"] = "0"
    trap = SummarizeFailureTrap()
    logging.getLogger("aegis.runtime.context").addHandler(trap)
    sf = get_session_factory()
    await preflight(sf)
    recorder = Recorder(build_gateway(), SESSION_ID)  # 构造期绑定会话，失配快速失败（replay.py:253）
    runtime = AgentRuntime(recorder, sf)  # 摘要钩子由 runtime 内部经 scoped_view 自动分道
    await ensure_session_row(sf)

    transcript: dict[int, str] = {}  # 轮号 -> 该轮 assistant 终稿（探针判据的数据源）
    summaries: list[tuple[int, int]] = []  # 每次 summary_updated 的 (turn_from, turn_to)
    guard_hits: list[str] = []  # 任何护栏痕迹都记下来：非空即自检失败（偏差块 #3）
    tokens, cost, calls = 0, Decimal("0"), 0

    for i, user_input in enumerate(TURNS, 1):
        reasons: list[str] = []
        async for ev in runtime.run(SPEC, SESSION_ID, user_input):
            if ev.type is EventType.SUMMARY_UPDATED:
                summaries.append((ev.payload["turn_from"], ev.payload["turn_to"]))
            elif ev.type is EventType.ASSISTANT_MESSAGE:
                transcript[i] = ev.payload["content"]  # 终态覆盖：同轮多条取最后一条
                if ev.payload.get("guardrail_truncated"):
                    guard_hits.append(f"第 {i} 轮 assistant_message 被出口守卫截断")
            elif ev.type is EventType.GUARDRAIL_TRIGGERED:
                guard_hits.append(f"第 {i} 轮 guardrail_triggered：{dict(ev.payload)}")
            elif ev.type is EventType.LOOP_TERMINATED:
                reasons.append(ev.payload["reason"])
        if reasons != [TerminationReason.COMPLETED.value]:
            await abort(sf, f"第 {i} 轮终止异常（I4 要求恰一次 completed）：{reasons}——剧本或运行时有问题")
        if trap.failures:
            # 偏差块 #8/#11：fail-open 一出现本次录制就注定不合格（回放分歧源），
            # 跑满 40 轮只是白花钱——立即中止；self_check 的第六道判据保留作兜底
            await abort(
                sf,
                f"第 {i} 轮出现摘要 fail-open（回放分歧源，六道判据必死）——立即中止省预算：{trap.failures[-1]}",
            )
        tokens, cost, calls = await spend_of(sf, SESSION_ID)
        print(
            f"[{i:2d}/{len(TURNS)}] completed  tokens={tokens}  cost=¥{cost}  calls={calls}  summaries={len(summaries)}"
        )
        if tokens > MAX_TOTAL_TOKENS or cost > MAX_TOTAL_COST_YUAN or calls > MAX_LLM_CALLS:
            await abort(
                sf,
                f"预算超限（D5）：tokens={tokens}/{MAX_TOTAL_TOKENS}，"
                f"cost=¥{cost}/{MAX_TOTAL_COST_YUAN}，calls={calls}/{MAX_LLM_CALLS}",
            )

    failures = self_check(transcript, summaries, guard_hits, trap.failures)
    if failures:
        print("录制自检未过（D8：不合格 cassette 不入库）：")
        for item in failures:
            print(f"  - {item}")
        await abort(sf, "按诊断调剧本后重跑即可——每次重跑自动换 SESSION_ID（D10），花费 <¥1")

    cassette = recorder.cassette()
    scan_secrets(json.dumps(cassette.dump(), ensure_ascii=False))
    cassette.save(CASSETTE_PATH)  # M2.6 原子落盘：固定键序 / indent=2 / UTF-8+LF（陷阱 13）
    models = await models_of(sf, SESSION_ID)
    REPORT_PATH.write_text(
        build_report(
            cassette=cassette,
            tokens=tokens,
            cost=cost,
            calls=calls,
            summaries=summaries,
            transcript=transcript,
            models=models,
        ),
        encoding="utf-8",
    )
    print(f"落盘完成：\n  {CASSETTE_PATH}\n  {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
