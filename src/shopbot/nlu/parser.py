"""Rules-only order parser (SPEC section 9). Deterministic, no LLM by
default. `NLU_MODE=llm` is a pluggable alternative (llm_parser.py) that must
return the same ParseResult shape; not used unless explicitly configured."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

_NUMBERS_PATH = Path(__file__).with_name("numbers.yaml")
_NUMBER_WORDS: dict[str, int] = yaml.safe_load(_NUMBERS_PATH.read_text(encoding="utf-8"))

_QTY_PREFIX_RE = re.compile(r"^(\d+)\s*(?:x|pcs?|plates?)?\s+", re.IGNORECASE)
_QTY_X_RE = re.compile(r"^x\s*(\d+)\s+", re.IGNORECASE)
_QTY_SUFFIX_RE = re.compile(r"\s+(\d+)\s*(?:x|pcs?|plates?)?$", re.IGNORECASE)
_QTY_SUFFIX_X_RE = re.compile(r"\s+x\s*(\d+)$", re.IGNORECASE)

_MODIFIER_RE = re.compile(
    r"\b(no|without|extra|less|more)\s+([a-z]+)\b|\b(spicy|less spicy|mild)\b",
    re.IGNORECASE,
)

FUZZY_AUTO_ACCEPT = 90
FUZZY_ASK = 75


@dataclass
class MenuIndexItem:
    item_id: str
    name: str
    price_paise: int
    aliases: list[str]
    max_qty: int
    available: bool = True


@dataclass
class ParsedLine:
    item_id: str
    name: str
    unit_price_paise: int
    qty: int
    note: str | None = None


@dataclass
class Ambiguous:
    raw_segment: str
    qty: int
    candidates: list[str]  # menu item names, best first


@dataclass
class ParseResult:
    lines: list[ParsedLine] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    ambiguous: list[Ambiguous] = field(default_factory=list)
    over_max_qty: list[tuple[str, int, int]] = field(default_factory=list)  # name, requested, max
    notes: list[str] = field(default_factory=list)
    confidence: float = 1.0


def _extract_qty(segment: str) -> tuple[str, int]:
    """Return (remaining_text, qty). Defaults to qty=1."""
    m = _QTY_PREFIX_RE.match(segment)
    if m:
        return segment[m.end():].strip(), int(m.group(1))
    m = _QTY_X_RE.match(segment)
    if m:
        return segment[m.end():].strip(), int(m.group(1))
    m = _QTY_SUFFIX_X_RE.search(segment)
    if m:
        return segment[: m.start()].strip(), int(m.group(1))
    m = _QTY_SUFFIX_RE.search(segment)
    if m:
        return segment[: m.start()].strip(), int(m.group(1))

    tokens = segment.split()
    if tokens and tokens[0] in _NUMBER_WORDS:
        return " ".join(tokens[1:]).strip(), _NUMBER_WORDS[tokens[0]]
    return segment, 1


def _extract_modifiers(text: str) -> tuple[str, str | None]:
    notes = []
    for m in _MODIFIER_RE.finditer(text):
        notes.append(m.group(0).strip())
    cleaned = _MODIFIER_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    note = ", ".join(notes) if notes else None
    return cleaned, note


def build_menu_index(items: list[MenuIndexItem]) -> dict[str, MenuIndexItem]:
    """Map every alias (and the item name) -> MenuIndexItem, for exact lookup."""
    index: dict[str, MenuIndexItem] = {}
    for item in items:
        if not item.available:
            continue
        index[item.name.lower()] = item
        for alias in item.aliases:
            index[alias.lower()] = item
    return index


def _all_alias_names(items: list[MenuIndexItem]) -> list[str]:
    names = []
    for item in items:
        if not item.available:
            continue
        names.append(item.name.lower())
        names.extend(a.lower() for a in item.aliases)
    return names


def parse_order(text_norm: str, segments: list[str], menu_items: list[MenuIndexItem]) -> ParseResult:
    result = ParseResult()
    exact_index = build_menu_index(menu_items)
    alias_pool = _all_alias_names(menu_items)
    alias_to_item = {}
    for item in menu_items:
        if not item.available:
            continue
        for alias in [item.name.lower(), *[a.lower() for a in item.aliases]]:
            alias_to_item[alias] = item

    for segment in segments:
        remaining, qty = _extract_qty(segment)
        item_text, note = _extract_modifiers(remaining)
        if note:
            result.notes.append(note)
        if not item_text:
            continue

        if item_text in exact_index:
            item = exact_index[item_text]
        else:
            match = process.extractOne(
                item_text, alias_pool, scorer=fuzz.WRatio, score_cutoff=FUZZY_ASK
            )
            if match is None:
                result.unresolved.append(segment)
                continue
            best_alias, score, _ = match
            if score >= FUZZY_AUTO_ACCEPT:
                item = alias_to_item[best_alias]
            else:
                top = process.extract(item_text, alias_pool, scorer=fuzz.WRatio, limit=5)
                seen_names: list[str] = []
                for alias, sc, _ in top:
                    if sc < FUZZY_ASK:
                        continue
                    name = alias_to_item[alias].name
                    if name not in seen_names:
                        seen_names.append(name)
                    if len(seen_names) == 3:
                        break
                result.ambiguous.append(Ambiguous(raw_segment=segment, qty=qty, candidates=seen_names))
                continue

        if qty > item.max_qty:
            result.over_max_qty.append((item.name, qty, item.max_qty))
            continue

        result.lines.append(
            ParsedLine(
                item_id=item.item_id,
                name=item.name,
                unit_price_paise=item.price_paise,
                qty=qty,
                note=note,
            )
        )

    total_segments = max(len(segments), 1)
    unresolved_count = len(result.unresolved) + len(result.ambiguous) + len(result.over_max_qty)
    result.confidence = max(0.0, 1.0 - unresolved_count / total_segments)
    return result
