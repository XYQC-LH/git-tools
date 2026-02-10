#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
对话框模块

包含：
- confirm_danger: 危险操作确认对话框
- prompt_commit_dialog: 提交(Commit)对话框
- prompt_git_identity_dialog: Git 身份（user.name/user.email）配置对话框
- prompt_github_repo_config: GitHub 仓库配置对话框（用于首次推送/自动补齐）
- RemoteManagerDialog: 远程仓库管理对话框
"""

from __future__ import annotations

import threading
from collections.abc import Callable

import tkinter as tk
from tkinter import messagebox, ttk

from app.models import GitCommandError
from app.git_utils import (
    git_capture,
    parse_github_url,
    build_github_url,
    get_effective_github_config,
    normalize_github_owner_repo,
    write_repo_github_config,
    clear_repo_github_config,
)


def confirm_danger(parent: tk.Tk, *, action_type: str, impact: str, risks: str) -> bool:
    """
    显示危险操作确认对话框。
    
    Args:
        parent: 父窗口
        action_type: 操作类型
        impact: 影响范围
        risks: 风险评估
        
    Returns:
        用户是否确认
    """
    text = (
        "危险操作检测！\n\n"
        f"操作类型：{action_type}\n"
        f"影响范围：{impact}\n"
        f"风险评估：{risks}\n\n"
        "请确认是否继续？"
    )
    return bool(messagebox.askyesno("危险操作确认", text, parent=parent))


def prompt_github_repo_config(
    parent: tk.Tk,
    *,
    initial_owner_repo: str = "",
    initial_protocol: str = "https",
) -> tuple[str, str] | None:
    """提示用户输入 GitHub 仓库（owner/repo）与协议，返回 (owner/repo, protocol)。"""
    result: tuple[str, str] | None = None

    dialog = tk.Toplevel(parent)
    dialog.title("GitHub 仓库配置")
    dialog.geometry("640x240")
    dialog.transient(parent)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=10)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    owner_repo_var = tk.StringVar(value=(initial_owner_repo or "").strip())
    protocol_var = tk.StringVar(value=("ssh" if str(initial_protocol).strip().lower() == "ssh" else "https"))
    preview_var = tk.StringVar(value="")

    ttk.Label(frame, text="GitHub 仓库：").grid(row=0, column=0, sticky="w", pady=(0, 8))
    entry = ttk.Entry(frame, textvariable=owner_repo_var)
    entry.grid(row=0, column=1, sticky="we", pady=(0, 8))
    ttk.Label(
        frame,
        text="支持格式：user/repo、https://github.com/user/repo.git、git@github.com:user/repo.git",
        foreground="gray",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 8))

    protocol_frame = ttk.Frame(frame)
    protocol_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 8))
    ttk.Label(protocol_frame, text="协议：").pack(side="left")
    ttk.Radiobutton(protocol_frame, text="HTTPS", variable=protocol_var, value="https").pack(side="left", padx=(8, 0))
    ttk.Radiobutton(protocol_frame, text="SSH", variable=protocol_var, value="ssh").pack(side="left", padx=(8, 0))

    preview_frame = ttk.Frame(frame)
    preview_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=(0, 8))
    ttk.Label(preview_frame, text="预览：").pack(side="left")
    ttk.Label(preview_frame, textvariable=preview_var, foreground="blue").pack(side="left", padx=(8, 0))

    ttk.Label(frame, text="说明：用于首次推送时自动创建 origin 远程。", foreground="gray").grid(
        row=4, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )

    def update_preview() -> None:
        text = owner_repo_var.get().strip()
        if not text:
            preview_var.set("(请输入 GitHub 仓库，例如 user/repo)")
            return
        parsed = parse_github_url(text)
        if not parsed:
            preview_var.set("(无法解析为 GitHub 仓库)")
            return
        owner, repo = parsed
        preview_var.set(build_github_url(owner, repo, protocol_var.get()))

    def on_ok() -> None:
        nonlocal result
        text = owner_repo_var.get().strip()
        if not text:
            messagebox.showerror("错误", "GitHub 仓库不能为空。", parent=dialog)
            return
        parsed = parse_github_url(text)
        if not parsed:
            messagebox.showerror("错误", "无法解析为 GitHub 仓库，请输入 user/repo 或 GitHub URL。", parent=dialog)
            return
        owner, repo = parsed
        result = (f"{owner}/{repo}", protocol_var.get())
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    owner_repo_var.trace_add("write", lambda *_: update_preview())
    protocol_var.trace_add("write", lambda *_: update_preview())
    update_preview()

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right")
    ttk.Button(btn_frame, text="保存并继续", command=on_ok).pack(side="right", padx=(0, 8))

    dialog.bind("<Escape>", lambda _e: on_cancel())
    dialog.bind("<Return>", lambda _e: on_ok())
    entry.focus_set()

    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")

    parent.wait_window(dialog)
    return result


def prompt_commit_dialog(
    parent: tk.Tk,
    *,
    default_message: str = "",
    stage_all_default: bool = True,
    on_generate_ai: Callable[[bool], str] | None = None,
    on_generate_ai_stream: Callable[[bool, Callable[[str], None]], str] | None = None,
) -> tuple[str, bool] | None:
    """提示用户输入提交信息，并选择是否暂存全部改动。"""
    result: tuple[str, bool] | None = None
    generating = False

    dialog = tk.Toplevel(parent)
    dialog.title("提交(Commit)")
    dialog.geometry("760x260")
    dialog.transient(parent)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=10)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    msg_var = tk.StringVar(value=(default_message or "").strip())
    stage_all_var = tk.BooleanVar(value=bool(stage_all_default))

    ttk.Label(frame, text="提交信息：").grid(row=0, column=0, sticky="w", pady=(0, 8))
    entry = ttk.Entry(frame, textvariable=msg_var)
    entry.grid(row=0, column=1, sticky="we", pady=(0, 8))

    btn_ai: ttk.Button | None = None

    ttk.Checkbutton(frame, text="暂存全部改动（git add -A）", variable=stage_all_var).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )
    ttk.Label(frame, text="建议：你可以手写，也可以点击“AI生成”自动填写。", foreground="gray").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )

    ai_status_var = tk.StringVar(value="")
    ttk.Label(frame, textvariable=ai_status_var, foreground="gray").grid(
        row=3, column=0, columnspan=2, sticky="w", pady=(0, 8)
    )

    def normalize_single_line(text: str) -> str:
        lines = [segment.strip() for segment in str(text or "").replace("\r", "\n").split("\n") if segment.strip()]
        merged = " ".join(lines).strip()
        return " ".join(merged.split())

    def on_ai_done(generated: str | None, error: str | None) -> None:
        nonlocal generating
        generating = False
        if btn_ai is not None:
            btn_ai.configure(state="normal")

        if error:
            ai_status_var.set("AI 生成失败，请手写或重试。")
            messagebox.showerror("AI生成失败", str(error), parent=dialog)
            return

        text = normalize_single_line(generated or "")
        if not text:
            ai_status_var.set("AI 未返回有效内容，请手写或重试。")
            return

        msg_var.set(text)
        entry.focus_set()
        entry.icursor("end")
        ai_status_var.set("AI 已生成提交信息，可直接提交或继续编辑。")

    def on_generate() -> None:
        nonlocal generating
        if generating:
            return
        if on_generate_ai is None and on_generate_ai_stream is None:
            return

        generating = True
        if btn_ai is not None:
            btn_ai.configure(state="disabled")
        ai_status_var.set("AI 正在生成提交信息，请稍候...")
        msg_var.set("")

        stage_all = bool(stage_all_var.get())

        def append_chunk(chunk: str) -> None:
            if not chunk:
                return

            def do_append() -> None:
                text = str(msg_var.get() or "") + str(chunk)
                text = text.replace("\r", "").replace("\n", " ")
                text = " ".join(text.split())
                msg_var.set(text)
                entry.icursor("end")
                ai_status_var.set("AI 正在流式生成...")

            dialog.after(0, do_append)

        def worker() -> None:
            try:
                if on_generate_ai_stream is not None:
                    generated = on_generate_ai_stream(stage_all, append_chunk)
                elif on_generate_ai is not None:
                    generated = on_generate_ai(stage_all)
                else:
                    generated = ""
                dialog.after(0, lambda: on_ai_done(generated, None))
            except Exception as e:
                dialog.after(0, lambda: on_ai_done(None, str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def on_ok() -> None:
        nonlocal result
        if generating:
            messagebox.showinfo("提示", "AI 仍在生成中，请稍候或取消后手写。", parent=dialog)
            return
        msg = msg_var.get().strip()
        if not msg:
            messagebox.showerror("错误", "提交信息不能为空。", parent=dialog)
            return
        if "\n" in msg or "\r" in msg:
            messagebox.showerror("错误", "提交信息请使用单行文本。", parent=dialog)
            return
        result = (msg, bool(stage_all_var.get()))
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right")
    ttk.Button(btn_frame, text="提交", command=on_ok).pack(side="right", padx=(0, 8))
    if on_generate_ai is not None:
        btn_ai = ttk.Button(btn_frame, text="AI生成", command=on_generate)
        btn_ai.pack(side="right", padx=(0, 8))

    dialog.bind("<Escape>", lambda _e: on_cancel())
    dialog.bind("<Return>", lambda _e: on_ok())
    entry.focus_set()

    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")

    parent.wait_window(dialog)
    return result


def prompt_git_identity_dialog(
    parent: tk.Tk,
    *,
    default_name: str = "",
    default_email: str = "",
    default_scope: str = "local",
) -> tuple[str, str, str] | None:
    """
    提示用户配置 Git 身份信息（user.name / user.email）。

    Returns:
        (name, email, scope) 其中 scope 为 "local" 或 "global"
    """
    result: tuple[str, str, str] | None = None

    dialog = tk.Toplevel(parent)
    dialog.title("配置 Git 身份")
    dialog.geometry("720x280")
    dialog.transient(parent)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=10)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)

    name_var = tk.StringVar(value=(default_name or "").strip())
    email_var = tk.StringVar(value=(default_email or "").strip())
    scope = (default_scope or "").strip().lower()
    scope_var = tk.StringVar(value=("global" if scope == "global" else "local"))

    ttk.Label(frame, text="姓名(user.name)：").grid(row=0, column=0, sticky="w", pady=(0, 8))
    entry_name = ttk.Entry(frame, textvariable=name_var)
    entry_name.grid(row=0, column=1, sticky="we", pady=(0, 8))

    ttk.Label(frame, text="邮箱(user.email)：").grid(row=1, column=0, sticky="w", pady=(0, 8))
    entry_email = ttk.Entry(frame, textvariable=email_var)
    entry_email.grid(row=1, column=1, sticky="we", pady=(0, 8))

    scope_frame = ttk.LabelFrame(frame, text="作用范围")
    scope_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=(4, 8))
    scope_frame.columnconfigure(0, weight=1)

    ttk.Radiobutton(
        scope_frame,
        text="仅本仓库（写入 .git/config）",
        variable=scope_var,
        value="local",
    ).grid(row=0, column=0, sticky="w", padx=8, pady=(6, 2))
    ttk.Radiobutton(
        scope_frame,
        text="全局（写入 ~/.gitconfig，对所有仓库生效）",
        variable=scope_var,
        value="global",
    ).grid(row=1, column=0, sticky="w", padx=8, pady=(0, 6))

    ttk.Label(
        frame,
        text="提示：Git 必须配置 user.name/user.email 才能创建提交。",
        foreground="gray",
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

    def on_ok() -> None:
        nonlocal result
        name = name_var.get().strip()
        email = email_var.get().strip()
        if not name:
            messagebox.showerror("错误", "姓名(user.name)不能为空。", parent=dialog)
            return
        if "\n" in name or "\r" in name:
            messagebox.showerror("错误", "姓名请使用单行文本。", parent=dialog)
            return
        if not email:
            messagebox.showerror("错误", "邮箱(user.email)不能为空。", parent=dialog)
            return
        if "\n" in email or "\r" in email:
            messagebox.showerror("错误", "邮箱请使用单行文本。", parent=dialog)
            return
        if "@" not in email:
            ok = messagebox.askyesno("提示", "邮箱中未包含 '@'，仍然继续吗？", parent=dialog)
            if not ok:
                return
        result = (name, email, str(scope_var.get() or "local"))
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=4, column=0, columnspan=2, sticky="e", pady=(8, 0))
    ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side="right")
    ttk.Button(btn_frame, text="保存并继续", command=on_ok).pack(side="right", padx=(0, 8))

    dialog.bind("<Escape>", lambda _e: on_cancel())
    dialog.bind("<Return>", lambda _e: on_ok())
    entry_name.focus_set()

    dialog.update_idletasks()
    x = parent.winfo_x() + (parent.winfo_width() - dialog.winfo_width()) // 2
    y = parent.winfo_y() + (parent.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")

    parent.wait_window(dialog)
    return result


class RemoteManagerDialog:
    """远程仓库管理对话框"""
    
    def __init__(self, parent: tk.Tk, repo_root: str, current_remotes: dict[str, str], on_change_callback) -> None:
        """
        初始化远程仓库管理对话框。
        
        Args:
            parent: 父窗口
            repo_root: 仓库根目录
            current_remotes: 当前远程配置 {name: url}
            on_change_callback: 配置变更时的回调函数
        """
        self.parent = parent
        self.repo_root = repo_root
        self.current_remotes = current_remotes.copy()  # name -> url
        self.on_change_callback = on_change_callback
        self.changed = False
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("远程仓库管理")
        self.dialog.geometry("700x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self._build_ui()
        self._refresh_remote_list()
        
        # 居中显示
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")
    
    def _build_ui(self) -> None:
        """构建对话框 UI"""
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 远程列表区域
        list_frame = ttk.LabelFrame(main_frame, text="已配置的远程仓库")
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 远程列表
        columns = ("name", "url")
        self.remote_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=6)
        self.remote_tree.heading("name", text="名称")
        self.remote_tree.heading("url", text="URL")
        self.remote_tree.column("name", width=100, minwidth=80)
        self.remote_tree.column("url", width=500, minwidth=200)
        self.remote_tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.remote_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=8)
        self.remote_tree.configure(yscrollcommand=scrollbar.set)
        
        # 列表操作按钮
        list_btn_frame = ttk.Frame(list_frame)
        list_btn_frame.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        
        ttk.Button(list_btn_frame, text="编辑选中", command=self._on_edit_remote).pack(side="left", padx=(0, 8))
        ttk.Button(list_btn_frame, text="删除选中", command=self._on_delete_remote).pack(side="left", padx=(0, 8))
        ttk.Button(list_btn_frame, text="刷新列表", command=self._refresh_from_git).pack(side="left")
        
        # 添加远程区域
        add_frame = ttk.LabelFrame(main_frame, text="添加远程仓库")
        add_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        add_frame.columnconfigure(1, weight=1)
        
        # 远程名称
        ttk.Label(add_frame, text="远程名称：").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.remote_name_var = tk.StringVar(value="origin")
        self.remote_name_entry = ttk.Entry(add_frame, textvariable=self.remote_name_var, width=20)
        self.remote_name_entry.grid(row=0, column=1, sticky="w", padx=(0, 8), pady=8)
        
        owner_repo, protocol = get_effective_github_config(self.repo_root)

        # GitHub 仓库地址（用于快速添加远程，也可保存为本仓库默认配置）
        ttk.Label(add_frame, text="GitHub 仓库：").grid(row=1, column=0, sticky="w", padx=8, pady=(0, 8))
        self.github_url_var = tk.StringVar(value=(owner_repo or ""))
        self.github_url_var.trace_add("write", lambda *_: self._update_preview())
        self.github_url_entry = ttk.Entry(add_frame, textvariable=self.github_url_var)
        self.github_url_entry.grid(row=1, column=1, sticky="we", padx=(0, 8), pady=(0, 8))
        
        ttk.Label(add_frame, text="支持格式：user/repo、https://github.com/user/repo.git、git@github.com:user/repo.git",
                  foreground="gray").grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        
        # 协议选择
        protocol_frame = ttk.Frame(add_frame)
        protocol_frame.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        
        ttk.Label(protocol_frame, text="协议：").pack(side="left")
        self.protocol_var = tk.StringVar(value=(protocol or "https"))
        self.protocol_var.trace_add("write", lambda *_: self._update_preview())
        ttk.Radiobutton(protocol_frame, text="HTTPS", variable=self.protocol_var, value="https").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(protocol_frame, text="SSH", variable=self.protocol_var, value="ssh").pack(side="left", padx=(8, 0))
        
        # 预览
        preview_frame = ttk.Frame(add_frame)
        preview_frame.grid(row=4, column=0, columnspan=2, sticky="we", padx=8, pady=(0, 8))
        
        ttk.Label(preview_frame, text="预览：").pack(side="left")
        self.preview_var = tk.StringVar(value="(请输入仓库地址)")
        ttk.Label(preview_frame, textvariable=self.preview_var, foreground="blue").pack(side="left", padx=(8, 0))

        # 配置管理按钮
        cfg_frame = ttk.Frame(add_frame)
        cfg_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        ttk.Button(cfg_frame, text="保存为默认(用于 origin)", command=self._on_save_default_github).pack(side="left", padx=(0, 8))
        ttk.Button(cfg_frame, text="清除默认", command=self._on_clear_default_github).pack(side="left")
        
        # 添加按钮
        ttk.Button(add_frame, text="添加此远程", command=self._on_add_remote).grid(row=6, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        
        # 底部按钮
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=2, column=0, sticky="e")
        
        ttk.Button(btn_frame, text="关闭", command=self._on_close).pack(side="right")

        self._update_preview()
    
    def _refresh_remote_list(self) -> None:
        """刷新远程列表显示"""
        for item in self.remote_tree.get_children():
            self.remote_tree.delete(item)
        
        for name, url in self.current_remotes.items():
            self.remote_tree.insert("", "end", values=(name, url))
    
    def _refresh_from_git(self) -> None:
        """从 Git 重新读取远程配置"""
        try:
            remote_names = [r.strip() for r in git_capture(self.repo_root, ["remote"]).splitlines() if r.strip()]
            self.current_remotes = {}
            for name in remote_names:
                url = git_capture(self.repo_root, ["remote", "get-url", name]).strip()
                self.current_remotes[name] = url
            self._refresh_remote_list()
        except Exception as e:
            messagebox.showerror("错误", f"读取远程配置失败：{e}", parent=self.dialog)
    
    def _update_preview(self) -> None:
        """更新预览 URL"""
        url_input = self.github_url_var.get().strip()
        if not url_input:
            self.preview_var.set("(请输入仓库地址)")
            return
        
        parsed = parse_github_url(url_input)
        if parsed:
            owner, repo = parsed
            protocol = self.protocol_var.get()
            preview_url = build_github_url(owner, repo, protocol)
            self.preview_var.set(preview_url)
        else:
            # 如果无法解析，直接使用输入的 URL
            self.preview_var.set(url_input)
    
    def _on_add_remote(self) -> None:
        """添加远程"""
        name = self.remote_name_var.get().strip()
        if not name:
            messagebox.showerror("错误", "远程名称不能为空。", parent=self.dialog)
            return
        
        if name in self.current_remotes:
            messagebox.showerror("错误", f"远程 '{name}' 已存在。", parent=self.dialog)
            return
        
        url_input = self.github_url_var.get().strip()
        if not url_input:
            messagebox.showerror("错误", "仓库地址不能为空。", parent=self.dialog)
            return
        
        # 解析并构建 URL
        parsed = parse_github_url(url_input)
        owner_repo = normalize_github_owner_repo(url_input) if parsed else None
        if parsed:
            owner, repo = parsed
            protocol = self.protocol_var.get()
            url = build_github_url(owner, repo, protocol)
        else:
            # 直接使用输入的 URL
            url = url_input
        
        # 执行 git remote add
        try:
            git_capture(self.repo_root, ["remote", "add", name, url])
            self.current_remotes[name] = url
            self._refresh_remote_list()
            self.changed = True
            messagebox.showinfo("成功", f"已添加远程 '{name}'：\n{url}", parent=self.dialog)

            if name == "origin" and owner_repo:
                try:
                    write_repo_github_config(self.repo_root, owner_repo=owner_repo, protocol=self.protocol_var.get())
                except Exception as e:
                    messagebox.showwarning("提示", f"远程已添加，但保存默认配置失败：{e}", parent=self.dialog)
            
            # 清空输入
            self.github_url_var.set("")
            
            # 如果是第一个远程，设置默认名称为其他
            if len(self.current_remotes) == 1:
                self.remote_name_var.set("upstream")
            
        except GitCommandError as e:
            messagebox.showerror("错误", f"添加远程失败：{e}\n{e.output}", parent=self.dialog)

    def _on_save_default_github(self) -> None:
        """保存默认 GitHub 配置（用于首次推送补齐 origin）。"""
        text = self.github_url_var.get().strip()
        owner_repo = normalize_github_owner_repo(text)
        if not owner_repo:
            messagebox.showerror("错误", "无法解析为 GitHub 仓库，请输入 user/repo 或 GitHub URL。", parent=self.dialog)
            return
        protocol = self.protocol_var.get().strip().lower()
        try:
            write_repo_github_config(self.repo_root, owner_repo=owner_repo, protocol=protocol)
            self.github_url_var.set(owner_repo)
            self._update_preview()
            messagebox.showinfo("成功", f"已保存默认 GitHub 配置：{owner_repo} ({protocol})", parent=self.dialog)
        except Exception as e:
            messagebox.showerror("错误", f"保存默认 GitHub 配置失败：{e}", parent=self.dialog)

    def _on_clear_default_github(self) -> None:
        """清除默认 GitHub 配置。"""
        try:
            clear_repo_github_config(self.repo_root)
        except Exception as e:
            messagebox.showerror("错误", f"清除默认 GitHub 配置失败：{e}", parent=self.dialog)
            return
        self.github_url_var.set("")
        self.protocol_var.set("https")
        self._update_preview()
        messagebox.showinfo("成功", "已清除默认 GitHub 配置。", parent=self.dialog)
    
    def _on_edit_remote(self) -> None:
        """编辑选中的远程"""
        selection = self.remote_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个远程。", parent=self.dialog)
            return
        
        item = selection[0]
        values = self.remote_tree.item(item, "values")
        old_name = values[0]
        old_url = values[1]
        
        # 弹出编辑对话框
        edit_dialog = tk.Toplevel(self.dialog)
        edit_dialog.title(f"编辑远程：{old_name}")
        edit_dialog.geometry("500x200")
        edit_dialog.transient(self.dialog)
        edit_dialog.grab_set()
        
        frame = ttk.Frame(edit_dialog, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        
        ttk.Label(frame, text="远程名称：").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Label(frame, text=old_name, font=("", 10, "bold")).grid(row=0, column=1, sticky="w", pady=8)
        
        ttk.Label(frame, text="新 URL：").grid(row=1, column=0, sticky="w", pady=8)
        new_url_var = tk.StringVar(value=old_url)
        new_url_entry = ttk.Entry(frame, textvariable=new_url_var)
        new_url_entry.grid(row=1, column=1, sticky="we", pady=8)
        
        # 协议快速切换
        protocol_frame = ttk.Frame(frame)
        protocol_frame.grid(row=2, column=0, columnspan=2, sticky="w", pady=8)
        
        def switch_to_https():
            parsed = parse_github_url(new_url_var.get())
            if parsed:
                new_url_var.set(build_github_url(parsed[0], parsed[1], "https"))
        
        def switch_to_ssh():
            parsed = parse_github_url(new_url_var.get())
            if parsed:
                new_url_var.set(build_github_url(parsed[0], parsed[1], "ssh"))
        
        ttk.Button(protocol_frame, text="转换为 HTTPS", command=switch_to_https).pack(side="left", padx=(0, 8))
        ttk.Button(protocol_frame, text="转换为 SSH", command=switch_to_ssh).pack(side="left")
        
        def do_save():
            new_url = new_url_var.get().strip()
            if not new_url:
                messagebox.showerror("错误", "URL 不能为空。", parent=edit_dialog)
                return
            
            if new_url == old_url:
                edit_dialog.destroy()
                return
            
            try:
                git_capture(self.repo_root, ["remote", "set-url", old_name, new_url])
                self.current_remotes[old_name] = new_url
                self._refresh_remote_list()
                self.changed = True
                messagebox.showinfo("成功", f"已更新远程 '{old_name}' 的 URL。", parent=edit_dialog)
                if old_name == "origin":
                    owner_repo = normalize_github_owner_repo(new_url)
                    if owner_repo:
                        try:
                            write_repo_github_config(self.repo_root, owner_repo=owner_repo, protocol=("ssh" if new_url.lower().startswith("git@") else "https"))
                        except Exception:
                            pass
                edit_dialog.destroy()
            except GitCommandError as e:
                messagebox.showerror("错误", f"更新远程失败：{e}\n{e.output}", parent=edit_dialog)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(btn_frame, text="保存", command=do_save).pack(side="right", padx=(8, 0))
        ttk.Button(btn_frame, text="取消", command=edit_dialog.destroy).pack(side="right")
        
        # 居中
        edit_dialog.update_idletasks()
        x = self.dialog.winfo_x() + (self.dialog.winfo_width() - edit_dialog.winfo_width()) // 2
        y = self.dialog.winfo_y() + (self.dialog.winfo_height() - edit_dialog.winfo_height()) // 2
        edit_dialog.geometry(f"+{x}+{y}")
    
    def _on_delete_remote(self) -> None:
        """删除选中的远程"""
        selection = self.remote_tree.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个远程。", parent=self.dialog)
            return
        
        item = selection[0]
        values = self.remote_tree.item(item, "values")
        name = values[0]
        
        if not messagebox.askyesno("确认删除", f"确定要删除远程 '{name}' 吗？\n\n这只会删除本地的远程配置，不会影响远程仓库。", parent=self.dialog):
            return
        
        try:
            git_capture(self.repo_root, ["remote", "remove", name])
            del self.current_remotes[name]
            self._refresh_remote_list()
            self.changed = True
            messagebox.showinfo("成功", f"已删除远程 '{name}'。", parent=self.dialog)
        except GitCommandError as e:
            messagebox.showerror("错误", f"删除远程失败：{e}\n{e.output}", parent=self.dialog)
    
    def _on_close(self) -> None:
        """关闭对话框"""
        if self.changed and self.on_change_callback:
            self.on_change_callback()
        self.dialog.destroy()
