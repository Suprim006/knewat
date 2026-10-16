"""Duplicate detection for facts (P9-c B0/B1/B2): precision guards, a token-Jaccard second tier, soft duplicates.

An embedding cannot tell ``enabled`` from ``not enabled``, ``5 minutes`` from ``5 hours`` or ``at least 3`` from
``at most 3`` (cosine distance 0.02-0.07 for all of them; PRODUCT_FIXES_ANALYSIS B.1). Merging such a pair
silently throws a statement away. So a candidate is only ever a duplicate when its **discriminator key** equals the
new value's key; the key is a deterministic, LLM-free multiset of everything that flips meaning:

* numbers and versions (``16`` != ``15``; ``1.2.3`` != ``1.2.4``), number words (``two`` == ``2``, ``twenty five`` == ``25``),
  ordinals (``first`` == ``1st``);
* quantities in a base unit (``5 minutes`` == ``300 s`` != ``5 hours``; ``1 GB`` == ``1000 MB`` != ``1 GiB``);
* negation (``not no never without cannot n't``, and an un-/dis-/non- prefix on a word) and a reviewed table of
  antonym pairs (enabled/disabled, above/below, least/most, all/some, ...);
* a **sequence guard** for the one thing a bag of words cannot see: when two values have the *same* content words but
  in a different order (``A calls B`` / ``B calls A``, ``from X to Y`` / ``to X from Y``) they are never auto-merged.

Tier 1 (cosine <= 0.08, the existing threshold) and tier 2 (token Jaccard >= 0.6 AND cosine <= 0.16, the
embedding being only a sanity floor so that two short values sharing most of a few words are never merged on words
alone) both need the keys to be equal. Tier 3 (cosine <= 0.20 or Jaccard >= 0.5, keys equal) is *advisory*: the new
fact is created as usual and linked ``(new)-[:DUPLICATES_MAYBE]->(old)`` for an agent to confirm or reject.
"""

# ruff: noqa: E501 - long literal tables and prose lines

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from plexus.common import OPEN
from plexus.common import now_ms as _now_ms
from plexus.engram.errors import EngramError

# ----------------------------------------------------------------------------------------------- settings
DEFAULT_JACCARD = 0.6  # tier 2: stemmed, stop-word-free token Jaccard
DEFAULT_TIER2_COS = 0.16  # tier 2: cosine distance ceiling (tier 1 is Engram.dup_threshold, 0.08)
DEFAULT_MAYBE_COS = 0.20  # tier 3: soft link when the cosine distance is within this
DEFAULT_MAYBE_JACCARD = 0.5  # tier 3: ... or the Jaccard is at least this
MAYBE_CAP = 5  # at most this many soft links per asserted fact (the nearest first)


@dataclass(frozen=True)
class DedupSettings:
    """Thresholds of tiers 2 and 3, from the environment: ``PLEXUS_DUP_JACCARD`` [0.6], ``PLEXUS_DUP_TIER2_COS``
    [0.16], ``PLEXUS_DUP_MAYBE_COS`` [0.20], ``PLEXUS_DUP_MAYBE_JACCARD`` [0.5]."""

    jaccard: float = DEFAULT_JACCARD
    tier2_cos: float = DEFAULT_TIER2_COS
    maybe_cos: float = DEFAULT_MAYBE_COS
    maybe_jaccard: float = DEFAULT_MAYBE_JACCARD

    def __post_init__(self) -> None:
        for name, v in (
            ("PLEXUS_DUP_JACCARD", self.jaccard),
            ("PLEXUS_DUP_MAYBE_JACCARD", self.maybe_jaccard),
        ):
            if not 0.0 < v <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        for name, v in (("PLEXUS_DUP_TIER2_COS", self.tier2_cos), ("PLEXUS_DUP_MAYBE_COS", self.maybe_cos)):
            if not 0.0 <= v <= 2.0:
                raise ValueError(f"{name} must be a cosine distance in [0, 2]")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DedupSettings:
        e = os.environ if env is None else env

        def num(name: str, default: float) -> float:
            raw = (e.get(name) or "").strip()
            try:
                return float(raw) if raw else default
            except ValueError:
                raise ValueError(f"{name} must be a number") from None

        return cls(
            jaccard=num("PLEXUS_DUP_JACCARD", DEFAULT_JACCARD),
            tier2_cos=num("PLEXUS_DUP_TIER2_COS", DEFAULT_TIER2_COS),
            maybe_cos=num("PLEXUS_DUP_MAYBE_COS", DEFAULT_MAYBE_COS),
            maybe_jaccard=num("PLEXUS_DUP_MAYBE_JACCARD", DEFAULT_MAYBE_JACCARD),
        )


# ----------------------------------------------------------------------------------------------- tables
_TOKEN = re.compile(r"\d+(?:\.\d+)*|%|[^\W\d_]+", re.UNICODE)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NT = re.compile(r"n[’']t\b")
_PLAIN_INT = re.compile(r"\d+")
_PLAIN_DEC = re.compile(r"\d+\.\d+")

_ONES = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen".split()
    )
}
_TENS = {
    w: 10 * i
    for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split())
    if w != "_"
}
_SCALE = {"hundred": 100, "thousand": 1000, "million": 10**6, "billion": 10**9}
_ORDINALS = {
    w: i
    for i, w in enumerate("first second third fourth fifth sixth seventh eighth ninth tenth".split(), start=1)
    if w != "second"  # 'second' is far more often the unit than the ordinal
}
_ORD_SUFFIX = {"st", "nd", "rd", "th"}

_SEC = {
    "ms": Fraction(1, 1000),
    "millisecond": Fraction(1, 1000),
    "s": 1,
    "sec": 1,
    "second": 1,
    "min": 60,
    "minute": 60,
    "h": 3600,
    "hr": 3600,
    "hour": 3600,
    "d": 86400,
    "day": 86400,
    "w": 604800,
    "week": 604800,
}
_BYTES = {"b": 1, "byte": 1, "kb": 10**3, "mb": 10**6, "gb": 10**9, "tb": 10**12}
_IBYTES = {"kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}
_PCT = {"%", "percent", "pct"}

_NEG = {"not", "no", "never", "without", "cannot", "none", "nobody", "nothing", "neither", "nor", "non", "nt"}
_NEG_PREFIXED = {  # words whose in-/im-/ir-/il- prefix is a negation (a closed list: those prefixes are too common)
    "invalid",
    "inactive",
    "impossible",
    "illegal",
    "irrelevant",
    "insecure",
    "inaccessible",
    "inconsistent",
    "incorrect",
    "incompatible",
    "incomplete",
    "inefficient",
    "indirect",
    "ineligible",
    "impure",
    "irreversible",
    "irregular",
    "illegible",
    "inadequate",
    "inappropriate",
    "intolerant",
    "unsafe",
    "improper",
    "imperfect",
}
_PREFIX_EXCEPT = {  # un-/dis-/non- words that do not negate
    "under",
    "understand",
    "understood",
    "underlying",
    "undo",
    "undone",
    "undergo",
    "unit",
    "units",
    "union",
    "unique",
    "uniform",
    "universal",
    "universe",
    "unix",
    "unicode",
    "until",
    "unless",
    "unified",
    "unify",
    "unity",
    "unite",
    "united",
    "unicast",
    "display",
    "displays",
    "displayed",
    "disk",
    "disks",
    "distribute",
    "distributed",
    "distribution",
    "distributor",
    "discover",
    "discovery",
    "dispatch",
    "dispatcher",
    "discord",
    "discount",
    "distance",
    "distinct",
    "district",
    "disclose",
    "discipline",
    "dispose",
    "disposal",
    "dispute",
    "distro",
    "discuss",
    "discussion",
    "disrupt",
    "disruption",
    "dissolve",
    "distill",
    "distinguish",
    "discretion",
    "discrete",
    "disaster",
    "dismiss",
    "dismissed",
    "nonce",
    "nonetheless",
    "unnamed",
}

# antonym groups: (group, positive words, negative words); words are stemmed with the same _stem used for lookup.
# A word listed on one side only (e.g. 'off', 'down', 'under') makes the pair differ from the plain/other side.
_GROUPS: list[tuple[str, str, str]] = [
    ("onoff", "", "off"),
    ("enable", "enable activate activated", "disable deactivate deactivated inactive"),
    (
        "allow",
        "allow permit authorize authorise accept grant whitelist",
        "deny forbid prohibit disallow block reject revoke refuse ban blacklist",
    ),
    (
        "cmp",
        "above over exceed greater higher larger bigger more longer faster",
        "below under less fewer lower smaller shorter slower",
    ),
    ("bound", "least minimum min lowest floor", "most maximum max highest ceiling cap"),
    ("order", "before earlier prior", "after later following"),
    ("inc", "increase grow raise expand extend", "decrease reduce shrink cut drop decline"),
    ("start", "start begin launch", "stop halt terminate kill"),
    ("open", "open", "close"),
    ("bool", "true", "false"),
    ("req", "required mandatory", "optional"),
    ("vis", "public", "private"),
    ("loc", "internal local", "external remote"),
    ("sync", "synchronous sync", "asynchronous async"),
    ("dir", "inbound ingress", "outbound egress"),
    ("rw", "read", "write"),
    ("pp", "push", "pull"),
    ("sr", "send", "receive"),
    ("ar", "add", "remove delete"),
    ("cd", "create", "destroy"),
    ("crypt", "encrypt", "decrypt"),
    ("lock", "lock", "unlock"),
    ("incl", "include", "exclude"),
    ("ok", "success succeed pass", "failure fail"),
    ("line", "online", "offline"),
    ("inst", "install", "uninstall"),
    ("mut", "mutable", "immutable"),
    ("state", "stateful", "stateless"),
    ("persist", "persistent", "ephemeral transient"),
    ("up", "", "down"),
    ("ee", "enter", "exit"),
]
# 'all/every/each' emit nothing: they are the default reading of a generic plural ('every deploy' == 'deploys');
# only the words that narrow or widen it do.
_QUANT = {
    "some": "some",
    "any": "any",
    "only": "only",
    "few": "few",
    "many": "many",
    "always": "always",
    "sometimes": "sometimes",
    "often": "often",
    "rarely": "rarely",
    "usually": "usually",
    "occasionally": "occasionally",
    "both": "both",
    "either": "either",
}

_STOP = set(
    """a an the is are was were be been being am of to in on at by for with from and or it its this that these those as
    must should shall will would can could may might do does did has have had need needs require requires required
    please also just very so every each all than then there here which who whom whose what when where how if into onto via per
    st nd rd th their there they them we our us you your i me my he she his her him about up s""".split()
) - {"up"}
_STOP.discard("required")  # 'required' is a discriminator (req group) and a content word
# words kept in the sequence (not the set): a different order of these with the same content words is a different statement
_DIRECTION = {
    "to",
    "from",
    "into",
    "by",
    "via",
    "than",
    "between",
    "before",
    "after",
    "over",
    "under",
    "onto",
}


def _stem(w: str) -> str:
    """A small deterministic suffix stripper: deploys/deployed/deploying -> deploy, approve/approved -> approv."""
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("ing") and len(w) > 5:
        w = w[:-3]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
            w = w[:-1]
    elif w.endswith("ed") and len(w) > 4:
        w = w[:-2]
        if len(w) > 2 and w[-1] == w[-2] and w[-1] not in "lsz":
            w = w[:-1]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")) and len(w) > 3:
        w = w[:-1]
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def _build_lookup() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for group, pos, neg in _GROUPS:
        for sign, words in (("+", pos), ("-", neg)):
            for w in words.split():
                out[_stem(w)] = (group, sign)
                out[w] = (group, sign)
    return out


_ANTONYM = _build_lookup()
_UNIT_NAMES = set(_SEC) | set(_BYTES) | set(_IBYTES) | {"percent", "pct", "%"}


def _fmt(v: Fraction | int) -> str:
    v = Fraction(v)
    if v.denominator == 1:
        return str(v.numerator)
    s = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return s


def _unit_token(value: Fraction, unit: str) -> str | None:
    u = unit.casefold()
    if u in _PCT:
        return f"q:{_fmt(value)}%"
    for singular in (u, u[:-1] if u.endswith("s") else u):
        if singular in _SEC:
            return f"q:{_fmt(value * Fraction(_SEC[singular]))}s"
        if singular in _BYTES:
            return f"q:{_fmt(value * _BYTES[singular])}B"
        if singular in _IBYTES:
            return f"q:{_fmt(value * _IBYTES[singular])}iB"
    return None


# ----------------------------------------------------------------------------------------------- features
@dataclass(frozen=True)
class Features:
    """What the dedup rules need from a value: ``key`` (discriminators), ``tok`` (sorted unique stemmed content
    tokens, for Jaccard) and ``seq`` (the ordered content + direction tokens, for the sequence and substitution guards)."""

    key: str
    tok: list[str]
    seq: list[str]


def _numbers_and_words(text: str) -> list[tuple[str, str]]:
    """The token stream as ``(kind, text)``: ``num`` (value as string), ``word`` (casefolded), ``pct``."""
    s = _NT.sub(" not", text.replace("’", "'"))
    s = _THOUSANDS.sub("", s)
    raw = _TOKEN.findall(s)
    out: list[tuple[str, str]] = []
    first = True
    for t in raw:
        if t == "%":
            out.append(("word", "%"))
        elif t[0].isdigit():
            out.append(("num", t))
        else:
            # a capital 'A' that is not the first word is an identifier ('Service A calls B'), never the article
            if t == "A" and not first:
                out.append(("word", "a#"))
            else:
                out.append(("word", t.casefold()))
        first = False
    return out


def _merge_number_words(stream: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Fold number words and scale words into ``num`` tokens: 'twenty five' -> 25, 'two hundred' -> 200, 'half' -> 0.5."""
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(stream):
        kind, t = stream[i]
        val: Fraction | None = None
        if kind == "num" and _PLAIN_INT.fullmatch(t):
            val = Fraction(int(t))
        elif kind == "word" and (t in _ONES or t in _TENS):
            val = Fraction(_ONES.get(t, _TENS.get(t, 0)))
        elif kind == "word" and t == "half":
            out.append(("num", "0.5"))
            i += 1
            continue
        if val is None:
            out.append((kind, t))
            i += 1
            continue
        j = i + 1
        is_word_start = kind == "word"
        # tens + ones: 'twenty five'
        if (
            is_word_start
            and t in _TENS
            and j < len(stream)
            and stream[j][0] == "word"
            and 0 < _ONES.get(stream[j][1], 0) < 10
        ):
            val += _ONES[stream[j][1]]
            j += 1
        # scale: 'two hundred', '5 thousand' (a single scale per number is enough for config values)
        if j < len(stream) and stream[j][0] == "word" and stream[j][1] in _SCALE:
            val *= _SCALE[stream[j][1]]
            j += 1
        out.append(("num", _fmt(val) if kind == "word" or j > i + 1 else t))
        i = j
    return out


def _discriminators(stream: list[tuple[str, str]]) -> tuple[list[str], list[tuple[str, str]]]:
    """(discriminator tokens, remaining content stream with consumed words removed)."""
    d: list[str] = []
    rest: list[tuple[str, str]] = []
    i = 0
    n = len(stream)
    while i < n:
        kind, t = stream[i]
        if kind == "num":
            nxt = stream[i + 1] if i + 1 < n else None
            if nxt and nxt[0] == "word":
                w = nxt[1]
                if w in _ORD_SUFFIX and _PLAIN_INT.fullmatch(t):
                    d.append(f"o:{int(t)}")
                    i += 2
                    continue
                if _PLAIN_INT.fullmatch(t) or _PLAIN_DEC.fullmatch(t):
                    q = _unit_token(Fraction(t), w)
                    if q:
                        d.append(q)
                        rest.append(("q", q))  # '5 minutes' and '300 s' are the same content token
                        i += 2
                        continue
            d.append(f"n:{t}")
            rest.append(("num", t))
            i += 1
            continue
        w = kind == "word" and t or ""
        i += 1
        if w in _ORDINALS:
            d.append(f"o:{_ORDINALS[w]}")
            rest.append(("word", w))
            continue
        if w in _NEG or w in _NEG_PREFIXED:
            d.append("neg")
            if w in _NEG:
                continue  # negations carry no content
        sw = _stem(w)
        hit = _ANTONYM.get(w) or _ANTONYM.get(sw)
        if hit:
            d.append(f"p:{hit[0]}:{hit[1]}")
        elif w in _QUANT:
            d.append(f"x:{_QUANT[w]}")
        elif (
            len(w) >= 6
            and w not in _PREFIX_EXCEPT
            and w not in _NEG_PREFIXED
            and (w.startswith(("un", "dis")) and not w.startswith(("uni", "under", "disk")))
        ):
            base = w[2:] if w.startswith("un") else w[3:]
            bhit = _ANTONYM.get(base) or _ANTONYM.get(_stem(base))
            if bhit:
                d.append(f"p:{bhit[0]}:{'-' if bhit[1] == '+' else '+'}")
            else:
                d.append("neg")
        rest.append(("word", w))
    return d, rest


def features(text: str) -> Features:
    """The dedup features of ``text`` (see the module docstring). Pure and deterministic."""
    stream = _merge_number_words(_numbers_and_words(text))
    disc, rest = _discriminators(stream)
    key = " ".join(sorted(disc))
    content: list[str] = []
    seq: list[str] = []
    for kind, t in rest:
        if kind in ("num", "q"):
            tk = f"#{t}" if kind == "num" else t
            content.append(tk)
            seq.append(tk)
            continue
        if t in _NEG or t == "%":
            continue
        if t in _DIRECTION:
            seq.append(t)
            continue
        if t in _STOP:
            continue
        if t in _ORD_SUFFIX:
            continue
        s = _stem(t) if t != "a#" else "a#"
        content.append(s)
        seq.append(s)
    return Features(key=key, tok=sorted(set(content)), seq=seq)


def jaccard(a: Sequence[str], b: Sequence[str]) -> float:
    """Jaccard similarity of two token collections (0.0 when both are empty)."""
    sa, sb = set(a), set(b)
    union = sa | sb
    return len(sa & sb) / len(union) if union else 0.0


def sequence_blocks(a: Features, b: Features) -> bool:
    """True when ``a`` and ``b`` have the same content words in a different order: never auto-merge those."""
    return a.tok == b.tok and a.seq != b.seq


def substitution_blocks(a: Features, b: Features) -> bool:
    """True when ``b`` is ``a`` with exactly one content token replaced by another ('on Monday' / 'on Tuesday').

    Either one token on each side differs as a set, or the sequences have the same length and differ in one position
    (which also catches a replacement by a word that occurs elsewhere in the sentence). The statement mirrors this.
    """
    inter = len(set(a.tok) & set(b.tok))
    if len(a.tok) - inter == 1 and len(b.tok) - inter == 1:
        return True
    return len(a.seq) == len(b.seq) and sum(1 for x, y in zip(a.seq, b.seq, strict=True) if x != y) == 1


def auto_merge_blocked(a: Features, b: Features) -> bool:
    """The guards of tiers 1 and 2 (the Cypher statement implements the same rule on the stored token lists)."""
    return sequence_blocks(a, b) or substitution_blocks(a, b)


# ----------------------------------------------------------------------------------------------- confirm / reject
class DuplicateError(EngramError, ValueError):
    """A confirm / reject request that cannot be carried out (unknown fact, no soft link, facts no longer current)."""


class Dedup:
    """Resolve soft duplicates (``DUPLICATES_MAYBE``) on one tenant graph: confirm (merge) or reject (and undo)."""

    def __init__(self, client: Any, graph: str):
        self.client = client
        self.graph = graph

    def _pair(self, new_id: str, old_id: str) -> dict[str, Any]:
        if new_id == old_id:
            raise DuplicateError("new_id and old_id must be two different facts")
        rows = self.client.ro(
            self.graph, "engram/duplicate_pair", {"new_id": new_id, "old_id": old_id, "open_to": OPEN}
        )
        if not rows:
            raise DuplicateError("unknown fact: both new_id and old_id must be existing fact ids")
        return rows[0]

    def confirm_duplicate(self, new_id: str, old_id: str, *, now: int | None = None) -> dict[str, Any]:
        """Merge ``new_id`` into ``old_id``: the new fact becomes a duplicate of the old one (reversible).

        Needs the soft link ``(new)-[:DUPLICATES_MAYBE]->(old)`` that ``assert_fact`` created and a *current* new fact.
        The old fact keeps (or regains, if the new one had superseded it) the current value; the agents that asserted
        the new fact now also assert the old one, with the wording they used on ``ASSERTED_BY.text``. Idempotent:
        confirming a confirmed pair returns ``merged: False, already: True``.
        """
        p = self._pair(new_id, old_id)
        if p["confirmed"]:
            return {
                "new_id": new_id,
                "old_id": old_id,
                "merged": False,
                "already": True,
                "reopened": False,
                "moved": [],
            }
        if not p["linked"]:
            raise DuplicateError(
                "these facts are not linked as possible duplicates (no DUPLICATES_MAYBE link from new_id to old_id)"
            )
        t = now if now is not None else _now_ms()
        rows = self.client.rw(
            self.graph,
            "engram/confirm_duplicate",
            {"new_id": new_id, "old_id": old_id, "open_to": OPEN, "now": t},
        )
        if not rows:
            raise DuplicateError(
                "cannot merge: new_id is no longer the current value, or old_id was replaced by another fact"
            )
        r = rows[0]
        return {
            "new_id": new_id,
            "old_id": old_id,
            "merged": True,
            "already": False,
            "reopened": bool(r["reopened"]),
            "moved": list(r["moved"]),
        }

    def reject_duplicate(self, new_id: str, old_id: str) -> dict[str, Any]:
        """Say the pair is not a duplicate: remove the soft link. On an already *confirmed* pair this undoes the merge.

        Returns ``{rejected: True}`` when a soft link was removed, ``{undone: True}`` when a merge was undone,
        ``{rejected: False, undone: False}`` when there was nothing to do.
        """
        p = self._pair(new_id, old_id)
        if p["confirmed"]:
            rows = self.client.rw(
                self.graph, "engram/split_duplicate", {"new_id": new_id, "old_id": old_id, "open_to": OPEN}
            )
            if not rows:
                raise DuplicateError("cannot undo the merge: the facts have changed since it was confirmed")
            return {
                "new_id": new_id,
                "old_id": old_id,
                "rejected": False,
                "undone": True,
                "restored": bool(rows[0]["restored"]),
            }
        rows = self.client.rw(self.graph, "engram/reject_duplicate", {"new_id": new_id, "old_id": old_id})
        removed = int(rows[0]["removed"]) if rows else 0
        return {
            "new_id": new_id,
            "old_id": old_id,
            "rejected": removed > 0,
            "undone": False,
            "restored": False,
        }
