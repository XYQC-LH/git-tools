#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
管理操作区域（OpsFrame）。
"""

from __future__ import annotations

from collections.abc import Callable

import tkinter as tk
from tkinter import ttk


class OpsFrame(ttk.LabelFrame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, text="管理操作")

        self._on_commit: Callable[[], None] | None = None
        self._on_checkout_branch: Callable[[], None] | None = None
        self._on_delete_branch: Callable[[], None] | None = None
        self._on_delete_tag: Callable[[], None] | None = None

        self.btn_commit = ttk.Button(self, text="提交(Commit)", command=self._handle_commit)
        self.btn_commit.grid(row=0, column=0, sticky="w", padx=8, pady=8)

        self.btn_checkout_branch = ttk.Button(self, text="切换分支", command=self._handle_checkout_branch)
        self.btn_checkout_branch.grid(row=0, column=1, sticky="w", padx=8, pady=8)

        self.force_delete_branch_var = tk.BooleanVar(value=False)
        self.chk_force_delete = ttk.Checkbutton(self, text="强制删除(-D)", variable=self.force_delete_branch_var)
        self.chk_force_delete.grid(row=0, column=2, sticky="w", padx=8, pady=8)

        self.btn_delete_branch = ttk.Button(self, text="删除分支（本地+远程）", command=self._handle_delete_branch)
        self.btn_delete_branch.grid(row=0, column=3, sticky="w", padx=8, pady=8)

        ttk.Separator(self, orient="vertical").grid(row=0, column=4, sticky="ns", padx=8, pady=6)

        self.btn_delete_tag = ttk.Button(self, text="删除Tag（本地+远程）", command=self._handle_delete_tag)
        self.btn_delete_tag.grid(row=0, column=5, sticky="w", padx=8, pady=8)

        legend_frame = ttk.Frame(self)
        legend_frame.grid(row=0, column=6, sticky="e", padx=8, pady=8)
        ttk.Label(legend_frame, text="图例：", foreground="gray").pack(side="left")
        ttk.Label(legend_frame, text="[L]本地", foreground="blue").pack(side="left", padx=(4, 0))
        ttk.Label(legend_frame, text="[R]远程", foreground="green").pack(side="left", padx=(4, 0))
        ttk.Label(legend_frame, text="[L+R]两者", foreground="purple").pack(side="left", padx=(4, 0))
        ttk.Label(legend_frame, text="*当前", foreground="red").pack(side="left", padx=(4, 0))

        self.set_enabled(repo_loaded=False, idle=True)

    def set_callbacks(
        self,
        *,
        on_commit: Callable[[], None],
        on_checkout_branch: Callable[[], None],
        on_delete_branch: Callable[[], None],
        on_delete_tag: Callable[[], None],
    ) -> None:
        self._on_commit = on_commit
        self._on_checkout_branch = on_checkout_branch
        self._on_delete_branch = on_delete_branch
        self._on_delete_tag = on_delete_tag

    def set_enabled(self, *, repo_loaded: bool, idle: bool) -> None:
        enabled = bool(repo_loaded and idle)
        state = "normal" if enabled else "disabled"
        self.btn_commit.configure(state=state)
        self.btn_checkout_branch.configure(state=state)
        self.chk_force_delete.configure(state=state)
        self.btn_delete_branch.configure(state=state)
        self.btn_delete_tag.configure(state=state)

    def get_force_delete_branch(self) -> bool:
        return bool(self.force_delete_branch_var.get())

    def _handle_commit(self) -> None:
        if self._on_commit is not None:
            self._on_commit()

    def _handle_checkout_branch(self) -> None:
        if self._on_checkout_branch is not None:
            self._on_checkout_branch()

    def _handle_delete_branch(self) -> None:
        if self._on_delete_branch is not None:
            self._on_delete_branch()

    def _handle_delete_tag(self) -> None:
        if self._on_delete_tag is not None:
            self._on_delete_tag()

