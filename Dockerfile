FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.10.0
COPY pyproject.toml uv.lock README.md LICENSE NOTICE.md ./
COPY undertow_mcp_adapter ./undertow_mcp_adapter
RUN uv sync --locked --no-dev --no-editable --no-cache
USER 65532:65532
CMD ["/app/.venv/bin/undertow-mcp"]
