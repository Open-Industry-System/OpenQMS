from __future__ import annotations

import re
from dataclasses import dataclass, field

_WS = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    return _WS.sub(" ", text.strip()).lower()


@dataclass
class PLHit:
    product_line_code: str
    product_type_code: str | None
    factory_id: str
    hit_criteria: list[str] = field(default_factory=list)
    evidence: dict[str, list[dict]] = field(default_factory=dict)


def aggregate_by_type(
    hits: list[dict], *, max_types: int = 50, max_pls_per_type: int = 30
) -> tuple[list[dict], bool]:
    """合并同 PL 命中、按 type 分组、稳定排序+截断。返回 (similar_products, truncated)。"""
    by_pl: dict[str, dict] = {}
    for h in hits:
        code = h["product_line_code"]
        cur = by_pl.get(code)
        if cur is None:
            cur = {
                "product_line_code": code,
                "product_type_code": h.get("product_type_code"),
                "factory_id": h["factory_id"],
                "hit_criteria": [],
                "evidence": {},
            }
            by_pl[code] = cur
        for c in h["hit_criteria"]:
            if c not in cur["hit_criteria"]:
                cur["hit_criteria"].append(c)
        for k, v in h.get("evidence", {}).items():
            cur["evidence"].setdefault(k, [])
            cur["evidence"][k].extend(v)

    # 按 type 分组
    groups: dict[str, list[dict]] = {}
    for pl in by_pl.values():
        type_code = pl["product_type_code"] or "unknown"
        groups.setdefault(type_code, []).append(pl)

    out: list[dict] = []
    for type_code in sorted(groups.keys()):
        full_pls = sorted(groups[type_code], key=lambda p: p["product_line_code"])
        pls = full_pls[:max_pls_per_type]
        out.append({
            "product_type_code": type_code,
            "product_type_name": "未分类" if type_code == "unknown" else type_code,
            "hit_criteria": sorted({c for p in pls for c in p["hit_criteria"]}),
            "suggestion_direction": None,  # LLM 填（Task 4）
            "product_lines": [
                {"code": p["product_line_code"], "factory_id": p["factory_id"]} for p in pls
            ],
            "evidence": {k: v for p in pls for k, v in p["evidence"].items()},
        })

    truncated = len(groups) > max_types or any(
        len(groups[type_code]) > max_pls_per_type for type_code in groups
    )
    out = out[:max_types]
    return out, truncated
