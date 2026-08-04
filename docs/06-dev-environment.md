# 06 · 开发环境与协作方式

> 记录 2026-07 敲定的环境决策与协作约定。环境问题在第一天解决一次，好过在每个里程碑里反复踩。

## 1. 决策速览

| 项 | 决定 | 结论 |
|---|---|---|
| Python | 3.13（标准 GIL 构建） | ✅ 可用，全部依赖已支持（注意 Celery ≥ 5.5） |
| 包管理 | uv（`pyproject.toml` + `uv.lock` 入库） | ✅ 2026 年 Python 项目的正确默认 |
| IDE | PyCharm（Community 够用） | ✅ 解释器指向 uv 创建的 `.venv` |
| 操作系统 | Windows 11 + Docker Desktop | ✅ 有三个已知坑，见 §4 |
| LLM | 阿里云百炼（OpenAI 兼容模式） | ✅ 档位映射见 §5 |
| Embedding | 百炼 text-embedding-v4（dimensions=1024） | ✅ 摄取流水线按 IO 密集设计 |
| 代码托管 | GitHub | ✅ 规范见 §6 |

## 2. Python 3.13 注意点

- 用**标准构建**，不要用 free-threaded（3.13t）实验构建——生态兼容性未就绪，
  且本项目并发模型是 asyncio，不吃 no-GIL 红利；
- `pyproject.toml` 里写 `requires-python = ">=3.13"`；
- 关键依赖版本下限：Celery ≥ 5.5（3.13 支持）、SQLAlchemy ≥ 2.0.31、asyncpg ≥ 0.30、
  pydantic ≥ 2.9（M0 时以 `uv add` 解析到的最新稳定版为准，锁进 uv.lock）。

## 3. uv 工作流（日常只需这几条）

```bash
uv init --python 3.13      # M0 初始化（只做一次）
uv add fastapi             # 加依赖（自动更新 pyproject.toml 和 uv.lock）
uv add --dev ruff mypy pytest
uv sync                    # 克隆仓库后/换机器时还原环境
uv run pytest              # 在项目环境里执行命令（不必手动激活 venv）
uv run uvicorn api.main:app --reload
```

- `uv.lock` **必须提交**——可复现构建是工程交付的一部分，CI 用 `astral-sh/setup-uv` + `uv sync`；
- PyCharm：Settings → Project → Python Interpreter → 选择 uv 生成的 `.venv`
  （新版 PyCharm 原生识别 uv 环境）。

## 4. Windows 开发的三个已知坑（现在记下，M0 就位）

1. **Celery 在 Windows 上不支持 prefork 池**（Celery 4 起官方放弃 Windows 支持）。
   约定：本地调试 worker 用 `uv run celery -A workers.app worker --pool=solo`；
   docker-compose 里的 worker 容器（Linux）用默认 prefork——**生产形态以容器为准**，
   本地 solo 池只是调试便利。演示/压测一律走容器；
2. **行尾符**：仓库根放 `.gitattributes`（`* text=auto eol=lf`），避免 Windows CRLF
   污染仓库（shell 脚本/Dockerfile 对 CRLF 敏感）。

3. **PowerShell 管道中文乱码**（2026-07-07 M2.0 实测踩中）：Python 往管道写 UTF-8，
   PowerShell 按 `[Console]::OutputEncoding`（中文 Windows 默认 GBK）解码原生命令输出，
   `脚本 | Tee-Object 文件` 落盘即乱码。修法两端钉死 UTF-8（写进 `$PROFILE` 一劳永逸）：
   `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + `$env:PYTHONUTF8 = "1"`；
   `Add-Content` 一律带 `-Encoding utf8`。**第二刀（同日踩中）**：Windows PowerShell 5.1 的
   `Tee-Object` 落盘默认 UTF-16（git 当二进制、diff 不可读）——凭证落盘用
   `Out-File -Encoding utf8`；根治 = 换 pwsh 7（默认 UTF-8 无 BOM）。

基础设施（PG + Redis）一律跑在 Docker Desktop（WSL2 后端）里，不在 Windows 裸装。

## 5. 阿里云百炼配置

- **接入方式**：OpenAI 兼容模式，`base_url = https://dashscope.aliyuncs.com/compatible-mode/v1`，
  API key 放环境变量 `DASHSCOPE_API_KEY`（`.env` 文件，永不入库）；
  我们的 `openai_compat.py` 适配器直接对接，无需百炼专用 SDK；
- **档位映射（配置文件，非代码）**：

| 档位 | 模型（2026-07-17 模型池重构后名单；沿革见下注） | 用途 |
|---|---|---|
| fast | qwen-flash（备选 qwen-turbo） | 意图分类、摘要压缩、结果截断摘要 |
| standard | qwen-plus（备选 qwen-turbo） | 普通对话轮 |
| strong | qwen3.7-max（备选 qwen-plus） | 复杂推理、工具编排、LLM-as-judge |
| embedding | text-embedding-v4（dimensions=1024） | RAG / 长期记忆 |

> **2026-07-17 模型池重构（充值解锁 + 幻影候选移除）**：qwen-flash/turbo/plus 恢复可用，按
> "便宜优先"分层回归 M1 形态；**glm5.2 移除——07-16 写入的容灾候选实测 404 `model_not_found`
> （幻影模型），三档 fallback 断链两日无人察觉**。qwen3.7-plus 退出路由（价目保留供历史账本核对）。
> **入池三验纪律（幻影+思考两教训定案，plans/m2.11 偏差 #12）**：任何模型写进 model_routes 前
> 必须探针实测三件事——①存在性②思考默认态③`enable_thinking:false` 接受性。
> **思考型模型口径**：qwen3.7 系默认思考——思考流会饿死首块 25s 计时器（适配器不消费
> reasoning_content，解析层零产出）且隐藏思考 token 使 completion 计费虚高十余倍；适配器已
> 全池统一 `enable_thinking: false`（openai_compat `_build_payload`，00 §2.2 C1 补注、§10.1 #41）。
> **确切模型 ID 以百炼控制台为准**——2026-07-16 变更（额度收窄至 qwen3.7 系+glm5.2）未做实测
> 即为反例。M1 时代名单（reports/ 凭证口径，不改写）：fast=qwen-flash/turbo、standard=qwen-plus、
> strong=qwen-max。

- **模型 fallback 口径（2026-07-17 起回归 M1 形态）**：各档在 qwen 梯队内按价降级
  （flash→turbo / plus→turbo / 3.7-max→plus）——M1 毕业实验的 fallback 实测凭证
  （qwen-flash→qwen-turbo，`reports/m1_fault_injection.txt`）与此形态逐词吻合；
  ~~"同平台异族容灾"（deepseek-v3、glm5.2 两代候选均已退场）~~叙事作废，05 简历
  相关字样随 00 §10.1 #28 删改；平台级容灾由 Anthropic 适配器（桩测试）证明架构能力；
- **成本防护（第一天就做）**：百炼控制台设置消费限额告警；网关的三级 token 预算 +
  usage_ledger 从 M1 起就让每一分钱可见。新用户免费额度通常够 M1–M2 的开发调试；
- 模型名单、批量上限、免费额度以开工时百炼控制台/文档实测为准——平台迭代快，文档不锁死；
- **模型版本钉扎口径（2026-07-07 评审 C36 落档）**：档位映射用滚动别名（qwen-plus 等）是
  主动选择——v1 以免维护换灵活，代价是上游静默升级可能改变行为。缓解与升级路径：
  M4 评测双流水线本就是行为漂移的检测网；生产形态应钉快照版（qwen-plus-20xx-xx-xx）并把
  模型升级当变更管理（评测回归通过才切）；usage_ledger 的 model 字段记录 API 回显名，
  排障时结合日期与百炼发布记录归因。

## 6. GitHub 规范

- **可见性**：建议 public——简历项目的仓库本身就是交付物；若开发期想私有、完成后再公开也可；
- **第一个提交**就包含 `.gitignore`（`.env`、`.venv/`、`__pycache__/`、`*.pyc`、cassette 中的敏感字段）——
  密钥一旦进过历史，`git rm` 救不回来，只能换 key；
- **提交习惯（面试官真的会看提交历史）**：小步提交，一个提交一个主题；
  message 写"为什么"不只写"做了什么"（`feat(gateway): 熔断半开探测加互斥令牌，防多副本惊群`）；
  里程碑打 tag（`m1-gateway`）。你亲手敲代码 + 真实的提交节奏，本身就是项目真实性的最好证明；
- CI 从 M0 起生效：push 即跑 lint + 测试 + import-linter 分层检查。

## 7. 协作方式约定（学习者模式）

> **⚠️ 本节已被取代（2026-07-10 注记）**：协作规约的**权威文本在 00-master-plan §2.1**
> （2026-07-09 合并重写：交付改"四件套"、测试代码 AI 直写、排错表取消、深挖题集中
> `interview-questions.md`）。本节保留为历史记录，任何冲突以 00 §2.1 为准。
> 接续模型操作手册见 `docs/07-handoff-guide.md`。

你亲手敲所有代码、亲手执行所有指令；我每一步交付五件东西：

1. **设计讲解**——这一步在整体架构里的位置、为什么这么设计（对应哪条 ADR/文档）；
2. **完整代码** + 逐段解释——不是伪代码，是可直接工作的实现，关键行有"为什么"；
3. **落盘位置与指令**——文件路径、要执行的命令、命令每个参数的含义；
4. **验收检查点**——敲完之后运行什么、应该看到什么输出，与路线图验收标准对齐；
5. **常见报错排查**——这一步典型的坑和 traceback 长什么样。

配套约定：
- 遇到报错**先自己读 traceback、试着定位**，再把你的判断和报错一起发给我——
  "我觉得是 X 因为 Y，对吗"的提问方式，三个月后你的调试能力会完全不同；
- 每个模块收尾时我出 3–5 个面试深挖问题，你先答，我补充——文档 05 的问答索引就这样逐步内化；
- 你可以随时质疑设计（就像这次的四个问题）——改文档永远比改代码便宜。
