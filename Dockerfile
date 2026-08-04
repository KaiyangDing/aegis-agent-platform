# M4.7（#26）：api / worker / beat / migrate 单镜像多 command——同代码同依赖，
# 三份 Dockerfile 是漂移源（plans/m4 §3-2 定案）。基底=uv 官方 Python 镜像。
# 镜像内无 .env 无密钥（.dockerignore 第一行）；密钥经 compose env_file 注入运行时。
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 依赖层先行：锁文件不变则该层缓存命中（--no-install-project=本包代码后到再装）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# COPY 白名单式逐项（§7-5：绝不 COPY . 一把梭——.env 进镜像层=进历史）
COPY alembic.ini ./
COPY migrations ./migrations
COPY aegis ./aegis
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

# 缺省 command 给 api（应用入口无模块级 app，须 --factory——M4.0① 差异⑷）；
# compose 逐服务覆盖为 alembic / celery worker / celery beat
CMD ["uvicorn", "aegis.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
