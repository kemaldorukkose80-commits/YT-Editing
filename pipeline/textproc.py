"""Metin işleme: cümle bölme, sahne gruplama, anahtar kelime, varlık (sayı/para/isim) algılama."""
from __future__ import annotations

import re
import unicodedata
from typing import List

from .languages import (ABBREVIATIONS, CURRENCY_SYMBOLS, CURRENCY_WORDS,
                        MAGNIFIERS, STOPWORDS, common_words_excluded,
                        detect_language, is_cjk)

_PROT_DOT = "\x01"

# Cümle sonu: . ! ? … 。！？ ve sonrasında boşluk + büyük harf / rakam / tırnak
_SENT_SPLIT = re.compile(r"(?<=[.!?…。！？])\s+(?=[\d\[\(\"'“„«A-ZÀ-ÖØ-ÞА-Я\u0370-\u03FF\u0400-\u04FF\u0600-\u06FF\u0900-\u097FİIĞÜŞÖÇ])")


def _protect(text: str) -> str:
    text = re.sub(r"(?<=\d)[.](?=\d)", _PROT_DOT, text)          # 3.5 / 1.000.5
    def abbr_repl(m):
        return m.group(0).replace(".", _PROT_DOT)
    abbrs = "|".join(re.escape(a) for a in sorted(ABBREVIATIONS, key=len, reverse=True))
    text = re.sub(rf"(?<=\b)(?:{abbrs})(?=\.)(?=\.(\s|$|[,;]))", abbr_repl, text, flags=re.IGNORECASE)
    return text


def _restore(text: str) -> str:
    return text.replace(_PROT_DOT, ".")


def split_sentences(text: str) -> List[str]:
    """Metni cümlelere ayır (çok dilli). Yeni satırlar da sınır sayılır."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    sentences: List[str] = []
    cjk_term = re.compile(r"(?<=[。！？；])")
    for para in paragraphs:
        protected = _protect(para)
        parts: List[str] = []
        # 1) CJK noktalama: boşluk gerektirmez
        for seg in cjk_term.split(protected):
            # 2) boşluklu cümle sonları
            parts.extend(_SENT_SPLIT.split(seg))
        for part in parts:
            s = _restore(part).strip()
            s = re.sub(r"\s+([,.!?;:…])", r"\1", s)
            if s:
                sentences.append(s)
    return sentences


# ---------------------------------------------------------------------------
# Kelime/ayraç yardımcıları
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
_CJK_RUN = re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF\uAC00-\uD7AF]{2,8}")


def _strip_suffix(word: str) -> str:
    """Türkçe/Lehçe ekli biçimleri tabana indir: Türkiye'nin -> Türkiye"""
    if "'" in word or "’" in word:
        base = re.split("['’]", word)[0]
        if len(base) >= 2:
            return base
    return word


def _is_capitalized(word: str) -> bool:
    ch = word[0]
    return ch.isalpha() and ch.isupper()


def tokenize(text: str) -> List[str]:
    return [m.group(0) for m in _WORD_RE.finditer(text)]


# ---------------------------------------------------------------------------
# Anahtar kelimeler (görsel arama sorguları)
# ---------------------------------------------------------------------------
def keywords_for(text: str, lang: str, doc_freq: dict = None, total_scenes: int = 1) -> List[str]:
    import math
    doc_freq = doc_freq or {}
    stop = STOPWORDS.get(lang, set()) | common_words_excluded(lang)
    if is_cjk(lang):
        runs = _CJK_RUN.findall(text)
        scored = sorted(set(runs), key=lambda r: -len(r))
        return scored[:2]
    scores = {}
    for raw in tokenize(text):
        base = _strip_suffix(raw)
        low = base.lower()
        if low in stop or len(low) < 3:
            continue
        cap_bonus = 1.5 if _is_capitalized(base) else 1.0
        idf = 1.0 + math.log(1 + total_scenes / (1 + doc_freq.get(low, 0)))
        scores[base] = min(len(base), 14) * cap_bonus * idf
    ranked = sorted(scores, key=lambda k: -scores[k])[:3]
    return ranked


# ---------------------------------------------------------------------------
# Varlık algılama (overlay metinleri): para > sayı > yıl > isim
# ---------------------------------------------------------------------------
_NUM = r"\d[\d.,]*"
_MONEY_PATTERNS = None


def _money_regex(lang: str):
    cur = "|".join(sorted(CURRENCY_WORDS.get(lang, set()) | CURRENCY_WORDS.get("en", set()), key=len, reverse=True))
    mag = "|".join(sorted(set(MAGNIFIERS.get(lang, {})) | set(MAGNIFIERS.get("en", {})), key=len, reverse=True))
    sym = re.escape("".join(CURRENCY_SYMBOLS))
    pats = [
        rf"(?:[{sym}]\s?{_NUM}(?:\s?(?:{mag}))?)(?:\s(?:{cur}))?",   # $1.5 milyon / ₺2.400.000
        rf"\b{_NUM}\s(?:{mag})\s(?:{cur})\b",                        # 3 milyon dolar
        rf"\b{_NUM}\s(?:{cur})\b",                                   # 500 dolar
    ]
    return re.compile("|".join(pats), re.IGNORECASE)


def _clean_entity(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip(" ,;:.…-")
    return s


def detect_entities(text: str, lang: str, scene_start_char: int = 0):
    """Sahnendeki para/sayı/isim adayları → [{text, kind, score, rel}] rel: metindeki göreç konum (0-1)."""
    out = []
    money_re = _money_regex(lang)
    for m in money_re.finditer(text):
        frag = _clean_entity(m.group(0))
        if not frag:
            continue
        low = frag.lower()
        score = 10.0
        if any(sym in frag for sym in CURRENCY_SYMBOLS):
            score += 1.5
        if any(mag in low for mag in MAGNIFIERS.get(lang, {})) or any(mag in low for mag in MAGNIFIERS.get("en", {})):
            score += 2.0
        out.append({"text": frag, "kind": "money", "score": score, "rel": (scene_start_char + m.start()) / max(1, len(text))})

    for m in re.finditer(rf"(?<![\w.,]){ _NUM }(?:\s?%| percent| yüzde)?(?![\w.,])", text):
        frag = _clean_entity(m.group(0))
        digits = re.sub(r"\D", "", frag)
        is_year = 4 == len(digits) and (frag.startswith("1") or frag.startswith("2"))
        if "%" in frag or "percent" in frag.lower() or "yüzde" in frag.lower():
            score = 8.0
        elif is_year:
            score = 5.0
        elif len(digits) >= 4:
            score = 7.0
        elif len(digits) == 3:
            score = 4.0
        else:
            score = 0.0  # 1-99 arası tek başına sayılar zayıf
        if score:
            out.append({"text": frag, "kind": "number", "score": score, "rel": (scene_start_char + m.start()) / max(1, len(text))})

    # büyüklüklü sayılar: "3 milyon", "85 million" (para kelimesi olmadan da)
    mag = "|".join(sorted(set(MAGNIFIERS.get(lang, {})) | set(MAGNIFIERS.get("en", {})), key=len, reverse=True))
    for m in re.finditer(rf"(?<![\w.,]){_NUM}\s(?:{mag})\b", text, re.IGNORECASE):
        frag = _clean_entity(m.group(0))
        if not any((frag in e["text"]) or (e["text"] in frag) for e in out):
            out.append({"text": frag, "kind": "number", "score": 8.0,
                        "rel": (scene_start_char + m.start()) / max(1, len(text))})
    # yüzde önde gelirse: "yüzde 40", "% 40"
    for m in re.finditer(rf"(?:%|yüzde)\s?{_NUM}", text, re.IGNORECASE):
        frag = _clean_entity(m.group(0))
        if not any(e["text"] == frag for e in out):
            out.append({"text": frag, "kind": "number", "score": 8.0,
                        "rel": (scene_start_char + m.start()) / max(1, len(text))})

    # İsimler: ardışık büyük harfli kelimeler + kısaltmalar
    stop = common_words_excluded(lang)
    toks = [(m.group(0), m.start()) for m in _WORD_RE.finditer(text)]
    run, run_start = [], None
    def flush_run(end_idx):
        nonlocal run, run_start
        if len(run) >= 2:
            words = [_strip_suffix(w) for w in run]
            frag = _clean_entity(" ".join(words))
            if 2 <= len(words) <= 4 and len(frag) <= 44:
                out.append({"text": frag, "kind": "name", "score": 8.0 + min(len(words), 3) * 0.4,
                            "rel": (scene_start_char + run_start) / max(1, len(text))})
        elif len(run) == 1 and run_start > 0:
            base = _strip_suffix(run[0])
            low = base.lower()
            if low not in stop and len(base) >= 3 and _is_capitalized(base) and not base.isupper():
                out.append({"text": base, "kind": "name", "score": 3.8,
                            "rel": (scene_start_char + run_start) / max(1, len(text))})
        run, run_start = [], None

    for i, (tok, pos) in enumerate(toks):
        base = _strip_suffix(tok)
        low = base.lower()
        if base.isupper() and 2 <= len(base) <= 6 and base.isalpha():
            flush_run(i)
            out.append({"text": base, "kind": "acronym", "score": 7.5,
                        "rel": (scene_start_char + pos) / max(1, len(text))})
            continue
        if _is_capitalized(tok) and low not in stop:
            if not run:
                run_start = pos
            run.append(tok)
        else:
            flush_run(i)
    flush_run(len(toks))
    return out


def select_overlays(scenes, total_duration: float, max_overlays=5, min_gap=40.0, hook_seconds=90.0):
    """Tüm video için 3-5 overlay seç; hook'a (giriş) öncelik, yayılım için min boşluk."""
    # kısa videolarda aralığı ölçekle ki 3-5 efekt sığsın
    eff_gap = max(8.0, min(min_gap, total_duration / max(max_overlays, 1)))
    cands = []
    for sc in scenes:
        for ent in sc.get("entities", []):
            t = sc["start"] + ent["rel"] * sc["duration"]
            score = ent["score"]
            hook_end = min(hook_seconds, total_duration * 0.15)
            if t <= hook_end:
                score += 6.0
            elif t <= total_duration * 0.4:
                score += 2.0
            cands.append({"text": ent["text"], "kind": ent["kind"], "time": t,
                          "scene_idx": sc["index"], "score": score})
    cands.sort(key=lambda c: (-c["score"], c["time"]))
    chosen = []
    for c in cands:
        if len(chosen) >= max_overlays:
            break
        if any(ch["scene_idx"] == c["scene_idx"] for ch in chosen):
            continue
        if any(ch["text"].lower() == c["text"].lower() for ch in chosen):
            continue
        if any(abs(ch["time"] - c["time"]) < eff_gap for ch in chosen):
            continue
        chosen.append(c)
    chosen.sort(key=lambda c: c["time"])
    return chosen
