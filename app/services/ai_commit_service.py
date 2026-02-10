#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AI Commit Message 生成服务。

职责：
- 收集当前仓库改动（按是否“暂存全部”区分）
- 调用智谱 OpenAPI 生成单行提交信息

约定：
- 不依赖 tkinter（便于在控制器/UI 外复用）
"""

from __future__ import annotations

import codecs
import json
import os
from collections.abc import Callable
from pathlib import Path
import urllib.error
import urllib.request

from app.git_utils import git_capture
from app.models import GitCommandError

DEFAULT_BIGMODEL_BASE_URL = "https://open.bigmodel.cn/api/coding/paas/v4"
DEFAULT_BIGMODEL_MODEL = "glm-4.7"
MAX_DIFF_CHARS = 12000
_DOTENV_CACHE: dict[str, str] | None = None


def _parse_dotenv_line(raw_line: str) -> tuple[str, str] | None:
    line = str(raw_line or "").strip()
    if not line or line.startswith("#"):
        return None

    if line.startswith("export "):
        line = line[len("export "):].strip()

    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = value.strip()
    if value and value[0] in {'"', "'"} and value[-1:] == value[0]:
        quote = value[0]
        value = value[1:-1]
        if quote == '"':
            value = (
                value.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace('\\"', '"')
            )

    return key, value


def _load_dotenv_values() -> dict[str, str]:
    global _DOTENV_CACHE
    if _DOTENV_CACHE is not None:
        return dict(_DOTENV_CACHE)

    values: dict[str, str] = {}
    project_root = Path(__file__).resolve().parents[2]
    candidates = [project_root / ".env", Path.cwd() / ".env"]

    seen: set[str] = set()
    for path in candidates:
        path_key = str(path.resolve())
        if path_key in seen:
            continue
        seen.add(path_key)

        if not path.exists() or not path.is_file():
            continue

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue

        for raw_line in lines:
            parsed = _parse_dotenv_line(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            values[key] = value

    _DOTENV_CACHE = dict(values)
    return dict(values)


def _resolve_setting(explicit_value: str | None, *, env_keys: tuple[str, ...], default: str | None = None) -> str:
    if explicit_value and explicit_value.strip():
        return explicit_value.strip()

    for env_key in env_keys:
        value = os.getenv(env_key, "").strip()
        if value:
            return value

    dotenv_values = _load_dotenv_values()
    for env_key in env_keys:
        value = str(dotenv_values.get(env_key, "") or "").strip()
        if value:
            return value

    if default is not None:
        return default

    raise RuntimeError(f"缺少配置项：{', '.join(env_keys)}")


def _resolve_api_key(explicit_api_key: str | None) -> str:
    try:
        return _resolve_setting(
            explicit_api_key,
            env_keys=("BIGMODEL_API_KEY", "ZHIPUAI_API_KEY", "GLM_API_KEY"),
            default=None,
        )
    except RuntimeError as e:
        raise RuntimeError(
            "未找到智谱 API Key。请在 .env 中配置 BIGMODEL_API_KEY，或设置系统环境变量 BIGMODEL_API_KEY（兼容 ZHIPUAI_API_KEY / GLM_API_KEY）。"
        ) from e


def _normalize_single_line(text: str) -> str:
    parts = [segment for segment in (text or "").replace("\r", "\n").split("\n") if segment.strip()]
    merged = " ".join(parts).strip()
    return " ".join(merged.split())


def _collect_changes(repo_root: str, *, stage_all: bool) -> tuple[str, str]:
    """
    收集变更摘要与 diff 文本。

    Returns:
        (变更文件摘要, diff 文本)
    """
    staged_files = (git_capture(repo_root, ["diff", "--cached", "--name-status"]) or "").strip()
    staged_diff = git_capture(repo_root, ["diff", "--cached", "--", "."])

    if stage_all:
        unstaged_files = (git_capture(repo_root, ["diff", "--name-status"]) or "").strip()
        unstaged_diff = git_capture(repo_root, ["diff", "--", "."])
    else:
        unstaged_files = ""
        unstaged_diff = ""

    files_parts: list[str] = []
    if staged_files:
        files_parts.append("[已暂存文件]\n" + staged_files)
    if unstaged_files:
        files_parts.append("[未暂存文件]\n" + unstaged_files)
    files_summary = "\n\n".join(files_parts).strip()

    diff_parts: list[str] = []
    if staged_diff.strip():
        diff_parts.append("[已暂存 diff]\n" + staged_diff)
    if unstaged_diff.strip():
        diff_parts.append("[未暂存 diff]\n" + unstaged_diff)
    diff_text = "\n\n".join(diff_parts).strip()

    if not files_summary and not diff_text:
        if stage_all:
            raise RuntimeError("当前没有可提交改动，无法生成提交信息。")
        raise RuntimeError("当前暂存区为空，请先暂存改动或勾选“暂存全部改动（git add -A）”。")

    if len(diff_text) > MAX_DIFF_CHARS:
        diff_text = diff_text[:MAX_DIFF_CHARS] + "\n\n[...diff 已截断...]"

    return files_summary, diff_text


def _build_prompt(*, files_summary: str, diff_text: str) -> list[dict[str, str]]:
    system_prompt = (
        "你是资深软件工程师，请根据 Git 变更生成高质量 commit message。\n"
        "要求：\n"
        "1) 仅输出一行文本，不要任何解释。\n"
        "2) 使用中文，简洁明确，建议 12~40 字。\n"
        "3) 以动词开头（如：新增/修复/重构/优化/调整）。\n"
        "4) 不要包含引号、换行、列表、前缀符号。"
    )

    user_prompt = (
        "以下是本次代码改动信息，请生成 commit message：\n\n"
        f"{files_summary or '[无文件摘要]'}\n\n"
        f"{diff_text or '[无 diff]'}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _request_commit_message(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": False,
    }

    req = urllib.request.Request(
        endpoint,
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            response_text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(f"AI 请求失败（HTTP {e.code}）：{body or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"AI 请求失败：{e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"AI 请求失败：{e}") from e

    try:
        data = json.loads(response_text)
    except Exception as e:
        raise RuntimeError(f"AI 返回解析失败：{e}") from e

    try:
        content = str(data["choices"][0]["message"]["content"])
    except Exception as e:
        raise RuntimeError(f"AI 返回格式不符合预期：{data}") from e

    message = _normalize_single_line(content)
    if not message:
        raise RuntimeError("AI 未返回有效提交信息。")
    return message


def _extract_text_from_stream_chunk(data: dict) -> str:
    if not isinstance(data, dict):
        return ""

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        return ""

    delta = first.get("delta")
    if isinstance(delta, str):
        return delta
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        text_value = delta.get("text")
        if isinstance(text_value, str):
            return text_value
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
                        continue
                    content_value = item.get("content")
                    if isinstance(content_value, str):
                        parts.append(content_value)
            return "".join(parts)

    text = first.get("text")
    if isinstance(text, str):
        return text

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content

    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text

    return ""


def _iter_sse_data_payloads(resp: object) -> list[str]:
    """
    增量解析 SSE 数据帧，尽早产出 data payload。

    说明：
    - 不依赖 readline，避免部分环境中“等整行/等结束”才返回。
    - 以空行分隔事件；一个事件可能包含多条 data: 行。
    """
    if not hasattr(resp, "read"):
        return []

    read = getattr(resp, "read")
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    pending = ""
    data_lines: list[str] = []
    payloads: list[str] = []

    while True:
        chunk = read(256)
        if not chunk:
            break

        pending += decoder.decode(chunk)

        while True:
            line_end = pending.find("\n")
            if line_end < 0:
                break

            raw_line = pending[:line_end]
            pending = pending[line_end + 1 :]
            line = raw_line.rstrip("\r")
            stripped = line.strip()

            if not stripped:
                if data_lines:
                    payloads.append("\n".join(data_lines))
                    data_lines = []
                continue

            if stripped.startswith(":"):
                continue

            if stripped.startswith("data:"):
                data_lines.append(stripped[len("data:") :].lstrip())

    pending += decoder.decode(b"", final=True)
    if pending:
        for raw_line in pending.splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("data:"):
                data_lines.append(stripped[len("data:") :].lstrip())

    if data_lines:
        payloads.append("\n".join(data_lines))

    return payloads


def _request_commit_message_stream(
    *,
    api_key: str,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    on_stream_text: Callable[[str], None] | None,
) -> str:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "stream": True,
    }

    req = urllib.request.Request(
        endpoint,
        method="POST",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    chunks: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            for payload_text in _iter_sse_data_payloads(resp):
                payload_text = str(payload_text or "").strip()
                if not payload_text:
                    continue
                if payload_text == "[DONE]":
                    break

                try:
                    data = json.loads(payload_text)
                except Exception:
                    continue

                text = _extract_text_from_stream_chunk(data)
                if not text:
                    continue

                chunks.append(text)
                if on_stream_text is not None:
                    try:
                        on_stream_text(text)
                    except Exception:
                        pass
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise RuntimeError(f"AI 请求失败（HTTP {e.code}）：{body or e.reason}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"AI 请求失败：{e.reason}") from e
    except Exception as e:
        raise RuntimeError(f"AI 请求失败：{e}") from e

    message = _normalize_single_line("".join(chunks))
    if not message:
        raise RuntimeError("AI 流式返回为空，未生成有效提交信息。")
    return message


def generate_commit_message_with_ai(
    repo_root: str,
    *,
    stage_all: bool,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    stream: bool = False,
    on_stream_text: Callable[[str], None] | None = None,
) -> str:
    """
    基于当前仓库改动生成 commit message（单行）。

    Args:
        repo_root: 仓库根目录
        stage_all: 是否按“暂存全部改动”语义收集改动
        api_key: 可选，显式传入 API Key。未传入时从环境变量读取
        base_url: API 基础端点
        model: 模型名
        stream: 是否使用流式接口
        on_stream_text: 流式回调（每次收到新文本块时调用）
    """
    try:
        files_summary, diff_text = _collect_changes(repo_root, stage_all=stage_all)
    except GitCommandError as e:
        raise RuntimeError(f"读取仓库改动失败：{e}\n{e.output}") from e

    resolved_key = _resolve_api_key(api_key)
    resolved_base_url = _resolve_setting(
        base_url,
        env_keys=("BIGMODEL_BASE_URL", "ZHIPUAI_BASE_URL", "GLM_BASE_URL"),
        default=DEFAULT_BIGMODEL_BASE_URL,
    )
    resolved_model = _resolve_setting(
        model,
        env_keys=("BIGMODEL_MODEL", "ZHIPUAI_MODEL", "GLM_MODEL"),
        default=DEFAULT_BIGMODEL_MODEL,
    )
    messages = _build_prompt(files_summary=files_summary, diff_text=diff_text)
    if stream or on_stream_text is not None:
        return _request_commit_message_stream(
            api_key=resolved_key,
            base_url=resolved_base_url,
            model=resolved_model,
            messages=messages,
            on_stream_text=on_stream_text,
        )

    return _request_commit_message(
        api_key=resolved_key,
        base_url=resolved_base_url,
        model=resolved_model,
        messages=messages,
    )
