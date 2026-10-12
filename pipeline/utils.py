"""Küçük yardımcılar: ffmpeg konumu, çıktı ayrıştırma (ffprobe'suz), alt süreç yönetimi."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_FFMPEG_CACHE = None


def ffbin() -> str:
    """ffmpeg çalıştırılabilirini bul."""
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE
    env = os.environ.get("FFMPEG_BIN")
    if env and Path(env).exists():
        _FFMPEG_CACHE = env
        return env
    which = shutil.which("ffmpeg")
    if which:
        _FFMPEG_CACHE = which
        return which
    try:
        import imageio_ffmpeg

        _FFMPEG_CACHE = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG_CACHE
    except Exception as e:  # pragma: no cover
        raise RuntimeError("ffmpeg bulunamadı. 'bash setup.sh' çalıştırın.") from e


def run(cmd: list, log_file=None, timeout=None, env=None):
    """Alt süreç çalıştır; çıktıyı (rc, stdout+stderr) döndür. log_file verilirse canlı yazar."""
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", timeout=timeout, env=env,
    )
    if log_file:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(" ".join(map(str, cmd)) + "\n" + (proc.stdout or "") + "\n")
    return proc.returncode, proc.stdout or ""


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VID_RE = re.compile(r"Stream #\d+:\d+.*?: Video: .{0,200}?(\d{2,5})x(\d{2,5})")


def probe(path) -> dict:
    """ffmpeg -i ile süre/çözünürlük/ses bilgisi ayrıştır (ffprobe gerekmez)."""
    p = subprocess.run(
        [ffbin(), "-hide_banner", "-i", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace", timeout=180,
    )
    err = p.stdout or ""
    out = {"duration": None, "width": 0, "height": 0, "has_audio": "Audio:" in err}
    m = _DUR_RE.search(err)
    if m:
        h, mn, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
        out["duration"] = h * 3600 + mn * 60 + s
    dims = _VID_RE.findall(err)
    if dims:
        w, h = map(int, dims[-1])
        # 0x0 gibi sahte eşleşmeleri at
        if w > 16 and h > 16:
            out["width"], out["height"] = w, h
    return out


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:16]


def ensure_dir(p) -> Path:
    p = Path(p)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(p).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def fmt_ts(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def safe_slug(s: str, maxlen=48) -> str:
    s = (s or "video").strip().lower()
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosucgiosu")
    s = s.translate(tr_map)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return (s or "video")[:maxlen]
