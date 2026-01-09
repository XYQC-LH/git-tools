#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git 仓库管理工具 - 应用包

模块结构：
- config.py: 配置管理
- models.py: 数据模型
- git_utils.py: Git 工具函数
- dialogs.py: 对话框类
- main.py: 主应用类
"""

from app.config import AppConfig, CONFIG_FILE
from app.models import GitCommandError, RepoData
from app.git_utils import (
    mask_remote_url,
    find_repo_root,
    git_capture,
    list_remote_branches_ls_remote,
    list_remote_tags_ls_remote,
    local_ref_exists,
    remote_ref_exists,
    parse_github_url,
    build_github_url,
)
from app.dialogs import RemoteManagerDialog, confirm_danger
from app.main import GitRepoManagerApp, main

__all__ = [
    # 配置
    "AppConfig",
    "CONFIG_FILE",
    # 数据模型
    "GitCommandError",
    "RepoData",
    # Git 工具函数
    "mask_remote_url",
    "find_repo_root",
    "git_capture",
    "list_remote_branches_ls_remote",
    "list_remote_tags_ls_remote",
    "local_ref_exists",
    "remote_ref_exists",
    "parse_github_url",
    "build_github_url",
    # 对话框
    "RemoteManagerDialog",
    "confirm_danger",
    # 主应用
    "GitRepoManagerApp",
    "main",
]