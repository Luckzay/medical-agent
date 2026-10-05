"""跨平台统一开发启动入口。

用法::

    uv run python -m app.devserver              # 启动开发服务器
    uv run python -m app.devserver --reload     # 热重载
    uv run python -m app.devserver --port 9000  # 自定义端口

为什么需要这个模块：sentence_transformers 启动时即使本地已有模型缓存，
仍会向 huggingface.co 发 HEAD 请求做版本校验，国内直连会超时并长时间重试。
本模块在任何 HuggingFace 库被导入之前完成配置：

- 检测到本地模型缓存 -> 启用离线模式（HF_HUB_OFFLINE=1），直接读缓存
- 未检测到缓存（新机器首次运行）-> 使用国内镜像 HF_ENDPOINT=https://hf-mirror.com

任何机器 clone 仓库后都无需手动 export 环境变量；已存在的环境变量优先，不会被覆盖。
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _configure_huggingface() -> None:
    model = os.environ.get("AGENT_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
    cache_repo = model.replace("/", "--")
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    snapshots = hf_home / "hub" / f"models--{cache_repo}" / "snapshots"
    if snapshots.is_dir() and any(snapshots.iterdir()):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    else:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 开发服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    _configure_huggingface()

    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
