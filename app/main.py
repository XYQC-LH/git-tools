#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主应用模块（组装 View + Controller）。
"""

from __future__ import annotations

import tkinter as tk

from app.controllers.app_controller import AppController
from app.ui.main_view import MainView


class GitRepoManagerApp:
    """Git 仓库管理工具主应用类"""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Git 仓库管理工具（GUI）")

        self.view = MainView(self.root)
        self.controller = AppController(root=self.root, view=self.view)

    def run(self) -> None:
        """运行应用"""
        self.root.mainloop()
        self.controller.shutdown()


def main() -> None:
    """入口函数"""
    GitRepoManagerApp().run()


if __name__ == "__main__":
    main()

