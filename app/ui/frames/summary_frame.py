#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
概要信息区域（SummaryFrame）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class SummaryFrame(ttk.LabelFrame):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, text="概要")

        self.columnconfigure(0, weight=1)

        self.summary_var = tk.StringVar(value="(未加载)")
        ttk.Label(self, textvariable=self.summary_var, justify="left").grid(
            row=0, column=0, sticky="w", padx=8, pady=8
        )

    def set_summary(self, text: str) -> None:
        self.summary_var.set(str(text or ""))

