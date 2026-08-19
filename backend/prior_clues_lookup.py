"""Prior-clue metadata parsing (matches exet-prior-clues.js)."""

from __future__ import annotations


def answer_key(s: str) -> str:
    if not s:
        return ""
    return "".join(ch for ch in str(s).upper() if "A" <= ch <= "Z")


def parse_meta(meta_str: str) -> dict:
    if not meta_str:
        return {
            "kind": "",
            "source": "",
            "date": "",
            "label": "",
            "definition": "",
        }
    parts = meta_str.split("|")
    kind = parts[0] if parts else ""
    if kind == "g":
        return {
            "kind": "cryptic",
            "source": parts[1] if len(parts) > 1 else "",
            "date": parts[2] if len(parts) > 2 else "",
            "label": parts[3] if len(parts) > 3 else "",
            "definition": parts[4] if len(parts) > 4 else "",
        }
    if kind == "x":
        pub = parts[1] if len(parts) > 1 else ""
        year = parts[2] if len(parts) > 2 else ""
        return {
            "kind": "xd",
            "source": pub,
            "date": year,
            "label": pub + (f" {year}" if year else ""),
            "definition": "",
        }
    return {
        "kind": "",
        "source": "",
        "date": "",
        "label": meta_str,
        "definition": "",
    }
