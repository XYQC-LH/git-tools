#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
分支/Tag 列表区域（ListsFrame）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import tkinter as tk
from tkinter import ttk


def _item_field(item: Any, key: str, default: Any) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    if hasattr(item, key):
        return getattr(item, key)
    return default


class BranchListFrame(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text="分支（双击切换，右键菜单）")

        self._enabled = True
        self._on_branch_selected: Callable[[str], None] | None = None
        self._on_checkout_branch: Callable[[], None] | None = None
        self._on_set_as_push_target: Callable[[str], None] | None = None
        self._on_delete_branch: Callable[[], None] | None = None
        self._on_copy_text: Callable[[str], None] | None = None

        self._items: list[Any] = []
        self._filtered_items: list[Any] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=(8, 0))
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.listbox = tk.Listbox(self, selectmode="extended")
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._handle_select())
        self.listbox.bind("<Double-Button-1>", lambda _e: self._handle_double_click())
        self.listbox.bind("<Button-3>", self._show_context_menu)

        sb = ttk.Scrollbar(self, orient="vertical", command=self.listbox.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=8)
        self.listbox.configure(yscrollcommand=sb.set)

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="切换到此分支", command=self._handle_checkout)
        self._menu.add_command(label="设为推送目标", command=self._handle_set_as_target)
        self._menu.add_separator()
        self._menu.add_command(label="删除分支", command=self._handle_delete)
        self._menu.add_command(label="复制分支名", command=self._handle_copy)

    def set_callbacks(
        self,
        *,
        on_branch_selected: Callable[[str], None],
        on_checkout_branch: Callable[[], None],
        on_set_as_push_target: Callable[[str], None],
        on_delete_branch: Callable[[], None],
        on_copy_text: Callable[[str], None],
    ) -> None:
        self._on_branch_selected = on_branch_selected
        self._on_checkout_branch = on_checkout_branch
        self._on_set_as_push_target = on_set_as_push_target
        self._on_delete_branch = on_delete_branch
        self._on_copy_text = on_copy_text

    def set_enabled(self, *, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.search_entry.configure(state=("normal" if self._enabled else "disabled"))
        # 注意：Listbox 在 disabled 状态下无法插入/删除内容（且不会抛异常），会导致刷新“没有任何返回”。
        # 这里保持 listbox 可写，交互由 _enabled 标志控制。
        self.listbox.configure(state="normal")

    def set_items(self, items: list[Any]) -> None:
        self._items = list(items or [])
        self._apply_filter()

    def focus_search(self) -> None:
        self.search_var.set("")
        self.search_entry.focus_set()

    def get_selected_name(self) -> str:
        sel = self.listbox.curselection()
        if not sel:
            return ""
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._filtered_items):
            return ""
        item = self._filtered_items[idx]
        return str(_item_field(item, "name", "") or "")

    def _apply_filter(self) -> None:
        term = str(self.search_var.get() or "").strip().lower()
        self._filtered_items = [
            item
            for item in self._items
            if (not term) or (term in str(_item_field(item, "name", "") or "").lower())
        ]
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for item in self._filtered_items:
            self.listbox.insert("end", self._format_item(item))

    def _format_item(self, item: Any) -> str:
        name = str(_item_field(item, "name", "") or "")
        local = bool(_item_field(item, "local", False))
        remote = bool(_item_field(item, "remote", False))
        is_current = bool(_item_field(item, "current", False))

        if local and remote:
            status = "[L+R]"
        elif local:
            status = "[L]"
        elif remote:
            status = "[R]"
        else:
            status = ""

        current_mark = "* " if is_current else "  "
        return f"{current_mark}{name} {status}"

    def _handle_select(self) -> None:
        if not self._enabled:
            return
        name = self.get_selected_name()
        if name and self._on_branch_selected is not None:
            self._on_branch_selected(name)

    def _handle_double_click(self) -> None:
        if not self._enabled:
            return
        if self._on_checkout_branch is not None:
            self._on_checkout_branch()

    def _handle_checkout(self) -> None:
        if not self._enabled:
            return
        if self._on_checkout_branch is not None:
            self._on_checkout_branch()

    def _handle_set_as_target(self) -> None:
        if not self._enabled:
            return
        name = self.get_selected_name()
        if name and self._on_set_as_push_target is not None:
            self._on_set_as_push_target(name)

    def _handle_delete(self) -> None:
        if not self._enabled:
            return
        if self._on_delete_branch is not None:
            self._on_delete_branch()

    def _handle_copy(self) -> None:
        if not self._enabled:
            return
        name = self.get_selected_name()
        if name and self._on_copy_text is not None:
            self._on_copy_text(name)

    def _show_context_menu(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        try:
            self.listbox.selection_clear(0, "end")
            idx = self.listbox.nearest(int(event.y))
            self.listbox.selection_set(idx)
            self._menu.tk_popup(int(event.x_root), int(event.y_root))
        finally:
            self._menu.grab_release()


class TagListFrame(ttk.LabelFrame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, text="Tag（版本）（右键菜单）")

        self._enabled = True
        self._on_checkout_tag: Callable[[], None] | None = None
        self._on_delete_tag: Callable[[], None] | None = None
        self._on_copy_text: Callable[[str], None] | None = None

        self._items: list[Any] = []
        self._filtered_items: list[Any] = []

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, columnspan=2, sticky="we", padx=8, pady=(8, 0))
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.listbox = tk.Listbox(self, selectmode="extended")
        self.listbox.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._handle_copy())
        self.listbox.bind("<Button-3>", self._show_context_menu)

        sb = ttk.Scrollbar(self, orient="vertical", command=self.listbox.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=8)
        self.listbox.configure(yscrollcommand=sb.set)

        self._menu = tk.Menu(self, tearoff=0)
        self._menu.add_command(label="切换到此Tag", command=self._handle_checkout)
        self._menu.add_command(label="复制Tag名", command=self._handle_copy)
        self._menu.add_separator()
        self._menu.add_command(label="删除Tag", command=self._handle_delete)

    def set_callbacks(
        self,
        *,
        on_checkout_tag: Callable[[], None],
        on_delete_tag: Callable[[], None],
        on_copy_text: Callable[[str], None],
    ) -> None:
        self._on_checkout_tag = on_checkout_tag
        self._on_delete_tag = on_delete_tag
        self._on_copy_text = on_copy_text

    def set_enabled(self, *, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.search_entry.configure(state=("normal" if self._enabled else "disabled"))
        # 同 BranchListFrame：保持 listbox 可写，交互由 _enabled 标志控制。
        self.listbox.configure(state="normal")

    def set_items(self, items: list[Any]) -> None:
        self._items = list(items or [])
        self._apply_filter()

    def get_selected_name(self) -> str:
        sel = self.listbox.curselection()
        if not sel:
            return ""
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._filtered_items):
            return ""
        item = self._filtered_items[idx]
        return str(_item_field(item, "name", "") or "")

    def _apply_filter(self) -> None:
        term = str(self.search_var.get() or "").strip().lower()
        self._filtered_items = [
            item
            for item in self._items
            if (not term) or (term in str(_item_field(item, "name", "") or "").lower())
        ]
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        for item in self._filtered_items:
            self.listbox.insert("end", self._format_item(item))

    def _format_item(self, item: Any) -> str:
        name = str(_item_field(item, "name", "") or "")
        local = bool(_item_field(item, "local", False))
        remote = bool(_item_field(item, "remote", False))

        if local and remote:
            status = "[L+R]"
        elif local:
            status = "[L]"
        elif remote:
            status = "[R]"
        else:
            status = ""

        return f"{name} {status}"

    def _handle_checkout(self) -> None:
        if not self._enabled:
            return
        if self._on_checkout_tag is not None:
            self._on_checkout_tag()

    def _handle_delete(self) -> None:
        if not self._enabled:
            return
        if self._on_delete_tag is not None:
            self._on_delete_tag()

    def _handle_copy(self) -> None:
        if not self._enabled:
            return
        name = self.get_selected_name()
        if name and self._on_copy_text is not None:
            self._on_copy_text(name)

    def _show_context_menu(self, event: tk.Event) -> None:
        if not self._enabled:
            return
        try:
            self.listbox.selection_clear(0, "end")
            idx = self.listbox.nearest(int(event.y))
            self.listbox.selection_set(idx)
            self._menu.tk_popup(int(event.x_root), int(event.y_root))
        finally:
            self._menu.grab_release()


class ListsFrame(ttk.PanedWindow):
    def __init__(self, parent: ttk.Frame) -> None:
        super().__init__(parent, orient="horizontal")

        self.branches_frame = BranchListFrame(self)
        self.tags_frame = TagListFrame(self)

        self.add(self.branches_frame, weight=3)
        self.add(self.tags_frame, weight=2)

    def set_callbacks(
        self,
        *,
        on_branch_selected: Callable[[str], None],
        on_checkout_branch: Callable[[], None],
        on_set_as_push_target: Callable[[str], None],
        on_delete_branch: Callable[[], None],
        on_copy_text: Callable[[str], None],
        on_checkout_tag: Callable[[], None],
        on_delete_tag: Callable[[], None],
    ) -> None:
        self.branches_frame.set_callbacks(
            on_branch_selected=on_branch_selected,
            on_checkout_branch=on_checkout_branch,
            on_set_as_push_target=on_set_as_push_target,
            on_delete_branch=on_delete_branch,
            on_copy_text=on_copy_text,
        )
        self.tags_frame.set_callbacks(
            on_checkout_tag=on_checkout_tag,
            on_delete_tag=on_delete_tag,
            on_copy_text=on_copy_text,
        )

    def set_enabled(self, *, repo_loaded: bool, idle: bool) -> None:
        enabled = bool(repo_loaded and idle)
        self.branches_frame.set_enabled(enabled=enabled)
        self.tags_frame.set_enabled(enabled=enabled)

    def set_branches(self, items: list[Any]) -> None:
        self.branches_frame.set_items(items)

    def set_tags(self, items: list[Any]) -> None:
        self.tags_frame.set_items(items)

    def focus_branch_search(self) -> None:
        self.branches_frame.focus_search()

    def get_selected_branch_name(self) -> str:
        return self.branches_frame.get_selected_name()

    def get_selected_tag_name(self) -> str:
        return self.tags_frame.get_selected_name()

    def get_branches_listbox(self) -> tk.Listbox:
        return self.branches_frame.listbox

    def get_tags_listbox(self) -> tk.Listbox:
        return self.tags_frame.listbox
