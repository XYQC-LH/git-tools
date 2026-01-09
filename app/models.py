#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据模型模块

包含：
- GitCommandError: Git 命令执行异常
- RepoData: 仓库数据类
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class GitCommandError(RuntimeError):
    """Git 命令执行失败异常"""
    
    def __init__(self, cmd: list[str], returncode: int, output: str) -> None:
        super().__init__(f"git 命令执行失败({returncode}): {subprocess.list2cmdline(cmd)}")
        self.cmd = cmd
        self.returncode = returncode
        self.output = output


@dataclass(frozen=True)
class RepoData:
    """仓库数据类，存储仓库的各种信息"""
    
    repo_root: str
    branch: str
    detached: bool
    head_short: str
    dirty: bool
    remotes: dict[str, str]  # name -> masked url
    local_branches: list[str]
    remote_branches: list[str]  # e.g. origin/main
    local_tags: list[str]
    remote_tags: list[str]