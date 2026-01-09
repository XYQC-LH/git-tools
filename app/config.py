#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置管理模块

包含：
- CONFIG_FILE: 配置文件路径
- AppConfig: 应用配置类
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# 配置文件路径
CONFIG_FILE = Path.home() / ".git_repo_manager_config.json"


@dataclass
class AppConfig:
    """应用配置"""
    
    recent_repos: list[str] = field(default_factory=list)
    window_geometry: str = "1200x760"
    last_repo: str = ""
    
    @classmethod
    def load(cls) -> "AppConfig":
        """从配置文件加载配置"""
        try:
            if CONFIG_FILE.exists():
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                return cls(
                    recent_repos=data.get("recent_repos", [])[:10],
                    window_geometry=data.get("window_geometry", "1200x760"),
                    last_repo=data.get("last_repo", ""),
                )
        except Exception:
            pass
        return cls()
    
    def save(self) -> None:
        """保存配置到文件"""
        try:
            data = {
                "recent_repos": self.recent_repos[:10],
                "window_geometry": self.window_geometry,
                "last_repo": self.last_repo,
            }
            CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    
    def add_recent_repo(self, repo_path: str) -> None:
        """添加最近使用的仓库"""
        repo_path = os.path.abspath(repo_path)
        self.recent_repos = [r for r in self.recent_repos if r != repo_path]
        self.recent_repos.insert(0, repo_path)
        self.recent_repos = self.recent_repos[:10]
        self.last_repo = repo_path
        self.save()