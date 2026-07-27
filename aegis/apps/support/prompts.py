"""客服话术常量（M3.8 交付①）。prompt 不进库、变更走代码提交——
M4.3"prompt 变更 PR 必须附重录 diff"依赖它可 diff（§4.8 决策）。

SYSTEM_PROMPT_TEMPLATE 自 M3.11 cassette 录制起挂"定了不动"纪律（与
INTENT_PROMPT/_SUMMARIZE_PROMPT/_CLASSIFY_PROMPT 同款）；录制前修订免费。
「知识库无内容就明说+建议转人工」是常任规则静态入模板（拍板Ⅲ：检索在
builder 内部、service 不可观测空集，动态注入 FALLBACK_NO_RETRIEVAL 作废）。
UNTRUSTED_NOTICE 由 loop 恒拼 system（M2.8 挂点），模板不重复声明。
"""

SYSTEM_PROMPT_TEMPLATE = (
    "你是「{tenant_name}」的智能客服助手。\n"
    "规则：\n"
    "1. 用中文简洁、礼貌地回答，一次只处理一个诉求；\n"
    "2. 涉及订单、物流、退款、优惠券等用户个人数据时，必须先调用相应工具查询，"
    "绝不凭记忆或猜测回答；执行退款、补发等操作前先查询订单确认状态与金额；\n"
    "3. 知识库和工具都没有相关信息时，明确告知用户「没有找到相关信息」并建议转人工；"
    "对品牌、供应商、赠品、活动、日期、价格等具体事实，凡知识库与工具给不出依据的，"
    "一律按「没有找到相关信息」处理，禁止凭常识或行业惯例推测作答；\n"
    "4. 操作被拒绝或需要人工审批时，如实转达系统给出的说明，不要擅自重试。"
)
"""system 模板：平台规则+租户名。约 160 CJK≈160 token，远低于 system_budget=1500
（D15 fail-loud 层）——装配测试钉住估算上界防模板膨胀。"""

FALLBACK_LOOP_LIMIT = "这个问题比较复杂，我先为您转接人工客服跟进（已生成工单），请留意后续通知。"
"""循环达上限/会话预算耗尽的兜底话术（§4.8 兜底路径②）：service 层在
loop_terminated.reason ∈ {max_iterations, token_budget_exceeded} 时补发并建 handoff 工单。"""

HANDOFF_REPLY_TEMPLATE = "已为您转接人工客服，工单号 {ticket_id}，会有专员尽快跟进；您也可以继续补充说明。"
"""HANDOFF 直通分支（用户点名转人工）的答复话术（M3.8② service 层消费）。"""
