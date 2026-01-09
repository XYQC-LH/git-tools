#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
仓库选择区域（RepoFrame）。
"""

from __future__ import annotations

from collections.abc import Callable

import tkinter as tk
from tkinter import ttk


class RepoFrame(ttk.LabelFrame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, text="仓库")

        self._on_pick_repo: Callable[[], None] | None = None
        self._on_refresh: Callable[[], None] | None = None
        self._on_refresh_local: Callable[[], None] | None = None
        self._on_fetch: Callable[[], None] | None = None
        self._on_init_repo: Callable[[], None] | None = None
        self._on_open_recent: Callable[[str], None] | None = None
        self._on_clear_recent: Callable[[], None] | None = None
        self._on_repo_enter: Callable[[str], None] | None = None

        self.columnconfigure(1, weight=1)

        self.repo_dir_var = tk.StringVar()
        ttk.Label(self, text="目录：").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.repo_entry = ttk.Entry(self, textvariable=self.repo_dir_var)
        self.repo_entry.grid(row=0, column=1, sticky="we", padx=8, pady=8)
        self.repo_entry.bind("<Return>", lambda _e: self._handle_repo_enter())

        self.btn_pick_repo = ttk.Button(self, text="选择...", command=self._handle_pick_repo)
        self.btn_pick_repo.grid(row=0, column=2, padx=8, pady=8)

        self.btn_recent = ttk.Menubutton(self, text="最近")
        self.btn_recent.grid(row=0, column=3, padx=8, pady=8)
        self._recent_menu = tk.Menu(self.btn_recent, tearoff=0)
        self.btn_recent["menu"] = self._recent_menu

        self.btn_refresh = ttk.Button(self, text="刷新(F5)", command=self._handle_refresh)
        self.btn_refresh.grid(row=0, column=4, padx=8, pady=8)

        self.btn_refresh_local = ttk.Button(self, text="离线刷新", command=self._handle_refresh_local)
        self.btn_refresh_local.grid(row=0, column=5, padx=(0, 8), pady=8)

        self.btn_fetch = ttk.Button(self, text="拉取(Fetch)", command=self._handle_fetch)
        self.btn_fetch.grid(row=0, column=6, padx=(0, 8), pady=8)

        self.btn_init_repo = ttk.Button(self, text="初始化...", command=self._handle_init_repo)
        self.btn_init_repo.grid(row=0, column=7, padx=(0, 8), pady=8)

        self.set_recent_repos([])

    def set_callbacks(
        self,
        *,
        on_pick_repo: Callable[[], None],
        on_refresh: Callable[[], None],
        on_refresh_local: Callable[[], None],
        on_fetch: Callable[[], None],
        on_init_repo: Callable[[], None],
        on_open_recent: Callable[[str], None],
        on_clear_recent: Callable[[], None],
        on_repo_enter: Callable[[str], None],
    ) -> None:
        self._on_pick_repo = on_pick_repo
        self._on_refresh = on_refresh
        self._on_refresh_local = on_refresh_local
        self._on_fetch = on_fetch
        self._on_init_repo = on_init_repo
        self._on_open_recent = on_open_recent
        self._on_clear_recent = on_clear_recent
        self._on_repo_enter = on_repo_enter

    def set_repo_path(self, path: str) -> None:
        self.repo_dir_var.set(str(path or ""))

    def get_repo_path(self) -> str:
        return str(self.repo_dir_var.get() or "")

    def set_recent_repos(self, repos: list[str]) -> None:
        self._recent_menu.delete(0, "end")
        repos = [str(r) for r in (repos or []) if str(r or "").strip()]

        if not repos:
            self._recent_menu.add_command(label="(无最近仓库)", state="disabled")
            return

        for repo_path in repos:
            display_name = repo_path
            if len(display_name) > 50:
                display_name = "..." + display_name[-47:]
            self._recent_menu.add_command(
                label=display_name,
                command=lambda p=repo_path: self._handle_open_recent(p),
            )

        self._recent_menu.add_separator()
        self._recent_menu.add_command(label="清除历史", command=self._handle_clear_recent)

    def set_enabled(self, *, repo_loaded: bool, idle: bool, can_init_repo: bool) -> None:
        self.btn_pick_repo.configure(state=("normal" if idle else "disabled"))
        self.btn_recent.configure(state=("normal" if idle else "disabled"))
        self.repo_entry.configure(state=("normal" if idle else "disabled"))

        repo_state = "normal" if (repo_loaded and idle) else "disabled"
        self.btn_refresh.configure(state=repo_state)
        self.btn_refresh_local.configure(state=repo_state)
        self.btn_fetch.configure(state=repo_state)
        self.btn_init_repo.configure(state=("normal" if (can_init_repo and idle) else "disabled"))

    def _handle_pick_repo(self) -> None:
        if self._on_pick_repo is not None:
            self._on_pick_repo()

    def _handle_refresh(self) -> None:
        if self._on_refresh is not None:
            self._on_refresh()

    def _handle_refresh_local(self) -> None:
        if self._on_refresh_local is not None:
            self._on_refresh_local()

    def _handle_fetch(self) -> None:
        if self._on_fetch is not None:
            self._on_fetch()

    def _handle_init_repo(self) -> None:
        if self._on_init_repo is not None:
            self._on_init_repo()

    def _handle_open_recent(self, repo_path: str) -> None:
        if self._on_open_recent is not None:
            self._on_open_recent(repo_path)

    def _handle_clear_recent(self) -> None:
        if self._on_clear_recent is not None:
            self._on_clear_recent()

    def _handle_repo_enter(self) -> None:
        if self._on_repo_enter is not None:
            self._on_repo_enter(self.get_repo_path())

