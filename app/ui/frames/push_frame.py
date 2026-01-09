#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
推送配置区域（PushFrame）。
"""

from __future__ import annotations

from collections.abc import Callable

import tkinter as tk
from tkinter import ttk


class PushFrame(ttk.LabelFrame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, text="推送配置")

        self._on_manage_remote: Callable[[], None] | None = None
        self._on_push: Callable[[], None] | None = None

        for col in range(9):
            self.columnconfigure(col, weight=(1 if col in {1, 4, 6} else 0))

        ttk.Label(self, text="远程：").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.remote_var = tk.StringVar(value="")
        self.remote_combo = ttk.Combobox(self, textvariable=self.remote_var, state="disabled", width=14)
        self.remote_combo.grid(row=0, column=1, sticky="we", padx=(0, 4), pady=8)

        self.btn_manage_remote = ttk.Button(self, text="管理...", command=self._handle_manage_remote, width=6)
        self.btn_manage_remote.grid(row=0, column=2, padx=(0, 8), pady=8)

        ttk.Label(self, text="目标分支：").grid(row=0, column=3, sticky="w", padx=(8, 0), pady=8)
        self.target_branch_var = tk.StringVar(value="")
        self.target_branch_entry = ttk.Entry(self, textvariable=self.target_branch_var, width=24)
        self.target_branch_entry.grid(row=0, column=4, sticky="we", padx=(0, 8), pady=8)

        self.set_upstream_var = tk.BooleanVar(value=True)
        self.chk_set_upstream = ttk.Checkbutton(self, text="设置上游(-u)", variable=self.set_upstream_var)
        self.chk_set_upstream.grid(row=0, column=5, sticky="w", padx=(8, 0), pady=8)

        self.force_push_var = tk.BooleanVar(value=False)
        self.chk_force_push = ttk.Checkbutton(self, text="强制推送(--force-with-lease)", variable=self.force_push_var)
        self.chk_force_push.grid(row=0, column=6, sticky="w", padx=(8, 0), pady=8)

        self.create_tag_var = tk.BooleanVar(value=False)
        self.chk_create_tag = ttk.Checkbutton(
            self,
            text="创建并推送Tag(版本)",
            variable=self.create_tag_var,
            command=self._apply_tag_state,
        )
        self.chk_create_tag.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        ttk.Label(self, text="Tag名：").grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(0, 8))
        self.tag_name_var = tk.StringVar(value="")
        self.tag_name_entry = ttk.Entry(self, textvariable=self.tag_name_var, width=24, state="disabled")
        self.tag_name_entry.grid(row=1, column=4, sticky="we", padx=(0, 8), pady=(0, 8))

        ttk.Label(self, text="Tag备注：").grid(row=1, column=5, sticky="w", padx=(8, 0), pady=(0, 8))
        self.tag_msg_var = tk.StringVar(value="")
        self.tag_msg_entry = ttk.Entry(self, textvariable=self.tag_msg_var, state="disabled")
        self.tag_msg_entry.grid(row=1, column=6, columnspan=2, sticky="we", padx=(0, 8), pady=(0, 8))

        self.btn_push = ttk.Button(self, text="开始推送", command=self._handle_push)
        self.btn_push.grid(row=0, column=8, rowspan=2, sticky="ns", padx=(0, 8), pady=8)

        self.set_enabled(repo_loaded=False, idle=True)

    def set_callbacks(self, *, on_manage_remote: Callable[[], None], on_push: Callable[[], None]) -> None:
        self._on_manage_remote = on_manage_remote
        self._on_push = on_push

    def set_enabled(self, *, repo_loaded: bool, idle: bool) -> None:
        enabled = bool(repo_loaded and idle)
        state = "normal" if enabled else "disabled"

        self.remote_combo.configure(state=("readonly" if enabled else "disabled"))
        self.btn_manage_remote.configure(state=state)
        self.target_branch_entry.configure(state=state)
        self.chk_set_upstream.configure(state=state)
        self.chk_force_push.configure(state=state)
        self.chk_create_tag.configure(state=state)
        self.btn_push.configure(state=state)

        self._apply_tag_state()
        if not enabled:
            self.tag_name_entry.configure(state="disabled")
            self.tag_msg_entry.configure(state="disabled")

    def set_remote_values(self, values: list[str]) -> None:
        values = [str(v) for v in (values or []) if str(v or "").strip()]
        self.remote_combo.configure(values=values)

    def add_remote_value_if_missing(self, remote: str) -> None:
        remote = str(remote or "").strip()
        if not remote:
            return
        values = list(self.remote_combo.cget("values") or [])
        if remote not in values:
            self.remote_combo.configure(values=[*values, remote])

    def ensure_remote_selected(self) -> None:
        values = list(self.remote_combo.cget("values") or [])
        current = self.get_remote().strip()
        if values and current not in values:
            self.set_remote(values[0])

    def get_first_remote_value(self) -> str:
        values = list(self.remote_combo.cget("values") or [])
        return str(values[0]) if values else ""

    def get_remote(self) -> str:
        return str(self.remote_var.get() or "")

    def set_remote(self, remote: str) -> None:
        self.remote_var.set(str(remote or ""))

    def get_target_branch(self) -> str:
        return str(self.target_branch_var.get() or "")

    def set_target_branch(self, branch: str) -> None:
        self.target_branch_var.set(str(branch or ""))

    def get_set_upstream(self) -> bool:
        return bool(self.set_upstream_var.get())

    def get_force_push(self) -> bool:
        return bool(self.force_push_var.get())

    def get_create_tag(self) -> bool:
        return bool(self.create_tag_var.get())

    def get_tag_name(self) -> str:
        return str(self.tag_name_var.get() or "")

    def get_tag_message(self) -> str:
        return str(self.tag_msg_var.get() or "")

    def _apply_tag_state(self) -> None:
        enabled = str(self.btn_push.cget("state") or "") != "disabled"
        if not enabled or not self.get_create_tag():
            self.tag_name_entry.configure(state="disabled")
            self.tag_msg_entry.configure(state="disabled")
            return
        self.tag_name_entry.configure(state="normal")
        self.tag_msg_entry.configure(state="normal")

    def _handle_manage_remote(self) -> None:
        if self._on_manage_remote is not None:
            self._on_manage_remote()

    def _handle_push(self) -> None:
        if self._on_push is not None:
            self._on_push()

