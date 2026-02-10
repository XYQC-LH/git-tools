#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
应用控制器（Controller）。

职责：
- 维护应用状态（当前仓库、运行中标记、分支/Tag 列表等）
- 将 UI 事件映射为 services 调用
- 在后台线程执行耗时 Git 操作，并通过队列回传到主线程更新 UI
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any

import tkinter as tk
from tkinter import filedialog, messagebox

from app.config import AppConfig
from app.dialogs import (
    RemoteManagerDialog,
    confirm_danger,
    prompt_commit_dialog,
    prompt_github_repo_config,
    prompt_git_identity_dialog,
)
from app.git_utils import (
    build_github_url,
    find_repo_root,
    get_effective_github_config,
    git_capture,
    local_ref_exists,
    remote_ref_exists,
    write_repo_github_config,
)
from app.models import GitCommandError, RepoData
from app.services.git_stream import stream_git
from app.services.repo_data_service import collect_repo_data
from app.ui.main_view import MainView


@dataclass(frozen=True)
class BranchItem:
    name: str
    local: bool
    remote: bool
    current: bool


@dataclass(frozen=True)
class TagItem:
    name: str
    local: bool
    remote: bool


class AppController:
    def __init__(self, *, root: tk.Tk, view: MainView) -> None:
        self.root = root
        self.view = view

        self._config = AppConfig.load()
        self._repo_root: str | None = None
        self._current_branch: str = ""
        self._running = False

        self._q: queue.Queue[tuple] = queue.Queue()

        self.root.minsize(960, 650)
        self._apply_initial_window_geometry()
        self.root.bind("<Configure>", self._on_window_configure)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._wire_callbacks()
        self.update_recent_menu()
        self._apply_enabled_state()
        self._poll()

        initial_repo = (
            self._config.last_repo
            if self._config.last_repo and os.path.isdir(self._config.last_repo)
            else os.getcwd()
        )
        self.view.repo_frame.set_repo_path(initial_repo)
        self.try_set_repo(initial_repo, auto_refresh=True)

    # --- window geometry ---

    _GEOMETRY_RE = re.compile(r"^(?P<w>\d+)x(?P<h>\d+)(?P<x>[+-]\d+)?(?P<y>[+-]\d+)?$")

    def _apply_initial_window_geometry(self) -> None:
        geometry = str(self._config.window_geometry or "").strip()
        match = self._GEOMETRY_RE.match(geometry)
        if not match:
            self._reset_window_geometry()
            return

        width = int(match.group("w"))
        height = int(match.group("h"))
        x_str = match.group("x")
        y_str = match.group("y")

        try:
            if x_str is None or y_str is None:
                self._center_window(width=width, height=height)
                return

            x = int(x_str)
            y = int(y_str)
        except ValueError:
            self._reset_window_geometry()
            return

        # 先应用用户几何信息；若发现窗口完全跑到屏幕外，则重置并居中。
        try:
            self.root.geometry(f"{width}x{height}{x_str}{y_str}")
        except Exception:
            self._reset_window_geometry()
            return

        if not self._window_intersects_visible_area(width=width, height=height, x=x, y=y):
            self._reset_window_geometry(width=width, height=height)

    def _reset_window_geometry(self, *, width: int = 1200, height: int = 760) -> None:
        self._center_window(width=width, height=height)
        # 尽快修正持久化配置，避免“窗口丢失”后反复发生。
        self._config.window_geometry = self.root.geometry()

    def _center_window(self, *, width: int, height: int) -> None:
        left, top, right, bottom = self._get_virtual_screen_bounds()
        screen_w = max(1, right - left)
        screen_h = max(1, bottom - top)

        x = left + max(0, (screen_w - width) // 2)
        y = top + max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _get_virtual_screen_bounds(self) -> tuple[int, int, int, int]:
        """
        返回虚拟屏幕边界 (left, top, right, bottom)。

        - Windows: 使用 SM_*VIRTUALSCREEN 支持多显示器/负坐标。
        - 其他平台：退化为 Tk 的主屏幕尺寸。
        """
        if sys.platform == "win32":
            try:
                import ctypes  # 局部导入避免非 Windows 环境问题

                user32 = ctypes.windll.user32
                left = int(user32.GetSystemMetrics(76))  # SM_XVIRTUALSCREEN
                top = int(user32.GetSystemMetrics(77))  # SM_YVIRTUALSCREEN
                width = int(user32.GetSystemMetrics(78))  # SM_CXVIRTUALSCREEN
                height = int(user32.GetSystemMetrics(79))  # SM_CYVIRTUALSCREEN
                return left, top, left + width, top + height
            except Exception:
                pass

        width = int(self.root.winfo_screenwidth())
        height = int(self.root.winfo_screenheight())
        return 0, 0, width, height

    def _window_intersects_visible_area(self, *, width: int, height: int, x: int, y: int) -> bool:
        left, top, right, bottom = self._get_virtual_screen_bounds()

        # 只要有一小块在可见范围内，就认为“可找得到窗口”。
        min_visible = 64
        win_left, win_top = x, y
        win_right, win_bottom = x + width, y + height

        if win_right <= left + min_visible:
            return False
        if win_left >= right - min_visible:
            return False
        if win_bottom <= top + min_visible:
            return False
        if win_top >= bottom - min_visible:
            return False
        return True

    # --- lifecycle ---

    def shutdown(self) -> None:
        self._config.save()

    def _on_close(self) -> None:
        self.shutdown()
        self.root.destroy()

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget == self.root:
            self._config.window_geometry = self.root.geometry()

    # --- wiring / state ---

    def _wire_callbacks(self) -> None:
        self.view.repo_frame.set_callbacks(
            on_pick_repo=self.on_pick_repo,
            on_refresh=lambda: self.start_refresh(mode="auto"),
            on_refresh_local=lambda: self.start_refresh(mode="local"),
            on_fetch=self.on_fetch,
            on_init_repo=self.on_init_repo,
            on_open_recent=self.open_recent_repo,
            on_clear_recent=self.clear_recent_repos,
            on_repo_enter=lambda path: self.try_set_repo(path, auto_refresh=True),
        )
        self.view.push_frame.set_callbacks(on_manage_remote=self.on_manage_remote, on_push=self.on_push)
        self.view.lists_frame.set_callbacks(
            on_branch_selected=self.on_branch_selected,
            on_checkout_branch=self.on_checkout_branch,
            on_set_as_push_target=self.set_as_push_target,
            on_delete_branch=self.on_delete_branch,
            on_copy_text=self.copy_to_clipboard,
            on_checkout_tag=self.on_checkout_tag,
            on_delete_tag=self.on_delete_tag,
        )
        self.view.ops_frame.set_callbacks(
            on_commit=self.on_commit,
            on_checkout_branch=self.on_checkout_branch,
            on_delete_branch=self.on_delete_branch,
            on_delete_tag=self.on_delete_tag,
        )
        self.view.log_frame.set_callbacks(on_clear_log=self.clear_log)

        self.root.bind("<F5>", lambda _e: self.start_refresh(mode="auto"))
        self.root.bind("<Control-p>", lambda _e: self.on_push())
        self.root.bind("<Control-P>", lambda _e: self.on_push())
        self.root.bind("<Control-f>", lambda _e: self.view.lists_frame.focus_branch_search())
        self.root.bind("<Control-F>", lambda _e: self.view.lists_frame.focus_branch_search())
        self.root.bind("<Delete>", lambda _e: self.on_delete_selected())

    def _apply_enabled_state(self) -> None:
        repo_loaded = self._repo_root is not None
        idle = not self._running
        current_dir = (self.view.repo_frame.get_repo_path() or "").strip()
        abs_current_dir = os.path.abspath(current_dir) if current_dir else ""
        can_init_repo = (
            idle
            and bool(abs_current_dir)
            and os.path.isdir(abs_current_dir)
            and not os.path.exists(os.path.join(abs_current_dir, ".git"))
        )
        self.view.set_enabled(repo_loaded=repo_loaded, idle=idle, can_init_repo=can_init_repo)

    # --- queue / ui updates ---

    def emit(self, kind: str, *payload: Any) -> None:
        self._q.put((kind, *payload))

    def _poll(self) -> None:
        try:
            while True:
                kind, *payload = self._q.get_nowait()
                if kind == "log":
                    self.view.log_frame.append_log(str(payload[0]))
                elif kind == "progress":
                    pct, stage = int(payload[0]), str(payload[1])
                    self.view.log_frame.set_progress(pct, stage)
                elif kind == "status":
                    self.view.log_frame.set_status(str(payload[0]))
                elif kind == "data":
                    self.apply_repo_data(payload[0])
                elif kind == "done":
                    ok = bool(payload[0]) if len(payload) >= 1 else True
                    msg = str(payload[1]) if len(payload) >= 2 else "就绪"
                    self.finish_operation(ok=ok, message=msg)
                elif kind == "error":
                    messagebox.showerror(str(payload[0]), str(payload[1]), parent=self.root)
                else:
                    self.view.log_frame.append_log(f"[WARN] 未知事件：{kind} {payload}")
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def begin_operation(self, title: str) -> None:
        self._running = True
        self.view.log_frame.append_log(f"\n==> {title}\n")
        self.view.log_frame.set_status(title)
        self._apply_enabled_state()
        self.view.log_frame.start_indeterminate()

    def finish_operation(self, *, ok: bool, message: str) -> None:
        self._running = False
        self.view.log_frame.finish_progress(ok=ok)
        self.view.log_frame.set_status(message)
        self._apply_enabled_state()

    # --- common ui helpers ---

    def clear_log(self) -> None:
        self.view.log_frame.clear_log()

    def copy_to_clipboard(self, text: str) -> None:
        text = str(text or "")
        if not text:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.view.log_frame.append_log(f"[INFO] 已复制到剪贴板：{text}")
        except Exception:
            pass

    def on_delete_selected(self) -> None:
        focused = self.root.focus_get()
        if focused == self.view.lists_frame.get_branches_listbox():
            self.on_delete_branch()
        elif focused == self.view.lists_frame.get_tags_listbox():
            self.on_delete_tag()

    # --- recent repos ---

    def update_recent_menu(self) -> None:
        self.view.repo_frame.set_recent_repos(self._config.recent_repos[:10])

    def open_recent_repo(self, repo_path: str) -> None:
        repo_path = str(repo_path or "")
        if os.path.isdir(repo_path):
            self.view.repo_frame.set_repo_path(repo_path)
            self.try_set_repo(repo_path, auto_refresh=True)
            return

        messagebox.showerror("错误", f"目录不存在：{repo_path}", parent=self.root)
        self._config.recent_repos = [r for r in self._config.recent_repos if r != repo_path]
        self._config.save()
        self.update_recent_menu()

    def clear_recent_repos(self) -> None:
        self._config.recent_repos = []
        self._config.save()
        self.update_recent_menu()

    # --- repo selection ---

    def on_pick_repo(self) -> None:
        path = filedialog.askdirectory(title="选择仓库目录")
        if not path:
            return
        self.view.repo_frame.set_repo_path(path)
        self.try_set_repo(path, auto_refresh=True)

    def try_set_repo(self, path: str, *, auto_refresh: bool) -> None:
        abs_path = os.path.abspath(str(path or ""))
        if not os.path.isdir(abs_path):
            self._repo_root = None
            self.view.summary_frame.set_summary(f"目录不存在：{abs_path}")
            self._apply_enabled_state()
            return

        self.view.repo_frame.set_repo_path(abs_path)

        try:
            repo_root = find_repo_root(abs_path)
        except Exception as e:
            self._repo_root = None
            self.view.summary_frame.set_summary(
                "不是有效的 Git 仓库："
                f"{abs_path}\n{e}\n\n"
                "如果这是一个新目录，可点击右侧“初始化...”创建 .git，并配置 GitHub origin。"
            )
            self._apply_enabled_state()
            return

        self._repo_root = repo_root
        self._config.add_recent_repo(repo_root)
        self.update_recent_menu()
        self._apply_enabled_state()

        if auto_refresh:
            self.start_refresh(mode="auto")

    # --- placeholders (逐步实现) ---

    def apply_repo_data(self, data: RepoData) -> None:
        self._current_branch = data.branch if not data.detached else ""

        lines = [
            f"仓库：{data.repo_root}",
            (
                f"当前：{data.branch}    "
                f"HEAD：{data.head_short}    "
                f"工作区：{'有改动(未提交不会被推送)' if data.dirty else '干净'}"
            ),
        ]
        if data.remotes:
            remotes_line = "；".join([f"{k}={v}" for k, v in data.remotes.items()])
            lines.append(f"远程：{remotes_line}")
        else:
            lines.append("远程：(无)")
        self.view.summary_frame.set_summary("\n".join(lines))

        remote_names = list(data.remotes.keys())
        self.view.push_frame.set_remote_values(remote_names)
        self.view.push_frame.ensure_remote_selected()

        if not self.view.push_frame.get_target_branch().strip() and not data.detached and data.branch:
            self.view.push_frame.set_target_branch(data.branch)

        branch_local = set(data.local_branches)
        branch_remote = set(data.remote_branches)
        branch_names = sorted(branch_local | branch_remote)
        branches = [
            BranchItem(
                name=name,
                local=(name in branch_local),
                remote=(name in branch_remote),
                current=(name == self._current_branch),
            )
            for name in branch_names
        ]
        self.view.lists_frame.set_branches(branches)

        tag_local = set(data.local_tags)
        tag_remote = set(data.remote_tags)
        tag_names = sorted(tag_local | tag_remote)
        tags = [TagItem(name=name, local=(name in tag_local), remote=(name in tag_remote)) for name in tag_names]
        self.view.lists_frame.set_tags(tags)

        remote_text = ", ".join(remote_names) if remote_names else "(无)"
        self.view.log_frame.append_log(f"[INFO] 已加载：分支{len(branch_names)} Tag{len(tag_names)}；远程={remote_text}")

    def start_refresh(self, *, mode: str) -> None:
        if self._running or not self._repo_root:
            return

        mode = (mode or "").strip().lower()
        remote_query: str | None = None
        title = "刷新"
        if mode in {"auto", "remote"}:
            current_remote = self.view.push_frame.get_remote().strip()
            if current_remote:
                remote_query = current_remote
            else:
                remote_names = [r.strip() for r in git_capture(self._repo_root, ["remote"]).splitlines() if r.strip()]
                if remote_names:
                    remote_query = remote_names[0]
                    self.view.push_frame.set_remote(remote_query)

            if mode == "remote" and not remote_query:
                messagebox.showerror("错误", "未选择远程，无法执行远程刷新。", parent=self.root)
                return
        elif mode == "local":
            title = "离线刷新"
        else:
            messagebox.showerror("错误", f"未知刷新模式：{mode}", parent=self.root)
            return

        def worker() -> None:
            ok = False
            message = "就绪（刷新失败，查看日志）"
            try:
                data = collect_repo_data(self._repo_root or "", remote_query=remote_query)
                self.emit("data", data)
                ok = True
                branch_total = len(set(data.local_branches) | set(data.remote_branches))
                tag_total = len(set(data.local_tags) | set(data.remote_tags))
                message = f"就绪（分支{branch_total} Tag{tag_total}）"
            except GitCommandError as e:
                self.emit("log", f"[ERROR] 刷新失败：{e}")
                self.emit("log", e.output)
                self.emit("error", "刷新失败", str(e))
                if remote_query:
                    try:
                        data = collect_repo_data(self._repo_root or "", remote_query=None)
                        self.emit("data", data)
                        message = "就绪（远程刷新失败，已显示本地信息）"
                    except Exception:
                        pass
            except Exception as e:
                self.emit("log", f"[ERROR] 刷新失败：{e}")
                self.emit("error", "刷新失败", str(e))
            finally:
                self.emit("done", ok, message)

        self.begin_operation(title)
        threading.Thread(target=worker, daemon=True).start()

    def run_git_sequence(self, *, title: str, commands: list[list[str]], refresh_after: bool = True) -> None:
        if self._running or not self._repo_root:
            return

        self.begin_operation(title)
        remote_query = self.view.push_frame.get_remote().strip() or None

        def worker() -> None:
            ok = False
            message = f"就绪（{title}失败，查看日志）"
            try:
                ok = True
                failing_cmd: list[str] | None = None
                failing_rc: int | None = None
                for cmd in commands:
                    rc = stream_git(
                        self._repo_root or "",
                        cmd,
                        on_log=lambda line: self.emit("log", line),
                        on_progress=lambda pct, stage: self.emit("progress", pct, stage),
                        on_hint=lambda hint: self.emit("log", hint),
                    )
                    if rc != 0:
                        ok = False
                        failing_cmd = cmd
                        failing_rc = rc
                        break

                if not ok:
                    cmd_text = subprocess.list2cmdline(["git", "--no-pager", *(failing_cmd or [])])
                    self.emit("log", f"[ERROR] {title} 失败：返回码 {failing_rc}")
                    self.emit("log", f"[ERROR] 失败命令：{cmd_text}")
                    self.emit("error", f"{title}失败", f"git 返回码 {failing_rc}，请查看日志。")

                if refresh_after:
                    try:
                        data = collect_repo_data(self._repo_root or "", remote_query=remote_query)
                        self.emit("data", data)
                    except GitCommandError as e:
                        self.emit("log", f"[WARN] 刷新失败：{e}")
                        self.emit("log", e.output)
                        try:
                            data = collect_repo_data(self._repo_root or "", remote_query=None)
                            self.emit("data", data)
                        except Exception:
                            pass

                if ok:
                    message = f"就绪（{title}完成）"
            except Exception as e:
                ok = False
                self.emit("log", f"[ERROR] {title} 失败：{e}")
                self.emit("error", f"{title}失败", str(e))
            finally:
                self.emit("done", ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def on_branch_selected(self, branch_name: str) -> None:
        branch_name = str(branch_name or "").strip()
        if branch_name:
            self.view.push_frame.set_target_branch(branch_name)

    def set_as_push_target(self, branch_name: str) -> None:
        branch_name = str(branch_name or "").strip()
        if not branch_name:
            return
        self.view.push_frame.set_target_branch(branch_name)
        self.view.log_frame.append_log(f"[INFO] 已设置推送目标分支：{branch_name}")

    def on_checkout_branch(self) -> None:
        if self._running or not self._repo_root:
            return
        name = self.view.lists_frame.get_selected_branch_name().strip()
        if not name:
            messagebox.showinfo("提示", "请先选择一个分支。", parent=self.root)
            return

        if name == self._current_branch:
            messagebox.showinfo("提示", f"已经在分支 {name} 上。", parent=self.root)
            return

        try:
            dirty = bool(git_capture(self._repo_root, ["status", "--porcelain=v1"]).strip())
        except Exception:
            dirty = False

        if dirty:
            ok = messagebox.askyesno("提示", "工作区有未提交改动，切换分支可能导致冲突。\n是否继续？", parent=self.root)
            if not ok:
                return

        self.run_git_sequence(title=f"切换到分支 {name}", commands=[["checkout", name]])

    def on_checkout_tag(self) -> None:
        if self._running or not self._repo_root:
            return
        name = self.view.lists_frame.get_selected_tag_name().strip()
        if not name:
            messagebox.showinfo("提示", "请先选择一个 Tag。", parent=self.root)
            return

        try:
            dirty = bool(git_capture(self._repo_root, ["status", "--porcelain=v1"]).strip())
        except Exception:
            dirty = False

        if dirty:
            ok = messagebox.askyesno("提示", "工作区有未提交改动，切换到 Tag 可能导致冲突。\n是否继续？", parent=self.root)
            if not ok:
                return

        self.run_git_sequence(title=f"切换到 Tag {name}", commands=[["checkout", f"tags/{name}"]])

    def on_fetch(self) -> None:
        if self._running or not self._repo_root:
            return
        remote = self.view.push_frame.get_remote().strip()
        if not remote:
            messagebox.showerror("错误", "未选择远程，无法拉取。", parent=self.root)
            return
        self.run_git_sequence(title=f"从 {remote} 拉取", commands=[["fetch", remote, "--prune", "--tags", "--progress"]])

    def on_manage_remote(self) -> None:
        if not self._repo_root:
            messagebox.showerror("错误", "请先选择一个 Git 仓库。", parent=self.root)
            return

        try:
            remote_names = [r.strip() for r in git_capture(self._repo_root, ["remote"]).splitlines() if r.strip()]
            current_remotes: dict[str, str] = {}
            for name in remote_names:
                url = git_capture(self._repo_root, ["remote", "get-url", name]).strip()
                current_remotes[name] = url
        except GitCommandError as e:
            messagebox.showerror("错误", f"读取远程配置失败：{e}", parent=self.root)
            return

        RemoteManagerDialog(
            self.root,
            self._repo_root,
            current_remotes,
            on_change_callback=lambda: self.start_refresh(mode="auto"),
        )

    def on_init_repo(self) -> None:
        if self._running:
            return

        current_dir = (self.view.repo_frame.get_repo_path() or "").strip()
        if not current_dir or not os.path.isdir(os.path.abspath(current_dir)):
            messagebox.showerror("错误", "当前目录不存在，无法初始化。", parent=self.root)
            return

        abs_path = os.path.abspath(current_dir)

        configured = prompt_github_repo_config(self.root, initial_owner_repo="", initial_protocol="https")
        owner_repo: str | None = None
        protocol: str = "https"
        if configured:
            owner_repo, protocol = configured

        if not confirm_danger(
            self.root,
            action_type="初始化仓库",
            impact=f"{abs_path}\n将执行：git init",
            risks="将创建 .git 目录并写入配置；若目录已包含其他 VCS/配置可能冲突。",
        ):
            return

        try:
            out = git_capture(abs_path, ["init"])
            if out.strip():
                self.view.log_frame.append_log(out.strip())
        except GitCommandError as e:
            messagebox.showerror("错误", f"初始化失败：{e}\n{e.output}", parent=self.root)
            return
        except Exception as e:
            messagebox.showerror("错误", f"初始化失败：{e}", parent=self.root)
            return

        if owner_repo:
            try:
                owner, repo = owner_repo.split("/", 1)
            except ValueError:
                messagebox.showerror("错误", f"GitHub 仓库格式不合法：{owner_repo}", parent=self.root)
                return

            url = build_github_url(owner, repo, protocol)
            try:
                remote_names = [r.strip() for r in git_capture(abs_path, ["remote"]).splitlines() if r.strip()]
                if "origin" in remote_names:
                    git_capture(abs_path, ["remote", "set-url", "origin", url])
                else:
                    git_capture(abs_path, ["remote", "add", "origin", url])
                write_repo_github_config(abs_path, owner_repo=owner_repo, protocol=protocol)
                self.view.log_frame.append_log(f"[INFO] 已配置 origin：{url}")
            except GitCommandError as e:
                messagebox.showerror("错误", f"配置 origin 失败：{e}\n{e.output}", parent=self.root)
                return
            except Exception as e:
                messagebox.showerror("错误", f"配置 origin 失败：{e}", parent=self.root)
                return

        self.try_set_repo(abs_path, auto_refresh=True)

    def on_delete_branch(self) -> None:
        if self._running or not self._repo_root:
            return

        name = self.view.lists_frame.get_selected_branch_name().strip()
        if not name:
            messagebox.showinfo("提示", "请先在分支列表中选择一个分支。", parent=self.root)
            return

        if name == self._current_branch:
            messagebox.showerror("错误", f"不能删除当前所在分支：{name}\n请先切换到其他分支。", parent=self.root)
            return

        remote = self.view.push_frame.get_remote().strip()
        if not remote:
            remote = self.view.push_frame.get_first_remote_value().strip()
            if remote:
                self.view.push_frame.set_remote(remote)
        if not remote:
            messagebox.showerror("错误", "未配置远程，无法删除远程分支。", parent=self.root)
            return

        local_exists = local_ref_exists(self._repo_root, f"refs/heads/{name}")
        try:
            remote_exists = remote_ref_exists(self._repo_root, remote=remote, ref=f"refs/heads/{name}")
        except GitCommandError as e:
            self.view.log_frame.append_log(f"[ERROR] 查询远程分支失败：{e}")
            self.view.log_frame.append_log(e.output)
            messagebox.showerror("错误", f"查询远程分支失败：{e}", parent=self.root)
            return

        if not local_exists and not remote_exists:
            messagebox.showinfo("提示", f"分支不存在：{name}", parent=self.root)
            return

        force = bool(self.view.ops_frame.get_force_delete_branch())
        if not confirm_danger(
            self.root,
            action_type="删除分支",
            impact=f"{name}",
            risks="将删除远程分支与本地分支（若存在）；若分支未合并/远程受保护，可能失败。",
        ):
            return

        commands: list[list[str]] = []
        if remote_exists:
            commands.append(["push", remote, "--delete", name, "--progress"])
        if local_exists:
            commands.append(["branch", "-D" if force else "-d", name])

        self.run_git_sequence(title="删除分支", commands=commands)

    def on_delete_tag(self) -> None:
        if self._running or not self._repo_root:
            return

        name = self.view.lists_frame.get_selected_tag_name().strip()
        if not name:
            messagebox.showinfo("提示", "请先在 Tag 列表中选择一个 Tag。", parent=self.root)
            return

        remote = self.view.push_frame.get_remote().strip()
        if not remote:
            remote = self.view.push_frame.get_first_remote_value().strip()
            if remote:
                self.view.push_frame.set_remote(remote)
        if not remote:
            messagebox.showerror("错误", "未配置远程，无法删除远程 Tag。", parent=self.root)
            return

        local_exists = local_ref_exists(self._repo_root, f"refs/tags/{name}")
        try:
            remote_exists = remote_ref_exists(self._repo_root, remote=remote, ref=f"refs/tags/{name}")
        except GitCommandError as e:
            self.view.log_frame.append_log(f"[ERROR] 查询远程 Tag 失败：{e}")
            self.view.log_frame.append_log(e.output)
            messagebox.showerror("错误", f"查询远程 Tag 失败：{e}", parent=self.root)
            return

        if not local_exists and not remote_exists:
            messagebox.showinfo("提示", f"Tag 不存在：{name}", parent=self.root)
            return

        if not confirm_danger(
            self.root,
            action_type="删除Tag",
            impact=f"{name}",
            risks="将删除远程 Tag 与本地 Tag（若存在）；依赖该 Tag 的发布/回滚可能受影响。",
        ):
            return

        commands: list[list[str]] = []
        if remote_exists:
            commands.append(["push", remote, f":refs/tags/{name}", "--progress"])
        if local_exists:
            commands.append(["tag", "-d", name])

        self.run_git_sequence(title="删除Tag", commands=commands)

    def on_commit(self) -> None:
        if self._running or not self._repo_root:
            return

        commit_info = prompt_commit_dialog(self.root, default_message="", stage_all_default=True)
        if not commit_info:
            return
        message, stage_all = commit_info

        try:
            if stage_all:
                has_changes = bool(git_capture(self._repo_root, ["status", "--porcelain=v1"]).strip())
            else:
                has_changes = bool(git_capture(self._repo_root, ["diff", "--cached", "--name-only"]).strip())
        except Exception:
            has_changes = True

        if not has_changes:
            messagebox.showinfo("提示", "没有可提交的改动。", parent=self.root)
            return

        try:
            author_name = git_capture(self._repo_root, ["config", "--get", "user.name"]).strip()
        except GitCommandError:
            author_name = ""
        try:
            author_email = git_capture(self._repo_root, ["config", "--get", "user.email"]).strip()
        except GitCommandError:
            author_email = ""

        if not author_name or not author_email:
            configured = prompt_git_identity_dialog(
                self.root,
                default_name=author_name,
                default_email=author_email,
                default_scope="local",
            )
            if not configured:
                messagebox.showinfo("提示", "未配置 Git 身份，已取消提交。", parent=self.root)
                return
            author_name, author_email, scope = configured
            scope = (scope or "").strip().lower()

            if scope == "global":
                if not confirm_danger(
                    self.root,
                    action_type="设置 Git 全局身份",
                    impact=f"user.name={author_name}\nuser.email={author_email}",
                    risks="将写入 ~/.gitconfig，对此电脑上所有 Git 仓库生效。",
                ):
                    return
                prefix = ["config", "--global"]
            else:
                prefix = ["config"]

            try:
                git_capture(self._repo_root, [*prefix, "user.name", author_name])
                git_capture(self._repo_root, [*prefix, "user.email", author_email])
            except GitCommandError as e:
                messagebox.showerror("错误", f"写入 Git 身份失败：{e}\n{e.output}", parent=self.root)
                return
            except Exception as e:
                messagebox.showerror("错误", f"写入 Git 身份失败：{e}", parent=self.root)
                return

        if not confirm_danger(
            self.root,
            action_type="提交(Commit)",
            impact=(
                f"{self._repo_root}\n"
                f"消息：{message}\n"
                f"暂存：{'全部(git add -A)' if stage_all else '仅已暂存'}"
            ),
            risks="将创建新的提交记录；若暂存全部，可能误提交敏感文件或临时文件。",
        ):
            return

        commands: list[list[str]] = []
        if stage_all:
            commands.append(["add", "-A"])
        commands.append(["commit", "-m", message])
        self.run_git_sequence(title="提交", commands=commands)

    def ensure_remote_for_push(self) -> str | None:
        if not self._repo_root:
            return None

        remote = self.view.push_frame.get_remote().strip()
        if remote:
            return remote

        try:
            remote_names = [r.strip() for r in git_capture(self._repo_root, ["remote"]).splitlines() if r.strip()]
        except Exception:
            remote_names = []

        if remote_names:
            remote = remote_names[0]
            self.view.push_frame.set_remote(remote)
            return remote

        owner_repo, protocol = get_effective_github_config(self._repo_root)
        if not owner_repo:
            configured = prompt_github_repo_config(self.root, initial_owner_repo="", initial_protocol=protocol)
            if not configured:
                return None
            owner_repo, protocol = configured
            try:
                write_repo_github_config(self._repo_root, owner_repo=owner_repo, protocol=protocol)
            except Exception as e:
                messagebox.showwarning("提示", f"已获取配置，但写入 .git/config 失败：{e}", parent=self.root)

        try:
            owner, repo = owner_repo.split("/", 1)
        except ValueError:
            messagebox.showerror("错误", f"GitHub 仓库配置不合法：{owner_repo}", parent=self.root)
            return None

        url = build_github_url(owner, repo, protocol)
        try:
            git_capture(self._repo_root, ["remote", "add", "origin", url])
        except GitCommandError as e:
            messagebox.showerror("错误", f"自动创建 origin 失败：{e}\n{e.output}", parent=self.root)
            return None

        self.view.log_frame.append_log(f"[INFO] 已自动创建 origin：{url}")
        self.view.push_frame.set_remote("origin")
        self.view.push_frame.add_remote_value_if_missing("origin")
        return "origin"

    def on_push(self) -> None:
        if self._running or not self._repo_root:
            return

        target = self.view.push_frame.get_target_branch().strip()
        if not target:
            messagebox.showerror("错误", "目标分支不能为空。", parent=self.root)
            return
        if " " in target:
            messagebox.showerror("错误", "目标分支名包含空格，请检查。", parent=self.root)
            return

        remote = self.ensure_remote_for_push()
        if not remote:
            messagebox.showerror("错误", "未配置远程，无法推送。", parent=self.root)
            return

        try:
            git_capture(self._repo_root, ["rev-parse", "--verify", "HEAD"])
        except GitCommandError:
            messagebox.showerror(
                "错误",
                "当前仓库还没有提交（没有 HEAD）。\n请先完成一次提交（git commit）后再推送。\n\n提示：窗口下方「管理操作」里有「提交(Commit)」。",
                parent=self.root,
            )
            return

        try:
            dirty = bool(git_capture(self._repo_root, ["status", "--porcelain=v1"]).strip())
        except Exception:
            dirty = False
        if dirty:
            ok = messagebox.askyesno(
                "提示",
                "检测到工作区/暂存区有未提交改动。\n未提交的文件不会被推送。\n仍然继续推送吗？",
                parent=self.root,
            )
            if not ok:
                return

        if self.view.push_frame.get_force_push():
            if not confirm_danger(
                self.root,
                action_type="强制推送",
                impact=f"{remote}:{target}",
                risks="可能覆盖远程历史，导致他人提交丢失；请确认目标分支与影响范围。",
            ):
                return

        commands: list[list[str]] = []
        if self.view.push_frame.get_force_push():
            # --force-with-lease 需要本地有最新的远程分支信息；否则会报 stale info。
            # 先 fetch 一次以更新 refs/remotes/<remote>/*，提升成功率与可解释性。
            commands.append(["fetch", remote, "--prune", "--tags", "--progress"])

        if self.view.push_frame.get_create_tag():
            tag_name = self.view.push_frame.get_tag_name().strip()
            tag_msg = self.view.push_frame.get_tag_message().strip()
            if not tag_name:
                messagebox.showerror("错误", "已勾选创建Tag，但 Tag 名为空。", parent=self.root)
                return
            if " " in tag_name:
                messagebox.showerror("错误", "Tag 名包含空格，请检查。", parent=self.root)
                return
            if tag_msg:
                commands.append(["tag", "-a", tag_name, "-m", tag_msg])
            else:
                commands.append(["tag", tag_name])

        push_cmd = ["push", remote, f"HEAD:refs/heads/{target}", "--progress"]
        if self.view.push_frame.get_set_upstream():
            push_cmd.insert(1, "-u")
        if self.view.push_frame.get_force_push():
            push_cmd.append("--force-with-lease")
        commands.append(push_cmd)

        if self.view.push_frame.get_create_tag():
            tag_name = self.view.push_frame.get_tag_name().strip()
            commands.append(["push", remote, f"refs/tags/{tag_name}", "--progress"])

        self.run_git_sequence(title="推送到远程", commands=commands)
