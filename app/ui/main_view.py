#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主视图：负责组装各个 Frame 组件。
"""

from __future__ import annotations

from tkinter import ttk

from app.ui.frames.lists_frame import ListsFrame
from app.ui.frames.log_frame import LogFrame
from app.ui.frames.ops_frame import OpsFrame
from app.ui.frames.push_frame import PushFrame
from app.ui.frames.repo_frame import RepoFrame
from app.ui.frames.summary_frame import SummaryFrame


class MainView:
    def __init__(self, root: ttk.Frame) -> None:
        self._outer = ttk.Frame(root, padding=10)
        self._outer.pack(fill="both", expand=True)
        self._outer.columnconfigure(0, weight=1)
        self._outer.rowconfigure(3, weight=1)
        self._outer.rowconfigure(5, weight=1)

        self.repo_frame = RepoFrame(self._outer)
        self.repo_frame.grid(row=0, column=0, sticky="we")

        self.summary_frame = SummaryFrame(self._outer)
        self.summary_frame.grid(row=1, column=0, sticky="we", pady=(10, 0))

        self.push_frame = PushFrame(self._outer)
        self.push_frame.grid(row=2, column=0, sticky="we", pady=(10, 0))

        self.lists_frame = ListsFrame(self._outer)
        self.lists_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))

        self.ops_frame = OpsFrame(self._outer)
        self.ops_frame.grid(row=4, column=0, sticky="we", pady=(10, 0))

        self.log_frame = LogFrame(self._outer)
        self.log_frame.grid(row=5, column=0, sticky="nsew", pady=(10, 0))

    def set_enabled(self, *, repo_loaded: bool, idle: bool, can_init_repo: bool) -> None:
        self.repo_frame.set_enabled(repo_loaded=repo_loaded, idle=idle, can_init_repo=can_init_repo)
        self.push_frame.set_enabled(repo_loaded=repo_loaded, idle=idle)
        self.lists_frame.set_enabled(repo_loaded=repo_loaded, idle=idle)
        self.ops_frame.set_enabled(repo_loaded=repo_loaded, idle=idle)

