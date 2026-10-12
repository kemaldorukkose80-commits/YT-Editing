#!/usr/bin/env python3
"""Headless render: GitHub Actions ve güçlü kullanıcılar için.

Kullanım:
    python3 render_cli.py --job-dir jobs/ornek-video

Job klasörü içeriği:
    audio.mp3|wav|m4a|...   (seslendirme)
    script.txt              (video metni)
    options.json            (isteğe bağlı ayarlar)
Ortam değişkenleri: BRAVE_API_KEY, PEXELS_API_KEY
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.job import Pipeline
from pipeline.utils import read_json
from pipeline.visuals import VisualProvider


def main():
    ap = argparse.ArgumentParser(description="YT-Editing render")
    ap.add_argument("--job-dir", required=True, help="audio + script.txt + options.json içeren klasör")
    ap.add_argument("--out", default="", help="çıktı mp4 yolu (varsayılan: output/<ad>.mp4)")
    ap.add_argument("--mode", default="", choices=["", "real", "test"], help="görsel modu (options.json'u ezer)")
    args = ap.parse_args()

    jd = Path(args.job_dir)
    if not jd.exists():
        print(f"İş klasörü yok: {jd}", file=sys.stderr)
        sys.exit(2)

    audio = next((p for p in sorted(jd.iterdir())
                  if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".webm")),
                 None)
    script_f = jd / "script.txt"
    if not audio or not script_f.exists():
        print("Job klasöründe audio.* ve script.txt olmalı.", file=sys.stderr)
        sys.exit(2)

    opts = read_json(jd / "options.json", {}) or {}
    if args.mode:
        opts["mode"] = args.mode
    opts.setdefault("title", jd.name)

    mode = opts.get("mode", "real")
    provider = VisualProvider(
        cache_dir=Path("cache"),
        brave_key=os.environ.get("BRAVE_API_KEY", ""),
        pexels_key=os.environ.get("PEXELS_API_KEY", ""),
        mode=mode,
        language=opts.get("language") if opts.get("language") != "auto" else "",
        log=lambda m: print(m, flush=True),
    )

    out = Path(args.out) if args.out else Path("output") / f"{jd.name}.mp4"
    t0 = time.time()
    pipe = Pipeline(audio, script_f.read_text(encoding="utf-8"), opts,
                    workdir=jd / "work", out_path=out, provider=provider,
                    log=lambda m: print(m, flush=True))
    result = pipe.run()
    print(f"\n✅ {result} ({time.time()-t0:.0f} sn)")
    # sahne ara dosyalarını temizle (disk)
    scdir = jd / "work" / "scenes"
    if scdir.exists():
        for f in scdir.iterdir():
            f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
