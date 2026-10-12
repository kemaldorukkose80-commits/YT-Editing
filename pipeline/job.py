"""İş akışı: ses + metin → analiz → zamanlama → sahneler → görseller → render → final MP4."""
from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from . import render, textproc, timings
from .overlays import render_text_png
from .utils import ensure_dir, fmt_ts, probe, read_json, safe_slug, sha1, write_json
from .visuals import VisualProvider

DEFAULTS = {
    "resolution": "1080p",          # 1080p | 720p
    "fps": 30,
    "transition": 0.35,             # saniye — geçiş (fade) süresi
    "scene_min": 3.2,
    "scene_target_hi": 4.8,
    "scene_max": 8.5,
    "video_ratio": 0.25,            # sahnelerin ~%25'i video
    "overlay_max": 5,               # videoda en fazla bu kadar yazı efekti
    "overlay_min_gap": 40.0,        # iki yazı arasında min saniye
    "hook_seconds": 90.0,
    "language": "auto",
    "preset": "veryfast",
    "crf": 20,
    "workers": 0,                   # 0 = otomatik (cpu-1)
    "mode": "real",                 # real | test
    "title": "",
    "overlay_manual": [],           # [dosya| {"time": saniye, "text": ...}] elle yazı efektleri
}


class Pipeline:
    def __init__(self, audio_path, script_text, options=None, workdir=None, out_path=None,
                 provider: VisualProvider = None, log=print, progress=None, cancel=None):
        self.audio = Path(audio_path)
        self.script = script_text or ""
        self.opts = dict(DEFAULTS)
        if options:
            for k, v in options.items():
                if k in self.opts and v is not None:
                    self.opts[k] = v
        self.slug = safe_slug(self.opts.get("title") or Path(audio_path).stem)
        self.work = ensure_dir(Path(workdir) if workdir else Path("jobs") / self.slug / "work")
        self.scenes_dir = ensure_dir(self.work / "scenes")
        self.ov_dir = ensure_dir(self.work / "overlays")
        self.out_path = Path(out_path) if out_path else Path("output") / f"{self.slug}.mp4"
        self.provider = provider
        self.log = log
        self.progress = progress or (lambda stage, pct, detail="": None)
        self.cancel = cancel or (lambda: False)

    # ------------------------------------------------------------------ yardımcı
    def _check_cancel(self):
        if self.cancel():
            raise RuntimeError("İş iptal edildi")

    # ------------------------------------------------------------------ manuel overlay
    @staticmethod
    def _parse_manual_overlays(lines):
        out = []
        for raw in (lines or []):
            if isinstance(raw, dict):
                t, txt = raw.get("time"), raw.get("text")
            else:
                if "|" not in str(raw):
                    continue
                t, txt = str(raw).split("|", 1)
            t = str(t).strip()
            parts = t.split(":")
            try:
                secs = sum(int(p) * 60 ** i for i, p in enumerate(reversed(parts)))
            except Exception:
                continue
            txt = str(txt).strip()
            if txt:
                out.append({"time": float(secs), "text": txt})
        return sorted(out, key=lambda o: o["time"])

    # ------------------------------------------------------------------ ana akış
    def run(self) -> Path:
        opts = self.opts
        W, H = (1920, 1080) if opts["resolution"] == "1080p" else (1280, 720)
        fps = int(opts["fps"])

        # 1) Ses süresi
        self.progress("analiz", 2, "Ses dosyası okunuyor")
        info = probe(self.audio)
        audio_dur = info.get("duration") or 0
        if not audio_dur or audio_dur < 3:
            raise RuntimeError("Ses dosyası okunamadı veya çok kısa.")
        self.log(f"Ses süresi: {fmt_ts(audio_dur)}")

        # 2) Dil + cümleler
        lang = opts["language"] if opts["language"] and opts["language"] != "auto" else textproc.detect_language(self.script)
        self.log(f"Dil: {lang}")
        sentences = textproc.split_sentences(self.script)
        if not sentences:
            raise RuntimeError("Metinden cümle ayrıştırılamadı.")
        self.log(f"Cümle sayısı: {len(sentences)}")

        # 3) Zamanlama (oransal + sessizliğe kenetleme)
        self.progress("analiz", 8, "Ses–metin hizalama (sessizlik analizi)")
        t0 = time.time()
        silences = timings.detect_silences(str(self.audio))
        self.log(f"Sessizlik sayısı: {len(silences)} ({time.time()-t0:.1f} sn)")
        timed = timings.assign_timings(sentences, audio_dur, silences)

        # 4) Sahneler
        scenes = timings.group_scenes(timed, opts["scene_min"], opts["scene_target_hi"], opts["scene_max"])
        self.log(f"Sahne sayısı: {len(scenes)} (ortalama {audio_dur/len(scenes):.1f} sn)")
        self.progress("planlama", 15, f"{len(scenes)} sahne planlandı")

        # 5) Anahtar kelimeler
        doc_freq = {}
        for sc in scenes:
            seen = set()
            for w in textproc.tokenize(sc["text"].lower()):
                base = textproc._strip_suffix(w)
                if base not in seen:
                    seen.add(base)
                    doc_freq[base] = doc_freq.get(base, 0) + 1
        for sc in scenes:
            kws = textproc.keywords_for(sc["text"], lang, doc_freq, len(scenes))
            sc["keywords"] = kws
            sc["query"] = " ".join(kws[:2]) if kws else ""
            sc["lang"] = lang

        # boş kalan sorguları komşudan doldur
        for i, sc in enumerate(scenes):
            if not sc["query"]:
                for j in range(i - 1, -1, -1):
                    if scenes[j]["query"]:
                        sc["query"] = scenes[j]["query"]
                        break
                else:
                    for j in range(i + 1, len(scenes)):
                        if scenes[j]["query"]:
                            sc["query"] = scenes[j]["query"]
                            break
            if not sc["query"]:
                sc["query"] = "cinematic landscape"

        # 6) Varlıklar → overlay seçimi
        for sc in scenes:
            sc["entities"] = textproc.detect_entities(sc["text"], lang)
        manual = self._parse_manual_overlays(opts.get("overlay_manual") or [])
        if manual:
            overlays = []
            for mo in manual:
                idx = next((sc["index"] for sc in scenes if sc["start"] <= mo["time"] < sc["end"]), None)
                if idx is None and mo["time"] >= audio_dur - 1:
                    idx = scenes[-1]["index"]
                if idx is None:
                    continue
                sc = scenes[idx]
                overlays.append({"text": mo["text"][:60], "kind": "manual", "time": mo["time"], "scene_idx": idx})
        else:
            overlays = textproc.select_overlays(scenes, audio_dur, opts["overlay_max"], opts["overlay_min_gap"], opts["hook_seconds"])
        self.log(f"Yazı efekti (overlay) sayısı: {len(overlays)}")

        # overlay PNG'leri
        for ov in overlays:
            png = self.ov_dir / f"ov_{ov['scene_idx']}_{sha1(ov['text'])}.png"
            render_text_png(ov["text"], png)
            ov["png"] = str(png)

        # 7) Video sahnelere karar
        ratio = max(0.0, min(0.8, float(opts["video_ratio"])))
        step = max(int(round(1 / ratio)), 2) if ratio > 0 else 10 ** 9
        video_indices = set(range(3, len(scenes), step)) if ratio > 0 else set()

        # 8) Görselleri çek
        self.progress("gorseller", 20, "Görseller aranıyor/indiriliyor")
        provider = self.provider
        t0 = time.time()
        for k, sc in enumerate(scenes):
            self._check_cancel()
            want_video = sc["index"] in video_indices
            asset = provider.get_for_scene(sc, want_video)
            sc["asset"] = asset
            if k % 5 == 0 or k == len(scenes) - 1:
                pct = 20 + int(20 * (k + 1) / len(scenes))
                self.progress("gorseller", pct, f"Görsel {k+1}/{len(scenes)} — {sc['query'][:30]}")
        self.log(f"Görseller {time.time()-t0:.0f} sn'de hazır — istatistik: {provider.stats}")

        # 9) Ses normalleştirme
        self.progress("render", 42, "Ses normalize ediliyor")
        norm_audio = self.work / "audio_norm.wav"
        if not render.normalize_audio(self.audio, norm_audio, self.log):
            norm_audio = self.audio  # başarısızsa orijinal

        # 10) Render spec'leri + paralel sahne render
        specs = []
        for sc in scenes:
            ov = next((o for o in overlays if o["scene_idx"] == sc["index"]), None)
            spec = {
                "index": sc["index"],
                "type": sc["asset"]["type"],
                "file": sc["asset"]["file"],
                "duration": sc["duration"],
                "kb_variant": sc["index"],
                "transition": float(opts["transition"]),
            }
            if ov and ov.get("png"):
                spec["overlay"] = {"png": ov["png"],
                                   "start_in_scene": max(ov["time"] - sc["start"], 0.05),
                                   "duration": 3.6}
            specs.append(spec)

        workers = int(opts["workers"]) or max(1, (__import__("os").cpu_count() or 2) - 1)
        self.log(f"Sahne render başlıyor: {len(specs)} sahne, {workers} paralel işçi")
        done = 0
        fail = []
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {}
            for sp in specs:
                self._check_cancel()
                out_f = self.scenes_dir / f"scene_{sp['index']:05d}.mp4"
                sp["out"] = str(out_f)
                # devam: geçerli dosya varsa atla
                if out_f.exists():
                    pinf = probe(out_f)
                    if pinf["duration"] and abs(pinf["duration"] - sp["duration"]) < 0.35:
                        done += 1
                        continue
                futs[ex.submit(render.render_scene, sp, out_f, W, H, fps,
                               opts["preset"], opts["crf"], self.log, 1)] = sp
            for fut in as_completed(futs):
                self._check_cancel()
                sp = futs[fut]
                ok = False
                try:
                    ok = fut.result()
                except Exception as e:
                    self.log(f"  [sahne {sp['index']}] istisna: {e}")
                if not ok:
                    fail.append(sp)
                done += 1
                self.progress("render", 45 + int(45 * done / max(len(specs), 1)),
                              f"Sahne render {done}/{len(specs)}")

        # başarısız sahneleri bir kez daha dene (basitleştirilmiş ayarla)
        for sp in fail:
            self._check_cancel()
            sp2 = dict(sp)
            sp2["transition"] = 0.0
            if sp2.get("overlay"):
                sp2["overlay"]["start_in_scene"] = 0.0
            ok = render.render_scene(sp2, Path(sp2["out"]), W, H, fps, "ultrafast", 23, self.log, 1)
            if not ok:
                raise RuntimeError(f"Sahne {sp['index']} render edilemedi: {sp['file']}")

        # 11) Birleştir + ses ekle
        self.progress("final", 92, "Sahneler birleştiriliyor")
        concat_tmp = self.work / "concat.mp4"
        ordered = [Path(sp["out"]) for sp in sorted(specs, key=lambda s: s["index"])]
        if not render.concat_scenes([str(p) for p in ordered], concat_tmp, self.log):
            raise RuntimeError("Sahneler birleştirilemedi.")
        self.progress("final", 96, "Ses ekleniyor")
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        if not render.mux_final(concat_tmp, norm_audio, self.out_path, self.log):
            raise RuntimeError("Final video yazılamadı.")

        # 12) Rapor
        vinfo = probe(self.out_path)
        self._write_report(scenes, overlays, provider.stats, vinfo)
        self.progress("final", 100, f"Hazır: {self.out_path}")
        self.log(f"BİTTİ: {self.out_path} ({fmt_ts(vinfo.get('duration') or 0)})")
        # ara dosyaları temizle (disk)
        try:
            concat_tmp.unlink(missing_ok=True)
            for f in self.scenes_dir.iterdir():
                f.unlink(missing_ok=True)
            self.scenes_dir.rmdir()
        except Exception:
            pass
        return self.out_path

    # ------------------------------------------------------------------ rapor
    def _write_report(self, scenes, overlays, stats, vinfo):
        rp = {"title": self.opts.get("title") or self.slug,
              "output": str(self.out_path),
              "duration": vinfo.get("duration"),
              "resolution": vinfo.get("width") and f"{vinfo['width']}x{vinfo['height']}",
              "scene_count": len(scenes),
              "overlay_count": len(overlays),
              "visual_stats": stats,
              "scenes": [{"index": sc["index"], "start": sc["start"], "end": sc["end"],
                          "type": sc["asset"]["type"], "query": sc["query"],
                          "source": sc["asset"].get("source", ""),
                          "overlay": next((o["text"] for o in overlays if o["scene_idx"] == sc["index"]), None)}
                         for sc in scenes]}
        write_json(self.work / "report.json", rp)
        md = [f"# {rp['title']}", "",
              f"- Süre: {fmt_ts(rp['duration'] or 0)}  |  Sahne: {rp['scene_count']}  |  Yazı efekti: {rp['overlay_count']}",
              f"- Görsel istatistik: {stats}", ""]
        for o in sorted(overlays, key=lambda x: x["time"]):
            md.append(f"- Yazı efekti @ {fmt_ts(o['time'])} → **{o['text']}**")
        md += ["", "| # | Zaman | Tür | Sorgu | Kaynak |", "|---|-------|-----|-------|--------|"]
        for sc in scenes:
            md.append(f"| {sc['index']+1} | {fmt_ts(sc['start'])}-{fmt_ts(sc['end'])} | "
                      f"{sc['asset']['type']} | {sc['query'][:32]} | {sc['asset'].get('source','')[:60]} |")
        (self.work / "report.md").write_text("\n".join(md), encoding="utf-8")
