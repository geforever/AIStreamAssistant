"""Live2D 模型 (.model3.json) 解析 + auto-detect。

只支持 Cubism 3+ (model3.json)。遇到 Cubism 2 (.model.json) 会被 discover 忽略,
load_model_info 直接传 v2 路径会 raise(没有 FileReferences 字段)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Live2DModel:
    path: Path                # 模型文件绝对路径
    expressions: list[str]    # Expressions[*].Name,按 model3.json 中的顺序
    motions: list[str]        # Motions dict 的 keys,按 model3.json 中的顺序


def load_model_info(path: Path) -> Live2DModel:
    """解析 .model3.json,返回 Live2DModel。

    Raises:
        ValueError: JSON 无效或缺 FileReferences 字段。
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid model3.json at {path}: {e}") from e

    refs = data.get("FileReferences")
    if not isinstance(refs, dict):
        raise ValueError(
            f"model3.json at {path} missing FileReferences section "
            "(is this a valid Cubism 3+ model?)"
        )

    # 全部小写化 — 项目约定:LLM/schema/WebSocket/比对 都用小写
    expressions = [
        str(e.get("Name", "")).lower()
        for e in refs.get("Expressions", []) or []
        if isinstance(e, dict) and e.get("Name")
    ]
    motions_dict = refs.get("Motions", {}) or {}
    motions = (
        [k.lower() for k in motions_dict.keys()]
        if isinstance(motions_dict, dict) else []
    )

    return Live2DModel(path=Path(path), expressions=expressions, motions=motions)


def discover_model_path(live2d_dir: Path) -> Path | None:
    """扫 live2d_dir,取字母序第一个非隐藏子文件夹,递归找第一个 *.model3.json。

    找不到返回 None(调用方决定是 raise 还是 fallback)。
    """
    live2d_dir = Path(live2d_dir)
    if not live2d_dir.exists() or not live2d_dir.is_dir():
        return None

    subfolders = sorted(
        p for p in live2d_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not subfolders:
        return None

    first = subfolders[0]
    matches = sorted(first.rglob("*.model3.json"))
    return matches[0] if matches else None
