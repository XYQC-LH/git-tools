#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
仓库数据采集服务。

将“读取仓库状态/分支/Tag/远程”等逻辑从 UI 代码中抽离，保持无 UI 依赖。
"""

from __future__ import annotations

from app.git_utils import (
    git_capture,
    list_remote_branches_ls_remote,
    list_remote_tags_ls_remote,
    mask_remote_url,
)
from app.models import GitCommandError, RepoData


def collect_repo_data(repo_root: str, *, remote_query: str | None) -> RepoData:
    """收集仓库数据（可选查询远程分支/Tag）。"""
    try:
        head_short = git_capture(repo_root, ["rev-parse", "--short", "HEAD"]).strip()
    except GitCommandError:
        head_short = "(未提交)"

    detached = False
    try:
        branch = git_capture(repo_root, ["symbolic-ref", "--quiet", "--short", "HEAD"]).strip()
        if not branch:
            detached = True
            branch = "(detached HEAD)"
    except GitCommandError:
        detached = True
        branch = "(detached HEAD)"

    dirty = bool(git_capture(repo_root, ["status", "--porcelain=v1"]).strip())

    remotes: dict[str, str] = {}
    remote_names = [r.strip() for r in git_capture(repo_root, ["remote"]).splitlines() if r.strip()]
    for name in remote_names:
        url = git_capture(repo_root, ["remote", "get-url", name]).strip()
        remotes[name] = mask_remote_url(url)

    local_branches = [
        b.strip()
        for b in git_capture(repo_root, ["for-each-ref", "--format=%(refname:short)", "refs/heads"]).splitlines()
        if b.strip()
    ]
    local_branches.sort()

    local_tags = [t.strip() for t in git_capture(repo_root, ["tag", "--list"]).splitlines() if t.strip()]
    local_tags.sort()

    if remote_query:
        remote_branches = list_remote_branches_ls_remote(repo_root, remote=remote_query)
        remote_tags = list_remote_tags_ls_remote(repo_root, remote=remote_query)
    else:
        remote_branches = []
        remote_tags = []

    return RepoData(
        repo_root=repo_root,
        branch=branch,
        detached=detached,
        head_short=head_short,
        dirty=dirty,
        remotes=remotes,
        local_branches=local_branches,
        remote_branches=remote_branches,
        local_tags=local_tags,
        remote_tags=remote_tags,
    )

