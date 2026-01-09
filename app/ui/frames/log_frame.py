#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
日志 / 进度区域（LogFrame）。
"""

from __future__ import annotations

from collections.abc import Callable

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText


class LogFrame(ttk.LabelFrame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, text="日志 / 进度")

        self._on_clear_log: Callable[[], None] | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.log = ScrolledText(self, height=12, wrap="word")
        self.log.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
        self.log.configure(state="disabled")

        self.progress_var = tk.IntVar(value=0)
        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100, variable=self.progress_var)
        self.progress.grid(row=1, column=0, sticky="we", padx=8, pady=(0, 8))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self, textvariable=self.status_var).grid(row=1, column=1, sticky="w", padx=8, pady=(0, 8))

        self.btn_clear = ttk.Button(self, text="清空日志", command=self._handle_clear_log)
        self.btn_clear.grid(row=1, column=2, sticky="e", padx=8, pady=(0, 8))

    def set_callbacks(self, *, on_clear_log: Callable[[], None]) -> None:
        self._on_clear_log = on_clear_log

    def append_log(self, text: str) -> None:
        text = str(text or "")
        self.log.configure(state="normal")
        self.log.insert("end", text + ("" if text.endswith("\n") else "\n"))
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def set_status(self, text: str) -> None:
        self.status_var.set(str(text or ""))

    def set_progress(self, pct: int, stage: str) -> None:
        pct = max(0, min(100, int(pct)))
        if str(self.progress["mode"]) != "determinate":
            self.progress.stop()
            self.progress.configure(mode="determinate")
        self.progress_var.set(pct)
        self.status_var.set(f"{stage} {pct}%")

    def start_indeterminate(self) -> None:
        self.progress_var.set(0)
        self.progress.configure(mode="indeterminate")
        self.progress.start(10)

    def finish_progress(self, *, ok: bool) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress_var.set(100 if ok else 0)

    def _handle_clear_log(self) -> None:
        if self._on_clear_log is not None:
            self._on_clear_log()

