"""Ses–metin hizalama: karakter ağırlıklı oransal dağıtım + sessizlik kenetleme (whisper'sız)."""
from __future__ import annotations

import re
from typing import List

from .utils import ffbin, probe

import subprocess


def detect_silences(audio_path: str, noise_db: int = -35, min_dur: float = 0.30):
    """Sessizlik aralıklarını bul → [(start, end), ...]"""
    cmd = [ffbin(), "-hide_banner", "-i", audio_path, "-af",
           f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace", timeout=3600)
    err = p.stdout or ""
    silences, cur_start = [], None
    for line in err.splitlines():
        if "silence_start:" in line:
            try:
                cur_start = float(line.split("silence_start:")[1].strip().split()[0])
            except Exception:
                cur_start = None
        elif "silence_end:" in line and cur_start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                silences.append((cur_start, end))
            except Exception:
                pass
            cur_start = None
    return silences


def assign_timings(sentences: List[str], audio_duration: float, silences=None) -> List[dict]:
    """Her cümleye başlangıç/bitiş süresi tahsis et.

    1) karakter sayısı + cümle arası nefes payı ile oransal dağıt
    2) her sınırı, ±tol içindeki en yakın sessizlik ortasına kenetle (drift azaltma)
    """
    n = len(sentences)
    if n == 0:
        return []
    silences = silences or []
    # 1) oransal
    weights = [max(len(s), 1) + 14 for s in sentences]  # +14: cümle sonu nefes payı (~%4)
    total_w = sum(weights)
    bounds = [0.0]
    acc = 0
    for w in weights[:-1]:
        acc += w
        bounds.append(audio_duration * acc / total_w)
    bounds.append(audio_duration)

    # 2) sessizliğe kenetleme
    mids = [(s + e) / 2 for s, e in silences]
    tol = min(1.8, audio_duration / max(n * 3, 10))
    for i in range(1, n):
        est = bounds[i]
        cand = min(mids, key=lambda m: abs(m - est)) if mids else None
        if cand is not None and abs(cand - est) <= tol:
            bounds[i] = cand
    # monotonluk + min cümle süresi güvence
    for i in range(1, n):
        bounds[i] = max(bounds[i], bounds[i - 1] + 0.30)
    bounds[n] = max(bounds[n], bounds[n - 1] + 0.30)

    return [{"text": sentences[i], "start": bounds[i], "end": bounds[i + 1]} for i in range(n)]


def group_scenes(timed_sentences: List[dict], min_dur=3.4, target_hi=6.6, max_dur=9.0):
    """Cümleleri ortalama 5-6 sn'lik sahnelere grupla. Cümle ortası bölünmez."""
    scenes, cur = [], []
    for i, s in enumerate(timed_sentences):
        cur.append(s)
        d = s["end"] - cur[0]["start"]
        d_next = timed_sentences[i + 1]["end"] - cur[0]["start"] if i + 1 < len(timed_sentences) else None
        if d >= target_hi:
            scenes.append(cur); cur = []
        elif d >= min_dur and d_next is not None and d_next > max_dur:
            scenes.append(cur); cur = []
    if cur:
        if scenes and (cur[-1]["end"] - cur[0]["start"]) < 1.6:
            scenes[-1].extend(cur)
        else:
            scenes.append(cur)

    out = []
    for group in scenes:
        text = " ".join(x["text"] for x in group)
        out.append({
            "text": text,
            "start": round(group[0]["start"], 3),
            "end": round(group[-1]["end"], 3),
            "duration": round(group[-1]["end"] - group[0]["start"], 3),
        })
    # çok uzun tek sahne: 16 sn üstüyse ikiye böl (görsel çeşitliliği koru)
    final = []
    for sc in out:
        if sc["duration"] > 16.0:
            parts = max(2, int(sc["duration"] // 9) + 1)
            step = (sc["end"] - sc["start"]) / parts
            for k in range(parts):
                final.append({"text": sc["text"], "start": round(sc["start"] + k * step, 3),
                              "end": round(sc["start"] + (k + 1) * step, 3),
                              "duration": round(step, 3)})
        else:
            final.append(sc)
    for idx, sc in enumerate(final):
        sc["index"] = idx
    return final
