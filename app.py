#!/usr/bin/env python3
"""YT-Editing — Yüzükosman YouTube kanalları için otomatik video editörü (Web arayüzü).

Çalıştır: python3 app.py  →  http://0.0.0.0:8000
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from pipeline.job import DEFAULTS, Pipeline
from pipeline.utils import ensure_dir, fmt_ts, read_json, safe_slug, write_json
from pipeline.visuals import VisualProvider

ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = ROOT / "settings.json"
JOBS_DIR = ROOT / "jobs"
OUTPUT_DIR = ROOT / "output"

REPO_URL = ""  # çalışma anında git remote'tan okunur
app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB

DEFAULT_SETTINGS = {
    "brave_key": "",
    "pexels_key": "",
    "github_branch": "main",
    "workflow_file": "render-video.yml",
    "defaults": {
        "resolution": "1080p",
        "video_ratio": 0.25,
        "transition": 0.35,
        "overlay_max": 5,
        "language": "auto",
        "fps": 30,
    },
}

_lock = threading.Lock()
_job_queue: "queue.Queue[str]" = queue.Queue()
_worker_thread = None
_net_cache = {"ts": 0.0, "brave": None, "pexels": None}


# ---------------------------------------------------------------------------
# ayarlar
# ---------------------------------------------------------------------------
def load_settings() -> dict:
    s = read_json(SETTINGS_PATH, None)
    if not s:
        s = dict(DEFAULT_SETTINGS)
    for k, v in DEFAULT_SETTINGS.items():
        s.setdefault(k, v)
    return s


def save_settings(s: dict):
    write_json(SETTINGS_PATH, s)


# ---------------------------------------------------------------------------
# log / durum
# ---------------------------------------------------------------------------
def _log_file(job_id: str) -> Path:
    return JOBS_DIR / job_id / "log.txt"


def job_logger(job_id: str):
    f = _log_file(job_id)

    def log(msg: str):
        stamp = time.strftime("%H:%M:%S")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {msg}\n")
        print(f"[{job_id[:8]}] {msg}", flush=True)

    return log


def write_state(job_id: str, **kw):
    p = JOBS_DIR / job_id / "state.json"
    with _lock:
        st = read_json(p, {}) or {}
        st.update(kw)
        st["updated"] = time.time()
        write_json(p, st)


def read_state(job_id: str) -> dict:
    return read_json(JOBS_DIR / job_id / "state.json", {}) or {}


# ---------------------------------------------------------------------------
# yerel render işçisi
# ---------------------------------------------------------------------------
def _worker_loop():
    while True:
        job_id = _job_queue.get()
        try:
            _run_local_job(job_id)
        except Exception as e:
            write_state(job_id, status="error", error=str(e), stage="hata", pct=100)
            with open(_log_file(job_id), "a", encoding="utf-8") as f:
                f.write(f"[HATA] {e}\n")


def _run_local_job(job_id: str):
    meta = read_json(JOBS_DIR / job_id / "meta.json", {}) or {}
    log = job_logger(job_id)
    write_state(job_id, status="running", stage="analiz", pct=1, detail="Başlıyor")

    def progress(stage, pct, detail=""):
        write_state(job_id, stage=stage, pct=pct, detail=detail)

    settings = load_settings()
    mode = meta.get("mode", "test")
    if mode == "test":
        mode = "test"
    provider = VisualProvider(
        cache_dir=ROOT / "cache",
        brave_key=settings.get("brave_key", ""),
        pexels_key=settings.get("pexels_key", ""),
        mode=mode,
        language=meta.get("language") if meta.get("language") != "auto" else "",
        log=log,
    )
    cancel_flag = {"v": False}
    _CANCEL_FLAGS[job_id] = cancel_flag

    pipe = Pipeline(
        meta["audio"], meta.get("script", ""), meta.get("options", {}),
        workdir=JOBS_DIR / job_id / "work",
        out_path=OUTPUT_DIR / f"{job_id}.mp4",
        provider=provider, log=log, progress=progress,
        cancel=lambda: cancel_flag["v"],
    )
    t0 = time.time()
    out = pipe.run()
    try:
        (JOBS_DIR / job_id / "report.md").write_text(
            (JOBS_DIR / job_id / "work" / "report.md").read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass
    write_state(job_id, status="done", stage="bitti", pct=100,
                detail=f"{fmt_ts(time.time()-t0)} sürdü", output=f"/download/{job_id}")
    log(f"Çıktı: {out}")


_CANCEL_FLAGS: dict = {}


# ---------------------------------------------------------------------------
# GitHub Actions entegrasyonu
# ---------------------------------------------------------------------------
def _gh(*args, timeout=60):
    p = subprocess.run(["gh", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "").strip()


def _repo_slug() -> str:
    rc, out = _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    return out if rc == 0 else ""


def _run_actions_job(job_id: str):
    """Job dosyalarını repoya işle + workflow tetikle."""
    meta = read_json(JOBS_DIR / job_id / "meta.json", {}) or {}
    settings = load_settings()
    branch = settings.get("github_branch") or "main"
    wf = settings.get("workflow_file") or "render-video.yml"
    slug = meta.get("slug") or job_id
    log = job_logger(job_id)
    write_state(job_id, status="queued", stage="github", pct=5, detail="Repoya yükleniyor")

    tmp = ROOT / f".tmp_gh_{job_id}"
    rc, out = _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    if rc != 0:
        raise RuntimeError(f"GitHub bağlantısı yok: {out}")
    repo = out
    local_push = os.environ.get("GIT_PUSH_BRANCH", branch)  # testte mevcut dal kullanılabilir

    import shutil
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    rc, out = _gh("repo", "clone", repo, str(tmp), "--", "--depth", "1", "--branch", local_push, timeout=300)
    if rc != 0:
        # dal yoksa varsayılan daldan al
        rc, out = _gh("repo", "clone", repo, str(tmp), "--", "--depth", "1", timeout=300)
        if rc != 0:
            raise RuntimeError(f"Repo klonlanamadı: {out}")

    dest = tmp / "jobs" / slug
    dest.mkdir(parents=True, exist_ok=True)
    import shutil as sh
    for name in ("audio", "script.txt", "options.json"):
        src = JOBS_DIR / job_id / name if name != "audio" else Path(meta["audio"])
        if name == "audio":
            sh.copy(src, dest / ("audio" + Path(src).suffix.lower()))
        else:
            sh.copy(src, dest / name)
    # ses dosyası .gitignore'ludur → -f ile ekle
    for f in dest.iterdir():
        subprocess.run(["git", "add", "-f", str(f.relative_to(tmp))], cwd=tmp, check=True)
    subprocess.run(["git", "-c", "user.name=YT-Editing", "-c", "user.email=yt-editing@arena",
                    "commit", "-m", f"render job: {slug}"], cwd=tmp, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    push = subprocess.run(["git", "push", "origin", f"HEAD:{local_push}"], cwd=tmp,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
    if push.returncode != 0:
        raise RuntimeError(f"Push başarısız: {push.stdout[-300:]}")
    shutil.rmtree(tmp, ignore_errors=True)

    write_state(job_id, stage="github", pct=10, detail="Workflow tetikleniyor")
    rc, out = _gh("workflow", "run", wf, "--ref", local_push, "-f", f"job={slug}", timeout=120)
    if rc != 0:
        raise RuntimeError(f"Workflow tetiklenemedi (workflow repoda aktif mi?): {out}")

    # run id yakala
    run_id = None
    for _ in range(10):
        time.sleep(3)
        rc, out = _gh("run", "list", "--workflow", wf, "--json", "databaseId,createdAt,status",
                      "-L", "5")
        if rc == 0:
            try:
                runs = json.loads(out)
                if runs:
                    run_id = runs[0]["databaseId"]
                    break
            except Exception:
                pass
    write_state(job_id, status="running", stage="github", pct=15,
                detail=f"GitHub Actions çalışıyor (run {run_id})", run_id=run_id,
                run_url=f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else "")
    log(f"Actions run: {run_id}")


def _poll_actions_job(job_id: str):
    state = read_state(job_id)
    run_id = state.get("run_id")
    if not run_id:
        return
    rc, out = _gh("run", "view", str(run_id), "--json", "status,conclusion")
    if rc != 0:
        return
    try:
        info = json.loads(out)
    except Exception:
        return
    if info.get("status") == "completed":
        concl = info.get("conclusion")
        if concl == "success":
            write_state(job_id, status="done", stage="bitti", pct=100,
                        detail="GitHub Release hazır", output=state.get("release_url", state.get("run_url", "")))
        else:
            write_state(job_id, status="error", stage="hata", pct=100,
                        error=f"Actions {concl}", run_url=state.get("run_url", ""))


# ---------------------------------------------------------------------------
# ağ erişim kontrolü (sandbox'ta API'ler kapalı olabilir)
# ---------------------------------------------------------------------------
def _check_net():
    import requests
    now = time.time()
    if now - _net_cache["ts"] < 600:
        return {"brave": _net_cache["brave"], "pexels": _net_cache["pexels"]}
    res = {}
    for name, url in (("brave", "https://api.search.brave.com"), ("pexels", "https://api.pexels.com")):
        try:
            requests.head(url, timeout=4)
            res[name] = True
        except Exception:
            res[name] = False
    _net_cache.update({"ts": now, **res})
    return res


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(ROOT / "web", "index.html")


@app.get("/web/<path:p>")
def web_static(p):
    return send_from_directory(ROOT / "web", p)


@app.get("/api/status")
def api_status():
    s = load_settings()
    import shutil
    rc, _ = _gh("auth", "status", timeout=20)
    net = _check_net()
    return jsonify({
        "ffmpeg": bool(__import__("shutil").which("ffmpeg") or os.environ.get("FFMPEG_BIN")),
        "brave_key": bool(s.get("brave_key")),
        "pexels_key": bool(s.get("pexels_key")),
        "github_auth": rc == 0,
        "repo": _repo_slug() or None,
        "net": net,
        "outputs": sorted([f.name for f in OUTPUT_DIR.glob("*.mp4")], reverse=True)[:20] if OUTPUT_DIR.exists() else [],
    })


@app.get("/api/settings")
def api_get_settings():
    s = load_settings()
    masked = dict(s)
    masked["brave_key"] = ("•••" + s["brave_key"][-4:]) if s.get("brave_key") else ""
    masked["pexels_key"] = ("•••" + s["pexels_key"][-4:]) if s.get("pexels_key") else ""
    return jsonify(masked)


@app.post("/api/settings")
def api_set_settings():
    s = load_settings()
    d = request.get_json(force=True) or {}
    for k in ("brave_key", "pexels_key", "github_branch", "workflow_file"):
        if k in d and d[k] is not None and not str(d[k]).startswith("•••"):
            s[k] = str(d[k]).strip()
    if "defaults" in d and isinstance(d["defaults"], dict):
        s["defaults"].update({k: v for k, v in d["defaults"].items() if k in DEFAULT_SETTINGS["defaults"]})
    save_settings(s)
    return jsonify({"ok": True})


@app.post("/api/jobs")
def api_create_job():
    mode = request.form.get("mode", "actions")
    if mode not in ("actions", "test"):
        mode = "actions"
    title = (request.form.get("title") or "").strip() or "video"
    script = (request.form.get("script") or "").strip()
    if not script and request.files.get("script_file"):
        script = request.files["script_file"].read().decode("utf-8", "replace").strip()
    if not script:
        return jsonify({"error": "Video metni (script) boş olamaz."}), 400
    audio = request.files.get("audio")
    if not audio or not audio.filename:
        return jsonify({"error": "Ses dosyası yüklenmedi."}), 400

    opts = dict(load_settings().get("defaults", {}))
    if request.form.get("options"):
        try:
            opts.update(json.loads(request.form["options"]))
        except Exception:
            pass
    manual = (request.form.get("overlay_manual") or "").strip()
    if manual:
        opts["overlay_manual"] = [ln.strip() for ln in manual.splitlines() if ln.strip()]
    opts["mode"] = "test" if mode == "test" else "real"
    if opts.get("language") in (None, "", "auto"):
        opts["language"] = "auto"

    job_id = f"{safe_slug(title)}-{time.strftime('%m%d-%H%M%S')}"
    jd = ensure_dir(JOBS_DIR / job_id)
    audio_path = jd / ("audio" + Path(audio.filename).suffix.lower())
    audio.save(audio_path)
    (jd / "script.txt").write_text(script, encoding="utf-8")
    opts["title"] = title
    write_json(jd / "options.json", {k: v for k, v in opts.items() if k != "overlay_manual"})
    write_json(jd / "meta.json", {
        "id": job_id, "slug": job_id, "title": title, "mode": mode,
        "audio": str(audio_path), "script": script, "options": opts,
        "language": opts.get("language", "auto"),
        "created": time.time(),
    })
    write_state(job_id, status="queued", stage="kuyruk", pct=0,
                detail="GitHub Actions ile üretilir" if mode == "actions" else "Yerel test üretimi")
    write_json(JOBS_DIR / "index.json", {"ids": sorted(
        [p.name for p in JOBS_DIR.iterdir() if p.is_dir() and (p / "meta.json").exists()], reverse=True)[:200]})

    if mode == "actions":
        threading.Thread(target=_safe_actions, args=(job_id,), daemon=True).start()
    else:
        _job_queue.put(job_id)
    return jsonify({"ok": True, "id": job_id})


def _safe_actions(job_id):
    try:
        _run_actions_job(job_id)
    except Exception as e:
        write_state(job_id, status="error", stage="hata", pct=100, error=str(e))
        with open(_log_file(job_id), "a", encoding="utf-8") as f:
            f.write(f"[HATA] {e}\n")


@app.get("/api/jobs")
def api_jobs():
    jobs = []
    if JOBS_DIR.exists():
        for jd in sorted(JOBS_DIR.iterdir(), key=lambda p: p.name, reverse=True):
            meta_f = jd / "meta.json"
            if not meta_f.exists():
                continue
            meta = read_json(meta_f, {}) or {}
            st = read_state(jd.name)
            log = ""
            lf = _log_file(jd.name)
            if lf.exists():
                log = lf.read_text(encoding="utf-8", errors="replace")[-6000:]
            jobs.append({"id": jd.name, "title": meta.get("title"), "mode": meta.get("mode"),
                         "created": meta.get("created"), "state": st, "log": log})
    return jsonify(jobs)


@app.get("/api/job/<job_id>")
def api_job(job_id):
    meta = read_json(JOBS_DIR / job_id / "meta.json", {}) or {}
    st = read_state(job_id)
    if meta.get("mode") == "actions" and st.get("status") == "running":
        _poll_actions_job(job_id)
        st = read_state(job_id)
        # release ara
        if st.get("status") == "done" and not st.get("release_url"):
            pass
    log = ""
    lf = _log_file(job_id)
    if lf.exists():
        log = lf.read_text(encoding="utf-8", errors="replace")[-6000:]
    return jsonify({"id": job_id, "meta": meta, "state": st, "log": log})


@app.post("/api/job/<job_id>/cancel")
def api_cancel(job_id):
    fl = _CANCEL_FLAGS.get(job_id)
    if fl:
        fl["v"] = True
    write_state(job_id, status="canceled", detail="İptal edildi")
    return jsonify({"ok": True})


@app.delete("/api/job/<job_id>")
def api_delete(job_id):
    import shutil
    shutil.rmtree(JOBS_DIR / job_id, ignore_errors=True)
    (OUTPUT_DIR / f"{job_id}.mp4").unlink(missing_ok=True)
    return jsonify({"ok": True})


@app.get("/download/<job_id>")
def api_download(job_id):
    f = OUTPUT_DIR / f"{job_id}.mp4"
    if not f.exists():
        return jsonify({"error": "Dosya yok"}), 404
    return send_file(f, as_attachment=True, download_name=f"{job_id}.mp4")


@app.get("/media/<job_id>")
def api_media(job_id):
    f = OUTPUT_DIR / f"{job_id}.mp4"
    if not f.exists():
        return jsonify({"error": "Dosya yok"}), 404
    return send_file(f, as_attachment=False, mimetype="video/mp4", conditional=True)


# ---------------------------------------------------------------------------
def _start_worker():
    global _worker_thread
    if _worker_thread is None:
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()


if __name__ == "__main__":
    ensure_dir(JOBS_DIR)
    ensure_dir(OUTPUT_DIR)
    _start_worker()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), threaded=True, debug=False)
