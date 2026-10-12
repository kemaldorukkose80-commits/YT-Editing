#!/usr/bin/env python3
"""Test amaçlı sentetik konuşma sesi üretir: her cümle için ton + sessizlik.
pipeline'ın hizalama mantığını gerçekçi sessizliklerle doğrulamak için."""
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.textproc import split_sentences

SR = 16000


def main(script_path: str, out_wav: str, chars_per_sec: float = 15.0, pause: float = 0.45):
    sentences = split_sentences(Path(script_path).read_text(encoding="utf-8"))
    frames = []
    for i, s in enumerate(sentences):
        dur = max(len(s) / chars_per_sec, 1.2)
        n = int(SR * dur)
        f = 190 + (i % 5) * 22
        for k in range(n):
            t = k / SR
            env = min(1.0, t / 0.05, (dur - t) / 0.05)
            v = 0.42 * env * math.sin(2 * math.pi * f * t) * (1 + 0.22 * math.sin(2 * math.pi * 5.3 * t))
            frames.append(int(v * 32000))
        frames.extend([0] * int(SR * pause))
    out = Path(out_wav)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack("<" + "h" * len(frames), *frames))
    print(f"{out} yazıldı: {len(frames)/SR:.1f} sn, {len(sentences)} cümle")


if __name__ == "__main__":
    main(*sys.argv[1:4])
