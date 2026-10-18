"""Exact-match scoring of L6 answers (no LLM judge). ``score(family, expected, got)`` -> (strict, components).

Strict = every component exact. Components are reported separately so that "right count, wrong probes" is visible.
LLM replies are normalised leniently in form only (``"12"`` -> 12, ``"yes"`` -> True, ids case-folded and stripped), never
in substance.
"""

from __future__ import annotations

from typing import Any


def _int(x: Any) -> int | None:
    if isinstance(x, bool):
        return None
    if isinstance(x, int | float) and int(x) == x:
        return int(x)
    if isinstance(x, str) and x.strip().lstrip("-").isdigit():
        return int(x.strip())
    return None


def _bool(x: Any) -> bool | None:
    if isinstance(x, bool):
        return x
    if isinstance(x, str) and x.strip().casefold() in ("true", "yes", "affected", "blocked"):
        return True
    if isinstance(x, str) and x.strip().casefold() in (
        "false",
        "no",
        "not affected",
        "unaffected",
        "not blocked",
    ):
        return False
    return None


def _id(x: Any) -> str:
    return str(x).strip().strip("`\"' ").casefold()


def _ids(x: Any) -> list[str] | None:
    if isinstance(x, str) or not hasattr(x, "__iter__") or isinstance(x, dict):
        return None
    return [_id(i) for i in x]


def _bools(x: Any) -> list[bool] | None:
    if isinstance(x, str) or not hasattr(x, "__iter__") or isinstance(x, dict):
        return None
    out = [_bool(i) for i in x]
    return None if any(b is None for b in out) else out  # type: ignore[return-value]


def score_a(expected: dict[str, Any], got: Any) -> dict[str, bool]:
    if not isinstance(got, dict):
        return dict.fromkeys(expected, False)
    comp = {k: _int(got.get(k)) == expected[k] for k in ("facts", "agents", "decisions", "handoffs")}
    comp["probes"] = _bools(got.get("probes")) == expected["probes"]
    comp["earliest5"] = _ids(got.get("earliest5")) == [_id(i) for i in expected["earliest5"]]
    return comp


def score_dag(expected: dict[str, Any], got: Any) -> dict[str, bool]:
    if not isinstance(got, dict):
        return dict.fromkeys(expected, False)
    return {
        "tasks": _int(got.get("tasks")) == expected["tasks"],
        "probes": _bools(got.get("probes")) == expected["probes"],
        "first5": _ids(got.get("first5")) == [_id(i) for i in expected["first5"]],
    }


def score_b(expected: dict[str, Any], got: Any) -> dict[str, bool]:
    if not isinstance(got, dict):
        return {"chain": False, "agent": False}
    return {
        "chain": _ids(got.get("chain")) == [_id(i) for i in expected["chain"]],
        "agent": _id(got.get("agent")) == _id(expected["agent"]),
    }


def score_d(template: str, expected: Any, got: Any) -> dict[str, bool]:
    if template == "top_forgetter":
        if not isinstance(got, dict):
            return {"agent": False, "count": False}
        return {
            "agent": _id(got.get("agent")) == _id(expected["agent"]),
            "count": _int(got.get("count")) == expected["count"],
        }
    if template in ("shared_sources", "top_sprints"):
        g = _ids(got)
        e = [_id(i) for i in expected]
        return {
            "set" if template == "shared_sources" else "ordered": (sorted(g) == sorted(e))
            if template == "shared_sources" and g is not None
            else g == e
        }
    return {"count": _int(got) == expected}


def score(family: str, expected: Any, got: Any, template: str = "") -> tuple[bool, dict[str, bool]]:
    if family == "A":
        comp = score_a(expected, got)
    elif family == "dag":
        comp = score_dag(expected, got)
    elif family == "B":
        comp = score_b(expected, got)
    else:
        comp = score_d(template, expected, got)
    return all(comp.values()), comp
