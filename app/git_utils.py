#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Git 工具函数模块

包含所有 Git 命令封装函数和 URL 解析工具。
"""

from __future__ import annotations

import os
import re
import subprocess

from app.models import GitCommandError


def mask_remote_url(url: str) -> str:
    """
    脱敏远程 URL，隐藏认证信息。
    
    Args:
        url: 原始 URL
        
    Returns:
        脱敏后的 URL
    """
    url = (url or "").strip()
    if not url:
        return url
    try:
        if "://" in url:
            scheme, rest = url.split("://", 1)
            head = rest.split("/", 1)[0]
            if "@" in head:
                _, tail = rest.split("@", 1)
                return f"{scheme}://***@{tail}"
            return url
        if "@" in url and ":" in url:
            _, tail = url.split("@", 1)
            return f"***@{tail}"
    except Exception:
        return url
    return url


def find_repo_root(start_dir: str) -> str:
    """
    查找 Git 仓库根目录。
    
    Args:
        start_dir: 起始目录
        
    Returns:
        仓库根目录路径
        
    Raises:
        GitCommandError: 如果不是 Git 仓库
        RuntimeError: 如果无法识别仓库根目录
    """
    start_dir = os.path.abspath(start_dir)
    completed = subprocess.run(
        ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise GitCommandError(
            ["git", "-C", start_dir, "rev-parse", "--show-toplevel"],
            completed.returncode,
            (completed.stdout or "") + (completed.stderr or ""),
        )
    root = (completed.stdout or "").strip()
    if not root:
        raise RuntimeError("无法识别 Git 仓库根目录")
    return root


def git_capture(repo_root: str, args: list[str]) -> str:
    """
    执行 Git 命令并捕获输出。
    
    Args:
        repo_root: 仓库根目录
        args: Git 命令参数
        
    Returns:
        命令输出
        
    Raises:
        GitCommandError: 如果命令执行失败
    """
    completed = subprocess.run(
        ["git", "--no-pager", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise GitCommandError(["git", "--no-pager", *args], completed.returncode, out)
    return out


def list_remote_branches_ls_remote(repo_root: str, *, remote: str) -> list[str]:
    """
    使用 ls-remote 列出远程分支。
    
    Args:
        repo_root: 仓库根目录
        remote: 远程名称
        
    Returns:
        远程分支名称列表
    """
    out = git_capture(repo_root, ["ls-remote", "--heads", remote])
    branches: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        _sha, ref = parts[0].strip(), parts[1].strip()
        if not ref.startswith("refs/heads/"):
            continue
        name = ref[len("refs/heads/"):].strip()
        if not name:
            continue
        branches.append(name)
    branches.sort()
    return branches


def list_remote_tags_ls_remote(repo_root: str, *, remote: str) -> list[str]:
    """
    使用 ls-remote 列出远程 Tag。
    
    Args:
        repo_root: 仓库根目录
        remote: 远程名称
        
    Returns:
        远程 Tag 名称列表
    """
    out = git_capture(repo_root, ["ls-remote", "--tags", remote])
    tag_to_sha: dict[str, str] = {}
    tag_has_peeled: set[str] = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        sha, ref = parts[0].strip(), parts[1].strip()
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):].strip()
        if not name:
            continue
        peeled = False
        if name.endswith("^{}"):
            peeled = True
            name = name[:-3]
        if not name:
            continue
        if peeled:
            tag_has_peeled.add(name)
            tag_to_sha[name] = sha
            continue
        if name in tag_has_peeled:
            continue
        tag_to_sha.setdefault(name, sha)
    tags = sorted(tag_to_sha.keys())
    return tags


def local_ref_exists(repo_root: str, ref: str) -> bool:
    """
    检查本地引用是否存在。
    
    Args:
        repo_root: 仓库根目录
        ref: 引用路径（如 refs/heads/main）
        
    Returns:
        是否存在
    """
    completed = subprocess.run(
        ["git", "--no-pager", "show-ref", "--verify", "--quiet", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.returncode == 0


def remote_ref_exists(repo_root: str, *, remote: str, ref: str) -> bool:
    """
    检查远程引用是否存在。
    
    Args:
        repo_root: 仓库根目录
        remote: 远程名称
        ref: 引用路径
        
    Returns:
        是否存在
        
    Raises:
        GitCommandError: 如果查询失败
    """
    completed = subprocess.run(
        ["git", "--no-pager", "ls-remote", remote, ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise GitCommandError(["git", "--no-pager", "ls-remote", remote, ref], completed.returncode, out)
    return bool((completed.stdout or "").strip())


def parse_github_url(url_or_shorthand: str) -> tuple[str, str] | None:
    """
    解析 GitHub URL 或简写格式，返回 (owner, repo) 元组。
    
    支持的格式：
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo
    - git@github.com:owner/repo.git
    - git@github.com:owner/repo
    - owner/repo
    
    Args:
        url_or_shorthand: URL 或简写格式
        
    Returns:
        (owner, repo) 元组，如果无法解析则返回 None
    """
    url_or_shorthand = url_or_shorthand.strip()
    if not url_or_shorthand:
        return None
    
    # 简写格式: owner/repo
    if "/" in url_or_shorthand and ":" not in url_or_shorthand and "." not in url_or_shorthand.split("/")[0]:
        parts = url_or_shorthand.split("/")
        if len(parts) == 2 and parts[0] and parts[1]:
            owner, repo = parts[0].strip(), parts[1].strip()
            if repo.endswith(".git"):
                repo = repo[:-4]
            return (owner, repo)
    
    # HTTPS 格式: https://github.com/owner/repo.git
    https_pattern = re.compile(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", re.IGNORECASE)
    m = https_pattern.match(url_or_shorthand)
    if m:
        return (m.group(1), m.group(2))
    
    # SSH 格式: git@github.com:owner/repo.git
    ssh_pattern = re.compile(r"git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$", re.IGNORECASE)
    m = ssh_pattern.match(url_or_shorthand)
    if m:
        return (m.group(1), m.group(2))
    
    return None


def build_github_url(owner: str, repo: str, protocol: str = "https") -> str:
    """
    根据 owner/repo 和协议构建 GitHub URL。
    
    Args:
        owner: 仓库所有者
        repo: 仓库名称
        protocol: 协议类型（https 或 ssh）
        
    Returns:
        构建的 URL
    """
    if protocol.lower() == "ssh":
        return f"git@github.com:{owner}/{repo}.git"
    else:
        return f"https://github.com/{owner}/{repo}.git"


GIT_CONFIG_KEY_GITHUB_REPO = "auto-github.githubRepo"
GIT_CONFIG_KEY_PROTOCOL = "auto-github.protocol"


def normalize_github_owner_repo(value: str) -> str | None:
    """
    规范化 GitHub 仓库标识，返回 owner/repo 形式。

    支持：owner/repo、HTTPS URL、SSH URL。
    """
    parsed = parse_github_url(value.strip())
    if not parsed:
        return None
    owner, repo = parsed
    return f"{owner}/{repo}"


def _git_config_get_local(repo_root: str, key: str) -> str | None:
    completed = subprocess.run(
        ["git", "--no-pager", "config", "--local", "--get", key],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        return None
    value = (completed.stdout or "").strip()
    return value or None


def _git_config_unset_local(repo_root: str, key: str) -> None:
    completed = subprocess.run(
        ["git", "--no-pager", "config", "--local", "--unset", key],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode in {0, 5}:
        return
    out = (completed.stdout or "") + (completed.stderr or "")
    raise GitCommandError(["git", "--no-pager", "config", "--local", "--unset", key], completed.returncode, out)


def read_repo_github_repo(repo_root: str) -> str | None:
    """读取当前仓库保存的 GitHub 仓库（owner/repo 或 URL）。"""
    return _git_config_get_local(repo_root, GIT_CONFIG_KEY_GITHUB_REPO)


def read_repo_github_protocol(repo_root: str) -> str | None:
    """读取当前仓库保存的协议（https/ssh）。"""
    value = (_git_config_get_local(repo_root, GIT_CONFIG_KEY_PROTOCOL) or "").strip().lower()
    if value in {"https", "ssh"}:
        return value
    return None


def write_repo_github_config(repo_root: str, *, owner_repo: str, protocol: str) -> None:
    """写入当前仓库的 GitHub 配置（owner/repo + 协议）。"""
    owner_repo = owner_repo.strip()
    protocol = protocol.strip().lower()
    if protocol not in {"https", "ssh"}:
        protocol = "https"
    git_capture(repo_root, ["config", "--local", GIT_CONFIG_KEY_GITHUB_REPO, owner_repo])
    git_capture(repo_root, ["config", "--local", GIT_CONFIG_KEY_PROTOCOL, protocol])


def clear_repo_github_config(repo_root: str) -> None:
    """清除当前仓库保存的 GitHub 配置。"""
    _git_config_unset_local(repo_root, GIT_CONFIG_KEY_GITHUB_REPO)
    _git_config_unset_local(repo_root, GIT_CONFIG_KEY_PROTOCOL)


def infer_github_config_from_origin(repo_root: str) -> tuple[str, str] | None:
    """从 origin 远程 URL 推断 (owner/repo, protocol)。"""
    try:
        url = (git_capture(repo_root, ["remote", "get-url", "origin"]) or "").strip()
    except GitCommandError:
        return None
    if not url:
        return None
    owner_repo = normalize_github_owner_repo(url)
    if not owner_repo:
        return None
    protocol = "ssh" if url.lower().startswith("git@") else "https"
    return (owner_repo, protocol)


def get_effective_github_config(repo_root: str) -> tuple[str | None, str]:
    """
    获取当前仓库的 GitHub 配置。

    优先读取自定义 key（auto-github.*）；若缺失则尝试从 origin 推断。
    """
    protocol = read_repo_github_protocol(repo_root) or "https"

    raw = read_repo_github_repo(repo_root)
    if raw:
        owner_repo = normalize_github_owner_repo(raw)
        if owner_repo:
            return (owner_repo, protocol)

    inferred = infer_github_config_from_origin(repo_root)
    if inferred:
        return inferred

    return (None, protocol)
