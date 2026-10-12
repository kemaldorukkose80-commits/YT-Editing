"""Overlay yazıları için font çözümleme (repoya gömülü fontlar; sistem dışı bağımlılık yok)."""
from __future__ import annotations

import re
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_SCRIPTS = [
    ("arabic", re.compile(r"[\u0600-\u06FF\u0750-\u077F]"), "NotoSansArabic_700Bold.ttf", True),
    ("hebrew", re.compile(r"[\u0590-\u05FF]"), "NotoSansHebrew_700Bold.ttf", False),
    ("devanagari", re.compile(r"[\u0900-\u097F]"), "NotoSansDevanagari_700Bold.ttf", False),
    ("thai", re.compile(r"[\u0E00-\u0E7F]"), "NotoSansThai_700Bold.ttf", False),
    ("cjk", re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]"), "NotoSansJP_700Bold.ttf", False),
]

_FALLBACK = "DejaVuSans-Bold.ttf"  # Latin / Kiril / Yunan


def font_for_text(text: str):
    """(font_path, needs_arabic_shaping) döndür."""
    total = len(re.sub(r"\s", "", text)) or 1
    for name, rx, fname, shaping in _SCRIPTS:
        if len(rx.findall(text)) / total > 0.15:
            p = FONT_DIR / fname
            if p.exists():
                return str(p), shaping
    p = FONT_DIR / _FALLBACK
    if p.exists():
        return str(p), False
    return None, False
