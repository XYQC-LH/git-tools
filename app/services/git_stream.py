#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git 流式执行服务。

将 subprocess 读输出、解析进度、输出提示等逻辑从 UI 代码中抽离。
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable


PROGRESS_RE = re.compile(
    r"(?P<stage>Counting objects|Compressing objects|Writing objects|Receiving objects|Resolving deltas):\s+(?P<pct>\d+)%"
)


def stream_git(
    repo_root: str,
    args: list[str],
    *,
    on_log: Callable[[str], None],
    on_progress: Callable[[int, str], None] | None = None,
    on_hint: Callable[[str], None] | None = None,
) -> int:
    """流式执行 git 命令，将输出逐行回调给调用方。"""
    argv = ["git", "--no-pager", *args]
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_PAGER", "cat")

    on_log(f"$ {subprocess.list2cmdline(argv)}")

    proc = subprocess.Popen(
        argv,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n")
        on_log(line)

        if on_progress is not None:
            m = PROGRESS_RE.search(line)
            if m:
                on_progress(int(m.group("pct")), str(m.group("stage")))

        if on_hint is not None and ("Username for '" in line or "Password for '" in line):
            on_hint("[HINT] 检测到需要交互式认证；建议配置凭据管理器/SSH Key，或先在终端完成一次认证。")

    return int(proc.wait())

