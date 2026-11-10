"""spec 机制通用件：加载 spec、路径解析、HTTP。

接口规则（端点/参数/字段映射）只存在于 specs/*.json（D12），
代码仅含通用解析逻辑与领域归一化，接口变更时改 spec 不改代码。
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .. import config


class SpecError(Exception):
    """spec 缺失/不匹配/响应结构校验失败。"""


def load_spec(name: str, spec_dir: Path | None = None) -> dict:
    spec_dir = spec_dir or config.SPEC_DIR
    path = spec_dir / f"{name}.json"
    if not path.exists():
        raise SpecError(f"spec 不存在: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError(f"spec JSON 解析失败: {path}: {e}") from e


def resolve(obj: Any, path: str) -> Any:
    """按 'a.b.c' 取值；任一段缺失返回 None。"""
    cur = obj
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def _flatten(items: list) -> list:
    out: list[Any] = []
    for it in items:
        if isinstance(it, list):
            out.extend(_flatten(it))
        else:
            out.append(it)
    return out


def resolve_list(obj: Any, path: str) -> list[Any]:
    """路径中允许 '*'（如 'value.matchInfoList.*'），递归拍平嵌套列表。"""
    parts = path.split(".")
    cur: list[Any] = [obj]
    for seg in parts:
        nxt: list[Any] = []
        for item in cur:
            if seg == "*":
                if isinstance(item, list):
                    nxt.extend(_flatten(item))
            elif isinstance(item, dict) and seg in item:
                nxt.append(item[seg])
        cur = nxt
    return cur


def check_success(payload: dict, spec: dict) -> None:
    for chk in spec.get("success_checks", []):
        value = resolve(payload, chk["path"])
        if "equals" in chk and value != chk["equals"]:
            raise SpecError(
                f"响应成功判据失败: {chk['path']}={value!r} (期望 {chk['equals']!r}); "
                f"errorMessage={resolve(payload, 'errorMessage')!r}"
            )


_last_request_ts = 0.0


def http_get_json(
    url: str,
    params: dict | None = None,
    extra_headers: dict | None = None,
    timeout: int | None = None,
) -> dict:
    """GET 并解析 JSON。带浏览器头与进程内最小间隔保护。"""
    global _last_request_ts
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    headers = dict(config.BROWSER_HEADERS)
    if extra_headers:
        headers.update(extra_headers)

    wait = config.REQUEST_MIN_INTERVAL_SEC - (time.monotonic() - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.HTTP_TIMEOUT_SEC) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise SpecError(f"HTTP {e.code}: {url}") from e
    except urllib.error.URLError as e:
        raise SpecError(f"网络错误: {url}: {e.reason}") from e
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SpecError(f"响应不是有效 JSON: {url}: {e}") from e
