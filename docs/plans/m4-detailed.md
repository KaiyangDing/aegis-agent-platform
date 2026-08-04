# m4-detailed · M4 治理层步骤级详细计划（M4.0–M4.8）

> **写作基线**：M2.4 毕业，commit `014ec21`，301 测试全绿 · 撰写 2026-07-10（Fable 5 交接工程）
> **实际落地偏差：（毕业时回填；本块为差异权威，随步追加）**
>
> **§0 开工核对实况（2026-08-03，M4.0① 逐项 Read 核实）——六条与计划不符，以本块为准**：
> ⑴ **§0-14 `EventType` 实为 16 成员**（计划写 14；M2.8 +`guardrail_triggered`、M2.10 +`recovery_abandoned`）
> ——M4.3 断言字面量的事实源按 16 写；`TerminationReason` 8 成员与 `SCHEMA_VERSION=1` 无漂移。
> ⑵ **§0-5 层契约已五层化**（计划写四层）：`aegis.api | aegis.workers` → apps → runtime → gateway → core，
> 契约数 1（pyproject.toml:67-79）——**M4.1 的 `aegis.obs` 插进哪一层是待拍板项**（建议 runtime 之下、
> gateway 之上：obs 读 events 但不该被业务层反向依赖）。
> ⑶ **§0-3 cassette 实为 11 盘**：minimal_demo / long_dialog / adversarial ×4 / l3 ×5（+README）——
> 计划只列三族，漏了 M2.7 的对抗四盘；M4.3 manifest 按 11 盘挂账。
> ⑷ **§0-6 应用入口无模块级 `app` 变量**，只有 `create_app()` 工厂（main.py:35）——M4.7 容器 CMD
> 须用 `--factory`（或届时补一行模块级实例，属拍板项）。
> ⑸ **§0-16 docs 顶层实为 16 篇**（计划写 13）：+`atlas.md` +`retro-m2.md` +`compare-langgraph-m2.md`。
> ⑹ **§0-17 reports 实为 11 件**（计划写 3）。
> 其余 11 项对上，其中已实测确认：M3 基线 854/`6d2c531`/tag `m3-support`、回放三件与匹配键
> （`session_id` + 四道名 + 道内序号，`request_digest` 只作诊断域）、PII 单点 `guardrails.py:341-348`、
> 检索入口两签名形态不同（`Retriever.search` 位置参数 / `RetrievalProvider.search` keyword-only）、
> 粘滞化模板 `ratelimit.py:76-110` 与第二样本 `core/locks.py:221-250`、C41/C21 已落 02:179/02:251、
> CI 九道门与计划描述逐条一致。
>
> **M4.0 过程偏差**：
> ⓵ **交付顺序调整**（用户 2026-08-03 裁决）：原计划交付序为"CI 三道门→#29"，因 M4.0① 把候选③
> 定级 P0（真副作用），**缺陷批处理提前为交付②**，CI 三道门顺延为交付③、#29+kill-9+观察池归位为交付④。
> ⓶ **M4.0 范围较计划 §1 扩大**：计划只挂 #3/#4/#24/#29/#41，实际并入 M3 复盘遗产
> （#46/#48 kill-9 实录/#49 普查/#50 全部/㊲/(63)）——规模由 M 升 L，故切四份。
> ⓷ **AI 盘点漏项（用户跑门抓出）**：交付② 报"修改既有测试 2 个"实为 3 个，漏
> `test_refund_rejects_refunded_order`（同样断言拒因文本）。根因=只盘自己动过的文件。
> **教训入库**：**改判任何对外话术/返回值时，影响面盘点必须 grep 全仓"断言该输出"的测试**，
> 与既有教训"预告收集数须逐项点名后再报"同族（都是盘点不彻底）。
> ⓸ **指令块禁用 `&&`**（用户纠正）：本机 PowerShell 5.1 不支持管道链操作符，且 `&&` 串联会让
> 前序失败静默跳过后续判断——一律按 07 §2.3 模板**逐行单块 + 每行标预期**。
> ⓺ **AI 交付稿缺陷第四次同族（用户跑门抓出）**：M4.0③ 的 `chat.py` 修复在 `except` 块内
> `raise HTTPException` 未断异常链 → ruff B904（pyproject `select` 含 `"B"`）。前三次为
> mypy dict 不变性（M3.1）/ PyJWT 弱钥告警（M3.1）/ Decimal 序列化路径（M3.1）。
> **共性=交付稿发出前未过本地四门**——M3.4 起定型的"影子副本排练"工艺本可拦下，M4.0②③
> 两份交付都跳过了它。**纪律收紧**：AI 交付稿凡含 `except` 块／新 import／新装饰器／新
> `__table_args__` 者，**必须过影子门再发**，不得靠肉眼。（正解 `from None` 而非 `from e`：
> `IntegrityError` 是预期内的并发信号不是错误，404 是给客户端的正常答复，挂异常链只会让
> traceback 噪音进日志，且与同函数下方那条天然无链的 404 语义对齐。）
>
> ⓻ **`alembic check` 首跑抓出 HNSW 漂移，连带修正一处文档口径**：M3.4 §4.4 陷阱 2 写
> "autogenerate 不认识 `USING hnsw`"——**只对生成面成立**（确实不会自动写出，故当初手写
> 迁移的决定正确），**比对面它认得** `postgresql_using` + `postgresql_ops`（scratchpad 探针
> 用 `compare_metadata` 实证：补声明后差异归零）。故 ORM 侧必须补 `Index` 声明，否则这道门
> 永远红。否决 `env.py` 加 `include_object` 排除法：那是用"让门看不见"换"门变绿"，索引将来
> 被误删也无人报警。**探针副产品警示**：探针脚本只 import 了 `store.Base`+`rag.models`，
> 于是报出 13 条"remove_table/remove_index"假差异——真 `alembic check` 走 `migrations/env.py`
> （import 全量模型）只报 HNSW 一条。**读 autogenerate 差异前必须先确认 metadata 装载完整**。
>
> ⓹ **候选② 只修了信息面一半**：00 §10.1 #50 原修向含"细节进事件 payload"，该半需改
> `PrecheckHook` 冻结签名（`str | None` 既是模型观察又是事件内容），用户 2026-08-03 裁决
> **挂 M4.1 与 trace API 同做**；`_load_order` 仍无 user 维度=读不到 ctx 的结构性边界，
> 本次修的是"说什么"不是"读什么"。
>
> **M4.1 开工核对与五项拍板实况（2026-08-03，交付前逐项 Read 实码核实；与本章计划不符处以本块为准）**：
> ⑴ 端点已存在：`GET /v1/sessions/{id}/events` M3.10 已建（events_view.py 自标"M4.1 底座"）
> ——走 §3-1"升级响应"分支；【拍板⑤】响应整形替换为 TraceView，`after_seq`/`limit` 两参
> 退役（全仓无生产消费方，chat.html 走 /stream；分页/增量导出 v2），`_MAX_EVENTS` 随之移除，
> 全量装配边界写进模块 docstring。
> ⑵ **§3-2"跨租 404"裁决被 M3.10 实装取代**：实码 operator 越界=**403** 且测试
> （test_operator_cross_tenant_403）+题 142 钉死（staff 面点名口径，与 approvals 端点一致；
> 用户面 404 不泄露存在性相对）——【拍板④】沿用 403，本章 §3-2/§7-4 两条作废。
> ⑶ §4 蓝图 `_MASK_RULES` 三规则草稿作废：事实源=guardrails.PII_RULES_V1 **四**规则
> （蓝图漏 address_cn），各模式自带数字边界断言——§7-5"长模式在前"排序陷阱不存在；
> 【拍板②】masker 直接 import 该表不复制，guardrails 零改动。
> ⑷ 【拍板①】obs 层位=**`aegis.apps | aegis.obs` 同层互不 import**（M4.0① 偏差⑵ 记录的
> "runtime 之下 gateway 之上"方向作废：低位够不到 PII_RULES_V1 与 store ORM——单点被迫复制
> 或动 M2 冻结件，且 M4.2 §3-1 已裁 runtime/gateway 不许 import obs，低位唯一潜在收益为零）。
> ⑸ 耗时来源简化（登记偏差）：tool_result/tool_error 事件 payload **自带 latency_ms**
> （executor.py:216 实测写入，投影行 store.py:245 正是从 payload 抄的——同源同值）→ 直读
> payload，省掉 §4-4 的 tool_invocations join；关联字段名核实=`tool_call_id`。
> ⑹ assembler 签名较 §4 蓝图调整：`assemble(session: SessionRecord) -> TraceView`——鉴权留在
> 端点（403/404 分工需区分"不存在"与"他租"，蓝图"None 译 404"表达不了 403；会话行由端点经
> approvals_lookup 加载后递入）；**账本聚合包 `tenant_context(会话租户)`**（usage_ledger 在
> RLS 名单内，admin 跨租不包=静默空账——usage.py:65 同款，(58) 家族；RLS 在场证人挂交付②
> 落 test_rls 增量节）。
> ⑺ 【拍板③】候选② 半边形态=`PrecheckVeto(observation, detail)` dataclass + PrecheckHook
> 返回 `PrecheckVeto | None` + **第 17 类事件 `precheck_vetoed`**（走 M2.5 拍板 4 预定义的
> 扩枚举流程：快照测试先红 → 03 §5 表 → C31 核对（approval_id 顶层别名化通用，天然兼容）；
> `_rebuild_working` 正向匹配对未知类型天然忽略——两处兼容面交付前已核实），交付③承载。
> 交付切分：①obs 包底座（masking+trace+契约行）→ ②端点升级（TraceView+masker+审计保留）
> → ③候选② 半边（PrecheckVeto+新事件+runtime 两调用位+revalidate）。
>
> **M4.1 交付实录（2026-08-03 三交付一天收口）**：①`b0bbec5`（873→890）②`b7abb5a`（890→893）
> ③`0795f0c`（893→894）；凭证 `reports/m4_trace_sample.json`（chore 提交）——演示库被 M4.0④b
> 往返清空，改走 **l3 cassette 零 token 回放重建**（tool_roundtrip 盘）+ create_app() 生产链实拍，
> 红线 1 零真实调用。**过程偏差三条**：⑻ §5 测试预告 14–18 实为 **+21**（17/3/1；交付③预告
> "先红后绿 6–8 新测"实为断言升级——veto 覆盖面住进既有 4 文件更贴行为语义，净新 1）；
> ⑼ **AI 盘点漏项一枚由影子门 mypy 拦下**（test_recover_stale_claim 的 str 桩——首轮 grep 结果
> 被 head_limit 截断漏看；M4.0⓷"盘点必须全仓"家族第四例，**首次拦在交付前而非用户门前**；
> 纪律追加：影响面 grep 一律 head_limit=0 无截断复查）；⑽ RLS 证人做了**反向实证**（影子拆
> tenant_context → 红在 usage.requests 0==1 → 恢复复绿；M4.0④b"探针必须先证明会被抓"
> 纪律在测试面的第一次应用）。00 §2.2 新增"展示层 PII 打码单点"口径行；§8.2 第一条达成。
>
> **M4.2 开工核对/拍板与交付实录（2026-08-03 三交付+修复一天收口；与本章计划不符处以本块为准）**：
> 核对实况：预算列 `tenants.token_budget_monthly`（tenancy.py:48）；**月窗单点=
> `MeteringRecorder.month_spend`**（metering.py:113-125，DB 端 date_trunc+cached 排除）——#10 gauge
> **复用该方法**（空价目表构造，month_spend 不触价目）而非复刻 SQL；缓存命中记账 provider="cache"
> 实证（router.py:265）；首帧位置=chat.py peek `anext`——**打点定为首个 token 帧非首帧**（首帧可能是
> tool_status）。五项拍板全按建议：⑴/metrics 无认证+只绑 127.0.0.1（02 §7.1 已补行）⑵#23 演示
> ≤3 轮真实调用例外放行（附A #9 前半，M4.7 冒烟半边到步再裁）⑶#6 成本 gauge 保留+**增第 11 族
> `aegis_documents{tenant_id,status}`**（⑫⑱观测半）⑷限流扩挂 kb+approvals 同租户桶、stream 不挂
> ⑸观察池移位 ㊺→M5.2/(67)(68)→M4.7 前/(72)→M5.4 前（"指标口径撞上"复核不成立——/metrics 用量
> 来自账本不来自帧）/(77)→M5.4。
> **交付实录**：①`80299de`（894→903）②`4b33295`（903→909）③`5a17bf8`（909→918，**范围为计划外
> 观察池批**——㉓⑱⑥⑭(56)(61)(74) 六条七处）+修复 `ba372df`；凭证 `reports/m4_metrics_sample.txt`
> （`scripts/demo_metrics_acceptance.py`——**用户裁决入库为项目资产**而非弃置探针，README 已登记；
> 实跑 3 轮 ratio 0.0008025→0.003145）。
> **过程偏差四条**：⑾**计划 §4 伪码 `refresh(get_session_factory())` 是错的**——/metrics 无租户身份，
> app 工厂 RLS 世界全空集零报错（(58) 家族第三例、首次埋在计划伪码里）；正解=平台维护面
> （approvals_lookup 查读缝）。⑿**CI 空库红一课**（`ba372df`）：无租户维度共享 label 族（cache）
> 空库首刷零行不触发 set→保留上个测试世界旧值→delta 基线错位；**影子门跑在非空库 dev 库上
> 结构性抓不到**（M2.11"环境依赖测试"镜像版：本机绿 CI 红）；修=测试先 clear()；纪律=共享 label
> 断言先清 child 或找 delta 不变量。⒀中间件弃 BaseHTTPMiddleware 取纯 ASGI（SSE 长流风险），
> `scope["route"].path_format` 取路由模板经测试实证。⒁测试计数：本章 §5 预告 9–13，实收 **+24**
> （①9/②6/③9——③是计划外范围；修复 +0） | 全部登记本块，08/00 已同步。
>
> **M4.3 开工核对/拍板与交付实录（2026-08-03 四交付一天收口，`5240b09`/`360078a`/`ac09505`/`1126c1e`，
> 测试 918→945；与本章第四章不符处以本块为准）**：
> 核对实况两条计划过期：⒂ **`EventType` 实为 17 成员**（M4.0① 差异块⑴的"按 16"已被 M4.1③
> `precheck_vetoed` 超越——断言事实源以实码为准）；⒃ **参数化基数 11 非 §5 的 15–25**（按
> "M3.11 录 15–20 盘"旧估算写成，实录 5 盘；§6"隔离/预算硬约束≥10 例"同源，按 11 盘实况修订为
> "对抗类盘全覆盖"）。七处裁决全按建议（开工全景图 2026-08-03）：红绿手法=本地（等价性登记 00
> §8.2）／㉜ 不加缝（触发条件落 README §8）／㉗㊼㊾ 纯声明／(73) 照 M4.2③ 先例单列修缮交付／
> #47 薄层+三证人切交付②。
> **结构偏差四条**：⒄ **conftest.py 不建**（计划 §4 蓝图有）——tests 无包结构下测试模块无法可靠
> import conftest（M3.9"模块名全仓唯一"同族），且项目样式自 m2.6 起"共用道具不进 conftest"；
> 装置并入 test_behavior_regression.py 单文件，manifest 仍独立 JSON（PR 评审物）。⒅ 计划
> `replay_session(cassette_path)` 单签名对 11 盘不现实——三族三种装配改 **DRIVERS 注册表**
> （manifest 纯期望四键、装配归注册表；完整性测试升级为三向：盘面≡manifest≡DRIVERS）。
> ⒆ **C31 消费点精确化**：行为断言四键不需要等价比对；归一化的真实消费点=forbidden 扫描面
> （豁免 usage/latency+id 别名化），并新增机械噪声键剔除 {iteration, input_tokens_est, digest}
> ——哈希 hex 撞数字禁词（"259"）的概率逐盘恒定非零，隔离断言不押巧合。⒇ **minimal_demo
> 资产升级**（main 2→3 条，README §3 手写类手改路径）：原盘是 M2.6 格式演示品（loop 未建成时
> 手写，第二轮工具链缺终答不可回放），补终答条目后 README §6"completed_tool_roundtrip 承载"
> 承诺才真实兑现；既有条目数断言 1 处随改。
> **执行实录**：交付① 11 盘参数化一次全绿（iso_rag/iso_refund/hitl 三盘**历史首次端到端回放**；
> 两装置自检首红在 AgentEvent seq≥1 构造校验——防呆在工作）；交付② (62) 核对发现注册面证人
> 早已存在（test_module_import_registers_real_hook，M3.9④）=**站 10"零证人"表述系复盘免测试段
> 盲区**（免测试段拍板让复盘对测试面的断言失准——流程教训）；交付③ **影子门再抓盘点漏项**
> （影响面 grep 命中 test_stream_resume.py 后只改了两处注释命中行、漏同文件第三处帧序列断言，
> 影子首跑红——**纪律追加：影响面 grep 命中文件后须读该文件全部相关断言，不只看命中行**，
> "盘点必须全仓无截断"家族第五例、连续第二次拦在交付前）；交付④ 红绿探针**在影子副本执行**
> （本仓探针被权限分类器拦下——影子≡HEAD 等价性以探针前全量 945 passed 为证，本仓 git 零触碰
> 比本仓探针更合红线 6 精神），恰 1 红在 budget 盘 CassetteMismatch（响亮失配比终止断言红得
> 更早）、token_burn 不红（×10 后预算仍先于轮数=行为没变门不误报）；**§3-4 候选① 弃用实证**：
> 注释检索 WHERE tenant_id 在无 key 回放世界不可达（检索恒 fail-open 空集）——红绿改坏点必须
> 落在被测世界真正执行的语句上（M4.0④b 纪律回放版），已入凭证作反面教材。
>
> **M4.4 开工核对/拍板与交付实录（2026-08-03 四交付一天收口，`b5bb4ab`/`8b2e295`/`69959ae`/
> `3b2ebfd`+凭证 `b9ccffb`，测试 945→955；七处裁决全按建议；与本章第五章不符处以本块为准）**：
> 核对过期/缺漏四条：(21) **strong 链实为 qwen3.7-max/qwen-plus**（§2 的 qwen-max/deepseek-v3
> 被模型池 v3 取代；同族偏差论证反而更强=全链同 Qwen）；(22) **chunk 无稳定标识**（自增列）——
> 检索判据落为 document 粒度（ret 用例自带 chunk_source 文件名=唯一穿越重摄取的锚）；
> (23) **计划蓝图漏 eval_cases 的 RLS 前置义务**（M3.3：新表带 tenant_id 必自带 ENABLE+策略）；
> (24) **表设计缺 user_id 列**（e2e/adv 走完整对话需会话身份）。
> 结构偏差五条：(25) 目录用现有 evals/ 弃计划 evalsets/（写作时不知 M3.11 已建）；(26) §5 的
> test_cases_json.py 并入七层 lint（六层随迁+category↔kind 映射层）；(27) seed.jsonl 三依赖
> 随迁实况=lint 重写+fallback_rate 改读+record 脚本仅注释零改动；**用户验收裁决 seed.jsonl
> 封存保留**（README 声明不再被代码读取）；(28) **iso-06 挂起形态计划未预见**——超阈值补券先
> 挂审批，runner 扮演坐席拒单+resume 收尾（站 8 口径⑵推论=第二层防线的正确剧本）；iso-09/10
> approval 面=ci_pinned 特判零花费；(29) judge 与被评**共用唯一 sid**（初版两 sid+LIKE 前缀
> 被冒烟对账否决，见 (32)）。
> **过程事故一桩（如实登记）**：影子排练跑迁移时环境变量名写错（`AEGIS_DATABASE_URL`——
> Settings 无 env_prefix，正确名 `DATABASE_URL`）→ alembic 读 .env **误打 dev 库**（与用户
> 目标状态一致，裁决保持现状、指令块预期改 no-op）；改正后 aegis_shadow 裸库九跳全链自举实证。
> **纪律：影子指库前先核 Settings 环境变量名**。另有转义层事故一枚（heredoc→python 双层解义
> 把 \n 写成真换行断串）——影子门拦下，教训=脚本写码含转义序列时 ast.parse 自检先行。
> **真实批次实录三笔（冒烟先行的价值证明）**：(30) **judge 裸调用 42501**——全项目首个
> tenant_context 之外的网关调用点，计量写 usage_ledger 被 WITH CHECK 拒（(58) 家族第三例、
> 口径行落档当天被踩中）；计量"绝不拖垮请求"兜底首次真实验证（批次照跑仅账缺行）；修=judge
> 流消费包上下文。(31) **判分全 5 分=judge 打分维度零区分度**（如实归因不美化）：种子集是
> M3.12 调优后的行为面，质量信号当前全部来自机器断言面；出区分度两条路=M4.5 扩集加难例+
> spot-check 人工对照（rubrics §4 预言场景实锤）。(32) **`_row_cost` LIKE 前缀跨批撞账**
> （最终批行 cost 恰=账本全量）——对账核查抓获；修=共用唯一 sid 精确匹配，下批起行成本干净
> （本批行 cost 列虚高已在验收记录声明，报告 token 数来自 UsageChunk 实测不受影响）。
> 完整基线 20/20（adv10/e2e7/ret3）、28,650/150,000 token、真实总花费 ¥0.0445、judge 全程
> qwen3.7-max 零 fallback（C36 回显实录）。
>
> **M4.5 开工核对/拍板与交付实录（2026-08-03 三交付收口，`6a4a1c2`/`53d79c8`/`bdc55cc`+凭证，
> 测试 955→958；五处拍板全按建议；与本章第六章不符处以本块为准）**：
> (33) **§3-2 id 规则作废**——实况=细分类前缀（iso-/okb-/ret-/nor-）+七层 lint 映射+eval_runs
> 30 行已按旧 id 串联；扩充续编+新细分类 inj-（injection→adversarial）。(34) "诱导写工具重试"
> 换"冒充系统套内部信息"（前者正确行为的机器判据写不干净——用户让退合规单、攻击只在话术层；
> 后者用 must_not_contain 内部工具名字面即可判=判据原语零扩展）。(35) **四轮批次迭代实录**
> （首批 34/40→39/40→38/40 假绿修正→38/40 稳定）：首批四 fail 恰两两分属 M3.12 判准两侧
> （okb-02/08 判据漏报→信号集三轮反哺／okb-05/07 真编造→judge 1/2 分抓获=区分度首兑现+
> 规则 3 品类二轮扩容）；复跑撞环境状态污染（nor-03=l3 重录消耗 AZ-1002，跑批前复位纪律落
> README §5）与 okb-07 顽固编造（四轮反哺「不支持」修归因链）。(36) **spot-check 预填复核抓
> iso-12 假 pass**：en-dash 绕连字符禁词=字符形态盲区（normalized 尺 +en/em-dash），且字符
> 形态即取证=非复制而是编造撞值（隔离没破）。(37) **绊线架构归位**：okb-05 三轮措辞变体漏报
> 证明词面追逐是猫鼠游戏——machine_verdict 的 e2e fallback 绊线不中改交 judge 终裁（adv 保持
> 机器 fail），实现兑现 README"绊线只管召回"宣称；信号集 13 词冻结。(38) **spot-check 执行
> 形态偏差**：rubrics §4 原设计"用户主评盲评"，实际=用户委托 Claude 异族复评（vs qwen3.7-max
> ——同族偏差在复评侧不存在）+非严格盲评如实声明+用户终裁分歧点；±1 一致率 25/25=100%、
> 分歧 4 条皆颗粒度层。连带观察：iso-08 尾部引导提供他人收件信息=判据外引导面（挂 M4.6/M5）。
> 稳定基线 **38/40=95%**（两条强先验编造样本如实保留——"95% 且能逐条说出那 5%"的简历口径）。
>
> **M4.6 开工核对/拍板与交付实录（2026-08-03 四交付+两冒烟+两正式批一天收口，测试 958→965，
> 四笔 `e16aac3`①/`eae3bdf`②/`2f5e3ef`③/`934e8fc`④ 已推送；与本章第七章不符处以本块为准）**：
> 拍板八项全按建议（P1 80 条 30/40/20/10／P2 双基线／P3 见 (41)／P4 见 (42)／P5 进程内直驱／
> P6 工具题只读／P7 单脚本两相位／**P8 本步全量 AI 直写**——00 §2.1 单步例外第二例（M2.10 后；
> 用户指示"全部由你来做"：代码/测试/实验执行 AI；含 config 两字段生产面改动；**收口时用户追加
> 授权提交推送亦 AI 代跑，并全权委托 M4.7/M4.8**——例外范围扩展至 git 面）。
> (39) **§2/§4 的 `evalsets/` 目录不存在**——M4.4 偏差(25) 延续，问题集落 `evals/cost_questions.json`。
> (40) **「强制指定档」旁路生产不存在**（§2 核对点的答案）：classify/answer_faq 硬编码 fast
> （intent.py:86/129）、`build_agent_spec` 硬编码 standard（agent.py:51）、strong 在线链路无人用；
> 正解=`dataclasses.replace(spec, model_tier=...)`（frozen dataclass replace 重跑 `__post_init__`）
> +直驱 `runtime.run`——生产包零行为改动，run_eval `_execute_real` 是驱动形态先例。
> (41) **P3 计划分账案修正**：每组一租户→**每实验一租户（exp-route/exp-cache，tenant-a 镜像）+
> 组间精确 sid 清单分账**。实锚=`mock_orders.id` 全局主键（models.py:38 无租户维度）→跨租户克隆
> 同号必撞 PK→工具题题面被迫每组不同=「三组同题」最重要控制变量破产；M4.4④ LIKE 撞账已立
> 精确 sid 为对账正解。§3 例名 exp-route-base/exp-route-tiered（两租户名对三组）随之作废。
> (42) **预算居所**：§3"脚本顶部常量 BUDGET_TOKENS=300_000"案作废→config 两字段
> `cost_routing_token_budget`/`cost_cache_token_budget`=600_000（00 §8.0「写死在配置」字面+
> M4.4 `eval_run_token_budget` 先例；600k 经冒烟外推校准——实跑 388k/523k 双双入内，300k 会 partial）。
> (43) **§5 测试预告 3 实收 7**：+文件形状 id 规则/申报分布精确钉死（报告「集合构成」与文件绝不
> 漂移）/工具题订单引用 I1（cost_common 常量=事实源）/与评测集零交集由 §6"grep 抽查"升 CI 断言
> ——沿 eval-lint 层次化先例。`build_cache_traffic` 照 §4 签名；「200 条」=round(140/(1−0.3)) 派生
> 非写死；复述恰 60 **精确成立**（§5"30%±2%"的近似口径作废——生成器按槽位构造，断言精确值）。
> (44) **两冒烟一次全绿**（样本刻意异质：路由=1 FAQ+1 工具题、缓存=四 kind 各一×0.5 复述率）：
> 路由冒烟即现形省钱机制（B 直答 387 token vs A 全 Agent 1443）；缓存冒烟复述 4/4 全命中=
> 跨会话命中实证（缓存 key 无 session_id 的 M1.10 决定在实验②兑现；反面推论：当年混入
> session_id 则实验②降本恒 0% 且无任何报错）。
> (45) **并行跑批×flushdb 冲突排查**：两正式批并行（不同租户/进程、共享出站限流 QPS 余量足）
> 省墙钟约 25 分钟；期间欲预跑全量测试——**tests/conftest.py:23 `flushdb` 会打掉相位 D 的
> 实验缓存条目、烧掉整批费用**，grep 排查后四门推迟到批次后。教训=**与在跑实验共库共 Redis 的
> 任何并发操作，先 grep 破坏性触点（flushdb/DELETE/TRUNCATE）再动手**。
> (46) **正式批实录**：实验① 三组 80/80 零 errored、账本覆盖 sanity 全齐——**vs-strong 74.7%／
> vs-standard 18.9%**（¥0.3544/¥0.1106/¥0.0897；tiered=fast 105 调用 ¥0.0037+standard 68 调用
> ¥0.0860，25 题被 FAQ 直答短路）；实验② 两相位 200/200——**21.9%** @30% 复述假设（¥0.1907→
> ¥0.1489，cached 121 调用）；自检=复述 60/60 全命中/首现 0 误命中/关相位 0 命中（管线确定性
> 实证）；独立复算（LIKE run_tag 异形查询）与两报告逐位吻合。**观察一枚**：30% 复述→21.9% 降本
> ≠等比——复述均匀重抽撞上题目成本异质（闲聊 0.3k vs 工具题 3.2k token），流量构成决定折算率
> （报告 §4 限定语覆盖）。**M4.6 真实调用总账 ¥0.9261**（两冒烟+两正式批+setup embedding；
> chat 937k+embed 9.6k token）。深挖题 461–467；§8.2 第三条勾；顺带观察=§8.2 第一条 trace 行
> M4.1 已达成但复选框未翻，挂 M4.8 对账。
>
> 粒度=**接口级**（plans/README §5）：模块边界/表结构/端点形状给定，函数内细节留 M4.0 走查细化。
> 本计划写作时 **M2.5–M3.12 尚未落地**——文中引用的未来接口一律标【开工核对】；
> 已存在代码的签名均经 2026-07-10 时点源码逐一核实（`文件:行号`）。
> 范围权威：00 §8.1 各步骤行（不扩权不漏项）；口径权威：00 §2.2；冲突裁决序见 plans/README §2。
> **真实调用红线（00 §8.0）**：仅 M4.4 离线评测与 M4.6 成本实验产生真实调用，预算上限各自写死在配置；
> M4.3 回放回归零 token；测试与 CI 全程零真实调用。
> （另有两处一次性例外待用户裁定：M4.2 §6 验收演示 ≤3 轮、M4.7 §5 容器冒烟 1 次——见附A #9。）

---

## §0 开工核对清单（M4.0 动手前逐项核实；任何一项对不上：先停下，把差异报给用户并修订本计划）

| # | 核对项 | 核对方法（仓库根（本 repo）） | 期望 |
|---|---|---|---|
| 1 | **M3 毕业基线**：tag `m3-support` 存在；pytest 收集数与 00 §7 毕业登记一致 | `git tag` / `uv run pytest -q` 末行 | 收集数记为 **基线 B**，本计划各步"新增区间"都叠加在 B 上 |
| 2 | M2.6 回放基建实档：FakeGateway/cassette 的模块路径、类名、匹配键字段名（评审 C10：会话 id + 调用通道 tag + 通道内序号）、**重录流程文档**文件名、**事件等价性归一化规范**（C31）落点 | Glob `aegis/**/*cassette*`、`aegis/**/*fake*`、`docs/**/*replay*` 后 Read | M4.3 全部断言依赖此三件；对不上以实档为准改本计划 M4.3 §2 |
| 3 | cassette 库存盘点：M2.6 手写用例 + M2.11 长对话 + M3.11 L3 行为用例的存放目录与条数 | Glob cassette 目录 | M4.3 manifest 要逐一挂账 |
| 4 | M3.1 落地实况：tenants/users 迁移 revision 与实际列；认证依赖（角色守卫/当前用户）的函数名；月度预算闸门是否已切 tenants 表（00 §10.1 #13 裁决）及"本月"窗口口径 | Read 最新 migration + `aegis/api/` 依赖模块 | M4.1 权限、M4.2 #23 gauge 直接复用，不许凭记忆写 |
| 5 | M3 落地后 import-linter 契约形态（`aegis.api`/`aegis.apps.support`/`aegis.workers` 进层的方式） | Read `pyproject.toml` `[tool.importlinter]`（M2.4 时点为四层：pyproject.toml:49-60） | M4.1 的 `aegis.obs` 要插进同一契约 |
| 6 | M3.10 FastAPI 应用入口路径（如 `aegis.api.main:app`）与路由注册方式 | Read `aegis/api/` | M4.1/M4.2 挂端点、M4.7 容器 CMD 用 |
| 7 | M2.8 出口守卫的 PII 模式表位置与形态 | Grep `PII|正则` in `aegis/runtime/guardrails.py`（M2.8 交付；02 §8 规划名 guards.py 已被缝蓝图修正——m2.8 §3 D1） | M4.1 masker 与它共用同一模式事实源（单点） |
| 8 | 遗留项完成态：#5 kill -9（M2.10 或顺延）、#15 停 PG 演示（M2.12 或顺延）是否已在 M2 收口 | Read 00 §6.3 交付对账 + §10.1 | 未收口者并入 M4.0 范围 |
| 9 | M2.0 决策批中 C5（熔断 provider:model 细化）与 C30（429 配额冷却）的裁决记录——是否有"实现列 M4.0"的承接 | Read 00 §2.2 + §6.3 M2.0 行 | C30 在 00 §2.2 已显式冻结；C5 现状"误伤再细化"，无误伤记录则 M4.0 不做 |
| 10 | M3.11 种子评测集：文件路径、格式、条数（15–20，≥10 隔离对抗 + 5 知识库外） | Glob + Read | M4.4 迁表、M4.5 扩充的输入 |
| 11 | M3.5 检索入口的实际签名（M4.4 检索质量类用例要直接调用它） | Read `aegis/apps/support/rag/`（02 §8 规划位） | 以实装为准 |
| 12 | `RateLimiter` 降级粘滞化的实现模式（try_take 粘滞 + 5s 顺路探针，复盘补丁二，提交 `f18c6a7`）——#29 的施工模板 | Read `aegis/gateway/ratelimit.py` | M4.0 若裁决粘滞化，照此模式同构复制 |
| 13 | C41 首次 PG dump、C21 数据生命周期声明是否已随 M2.0"五段文档声明"完成（00 §6.3 M2.0 行） | Read 00 §6.3 + Grep docs | 未做者并入 M4.7 迁入前置 |
| 14 | 枚举值未漂移：`TerminationReason` 8 成员（spec.py:30-37）、`EventType` 14 成员（events.py:25-38）、`SCHEMA_VERSION = 1`（events.py:16） | Read 两文件 | M4.3 断言字面量的事实源 |
| 15 | `.gitattributes` 行尾规则覆盖 Dockerfile/*.sh（06 §4 坑 2） | Read `.gitattributes` | M4.7 容器化前置 |
| 16 | `docs/` 迁入时点实际文件清单（2026-07-10 实测：顶层 13 个 .md——00–08 共 9 篇 + retro/compare/review/interview 共 4 篇——另 adr/ 7 篇与 plans/；**07 交接手册与 08 代码地图已存在**（00 v1.5 §10.1 #36 落档产物），一并迁入；届时以 ls 为准） | `ls docs/` | M4.7 迁移范围 |
| 17 | reports/ 现有凭证（撰写时 3 件：m1_fault_injection / m2_ratelimit_retest / m2_ratelimit_degraded）+ M2/M3 毕业新增件 | `ls reports/` | M4.8 对账底册 |

---

## 第一章 M4.0 · 开工走查 + M1/M2 遗留归位（规模 M）

### §1 目标与定位

00 §8.1 M4.0 行：开工走查 + 遗留归位（§10.1）——缓存命中 QPS 放大复核（#3）、alembic check/downgrade 往返可选加固（#4）、kill -9 若 M2 顺延在此补（#5）、单请求预算闸门若未补在此收口（#1，**已于 M2.0 完成**，提交 `f176b1e`，`config.py:56` `request_token_budget`——本步只核对不重做）。另按 00 §10.1 挂本步：**#24 CI 阻断式密钥扫描 + 依赖漏洞扫描**（评审 C32）、**#29 Redis 触点粘滞化裁决**（复盘补丁二遗留）。若 #15（停 PG 演示）M2.12 未做，随 #5 一并在此补。
走查动作（00 §2.1 第 6 条）：重读 04 M4 节 + 03 §7 + 00 §8 全章 + 05（选读，评测叙事）；给用户 M4 全景图（步骤地图 + 契约走查 + 首步预告），确认后开工。

### §2 契约事实源

| 消费 | 出处（已核实） |
|---|---|
| 精确缓存 key 与命中路径 | `ExactCache._key`：`aegis:cache:v1:{tenant_id}:{sha256}`，语义本体哈希排除 request_id/session_id/tenant_id/deadline_s（cache.py:38-42）；入库标准 Stop 收尾且含实质内容（cache.py:12-14） |
| 限流粘滞化模板 | `RateLimiter`（factory.py:29 注入 `replicas=s.replica_count`）；粘滞 + 5s 顺路探针模式【开工核对 §0-12】 |
| Redis 客户端快速失败口径 | connect 1s / read 2s / `Retry(NoBackoff(), 1)`（00 §2.2 末行，`core/redis.py` 实装） |
| CI 现有九道门 | checkout→setup-uv→`uv sync --frozen`→ruff format --check→ruff check→mypy→lint-imports→alembic upgrade head→pytest（ci.yml:38-67）；action 一律钉完整 SHA（ci.yml:39-41） |
| dev 依赖组 | import-linter/mypy/pytest/pytest-asyncio/respx/ruff（pyproject.toml:15-23）——pip-audit 加在这里 |

提供给后续：两道新 CI 门（M4.3/M4.4 的流水线在其上叠加）；#29 裁决结果（M4.2 缓存命中指标口径引用）。

### §3 设计决策与口径

1. **#3 缓存命中 QPS 放大复核**（复核而非改码）。事实：缓存查询发生在一切闸门之前（retro-m0-m1 请求旅程口径），命中即返回、不过出站限流——热点问题可以以任意 QPS 消费 Redis 与出口带宽。复核产出=一段落档结论，建议裁决：**命中路径不加限流**——入站限流（M3.2，租户维度）已是命中路径的唯一且足够的闸门，出站限流保护的是供应商配额、命中不消耗配额；结论落 00 §10.1 #3 状态列 + ADR-005 角色 2 一句话。若复核发现 M3 实装的入站限流不覆盖缓存命中路径（如限流在意图路由之后），则升级为 M4.0 修复项。
2. **#4 alembic 往返（可选，建议做小不做大）**：
   - CI 新增一步 `uv run alembic check`（在 upgrade head 之后、pytest 之前）——挡"ORM 改了没生成迁移"的漂移。这个洞真实存在：CI 先 alembic 后 create_all，两条路径对不一致都不报错（tests/conftest.py:56 create_all 是本地兜底，对已存在表 no-op）。
   - downgrade 往返（`downgrade base → upgrade head`）只做**一次性本地验证**、结果落 `reports/m4_alembic_roundtrip.txt`，**不进 CI**（downgrade 清空业务表，CI 里跑在 pytest 前会删掉演示种子数据且拖时长）。
3. **#24 工具选型与 CI 接法**（评审 C32 点名 gitleaks 类 + pip-audit 类，照此选型不另起炉灶）：
   - **gitleaks**：`gitleaks/gitleaks-action@v2`（钉完整 SHA，口径同 ci.yml:39），置于 checkout 之后第一道；checkout 必须 `fetch-depth: 0`（全历史扫描）。仓库根加 `.gitleaks.toml`（初始为空规则集占位，将来豁免 cassette 中的形似密钥占位串）。个人 public 仓库免 license。
   - **pip-audit**：`uv add --dev pip-audit`，CI 在 `uv sync --frozen` 后加 `uv run pip-audit`（审计当前 venv，锁文件即事实源）。发现漏洞默认阻断；确需豁免用 `--ignore-vuln <ID>` 且豁免理由写进 ci.yml 注释。
   - 两步均为**阻断式**（评审 C32 原文口径），不设 continue-on-error。
4. **#29 Redis 触点粘滞化裁决——【用户拍板】**。判定框架（复盘补丁二同款）：
   - (a) 单次故障代价：客户端快速失败后为 connect 1s（连接拒绝时毫秒级）～read 2s 级；
   - (b) 每请求命中次数：熔断（每次调用读状态 + 失败记账）、精确缓存（get，写路径 set）——两触点在热路径上每请求至少各 1 次。**经读码核实：计量（metering.py）纯 PG 路径、全文件无 Redis 触点（record/month_spend 均只经 SessionFactory 走 PostgreSQL，metering.py:88-125），#29 对其天然不适用**——00 §10.1 #29 行"计量影子账本的 Redis 触点"措辞需修订，见附A #10；
   - (c) 放大判据：压测/演示 QPS × (a) × (b) ——10 QPS 下每秒最多白付 ~6s 等待时间片，M5.2 压测（多副本、3 档并发）必然放大成可见的 P99 污染；
   - (d) 粘滞化成本：每触点包一层"降级粘滞 + 5s 顺路探针"访问器 + 3 个单测，模式照抄 RateLimiter（同构，面试可讲一致性），估各半天。
   **建议**：熔断与精确缓存两个每请求热路径触点**做**粘滞化；计量无 Redis 触点（见 (b) 读码结论），无需裁决、无需改动。裁决结果当天登记 00 §10.1 #29（并顺带修订该行措辞，附A #10）。
5. #5/#15 若顺延至此：按 M2.10/M2.12 计划文件（plans/m2.10-recovery-reaper.md、m2.12-m2.13-graduation.md）的对应交付执行，本计划不重复展开——【开工核对 §0-8】。

### §4 实施蓝图

新建/修改文件：

| 文件 | 动作 | 内容 |
|---|---|---|
| `.github/workflows/ci.yml` | 修改 | checkout 加 `fetch-depth: 0`；新增两步：gitleaks（checkout 后）、`uv run pip-audit`（uv sync 后）；`uv run alembic check`（alembic upgrade head 后） |
| `.gitleaks.toml` | 新建 | 占位配置（默认规则集 + 空 allowlist，注释写用途） |
| `pyproject.toml` | 修改 | dev 组加 `pip-audit`（`uv add --dev pip-audit` 自动完成） |
| `aegis/gateway/breaker.py` / `cache.py` | 修改（仅当 #29 裁决"做"） | Redis 访问收口进"粘滞 + 探针"访问器，模式同 ratelimit.py【开工核对 §0-12】（metering.py 无 Redis 触点，不在改动面——§3-4 读码结论） |
| `reports/m4_alembic_roundtrip.txt` | 新建 | downgrade base → upgrade head 全输出 + 结论一行 |

关键不变量：
- gitleaks/pip-audit 两步失败必须让整个 workflow 红（阻断式）；
- #29 粘滞化不许改变降级语义本身（熔断 fail-open + 本地计数、缓存降级=miss——ADR-005 降级契约），只改"降级期是否还反复撞死 Redis"；
- 生产代码（gateway 两文件）由用户亲手敲，AI 只给完整代码+讲解（00 §2.1 第 1 条）。

### §5 测试蓝图

- `tests/gateway/test_breaker_sticky.py`（新建，仅当 #29 裁决"做"）：`test_degraded_sticky_skips_redis`（降级后第二次调用不再触 Redis——用 dead_r 夹具计数）、`test_probe_after_interval_recovers`（可注入时钟推进 5s，探针成功即回主路径）、`test_probe_failure_extends_stickiness`（探针失败顺延）。缓存触点同款三测 `tests/gateway/test_cache_sticky.py`。命名与注入手法参照复盘补丁二在 ratelimit 测试中的三单测【开工核对 §0-12 顺带盘点其测试文件名】。
- dead_r 夹具直接复用（tests/conftest.py:28-40，指向 6399 无人端口、NoBackoff）。
- CI 门（gitleaks/pip-audit/alembic check）无 pytest 用例——红绿验证走 §6。
- 预期新增：#29 实装（熔断+缓存，即全部有 Redis 触点的对象）= **6 个**；#29 裁决"不做"且 #5/#15 已收口 = **0 个**（本步纯配置+复核）。

### §6 验收对账清单

- [ ] M4 全景图已讲、用户确认开工；
- [ ] #3 复核结论落档（00 #3 状态翻转 + ADR-005 一句话）；
- [ ] `uv run alembic check` 在 CI 绿；roundtrip 凭证落 reports/（若做 #4）；
- [ ] gitleaks 红绿验证：本地临时分支塞一个假 `sk-` 形串提交 → push 该分支 → CI 红 → 删分支（**绝不能用真 key 验证**）；
- [ ] pip-audit 在 CI 绿（或豁免清单落 ci.yml 注释）；
- [ ] #29 裁决登记 00 §10.1；若实装：新单测全绿、粘滞语义与 ratelimit 同构；
- [ ] #5/#15 若在此补：对应计划文件验收项全勾；
- [ ] pytest 收集数 = 基线 B + 本步新增（逐项点名对账）。

### §7 陷阱与常见错误（症状 → 原因 → 正解）

1. gitleaks 只扫出最新提交的泄漏 → checkout 默认浅克隆（depth=1）→ `fetch-depth: 0` 全历史。
2. pip-audit 报"找不到包"或审计了错误环境 → 直接 `pip-audit` 用了全局解释器 → 必须 `uv run pip-audit`。
3. `alembic check` 在本地报连接失败 → 它要跑 env.py 真连库（migrations/env.py:17 用 get_settings().database_url）→ 先 `docker compose -f deploy/docker-compose.yml up -d`；CI 中该步必须在 service 容器健康后（现有位置天然满足）。
4. 把 downgrade 往返塞进 CI → 每次提交清库、种子数据蒸发、时长翻倍 → 一次性本地验证 + 凭证落盘。
5. 弱模型高发：把 #29 当"已裁决"直接改两处生产代码 → #29 是【用户拍板】项 → 先给裁决材料等拍板；粘滞化时顺手"重构"ratelimit.py 统一抽象 → 越范围，M4.0 只加不改既有主路径。
6. 用真实 DASHSCOPE key 验证 gitleaks 红 → key 进历史 = 只能换 key（06 §6 铁律）→ 用假串 `sk-fake…` 且在临时分支。
7. 交付正文被工具调用吞掉（M2.3① 事故）→ 生产代码正文必须放在回合最末、所有工具调用之后。

### §8 指令块模板（仓库根执行；每个交付一次；标注预期）

```powershell
uv run ruff format .        # 预期：N files left unchanged（0 reformatted）
uv run ruff check .         # 预期：All checks passed!
uv run pytest -q            # 预期：基线 B + 本步已交付新增数 passed
uv run mypy .               # 预期：Success: no issues found
uv run lint-imports         # 预期：Contracts: 1 kept, 0 broken（M3 后契约数以实况为准）
git add .github/workflows/ci.yml .gitleaks.toml pyproject.toml uv.lock
git commit -m "ci: 阻断式密钥扫描(gitleaks)+依赖漏洞扫描(pip-audit)+alembic check" -m "评审 C32/00 §10.1 #24：密钥进历史不可逆，扫描必须阻断式；alembic check 补上 ORM/迁移漂移无人报错的洞"
git push                    # 预期：CI 全绿（含两道新门）
```

（#29 实装为独立提交：`git add aegis/gateway/breaker.py aegis/gateway/cache.py tests/gateway/test_*_sticky.py`，message 写"降级粘滞化：故障绝不拖垮请求（复盘补丁二同款，#29 裁决）"。）

### §9 完成后动作

00 §10.1 #3/#4/#5/#24/#29（及 #15 若涉及）状态翻转；00 §6.3 式对账表在 §8 章下开 M4 实际交付表；本计划头部若有偏差先记一行；深挖题追加 `interview-questions.md`（候选：为什么密钥扫描必须阻断式且扫全历史；粘滞化与熔断半开为什么同构）；记忆文件项目状态行更新。

---

## 第二章 M4.1 · trace 查询 API（规模 M）

### §1 目标与定位

00 §8.1 M4.1 行：凭 trace_id 还原全链路每步输入输出与耗时（JSON；查看页 v2）；权限按端点×角色矩阵（仅 operator/admin、限本租户）；**展示层统一 PII masker**——events 存原文的口径（02 §3）在此兑现（02 §7.3）。自研 trace 而非 OTel 是刻意选择（04 M4 节 C37 落档段：session=trace、run=root span、事件=span event；obs 查询 API 是稳定接口，v2 可加 OTel 导出器）——面试叙事直接背此段。

### §2 契约事实源

消费（已核实）：
- `trace_id ≡ session_id`（00 §2.2 X5 三层 ID 模型；events 表有 run_id 列——migration 74da3bf5d6ab:43-55）；
- `EventRecord`：id/session_id/run_id/seq/type/schema_version/payload(JSONB 原文)/created_at，`(session_id, seq)` 唯一（store.py:92-109）；
- `ToolInvocationRecord.latency_ms`（store.py:126-142，executor 实测耗时）、`event_id` UNIQUE = tool_call 事件 id；
- `UsageRecord`：session_id 可空、prompt/completion_tokens、cached、cost Decimal（metering.py:38-49）；
- `SessionFactory = Callable[[], AsyncSession]`（store.py:168，按形状声明——obs 同样按此注入）；
- `EventType` 14 类（events.py:25-38）、`TerminationReason` 8 值（spec.py:30-37，loop_terminated payload 的 reason 域）；
- 权限矩阵（02 §7.1）：`GET /v1/sessions/{id}/events` user ❌（trace 含 system prompt/内部工具名，开放=出口防护旁路）、operator ✅ 仅本租户、admin ✅；
- M3.1 认证依赖与 M3 路由注册方式【开工核对 §0-4/§0-6】；M2.8 PII 模式表【开工核对 §0-7】。

提供：`aegis/obs/` 包（M4.2 复用其分层位置与 SessionFactory 注入模式）；masker 单点（日志/导出同用，02 §7.3）。

### §3 设计决策与口径

1. **端点复用 02 §9 既有名**：`GET /v1/sessions/{id}/events`，不发明新路径。M3 若已落权限骨架版，M4.1 = 升级其响应为完整 trace 视图 + masker；若未落，M4.1 全建【开工核对 §0-6】。
2. **权限判定顺序**（有唯一合理答案，定）：先角色（user → 403，矩阵 ❌ 是角色禁令）→ 再租户归属（operator 且 `session.tenant_id != operator.tenant_id` → **404**）。403/404 分工理由：角色不足是公开规则（403 无信息泄漏）；跨租户探测不能确认会话存在性（404 防枚举）。02 §7.1 只规定了"仅本租户"，具体状态码是本计划裁决。
3. **v1 恒脱敏、无 raw 通道**（定）：单一代码路径、02 §7.3"展示层同一 masker"口径；raw 导出列 v2。访问审计 v1 最小形态 = 结构化日志一行（operator_id、session_id、UTC 时间）——02 §7.3"留审计"的兑现，独立审计表列 v2。
4. **耗时口径**（定）：tool_result/tool_error 事件的 duration_ms 取 `tool_invocations.latency_ms`（executor 实测，最准）；llm_result 的 duration_ms = 同 run 内与前一 llm_call 事件的 `created_at` 差（DB 时钟，server_default now()——metering.py:6 同一报时员哲学）。配不上对的事件 duration_ms = null，不猜。
5. **masker 模式事实源单点**：与 M2.8 出口守卫共用同一模式表——若 M2.8 模式表在 `aegis/runtime/guardrails.py`（m2.8 §3 D1 定案文件名），obs 直接 import（分层 obs→runtime 合法，见 6）；若形态不适配，抽到 obs 后让 guardrails 反向引用是**禁止**的（runtime 不许 import obs）——此时复制模式常量并在两处注释互指【开工核对 §0-7】。
6. **分层**：新顶层包 `aegis.obs`，插入 import-linter 契约在 `aegis.apps` 之上或同层（obs 需 import runtime 的 ORM 与 gateway 的 UsageRecord；api 层 import obs）。契约实际写法以 M3 落地后的层清单为基座【开工核对 §0-5】；同层互不 import 的写法查 import-linter 文档现认，不凭记忆。

### §4 实施蓝图

新建：`aegis/obs/__init__.py`、`aegis/obs/masking.py`、`aegis/obs/trace.py`；修改：M3 的路由模块（挂端点）、`pyproject.toml`（import-linter 层清单）。

```python
# aegis/obs/masking.py —— 展示层 PII 单点（02 §7.3）
_MASK_RULES: tuple[tuple[str, str], ...] = (
    ("id_card", r"\d{17}[\dXx]"),          # 必须排在 phone 前：18 位号含 11 位子串
    ("phone", r"1[3-9]\d{9}"),
    ("email", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)  # 与 M2.8 守卫模式表对齐【开工核对 §0-7】

def mask_text(text: str) -> str: ...            # 命中替换为 ***{label}***
def mask_payload(payload: Mapping[str, Any]) -> dict[str, Any]: ...  # 递归遍历,只处理 str 叶子
```

```python
# aegis/obs/trace.py
class TraceEvent(BaseModel):
    seq: int; run_id: str; type: str
    created_at: datetime
    payload: dict[str, Any]            # 已过 mask_payload
    duration_ms: int | None = None

class TraceRun(BaseModel):
    run_id: str
    termination_reason: str | None     # loop_terminated payload 的 reason，无则 None
    events: list[TraceEvent]

class TraceUsage(BaseModel):
    requests: int; prompt_tokens: int; completion_tokens: int
    cached_hits: int; cost: Decimal

class TraceView(BaseModel):
    trace_id: str; session_id: str; tenant_id: str; run_state: str
    runs: list[TraceRun]; usage: TraceUsage

class TraceAssembler:
    def __init__(self, factory: SessionFactory) -> None: ...
    async def assemble(self, session_id: str, *, tenant_id: str) -> TraceView | None: ...
```

`assemble` 算法（编号步骤）：
1. 查 sessions 行；不存在或 `tenant_id` 不符 → 返回 `None`（api 层译 404）；
2. 拉 events `WHERE session_id=? ORDER BY seq`（唯一约束底层索引即查询路径）；
3. 按 run_id 分组，保持首次出现顺序（事件已按 seq 全序，run 天然不交错）；
4. 配耗时：遍历中记住每 run 最近一条 llm_call 的 created_at；tool_result/tool_error 按 `event_id`（=tool_call 事件 id？注意：投影行的 event_id 是 **tool_call** 事件 id——store.py:133 注释）批量查 tool_invocations 的 latency_ms，回填到对应 tool_result 事件【开工核对：tool_result 事件 payload 里携带的关联 id 字段名，以 M2.2/M2.4 payload 契约实档为准】；
5. 每事件 payload 过 `mask_payload`；
6. usage：`SELECT count(*), sum(prompt_tokens), sum(completion_tokens), sum(cost), count(*) FILTER (WHERE cached) FROM usage_ledger WHERE session_id=?`（报表用裸 SQL——00 §2.2 数据访问口径）；
7. termination_reason：各 run 最后一条 loop_terminated 事件的 `payload["reason"]`。

API 层：路由 handler 只做——角色守卫（M3.1 依赖）→ 调 assemble → None→404 → 审计日志一行 → 返回 TraceView。

关键不变量：masker 绝不抛异常（内部 try/except，失败整段替换为 `"<mask_error>"`——展示层不许拖垮）；events 原文只在 payload 域内被脱敏，seq/type/时间等结构字段原样；assemble 是只读操作，零写入。

### §5 测试蓝图

先读 `tests/runtime/test_executor_exec.py` 学风格（中文一句话 docstring、直用 db_session_factory、断言库表实况）。

| 文件 | 建议测试函数 | 断言要点 |
|---|---|---|
| `tests/obs/test_masking.py`（新建） | `test_masks_phone` / `test_masks_email` / `test_masks_id_card_before_phone`（18 位号不被拆成 11 位命中）/ `test_mask_payload_recursive`（嵌套 dict/list 内 str 叶子被处理）/ `test_mask_never_raises`（诡异输入返回占位不抛） | 纯函数，无夹具 |
| `tests/obs/test_trace_assembler.py`（新建） | `test_assemble_orders_events_by_seq` / `test_events_grouped_by_run` / `test_llm_duration_from_call_result_pair` / `test_tool_duration_from_invocation_latency` / `test_usage_aggregated_from_ledger`（含 cached_hits）/ `test_cross_tenant_returns_none` / `test_payload_masked_in_output`（造含手机号 payload） | 造数据**走 `EventWriter.open/append` 真实路径**（store.py:320/338）而非裸 INSERT——投影同事务派生与生产一致；ledger 行用 ORM 构造 |
| `tests/api/test_trace_endpoint.py`（新建或并入 M3 的 api 测试目录，以 M3 布局为准） | `test_end_user_403` / `test_operator_other_tenant_404` / `test_operator_same_tenant_ok_and_masked` / `test_admin_ok` | 认证夹具复用 M3【开工核对 §0-4】 |

fixture：复用 `db_session_factory`（tests/conftest.py:70-78，savepoint 隔离）。预期新增：**14–18 个**。

### §6 验收对账清单

- [ ] 00 §8.2 第一条达成：凭 trace_id 还原任一会话每步输入输出与耗时（拿一个 M3 演示会话实操，输出样例存 `reports/m4_trace_sample.json`）；
- [ ] 四角色路径各有测试（user 403 / operator 跨租户 404 / operator 本租户 masked / admin）；
- [ ] payload 出口无裸 PII（测试钉死）；masker 与 M2.8 模式表单点关系成立；
- [ ] import-linter 绿（obs 入层后）；
- [ ] pytest = 基线 B + M4.0 新增 + 本步 14–18，逐项点名对账。

### §7 陷阱与常见错误

1. llm 耗时全为 0 → PG `now()` 是**事务开始时间**，同事务写多事件时间戳冻结 → EventWriter 每 append 独立事务（现状即如此，store.py:338 注释"返回时已 durably committed"），别为"优化"把多事件合并进一个事务；
2. duration 用 Python 墙钟现算 → 回放/重启后不可复现且与 DB 时钟混用 → 一律 DB created_at 与 latency_ms；
3. 把 masker 挂进 events **写**路径 → 违反"events 存原文是恢复事实源"（02 §3）→ 脱敏只在展示层出口；
4. operator 跨租户返回 403 → 泄漏"该会话存在" → 404（本计划 §3-2 裁决）；
5. 身份证/手机号规则顺序反了 → 18 位串先被 11 位 phone 规则腰斩 → 长模式在前（蓝图已排序，别"整理"回字母序）;
6. 弱模型高发：凭记忆写 M3 认证依赖名/路由注册方式 → 先 Read `aegis/api/` 实档（§0-4/6）；把 trace 端点做成查看页（HTML）→ 04 裁剪表：查看页 v2，v1 只 JSON。

### §8 指令块模板

```powershell
uv run ruff format .   # N files left unchanged
uv run ruff check .    # All checks passed!
uv run pytest -q       # 基线 B + M4.0 增量 + 14–18 passed
uv run mypy .          # Success: no issues found
uv run lint-imports    # Contracts: … kept, 0 broken（obs 入层后契约仍单向）
git add aegis/obs pyproject.toml tests/obs <M3 路由文件> tests/api/test_trace_endpoint.py
git commit -m "feat(obs): trace 查询 API——事件流还原+展示层 PII 单点脱敏" -m "events 存原文口径在展示层兑现(02 §7.3)；trace_id≡session_id(X5)；耗时取 DB 时钟与 executor 实测"
git push
```

### §9 完成后动作

00 §8.2 第一条可勾预备；更新 `docs\08-code-map.md` 对应节（新增 aegis/obs 包——#36 维护纪律，00 §13 第 5 项）；深挖题（候选：为什么自研 trace 不接 OTel——背 04 C37 段；403/404 分工；为什么脱敏不在写路径）；masker 单点位置登记进 00 §2.2 若形成新口径。

---

## 第三章 M4.2 · Prometheus 指标 + /metrics（规模 M）

### §1 目标与定位

00 §8.1 M4.2 行 + 04 M4：成功率/P50/P99/token/工具成功率/转人工率/缓存命中率；**#23 租户预算使用率 gauge**（评审 C40：租户预算只有到线拦截无逼近告警，gauge 是逼近告警最小形态，通知渠道 v2）。`GET /metrics` 端点在 02 §9 已列（与 /healthz 并行）。

### §2 契约事实源

- `usage_ledger` 列（metering.py:38-49）：tenant_id/tier/prompt_tokens/completion_tokens/**cached**/cost/created_at；缓存命中也记账（provider="cache", cost=0——retro 计量口径），append-only → SUM 单调；
- `tool_invocations`：tool_name/status（running/succeeded/failed，store.py:50-55）；
- `events`：type 含 `handoff`/`loop_terminated`（events.py:37-38），**无 tenant_id 列**——租户维度须 join sessions（74da3bf5d6ab:43-55 vs :69-85）；
- `TerminationReason` 值集（spec.py:30-37）——成功率分子 = reason=completed；
- tenants.token_budget_monthly 独立列（02 §3；实际列名【开工核对 §0-4】）；月度窗口与 M3.1 闸门同口径【开工核对 §0-4】；
- 依赖新增：`prometheus-client`（运行时依赖，`uv add prometheus-client`）。

### §3 设计决策与口径

1. **双源架构**（定，理由=分层）：
   - **进程内观测**（Counter/Histogram）：只覆盖 API 层能看到的东西——HTTP 请求数、chat 首 token 延迟、chat 全程延迟。由 api 层中间件/路由计时，不给 L1/L2 塞 metrics 依赖（runtime/gateway 不许 import obs）。
   - **scrape 时 DB 派生**（Gauge）：token/成本/工具成功率/转人工率/缓存命中率/预算使用率——事实源就是账本与事件表（与"events 即 trace 源"同一哲学），scrape 时现算，演示级数据量毫秒级。
2. **指标清单（逐个，名字/类型/labels/来源/口径）**：

| # | 指标名 | 类型 | labels | 来源 | 04 对应 |
|---|---|---|---|---|---|
| 1 | `aegis_http_requests` | Counter | path, method, status | api 中间件 | 成功率（HTTP 层） |
| 2 | `aegis_chat_first_token_seconds` | Histogram | tenant_id | chat 路由首帧计时 | P50/P99（与 M3.12 首 token <2.5s、M5.2 压测同口径） |
| 3 | `aegis_chat_request_seconds` | Histogram | tenant_id | chat 路由全程 | P50/P99 |
| 4 | `aegis_runs_terminated` | Gauge（累计） | tenant_id, reason | events(loop_terminated) join sessions | 成功率（业务层：completed/全部） |
| 5 | `aegis_llm_tokens` | Gauge（累计） | tenant_id, tier, kind∈{prompt,completion} | usage_ledger SUM | token |
| 6 | `aegis_llm_cost_yuan` | Gauge（累计） | tenant_id | usage_ledger SUM(cost) | —（04/00 清单无"成本"项，本计划新增；理由：与 #23 预算 gauge 及 M4.6 成本对账同源 ledger、代价一条 SQL——保留与否随 §3-5 类口径一并向用户报备） |
| 7 | `aegis_tool_invocations` | Gauge（累计） | tool_name, status | tool_invocations count | 工具成功率 |
| 8 | `aegis_handoffs` | Gauge（累计） | tenant_id | events(type=handoff) join sessions | 转人工率（分子；分母用 #4，PromQL 算比率） |
| 9 | `aegis_cache_requests` | Gauge（累计） | result∈{hit,miss} | usage_ledger：cached=true 为 hit，false 为 miss | 缓存命中率 |
| 10 | `aegis_tenant_budget_used_ratio` | Gauge | tenant_id | 本月 SUM(prompt+completion) / tenants.token_budget_monthly | **#23** |

   口径注记（写进模块 docstring）：比率一律不预计算——导出原始计数，比率在 PromQL/查看侧算（Prometheus 惯例）；DB 派生指标是**跨进程重启单调的累计值**，用 Gauge 承载并在 HELP 文本声明"cumulative, safe for rate()"；budget=0（关闭）的租户不导出 #10 样本。
3. **自有 registry**（定）：模块级 `REGISTRY = CollectorRegistry()`，不用全局默认——躲开 prometheus-client 重复注册 ValueError（pytest 反复 import 的经典炸点），`/metrics` 用 `generate_latest(REGISTRY)`。
4. **不用 custom Collector**（定）：prometheus-client 的 `collect()` 是同步接口，塞不进 async DB 查询；改用"scrape 前刷新"——`/metrics` handler 先 `await refresh_db_metrics(...)` 再 render。
5. **/metrics 认证口径【用户拍板】**（02 §7.1 端点×角色矩阵未覆盖该端点——附A #7；权限矩阵空白处的补位是口径决策，00 §2.1 第 1 条归用户）。建议：v1 无认证 + 端口全程只绑 127.0.0.1（00 §2.2 安全底线）+ "生产应内网隔离或加 basic auth"一句话进模块 docstring；拍板后同步 02 §7.1 补行（附A #7）。
6. #10 的"本月"SQL 与 M3.1 月度闸门**共用同一实现**（同一函数或同一 SQL 常量）——两处口径漂移=告警与拦截对不上【开工核对 §0-4】。

### §4 实施蓝图

新建：`aegis/obs/metrics.py`、api 路由挂 `/metrics`（M3 路由布局【开工核对 §0-6】）；修改：`pyproject.toml`（依赖 + import-linter 无需再动，M4.1 已入层）。

```python
# aegis/obs/metrics.py
REGISTRY: CollectorRegistry = CollectorRegistry()
HTTP_REQUESTS: Counter = Counter("aegis_http_requests", "...", ["path", "method", "status"], registry=REGISTRY)
CHAT_FIRST_TOKEN_S: Histogram = Histogram(
    "aegis_chat_first_token_seconds", "...", ["tenant_id"], registry=REGISTRY,
    buckets=(0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 5.0, 10.0, 30.0),  # 2.5 桶界=M3 验收阈值
)
CHAT_REQUEST_S: Histogram = Histogram(...)  # buckets 上限放宽到 60
# DB 派生 Gauge 族（#4–#10）同 registry 声明 …

async def refresh_db_metrics(factory: SessionFactory) -> None:
    """scrape 前刷新：5–6 条聚合裸 SQL（00 §2.2 报表口径），任何一条失败→该族跳过+日志，绝不 500。"""

def render() -> tuple[bytes, str]:
    """返回 (generate_latest(REGISTRY), CONTENT_TYPE_LATEST)。"""
```

`/metrics` handler 算法：1) `await refresh_db_metrics(get_session_factory())`；2) `body, ctype = render()`；3) `Response(body, media_type=ctype)`。
中间件：请求前后计时 → `HTTP_REQUESTS.labels(...).inc()`；chat 路由内在产出首帧处 `CHAT_FIRST_TOKEN_S.observe(...)`（SSE 流式下的首帧时点以 M3.10 实装为准【开工核对 §0-6】）。

关键不变量：refresh 失败绝不拖垮 scrape（fail-safe，留上次值）；#10 与月度闸门同一 SQL 单点；path label 用路由模板（`/v1/sessions/{id}/events`）不用真实路径（防 label 基数爆炸）。

### §5 测试蓝图

| 文件 | 建议测试函数 | 断言要点 |
|---|---|---|
| `tests/obs/test_metrics.py`（新建） | `test_refresh_tokens_and_cost_from_ledger`（造 ledger 3 行 → gauge 值逐个对）/ `test_cache_hit_miss_split`（cached 真假各造）/ `test_tool_invocation_counts_by_status` / `test_runs_terminated_joins_tenant`（events 无 tenant_id，验证 join 正确）/ `test_budget_ratio`（budget=1000、用量 600 → 0.6）/ `test_budget_zero_not_exported`（无该租户样本）/ `test_refresh_db_down_does_not_raise`（工厂抛错 → 不抛、日志留痕） | db_session_factory 复用；gauge 读值用 `REGISTRY.get_sample_value(name, labels)` |
| `tests/api/test_metrics_endpoint.py`（新建） | `test_metrics_exposition_contains_families`（GET /metrics 文本含 10 族名）/ `test_scrape_is_readonly`（scrape 前后表行数不变） | M3 的 api 测试 client 夹具复用【开工核对 §0-4】 |

预期新增：**9–13 个**。注意：Histogram 中间件的时序数值**不做阈值断言**（时序敏感断言不进 CI——00 §2.2 测试纪律），只断"observe 发生过"（sample count ≥1）。

### §6 验收对账清单

- [ ] 10 个指标族全部出现在 `GET /metrics` 输出（curl 实拍存 `reports/m4_metrics_sample.txt`）；
- [ ] #23 gauge：演示租户设小预算、跑几轮对话、ratio 肉眼可见上升（凭证同上）。**注意**：此演示是 M4.4/M4.6 之外的真实调用，与 00 §8.0 字面口径有张力——见附A #9，执行前与用户确认，轮数写死 **≤3 轮**且在演示租户小预算内；
- [ ] refresh 失败 fail-safe 有测试；比率不预计算口径成立；
- [ ] pytest = 前序累计 + 9–13。

### §7 陷阱与常见错误

1. 测试第二次 import 报 `Duplicated timeseries in CollectorRegistry` → prometheus-client 全局默认 registry + 模块重复注册 → 自有 REGISTRY 且指标只在模块顶层声明一次；
2. 想在 custom Collector.collect() 里 `await` → 该接口是同步的 → "scrape 前刷新"模式（§3-4）；
3. 转人工率/成功率导出成预算好的百分比 → 两个时间窗对不上、无法 rate() → 只导出计数，比率查询侧算；
4. events 按 tenant 聚合时直接 `WHERE tenant_id` → events 表**没有** tenant_id 列（74da3bf5d6ab:43-55）→ join sessions；
5. path label 用了真实 URL（含 session id）→ label 基数爆炸、Prometheus 内存事故 → 路由模板名；
6. `cached` 列以为有 DB 默认 → ORM 侧 default（metering.py:47），裸 SQL 造数必须显式给值（schema 素材包 A.8 通用陷阱）；
7. 弱模型高发：把 metrics 打点塞进 gateway/runtime → 反向依赖，lint-imports 红 → 双源架构（§3-1）；顺手把 /healthz 改造 → 越范围。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check .   # unchanged / All checks passed!
uv run pytest -q                              # 前序累计 + 9–13 passed
uv run mypy . ; uv run lint-imports           # Success / kept
git add aegis/obs/metrics.py <api 路由文件> tests/obs/test_metrics.py tests/api/test_metrics_endpoint.py pyproject.toml uv.lock
git commit -m "feat(obs): /metrics 十族指标+租户预算使用率 gauge" -m "评审 C40/#23：到线拦截之外补逼近告警最小形态；DB 派生+进程内双源，分层不破坏"
git push
```

### §9 完成后动作

00 §10.1 #23 翻 ✅；更新 `docs\08-code-map.md` 对应节（obs/metrics.py 与 /metrics 端点——#36 维护纪律）；深挖题（候选：为什么比率不预计算；DB 派生指标为什么用 Gauge 承载累计值；label 基数为什么是运维事故源）；`reports/m4_metrics_sample.txt` 登记。

---

## 第四章 M4.3 · CI 回放回归流水线（规模 L）

### §1 目标与定位

00 §8.1 M4.3 行：每次提交**零 token**；断言**行为轨迹**（终止原因、工具调用序列、隔离/预算硬约束）；prompt 变更 PR 必须附重录 diff（重录流程 M2.6 已定义）；cassette 输入 = M2.6 手写 + M2.11 长对话 + M3.11 L3 行为用例；**红绿有效性验证：故意改坏一个硬约束，CI 必须变红**。评测双流水线之一（04 M4：与离线评测目的不同不可混——回放测**行为**，真实调用测**质量**，03 §7 末段同口径）。

### §2 契约事实源

- 回放契约（03 §7:196-198）：FakeGateway 匹配键=会话 id+轮次（非 prompt 哈希）；回放回归断言行为轨迹，回答质量归离线评测；
- C10 定稿口径（评审 review:160-167，M2.6 落地）：匹配键=（session_id, 调用通道 tag, 通道内序号），重录触发条件="调用结构变更"与"prompt 变更"**并列**；
- C31：事件等价性归一化规范（哪些字段参与断言、哪些豁免——时间戳/事件 id 等），M2.12 与 M4.3 共用；
- `TerminationReason` 字面量（spec.py:30-37）、`EventType` 字面量（events.py:25-38）——断言只许 import 枚举，不写裸字符串；
- FakeGateway/cassette 实档、归一化规范落点、三来源 cassette 清单：【开工核对 §0-2/§0-3】；
- CI 现状：pytest 已是第九道门（ci.yml:66-67）——回放测试进 tests/ 即自动进 CI，**不加新 workflow**。

### §3 设计决策与口径

1. **组织形态**（定）：`tests/replay/` 目录 + 单一 **manifest**（`tests/replay/expectations.json`）集中登记每个 cassette 的期望行为。选 manifest 不选 sidecar 文件：一处盘点、配"完整性测试"（每个 cassette 必须有条目）后弱模型漏挂立刻红。
2. **三类行为断言的定义**（本步核心交付）：
   - **终止原因**：回放 run 的 loop_terminated 事件 `payload["reason"] == expectations["termination_reason"]`（TerminationReason 值）；
   - **工具调用序列**：从事件流提取 `[(tool_name, outcome), …]` 有序列表逐项相等，outcome ∈ {ok, error}（tool_result/tool_error 二分）；
   - **隔离/预算硬约束**：两种断言原语——`forbidden_output`（整条事件流的文本域**不得出现**指定子串，如 B 租户专有语料标记、他人手机号）与 `required_event_types`（必须出现，如对抗用例必须走到 handoff/兜底）。预算类用例断 termination_reason=token_budget_exceeded + usage 不超上限（cassette 录制时预算已写死——M3.11 口径）。
3. **零 token 的双保险**（定）：a) 回放测试只注入 FakeGateway；b) CI 环境无 DASHSCOPE_API_KEY（现状即无 secret），真调用必然 401 炸红。不额外做 socket 禁用夹具（M2.6 FakeGateway 不发网络【开工核对 §0-2】，再加禁网层是注水）。
4. **红绿有效性验证**（一次性流程，不进代码库主干）：本地临时改坏一个硬约束 → 跑 `uv run pytest tests/replay -q` 必红 → 还原 → 全过程（改了什么、哪些用例红、还原确认）落 `reports/m4_replay_redgreen.txt`。候选改坏点（二选一，视 M3 实装）：① 把检索的 `WHERE tenant_id` 条件注释（隔离约束）；② 把 LoopPolicy 会话预算调成 10 倍（预算约束）。**绝不把坏代码提交/推送**。
   **手法与 00 口径的对齐【用户拍板】**：00 §8.1 M4.3 行与 §8.2 第二条字面是"CI 必须变红"。本地红=CI 红的等价性依据：CI 第九道门跑全量 `uv run pytest`（ci.yml:66-67，无路径过滤），tests/replay 收进即跑。若用户要求字面 CI 红凭证，改用 M4.0 §6 gitleaks 同款手法（临时分支 push → CI 红 → 删分支，不触碰已推送历史）；采用本地手法则把该等价性解释登记进 00（当天）。
5. **prompt 变更 PR 流程**（纪律+文档，不做自动检测——检测"prompt 是否变更"的规则脆，v1 不值）：在 M2.6 的重录流程文档【开工核对 §0-2 实档名】追加一节"PR 纪律"：触发条件（prompt 变更 **或** 调用结构变更——C10 并列口径）→ 跑录制脚本（预算上限写死）→ `git diff --stat` cassette 变更 → PR 描述附 diff 摘要 + 本次录制 token/费用 → 评审人核对期望行为是否需同步改 manifest。
6. expectations 的填写纪律（定）：期望值**先于录制**从用例设计推导（M3.11 用例本就带期望行为），不许"跑一遍把实际输出抄成期望"——那是快照不是回归。

### §4 实施蓝图

新建：`tests/replay/conftest.py`、`tests/replay/expectations.json`、`tests/replay/test_behavior_regression.py`；修改：重录流程文档（追加 PR 纪律节）；新建凭证 `reports/m4_replay_redgreen.txt`。

manifest 条目形状（key=cassette 相对路径，**统一 POSIX 斜杠**）：

```json
{
  "cassettes/l3/cross_tenant_probe.json": {
    "termination_reason": "completed",
    "tool_sequence": [["orders_lookup", "ok"]],
    "forbidden_output": ["鲜丰会员规则"],
    "required_event_types": ["handoff"]
  }
}
```

（`termination_reason` 必填；其余三键可缺省=不断言该维度。）

```python
# tests/replay/conftest.py
def load_manifest() -> dict[str, dict[str, Any]]: ...
async def replay_session(cassette_path: str) -> list[AgentEvent]:
    """装 FakeGateway 回放该 cassette 对应会话，返回归一化后的事件序列（C31 规范）。
    组装方式照抄 M2.12 回放一致性测试的既有装置【开工核对 §0-2】。"""
```

```python
# tests/replay/test_behavior_regression.py  伪代码骨架（≤15 行）
MANIFEST = load_manifest()

def test_every_cassette_has_expectation():
    on_disk = {POSIX 相对路径 for 全部 cassette 文件}
    assert on_disk == set(MANIFEST)          # 双向：多录漏挂、条目悬空都红

@pytest.mark.parametrize("path,exp", MANIFEST.items())
async def test_behavior_trace(path, exp):
    events = await replay_session(path)
    assert last_loop_terminated(events).payload["reason"] == exp["termination_reason"]
    if "tool_sequence" in exp:
        assert extract_tool_sequence(events) == [tuple(x) for x in exp["tool_sequence"]]
    for banned in exp.get("forbidden_output", []):
        assert banned not in dump_text(events)      # 全事件流文本域
    for etype in exp.get("required_event_types", []):
        assert any(e.type == EventType(etype) for e in events)
```

`extract_tool_sequence(events) -> list[tuple[str, str]]`：遍历事件，tool_result → `(payload 中工具名, "ok")`，tool_error → `(…, "error")`（payload 字段名以 M2.2 投影契约实档为准【开工核对】）。

关键不变量：断言字面量一律经 `TerminationReason`/`EventType` 枚举（typo 在 import 时炸而非静默过）；归一化后才比对（C31 豁免时间戳/事件 id）；manifest 双向完整性；本步**零生产代码改动**（全在 tests/ 与 docs/）。

### §5 测试蓝图

本步交付物即测试。数量 = 完整性 1 + 参数化用例数（=cassette 总数，【开工核对 §0-3】盘点后回填；按 M2.6 若干 + M2.11 ×1 + M3.11 15–20 估）≈ **15–25 个收集项**。另加 `test_extract_tool_sequence_unit`、`test_manifest_keys_are_posix` 2 个装置自检——**本步合计 17–27 个**（§8 预期同此口径）。fixture：FakeGateway 装置复用 M2.12（不新造回放器）。测试代码 AI 直写（00 §2.1 第 2 条——本步几乎全 AI 直写，用户审 manifest 期望值）。

### §6 验收对账清单

- [ ] manifest 覆盖三来源全部 cassette（完整性测试绿）；
- [ ] 三类断言各至少覆盖：终止原因=全部用例；工具序列 ≥5 例；隔离/预算硬约束 ≥10 例（M3.11 对抗用例基数）；
- [ ] **红绿凭证** `reports/m4_replay_redgreen.txt` 落盘（00 §8.2 第二条）；
- [ ] 重录流程文档含 PR 纪律节（触发条件为 C10 并列口径）；
- [ ] CI 全程零 token（无 key、FakeGateway）；
- [ ] pytest = 前序累计 + 本步收集项，逐项点名。

### §7 陷阱与常见错误

1. 断言 LLM 回答文本逐字相等 → 重录后必漂、回归变噪声 → 只断行为轨迹（04 M2 验收口径："结果逐字一致不可测，不承诺"）；
2. 期望值抄自实际输出 → 回归退化为快照、坏行为被固化 → 期望先于录制推导（§3-6）；
3. cassette 序号错位被 try/except 吞掉继续跑 → C10 要求响亮失配 → 失配异常直接让用例红，不许兜底；
4. manifest key 在 Windows 上写成反斜杠 → CI（Linux）对不上文件 → POSIX 斜杠 + `test_manifest_keys_are_posix` 钉死；
5. expectations.json 中文被 `\uXXXX` 转义 → diff 不可读 → 写入用 `ensure_ascii=False`；
6. 红绿验证的坏代码被顺手 commit → 已推送历史不改（00 §2.1 第 7 条）→ 全程本地、还原后 `git status` 确认干净再继续；
7. 弱模型高发：凭记忆发明 FakeGateway 构造参数/cassette 字段 → §0-2 核对先行；把离线评测（judge）混进本流水线 → 双流水线不可混（04 M4 加粗口径）。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check .
uv run pytest -q            # 前序累计 + 17–27 passed（15–25 含参数化展开 + 2 装置自检，§5 口径）
uv run mypy . ; uv run lint-imports
git add tests/replay docs/<重录流程文档> reports/m4_replay_redgreen.txt
git commit -m "test(replay): CI 行为回归——终止原因/工具序列/隔离预算三类断言" -m "回放测行为、真实调用测质量(03 §7)；红绿有效性凭证落 reports；PR 重录纪律落档(C10 并列触发)"
git push                    # CI 绿；红绿验证已在本地完成
```

### §9 完成后动作

00 §8.2 第二条可勾预备；深挖题（候选：为什么回放测行为与真实调用测质量不可互替——00 §8 面试考点原题；匹配键为什么不用 prompt 哈希）；manifest 维护纪律写进重录流程文档。

---

## 第五章 M4.4 · 离线质量评测（规模 L）

### §1 目标与定位

00 §8.1 M4.4 行：eval_cases/eval_runs 表迁移（02 §3——**02 未给列清单，列设计由本章首次给出**）；种子集从文件形态迁入落表；真实调用 + LLM-as-judge（strong 档）；nightly/手动触发；单次预算上限写死在配置；三类用例（检索质量/端到端/对抗）各有判据文档。挂本步：**#25**（评审 C38）judge 人工 spot-check 排期与判据（含同族自评偏差一段话）；C36 半句：eval_runs 记录当次实际模型回显名（上游缺口见文末清单）。

### §2 契约事实源

- 真实调用入口：`build_gateway() -> LLMGateway`（factory.py:18）；`LLMRequest(tier=…, messages=…, tenant_id=…, session_id=…)`（schema.py:45-60）；`Tier = Literal["fast","standard","strong"]`（schema.py:14）；
- strong 档=qwen-max，judge 用 strong（06 §5 档位表）；**strong 路由链含 fallback**：`["bailian:qwen-max", "bailian:deepseek-v3"]`（config.py:37）——judge 可能中途换模，回显名记录因此不是装饰而是必需；
- 计量自动化：judge 与被评调用走网关即入 usage_ledger（tenant/session 维度，metering.py:38-49），预算累计从 UsageChunk 或 ledger 读；
- 建表口径（仓库既有纪律，schema 素材包 A.8）：String(64) 应用侧 id、无 FK、枚举存字符串列+代码层 StrEnum（store.py:5-7 模块 docstring）、created_at 用 DB 时钟、钱用 Numeric/Decimal；
- **env.py 隐性契约**：新 ORM 模块必须在 migrations/env.py 顶部加 import，否则 autogenerate 失明（env.py:9-10 现有两行是先例）；
- 种子集文件、M3.5 检索入口：【开工核对 §0-10/§0-11】；ADR-002 决策 4：judge 不进在线链路。

### §3 设计决策与口径

1. **用例定义源在 repo、运行事实源在表**（定，消解素材包 H.12 的"两套并行"风险）：新建 `evalsets/cases.json`（版本化、PR 可审），`scripts/seed_eval_cases.py` 幂等 upsert 进 eval_cases 表；M3.11 种子文件迁格式入 cases.json 后**删除原文件**（单一定义源）。评测执行只读表。
2. **表设计**（理由：02 §3:105 仅一行"case 定义与每次回归结果"；以下为唯一出处）——见 §4 蓝图。eval_runs 采用"每用例每批次一行 + batch_id"而非独立批次表：02 只列了两张表，批次聚合可 GROUP BY 得出，不加第三张。
3. **判据文档**：`docs/eval-rubrics.md` 单文件三节（迁 repo 后可整体链接；三文件是注水）：
   - **检索质量**：机器判为主——期望 chunk（按稳定标识，形态视 M3.4 chunk id 设计【开工核对】）出现在 top-5 即 pass；judge 不参与；
   - **端到端**：judge 按 1–5 分打分（判据锚定示例：每档给一个样例回答——C38 缓解措施之一），**≥4 = pass**；rubric 维度=事实正确/引用知识库/无编造/语气合规；
   - **对抗**：机器硬断言优先（must_not_contain/必须兜底），judge 仅辅助解释，**pass 判定不依赖 judge**；全量人工复核（C38 缓解）。
4. **#25 spot-check 排期与同族偏差声明**（判据文档第四节，交付物的一部分不是可选项）：首个完整批次跑完后，抽 20–30 条 judge 判定做人工双评（用户为主评，AI 预填意见供对照），一致率落 `reports/m4_judge_spotcheck.txt`；文档写明：judge=qwen-max 与被评对象同为 Qwen 系，存在**同族自我偏好风险**（倾向给同家族文风高分），缓解=判据锚定示例、对抗类不依赖 judge、spot-check 一致率凭证；后续批次一致率显著下滑时重校准 rubric。
5. **预算上限写死在配置**（00 §8.0）：Settings 新增 `eval_run_token_budget: int = Field(default=150_000, gt=0)`。默认值推导：50 用例 ×（被评 run ≈1.5k token + judge ≈1k token）≈125k，留 20% 余量。**默认值数字【用户拍板】**（建议 150_000；judge/被评均过月度闸门双保险）。runner 每用例后累计（读 UsageChunk 实测值），超限即中止批次、已完成行保留、批次标记 partial。
6. **触发方式【用户拍板】**：建议 v1 **仅手动本地触发**（`uv run python scripts/run_eval.py`），不开 GitHub nightly cron——cron 需要把 DASHSCOPE key 放 GH secret 且每晚烧真金，演示项目收益小于风险；"nightly"以文档形式给出接法（workflow_dispatch + schedule 注释样例），需要时 10 分钟开启。00/04 写"nightly/手动触发"，斜杠给了选择权。
7. C36 落实：eval_runs.judge_model 记 API 回显名（UsageChunk.model，schema.py:78）；被评对象的模型名经 usage_ledger 按 session_id 可查，不冗余进表。

### §4 实施蓝图

新建：`aegis/obs/evaluation.py`（ORM+存取）、migration（`uv run alembic revision --autogenerate -m "eval_cases/eval_runs 评测双表"`）、`evalsets/cases.json`、`scripts/seed_eval_cases.py`、`scripts/run_eval.py`、`docs/eval-rubrics.md`；修改：`aegis/core/config.py`（预算字段）、**`migrations/env.py`（加 `import aegis.obs.evaluation  # noqa: F401`）**。

```python
# aegis/obs/evaluation.py
class EvalCategory(StrEnum):
    RETRIEVAL = "retrieval"; E2E = "e2e"; ADVERSARIAL = "adversarial"

class EvalVerdict(StrEnum):
    PASS = "pass"; FAIL = "fail"; ERROR = "error"   # error=执行/judge 异常，不算 fail

class EvalCaseRecord(Base):
    __tablename__ = "eval_cases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # 形如 case-adv-001，见 M4.5
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)  # 用例绑定演示租户
    category: Mapped[str] = mapped_column(String(16), index=True)
    question: Mapped[str] = mapped_column(Text)
    expectation: Mapped[dict[str, Any]] = mapped_column(JSONB)      # 按 category 结构，见 rubrics 文档
    source: Mapped[str] = mapped_column(String(16), default="seed") # seed | m4.5
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class EvalRunRecord(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    verdict: Mapped[str] = mapped_column(String(16))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)      # e2e 1–5；其余 None
    judge_model: Mapped[str | None] = mapped_column(String(64), nullable=True)  # API 回显名（C36）
    answer_digest: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)   # 本用例总消耗（被评+judge）
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index("ix_eval_runs_case_created", "case_id", "created_at"),)  # 趋势查询
```

`scripts/run_eval.py` 算法（编号）：
1. 生成 `batch_id = uuid4().hex`；加载 enabled 用例；
2. 逐用例执行被评对象：retrieval → 直接调 M3.5 检索入口【开工核对 §0-11】；e2e/adversarial → 走完整对话路径（真实调用，用例的 tenant_id 身份）；
3. 机器硬断言先行（retrieval 命中 / adversarial must_not_contain 与必须兜底）——硬断言 fail 则 verdict=fail，**不再花 judge 的钱**；
4. e2e（及机器断言通过的 adversarial 辅助解释）调 judge：`LLMRequest(tier="strong", …)`，prompt=rubrics 模板 + 用例期望 + 被评回答，要求 JSON 输出 `{score, reasons}`；
5. 写 eval_runs 行（verdict/score/judge_model=UsageChunk.model/成本累计）；
6. 累计 token ≥ `settings.eval_run_token_budget` → 打日志、中止批次；
7. 批次汇总：按 category 的通过率 → stdout + `reports/eval_baseline_<yyyymmdd>.txt`（含 batch_id、用例数、预算消耗、模型名分布）。

不变量：judge 永不进在线链路（ADR-002 决策 4——runner 是脚本不是服务）；runner 不进 CI；每行成本可与 usage_ledger 对账（评测走网关自动计量）；seed 脚本幂等（同 id upsert，重跑无副作用）。

### §5 测试蓝图（全部零真实调用——runner 的 LLM 依赖以注入桩替代）

| 文件 | 建议测试函数 | 断言要点 |
|---|---|---|
| `tests/obs/test_evaluation_store.py`（新建） | `test_eval_tables_roundtrip`（两表写读）/ `test_category_and_verdict_enum_values`（值快照，防漂移）/ `test_seed_script_idempotent`（同 JSON 跑两遍行数不变、字段更新生效） | db_session_factory 复用 |
| `tests/obs/test_eval_runner.py`（新建，runner 逻辑抽成可注入函数后测） | `test_budget_cap_aborts_batch`（桩网关回报大 usage → 中止且已完成行保留）/ `test_hard_assert_fail_skips_judge`（对抗 fail 不产生 judge 调用——桩计数）/ `test_judge_model_recorded_from_usage_chunk` / `test_judge_bad_json_yields_error_verdict`（judge 输出非 JSON → verdict=error 不算 fail） | 桩 gateway 用 GatewayLike 形状（runtime.py 协议先例） |
| `tests/obs/test_cases_json.py`（新建） | `test_cases_json_schema`（每条含 id/tenant_id/category/question/expectation 且 category 合法） | 纯文件校验 |

预期新增：**8–13 个**（三文件列举 3+4+1=8 个为下限，上限留给实施中的合理拆分）。

### §6 验收对账清单

- [ ] migration 应用后 `uv run alembic check` 仍绿（env.py import 已加的旁证）；
- [ ] 种子集完成"文件→cases.json→表"迁移，原文件已删，条数对上 M3.11 登记；
- [ ] 真实跑通一个小批次（可临时 `enabled` 收窄到 3–5 条控费），eval_runs 有行、judge_model 是回显名、成本与 ledger 对得上；
- [ ] `docs/eval-rubrics.md` 四节齐（三类判据 + spot-check/同族偏差）；
- [ ] 预算中止路径有测试；`eval_run_token_budget` 进 config 且有默认值；
- [ ] pytest = 前序累计 + 8–13。

### §7 陷阱与常见错误

1. autogenerate 生成的迁移里出现 `drop_table("eval_cases")` 或看不见新表 → migrations/env.py 忘加 import（env.py:9-10 契约）→ 先加 import 再 autogenerate，且**人工审阅生成的迁移**（模板注释原话"please adjust"）；
2. 单测里真调百炼 → 违反测试零真实调用红线（00 §8.0/§6.0）→ runner 依赖全部经 GatewayLike 形状注入桩；
3. judge 中途从 qwen-max fallback 到 deepseek-v3 没人知道 → strong 链含 fallback（config.py:37）→ 每行记回显名（C36），报告输出模型名分布；
4. 成本字段用 float → 账本纪律（metering.py:4 "浮点误差在账本里是事故"）→ Decimal/Numeric(12,6)；
5. 把"nightly"直接开成 GH cron 且把 key 塞 secret → 每晚烧钱+密钥面扩大 → 触发方式先过【用户拍板】；
6. spot-check 当可选项砍掉 → 它是 #25 交付物本体（00 §10.1 #25"排期与判据"）；砍法清单里能缩的是"judge 校准缩为人工 spot-check"（00 §11），即 spot-check 是**底线**不是装饰；
7. 弱模型高发：给 eval 两表发明 FK/PG ENUM → 全库口径无 FK、枚举字符串列（A.8）；把评测跑进 CI"顺便回归" → 双流水线不可混。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check .
uv run alembic upgrade head        # 预期：Running upgrade <前 head> -> <新 revision>, eval_cases/eval_runs 评测双表
uv run pytest -q                   # 前序累计 + 8–13 passed
uv run mypy . ; uv run lint-imports
git add aegis/obs/evaluation.py migrations/env.py migrations/versions/<新迁移>.py aegis/core/config.py evalsets/cases.json scripts/seed_eval_cases.py scripts/run_eval.py docs/eval-rubrics.md tests/obs
git commit -m "feat(eval): 离线质量评测——双表落库+LLM-as-judge(strong)+预算闸门" -m "种子集文件形态迁入表(00 M4.4)；judge 回显名记录(C36)；同族自评偏差与 spot-check 判据落档(#25/C38)"
git push
```

### §9 完成后动作

00 §10.1 #25 翻 ✅；更新 `docs\08-code-map.md` 对应节（obs/evaluation.py 双表与两脚本——#36 维护纪律）；首批次基线报告登记 reports/；深挖题（候选：LLM-as-judge 偏差怎么校准——00 §8 面试考点原题；为什么对抗类 pass 不依赖 judge；为什么记录回显名）；spot-check 排期写进用户待办。

---

## 第六章 M4.5 · 评测集扩充（规模 M）

### §1 目标与定位

00 §8.1 M4.5 行：种子 15–20 条 → **30–50 条**，三类用例覆盖。产出简历占位符"评测用例数 + 通过率基线"（00 §10.2 表，产出于 M4.5）。

### §2 契约事实源

cases.json 格式与 seed 脚本（M4.4 交付）；三类枚举 `EvalCategory`（M4.4）；演示租户设定（01 §5：A 数码商城/B 生鲜超市，00 §1 一页纸同）；M3.11 种子构成（≥10 隔离对抗 + 5 知识库外）【开工核对 §0-10】。

### §3 设计决策与口径

1. **目标条数与配比【用户拍板】**：建议 **40 条**（区间中点，留追加余量）——检索质量 12 / 端到端 14 / 对抗 14。对抗 14 = 种子隔离对抗 ~10 迁入 + 新增（水平越权变体、跨租户缓存探测、prompt 注入诱导泄 system prompt、诱导写工具重试）；知识库外 5 条归入端到端（期望=兜底/转人工——M3.12 验收 ≥95% 触发率同族）。
2. 用例 **id 规则**（定）：`case-<类别缩写 ret|e2e|adv>-NNN`（三位序号，只增不改——eval_runs 趋势按 case_id 串联，改 id=断趋势）。
3. 编写分工（定）：用例是数据不是生产代码——AI 起草全部 40 条进 cases.json，用户逐条审期望值（尤其对抗类的 must_not_contain 串要来自真实语料）；判据锚定示例同步补进 rubrics 文档。
4. **通过率基线**：扩充落库后跑一个完整批次（M4.4 runner，真实调用，预算内），报告即基线凭证 `reports/eval_baseline_<date>.txt`——简历占位符从此文件回填（M5.5）。基线数字**不做美化**：低了就低了，附逐条归因（M3.12"未触发逐条人工归因"同纪律）。

### §4 实施蓝图

修改：`evalsets/cases.json`（+20–25 条）、`docs/eval-rubrics.md`（锚定示例）；执行：`uv run python scripts/seed_eval_cases.py` → `uv run python scripts/run_eval.py`。无生产代码改动、无新迁移。

### §5 测试蓝图

`tests/obs/test_cases_json.py` 追加：`test_total_cases_in_30_50`、`test_each_category_min_coverage`（三类各 ≥8——防"扩充全堆一类"）、`test_case_ids_unique_and_wellformed`。预期新增：**2–3 个**。

### §6 验收对账清单

- [ ] 表内 enabled 用例 30–50 条、三类覆盖测试绿；
- [ ] 完整批次跑通、基线报告落盘（00 §8.2 第四条前半：评测集 30–50 条 + 离线流水线有基线记录）；
- [ ] M4.3 manifest 是否需要同步（新对抗用例若录了 cassette，两边都要挂——回放断行为、评测断质量，同一用例可以双挂但期望各表各的）；
- [ ] pytest = 前序累计 + 2–3。

### §7 陷阱与常见错误

1. 对抗用例期望写成具体文案（"应回答：抱歉…"）→ 重跑必炸 → 期望写行为类别（must_not_contain / 必须兜底）；
2. 扩充用例与 M4.6 成本实验问题集混用 → "评测集凑出来的"质疑成立 → 两个集合物理分文件、零交集（M4.6 §3）；
3. 基线不理想就调 rubric 放水 → 数字纪律（00 §2.2：没实测不写数字的孪生条款是"实测了不改数字"）→ 归因而非美化；
4. 弱模型高发：改旧用例 id/删旧用例来"凑配比" → 只增不改（趋势串联）；收集数错报——扩充后 `pytest -q` 收集数不变（用例是数据），别把 cases 条数当测试数报。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check . ; uv run pytest -q ; uv run mypy . ; uv run lint-imports
git add evalsets/cases.json docs/eval-rubrics.md tests/obs/test_cases_json.py reports/eval_baseline_*.txt
git commit -m "feat(eval): 评测集扩充至 40 条(检索12/端到端14/对抗14)+通过率基线落盘" -m "00 M4.5：三类覆盖；基线是简历占位符凭证(00 §10.2)，不美化只归因"
git push
```

### §9 完成后动作

00 §10.2"评测用例数+通过率基线"行状态 → ✅ 待回填；深挖题（候选：为什么对抗期望写行为不写文案）。

---

## 第七章 M4.6 · 成本对照实验 ×2（规模 L）

### §1 目标与定位

00 §8.1 M4.6 行：两组实验**口径分开**——① 档位路由降本（全唯一问题集，不受重复率污染）；② 精确缓存降本（声明分布假设的模拟流量单独测）；产出两个实测数字 + 口径说明，**不预设目标值**（04 M4："≥40% 这类可被评测集构成操纵的预设已删除"）。产出简历占位符两个（00 §10.2：档位路由降本 X% / 精确缓存降本 X%）。真实调用，预算上限写死（00 §8.0）。

### §2 契约事实源

- 路由链与价目：`model_routes`（config.py:33-38）、`model_prices` 元/千 token（config.py:48-54）；
- 缓存开关=`cache_ttl_seconds`（config.py:46，0=关闭）；缓存 key 语义本体（cache.py:38-42）——**逐字节相同请求才命中**；
- 计量：usage_ledger 按 tenant_id 聚合 cost（metering.py:38-51，ix_usage_tenant_created）；缓存命中记账 cached=true/cost=0；
- 意图路由（M3.6，fast 档分诊决定后续档位）【开工核对：分诊入口与"强制指定档"旁路的实装形态】；
- 脚本先例：`scripts/experiment_fault_injection.py`（M1.13 同类实验脚本，报告落盘模式照抄）。

### §3 设计决策与口径（实验设计=本章核心交付）

**共同控制变量**：故障注入关（rate=0）；月度预算闸门对实验租户不设限或调高（防中途拦截）；每组实验用**独立 tenant_id**（如 `exp-route-base` / `exp-route-tiered` / `exp-cache-off` / `exp-cache-on`）——账本天然按租户分账、事后可从 ledger 重算全部数字（可审计）；两实验问题集**与评测集零交集**、两实验之间也不混流。

**实验①（档位路由降本）**：
- 问题集：`evalsets/cost_questions.json`，**全唯一**（无一重复），条数与意图分布【用户拍板】——建议 **80 条**：FAQ 类 30% / RAG 类 40% / 工具类 20% / 闲聊 10%（贴近客服真实构成的声明性假设，写进报告口径节）；
- 对照组设计【用户拍板】——建议**双基线**（防"基线选贵的抬数字"质疑）：
  - A 组（基线1）：全部强制 strong 档（"不做分档的保守实现"）；
  - A′ 组（基线2）：全部强制 standard 档（"不做分档的朴素实现"）；
  - B 组（实验组）：正常意图分诊路由（fast 分类 + 按意图定档）；
  - 报告两个降本数字：vs-strong 与 vs-standard，各带口径；
- 缓存**关闭**（cache_ttl_seconds=0）——唯一集不受重复率污染的第二道保险；
- 降本% = (cost_基线 − cost_B) / cost_基线；附每档调用次数分布表与分诊自身的 fast 档成本（诚实计入 B 组总成本——分诊不是免费的）。

**实验②（精确缓存降本）**：
- 模拟流量：**200 条请求**，分布假设显式声明：**30% 为历史复述**（从前段唯一问题中重抽，复用**同一请求对象**保证逐字节一致）；生成器固定随机种子（seed 写死进脚本）——流量可精确重放；
- 两遍：C 组缓存关 vs D 组缓存开（TTL 临时调大覆盖实验窗，实验前 FLUSH 实验租户缓存键）；
- 降本% = (cost_C − cost_D) / cost_C；附**实测命中率 vs 设计 30%** 自检行（对不上=生成器或 key 语义有 bug，先修再报数）。

**产出物格式**（两份，`reports/m4_cost_routing.txt` / `reports/m4_cost_cache.txt`，段落骨架写死）：
1. 实验口径（集合构成与分布假设/控制变量清单/组别定义/执行时间与批次）；
2. 原始数字（各组总 cost、调用数、token、每档/命中分布——从 ledger 裸 SQL 聚合，SQL 附录进报告）；
3. 结果（降本%，口径限定语随数字走）；
4. 威胁与边界（分布假设是声明不是实测；价目为演示值 config.py:48；不预设目标值声明）。

预算：每脚本顶部常量 `BUDGET_TOKENS`（建议各 300_000，80 条×3 组/200 条×2 组的余量估算），超限中止并落 partial 标记。

### §4 实施蓝图

新建：`scripts/experiment_cost_routing.py`、`scripts/experiment_cost_cache.py`、`evalsets/cost_questions.json`；流量生成器抽纯函数（可单测）：

```python
def build_cache_traffic(questions: list[str], *, replay_ratio: float = 0.3, seed: int = 42) -> list[str]:
    """200 条请求序列：前段唯一消费 + 按比率从已出现问题重抽（random.Random(seed)）。"""
```

脚本算法（①，编号）：1) 读问题集断言无重复；2) 依次跑 A/A′/B 三组（各自 tenant_id，B 组走正常分诊、A/A′ 强制档位【开工核对 M3.6 旁路形态】）；3) 每组累计 token 触及预算即中止；4) 结束后按 tenant_id 聚合 ledger（裸 SQL）；5) 按 §3 骨架渲染报告落 reports/。（②同构：FLUSH → C 关缓存 → D 开缓存 → 聚合含 cached 命中数 → 报告。）

不变量：所有数字可由 ledger 重算（报告附聚合 SQL）；两实验零共享流量；脚本不进 CI；报告不出现任何预设目标措辞。

### §5 测试蓝图

`tests/obs/test_cost_traffic.py`（新建）：`test_replay_ratio_approx`（200 条中复述占比 30%±2%）、`test_seed_reproducible`（同 seed 两次生成逐条相等）、`test_unique_set_has_no_duplicates`（cost_questions.json 全唯一）。预期新增：**3 个**。实验本体（时序/费用敏感）不进 CI——演示脚本承载真实时间量（00 §2.2 测试纪律）。

### §6 验收对账清单

- [ ] 两份报告落盘、四段骨架齐、两个降本%产出（00 §8.2 第三条）；
- [ ] 实验②命中率自检行与设计 30% 吻合；
- [ ] 数字可从 ledger 重算（抽一组人工核）；
- [ ] 问题集与评测集零交集（grep 抽查）；
- [ ] 00 §10.2 两行 → ✅ 待回填；pytest = 前序累计 + 3。

### §7 陷阱与常见错误

1. 复述请求"改了个标点" → 精确缓存 key 是语义本体哈希（cache.py:39-41），逐字节不同=必 miss、实验②数字塌 → 复用同一请求对象；
2. 先跑"缓存开"再跑"缓存关" → 开组把缓存烧热污染顺序 → 先关后开 + 实验前 FLUSH 实验租户键；
3. 用评测集问题当实验集 → 04 原话"没法被质疑是评测集凑出来的"就是防这个 → 独立文件零交集；
4. 报告写"达成 40% 目标" → 预设目标已被评审删除（04 M4）→ 只报实测+口径；
5. 分诊成本不计入 B 组 → 降本数字虚高、面试被拆穿 → fast 分诊调用诚实入账（同租户自动入 ledger）；
6. 月度预算闸门中途拦断实验 → BudgetExceeded 混入结果 → 实验租户预算关闭或调高（控制变量清单里声明）；
7. 弱模型高发：把两实验合并成一个脚本"顺便都测" → 口径分开是评审定稿（00 §8.0 加粗）；报告数字四舍五入前后不一致——以 Decimal 输出为准。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check . ; uv run pytest -q ; uv run mypy . ; uv run lint-imports
# 实验执行（真实调用，跑前与用户确认预算）：
uv run python scripts/experiment_cost_routing.py    # 预期：三组进度日志 + reports/m4_cost_routing.txt
uv run python scripts/experiment_cost_cache.py      # 预期：命中率自检行 + reports/m4_cost_cache.txt
git add scripts/experiment_cost_*.py evalsets/cost_questions.json tests/obs/test_cost_traffic.py reports/m4_cost_routing.txt reports/m4_cost_cache.txt
git commit -m "feat(cost): 成本对照实验×2——档位路由(双基线)与精确缓存(声明分布)口径分开" -m "全唯一集防重复率污染；30%复述假设显式声明；数字可从 ledger 重算；不预设目标值(04 M4)"
git push
```

### §9 完成后动作

00 §10.2 两占位符行翻"✅ 待回填"；深挖题（候选：成本数字怎么做到不可质疑——00 §8 面试考点原题；为什么双基线；为什么分诊成本要入账）。

---

## 第八章 M4.7 · 设计文档迁入 repo + 应用容器化（规模 S→实际 M，见下）

### §1 目标与定位

00 §8.1 M4.7 行只写文档迁入（规模 S），但 00 §10.1 把 **#26 应用容器化**（评审 C20，**M5.3 硬依赖**——`--scale api=3` 没有应用镜像无从谈起；06 §4 还承诺"演示/压测一律走容器"）与 **#31 应用容器 restart 策略**同样挂在 M4.7——**本章两件事都做，实际规模 M**。附带收口：C41 首次 PG dump、C21 数据生命周期（若 M2.0 未完【开工核对 §0-13】）、C43 README 初稿（"终稿"在 M5.5）。

### §2 契约事实源

- 迁移源：`docs/` 全量（清单见 §0-16，含已落档的 07-handoff-guide.md 与 08-code-map.md；届时以 ls 为准）+ 项目级 仓外项目级 `CLAUDE.md`（repo 上层目录）；仓库已有 `CLAUDE.md`（指向仓外 docs 路径，迁入后必须改写）；
- compose 现状：仅 postgres/redis 两服务，`restart: unless-stopped`、端口绑 127.0.0.1、healthcheck 齐（deploy/docker-compose.yml 全文，40 行）；**无应用容器、无 Dockerfile、无 README**（schema 素材包附 8）；
- 连接默认值只服务宿主机：`postgresql+asyncpg://aegis:aegis@localhost:5432/aegis` / `redis://localhost:6379/0`（config.py:28-29）——容器内必须环境变量覆盖为服务名；
- 迁移执行命令：`uv run alembic upgrade head`（ci.yml:63-64 同款）；
- Celery：Windows 本地 `--pool=solo` 只是调试便利，**容器内（Linux）用默认 prefork，生产形态以容器为准**（06 §4 原文口径）；
- restart 选型先例：pg/redis 选 `unless-stopped` 而非 always——保住"手动 docker stop 看降级"的演示口径（00 §10.1 #31）；
- `.gitattributes` 已存在（仓库根，行尾规则覆盖确认【开工核对 §0-15】）。

### §3 设计决策与口径

1. **迁移步骤**（编号，两次独立提交：迁 docs 一次、容器化一次）：
   1. 前置（若 §0-13 核对为未做）：第一次 `pg_dump` 落 **仓外** 仓外上层 `backups\`（dump 含业务数据不入库）+ C21 生命周期一段话落 02；
   2. 复制 `docs/` 全量 → 仓库 `docs\`（含 adr/、plans/、reports 类文档不动——reports/ 已在仓内）；
   3. 修正文内绝对路径：全 docs grep 仓外旧绝对路径前缀，改相对链接（如 `docs/00-master-plan.md`）；改不动的（记忆文件路径等仓外引用）保留并加"仓外"注记；
   4. CLAUDE.md 合并：项目级 仓外项目级 `CLAUDE.md`（repo 上层目录） 的启动序列/八条硬规则并入仓库 CLAUDE.md，删除"文档在仓库外"的指路描述，改为指向 `docs/`；
   5. 原 `docs/` 目录留 `POINTER.md`（一句话：已迁入 repo，勿在此编辑）——防双写分叉；
   6. 记忆文件更新执行主文档新路径（`<repo>/docs/00-master-plan.md`）；
   7. `README.md` **初稿**（C43 措辞）：项目一句话（LLM 是 CPU，Aegis 是操作系统——ADR-001）、三层架构图占位、快速启动（compose 命令）、docs/ 索引、测试与 CI 徽章可选；终稿+架构图 M5.5；
   8. 此后文档变更一律走提交（00 M4.7 行"承诺在此兑现"）。
2. **容器化**：
   - **单 Dockerfile 多用途**（定）：api/worker/beat 同镜像不同 command——同代码同依赖，三份 Dockerfile 是漂移源；
   - 基底与构建（定）：`ghcr.io/astral-sh/uv:python3.13-bookworm-slim`（uv 官方 Python 镜像；具体 tag 开工时以 uv 文档现查钉版本），`uv sync --frozen --no-dev` 装进 `/app/.venv`，`ENV PATH="/app/.venv/bin:$PATH"`；COPY 范围：pyproject.toml、uv.lock、alembic.ini、migrations/、aegis/（tests/docs/reports 由 .dockerignore 排除）；
   - **alembic 执行顺序**（#26 点名）：专设 one-shot 服务 `migrate`（同镜像，command=`alembic upgrade head`，`restart: "no"`，depends_on postgres 健康）；api/worker/beat `depends_on: migrate: condition: service_completed_successfully`——先迁库后起应用，多副本不抢迁移；
   - **restart 策略**（#31）：api/worker/beat 一律 `unless-stopped`（与 pg/redis 同选型同理由）；migrate 是 `"no"`；
   - 优雅停机配套（评审 C35，验证归 M5.3/M5.4 不在本步）：api command 带 `--timeout-graceful-shutdown 10`，compose `stop_grace_period: 15s`——只落配置；
   - 环境变量注入：compose 内 `DATABASE_URL=postgresql+asyncpg://aegis:aegis@postgres:5432/aegis`、`REDIS_URL=redis://redis:6379/0`（**服务名不是 localhost**）；密钥经 `env_file: ../.env`（.env 永不入镜像——.dockerignore 第一行）；
   - api 端口：`127.0.0.1:8000:8000`（安全底线口径同 pg/redis）；healthcheck 用 python 一行探 /healthz（slim 无 curl）。

compose 新增服务一览（接口级）：

| 服务 | command（venv 已在 PATH） | depends_on | restart | 端口 |
|---|---|---|---|---|
| migrate | `alembic upgrade head` | postgres: healthy | "no" | — |
| api | `uvicorn <M3 app 路径【开工核对 §0-6】> --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 10` | migrate: completed; redis: healthy | unless-stopped | 127.0.0.1:8000:8000 |
| worker | `celery -A <M3.4 workers app 路径【开工核对】> worker`（容器内默认 prefork） | migrate: completed; redis: healthy | unless-stopped | — |
| beat | `celery -A <同上> beat` | migrate: completed; redis: healthy | unless-stopped | — |

### §4 实施蓝图

新建：`Dockerfile`、`.dockerignore`（.env/.git/.venv/tests/docs/reports/__pycache__/.pytest_cache 等）、`README.md`（初稿）、`docs/`（迁入全量）、仓外 `POINTER.md`；修改：`deploy/docker-compose.yml`（+4 服务）、`CLAUDE.md`（合并改写）。
Dockerfile 关键指令序（接口级，完整内容用户届时敲）：`FROM <uv 官方 py3.13-slim 镜像>` → `WORKDIR /app` → `COPY pyproject.toml uv.lock ./` → `RUN uv sync --frozen --no-dev` → `COPY alembic.ini ./` + `COPY migrations ./migrations` + `COPY aegis ./aegis` → `ENV PATH="/app/.venv/bin:$PATH"` → 默认 `CMD` 给 api（compose 逐服务覆盖 command）。
关键不变量：镜像内无 .env 无密钥；应用容器全部经 migrate 完成后启动；两次提交分离（docs 迁入 / 容器化）——万一容器化返工不连累文档历史。

### §5 测试蓝图

pytest 新增 **0 个**（部署面无单测价值；schema 一致性已有 alembic check 门）。验证=**容器冒烟**，凭证 `reports/m4_container_smoke.txt`：
1. `docker compose -f deploy/docker-compose.yml up -d --build` → 6 服务，migrate Exited(0)，其余 healthy/running；
2. `curl http://127.0.0.1:8000/healthz` → 200；
3. `docker compose exec postgres psql -U aegis -c "select version_num from alembic_version"` → 最新 revision；
4. worker 日志出现任务注册表（celery banner）；
5. 一次容器内端到端对话冒烟（**真实调用，写死仅 1 次**，M3 演示脚本【开工核对】）。此项是 M4.4/M4.6 之外的真实调用，与 00 §8.0 字面口径有张力——见附A #9，执行前与用户确认。

### §6 验收对账清单

- [ ] 仓库 `docs/` 与源目录清单一致（含 plans/、adr/、07-handoff-guide/08-code-map、CLAUDE.md 合并完成）；文内仓外旧绝对路径引用清零（仓外注记除外）；POINTER.md 落位；
- [ ] README 初稿在（C43 收口）；C41 dump/C21 声明确认（或本步补做）；
- [ ] 容器冒烟 5 项全过、凭证落盘；restart 策略齐（#31 应用容器部分收口）；
- [ ] **M5.3 硬依赖解除确认**：`docker compose up --scale api=3` 能起（Nginx 是 M5.3 的事，本步只验能 scale——端口映射与 scale 冲突时去掉固定宿主端口映射的坑见 §7-6）；
- [ ] 两次提交分离、CI 全绿。

### §7 陷阱与常见错误

1. 容器内连不上库（connection refused @localhost）→ config.py:28-29 默认值是宿主机口径 → compose 环境变量覆盖为服务名；
2. Dockerfile/entrypoint 报 `no such file or directory` 或 `\r` 语法错 → CRLF 行尾（06 §4 坑 2）→ `.gitattributes` 确认 + 编辑器 LF；
3. `depends_on` 只写服务名 → 只等"启动"不等"健康/完成"，api 抢在迁移前起 → 必须 `condition: service_healthy / service_completed_successfully`；
4. worker 在容器里被写成 `--pool=solo` → 那是 Windows 本地调试口径，容器是 Linux 用默认 prefork（06 §4：生产形态以容器为准）；
5. `.env` 被 COPY 进镜像（`COPY . .` 一把梭）→ 密钥进镜像层=进历史 → .dockerignore 先行 + COPY 白名单式逐项；
6. `--scale api=3` 起不来 → 固定宿主端口 `127.0.0.1:8000:8000` 三副本撞端口 → M5.3 上 Nginx 时 api 不再映射宿主端口（由 Nginx 统一入口）；本步冒烟单副本可保留映射，把这一句写进 compose 注释防 M5.3 踩雷；
7. 文档迁入后仓外旧目录继续被编辑 → 双写分叉、口径漂移 → POINTER.md + 记忆文件当天更新（本条也是给接续模型自己的：**迁入后一切文档读写走 repo**）；
8. 弱模型高发：顺手把 pg/redis 服务也"升级整理" → 基础设施容器已收口（#31 前半 ✅，提交 `729ff4c`），不动；迁 docs 时"顺手改写"文档内容 → 迁移提交只挪不改，内容修订是另外的提交。

### §8 指令块模板

```powershell
# 提交一：文档迁入（纯文档提交也走标准五命令——00 §2.1 第 3 条，ruff format 为必给项）
uv run ruff format . ; uv run ruff check . ; uv run pytest -q ; uv run mypy . ; uv run lint-imports   # 预期：全部不变/全绿，收集数不变
git add docs README.md CLAUDE.md
git commit -m "docs: 设计文档全量迁入 repo(00 §10.1 #9)——此后文档变更走提交" -m "M5 前迁入承诺兑现；绝对路径改相对；仓外留 POINTER 防双写"
git push
# 提交二：容器化（先本地冒烟）
docker compose -f deploy/docker-compose.yml up -d --build   # 预期：migrate Exited(0)，api/worker/beat running
curl http://127.0.0.1:8000/healthz                          # 预期：200
uv run ruff format . ; uv run ruff check . ; uv run pytest -q ; uv run mypy . ; uv run lint-imports   # 全绿，收集数不变
git add Dockerfile .dockerignore deploy/docker-compose.yml reports/m4_container_smoke.txt
git commit -m "feat(deploy): 应用容器化——api/worker/beat 同镜像编排+migrate 先行(#26/#31)" -m "M5.3 --scale 硬依赖；restart unless-stopped 保留手动停容器演示口径；alembic one-shot 先于应用"
git push
```

### §9 完成后动作

00 §10.1 #9/#26/#31（应用部分）翻 ✅；更新 `docs\08-code-map.md` 对应节（Dockerfile/compose 四服务与部署形态——#36 维护纪律；迁入后 08 本体已在 repo 内，就地更新）；记忆文件登记 docs 新家与"文档变更走提交"新规；深挖题（候选：为什么 migrate 要 one-shot 服务而不是 api 启动时自跑——多副本抢迁移；unless-stopped vs always 的演示口径）。

---

## 第九章 M4.8 · 毕业验收 + 整编（规模 S）

### §1 目标与定位

00 §8.1 M4.8 行：8.2 对账、报告落盘、毕业四件（tag `m4-governance`）。毕业清单模板=00 §13 六项。

### §2 契约事实源

00 §8.2 四项验收；00 §13 模板；00 §10.2 占位符表；00 §10.1 M4 归位条目（#3/#4/#5/#9/#23/#24/#25/#26/#29/#31）；04 M4 验收（差异：00 多"评测集 30–50 条，双流水线各自跑通且有基线记录"一条——**以 00 为准**，04 头部已声明冲突裁决）。

### §3 设计决策与口径

无新决策。对账口径：逐项点名核对 + pytest 收集数（00 §2.1 第 9 条：绝不对未核查部分说"全部正确"）。

### §4 实施蓝图（对账执行清单）

1. **00 §8.2 逐项**：
   - [ ] trace_id 还原任一会话（M4.1 凭证 `reports/m4_trace_sample.json` + 现场随机抽一条重演）；
   - [ ] CI 回放回归红绿有效（`reports/m4_replay_redgreen.txt`）；
   - [ ] 两组成本数字 + 口径报告（`reports/m4_cost_routing.txt` / `m4_cost_cache.txt`）；
   - [ ] 评测集 30–50 条、双流水线各自跑通且有基线记录（表内 enabled 计数 + `reports/eval_baseline_*.txt` + replay 套件绿）；
2. **§10.1 状态翻转清单**：#3/#4/#5（如涉及）/#9/#15（如涉及）/#23/#24/#25/#26/#29/#31 逐条改状态列；
3. **§10.2**：档位路由降本/精确缓存降本/评测用例数+通过率三行翻"✅ 待回填"；
4. **毕业四件**（00 §13）：CI 全绿 → `git tag m4-governance && git push origin m4-governance` → 记忆文件重写为 M5 就位状态 → 00 更新（§8 标 ✅、§6.3 式实际交付对账表、偏差登记）；
5. 本计划头部回填「实际落地偏差」块（无偏差也写"无偏差"——plans/README §4）；并核对 `docs/08-code-map.md` M4 各节已随各步更新收口（#36 维护纪律，00 §13 第 5 项——漏更即毕业清单不勾）；
6. **#33 提示**：LangGraph 迷你复刻 spike 的弹性窗=**M4 毕业后**（00 §10.1 #33，M5.0 清点核对）——毕业时向用户点名这扇窗，做不做由用户排期，不属于 M4 交付。

### §5 测试蓝图

新增 0 个；全量 `uv run pytest -q` 收集数与 00 登记的 M4 各步累计对平。

### §6 验收对账清单

即 §4 全表 + 00 §13 六项全勾（第六项：开新会话）。

### §7 陷阱与常见错误

1. 只跑 pytest 绿就宣布毕业 → 00 §8.2 有四条**非测试**验收（凭证文件）→ 逐项点名文件存在且内容对；
2. tag 打在未推送提交上 → 先 push 分支再 push tag；
3. 收集数对账用"大概多了几十个" → M2.4① 教训（预告收集数错报）：逐步累计逐项点名后再报总数；
4. 忘回填本计划偏差块 → plans/README §4 维护纪律，毕业当天完成；
5. 弱模型高发：毕业时"顺手"启动 M5.1 → 会话边界=00 §13 六项全勾后**开新会话**（00 §2.1 第 12 条）。

### §8 指令块模板

```powershell
uv run ruff format . ; uv run ruff check .   # 预期：N files left unchanged / All checks passed!
uv run pytest -q                       # 全绿，收集数=M4 最终登记值
uv run mypy . ; uv run lint-imports    # 预期：Success / Contracts kept, 0 broken
git tag m4-governance
git push ; git push origin m4-governance   # 预期：CI 绿 + tag 可见
```

### §9 完成后动作

记忆更新（项目状态：M4 ✅、测试数、教训增量）；00 §8 标 ✅；开新会话（M5.0 从 00 §9 + §10.2 起步，必读 04 M5 节 + 05 全文 + ADR-007）。

---

## 附A · 发现的上游文档问题（撰写本计划时核出，**不擅自改上游**，列此待用户裁）

1. **00 §8.1 M4.7 行文字不含容器化**，但 §10.1 #26/#31 挂 M4.7 且标"M5.3 硬依赖"——只读步骤表会漏掉 M5.3 前置。建议 00 M4.7 行补一句"+ 应用容器化（#26/#31）"。
2. **C36 的后半句无落点**：模型版本钉扎已落 06 §5，但"M4.4 的 eval_runs 记录当次实际模型名"半句在 00 M4.4 行缺失（素材包 H.7）。本计划已将其并入 M4.4 表设计（judge_model 列）；建议 00 M4.4 行补注。
3. **C5/C30 的"实现可列 M4.0"分支在 §10.1 无承接行**：C30 已在 00 §2.2 显式冻结（无问题）；C5（熔断 provider:model 细化）现状是"误伤再细化"的观察触发——M4.0 §0-9 核对 M2.0 裁决记录，若曾裁"M4.0 做"则 00 需补追踪行。
4. **04 M4 章节内嵌"M1 代码审计追加项"小节**（04:150-157）与 M4 交付无关，弱模型极易误读为 M4 范围——建议 04 加一行"此节为 M1 范围注明"或移位。
5. **00 §8.2 比 04 M4 验收多一条**（评测集 30–50 条 + 双流水线基线）——非冲突（04 头部已声明以 00 为准），仅提示对账以 00 §8.2 四条为准。
6. **02 §3 列出 eval_cases/eval_runs 但无列清单**——列设计由本计划 M4.4 首次给出；迁入 repo 后建议 02 §3 回填两表列（或指向本计划）。
7. **02 §9 的 `GET /metrics` 无权限矩阵行**（02 §7.1 矩阵未覆盖）——本计划 M4.2 §3-5 建议"无认证 + 仅绑 127.0.0.1 + 文档声明"（待用户拍板）；拍板后 02 §7.1 补一行。
8. **已解决（00 v1.5，2026-07-10）**：07-handoff-guide.md 与 08-code-map.md 已落档 `docs/`（交接工程产物，00 §10.1 #36 ✅，§0/§12/§13 均已挂载）——本条初稿"07/08 不存在"的断言已过时。两文档纳入 M4.7 迁移范围；迁移范围仍以迁入时 ls 实际清单为准（§0-16）。
9. **00 §8.0 真实调用口径未覆盖两处一次性验收动作**：本计划 M4.2 §6（#23 gauge 演示对话 ≤3 轮）与 M4.7 §5（容器内端到端冒烟 1 次）需要 M4.4/M4.6 之外的真实调用——建议 00 §8.0 增列"M4.2 验收演示与 M4.7 容器冒烟各一次性真实调用（次数/预算写死）"；用户若裁"不开口子"，则两处改用 FakeGateway/回放驱动（容器冒烟第 5 项相应降格为"应用容器内跑通回放对话"）。
10. **00 §10.1 #29 行措辞需修订**："熔断/精确缓存/计量影子账本的 Redis 触点"中**计量项不成立**——经读码核实 metering.py 全文件无 Redis 触点（record/month_spend 纯 PG 路径，metering.py:88-125）；aegis/gateway 下实际触 Redis 的仅 breaker.py/cache.py/ratelimit.py。建议 #29 行删去"计量影子账本"，M4.0 裁决材料以两触点为准（本计划 M4.0 §3-4 已按读码结论改写）。
