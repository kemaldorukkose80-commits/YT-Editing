"""Görsel sağlama: Brave Image Search (fotoğraflar) + Pexels Video API (videolar).

- Sorgu başına havuz (pool) oluşturur, disk önbelleğinde saklar → aynı konu tekrar
  sorulduğunda API kotası harcanmaz.
- Test modu: API'siz, yerelde üretilen renkli kartlarla çalışır (pipeline denemesi).
- API erişilemezse render asla ölmez: önceki görseli tekrar kullanır / test kartı üretir.
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

import requests

from .utils import ensure_dir, probe, read_json, sha1, write_json

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

BRAVE_URL = "https://api.search.brave.com/res/v1/images/search"
PEXELS_URL = "https://api.pexels.com/videos/search"


class RateLimiter:
    def __init__(self, min_interval: float):
        self.min_interval = min_interval
        self.lock = threading.Lock()
        self.last = 0.0

    def wait(self):
        while True:
            with self.lock:
                now = time.time()
                if now - self.last >= self.min_interval:
                    self.last = now
                    return
                sleep = self.min_interval - (now - self.last)
            time.sleep(min(sleep, 1.5))


class VisualProvider:
    def __init__(self, cache_dir, brave_key="", pexels_key="", mode="real",
                 language="en", log=print):
        self.cache_dir = ensure_dir(Path(cache_dir))
        self.img_dir = ensure_dir(self.cache_dir / "images")
        self.vid_dir = ensure_dir(self.cache_dir / "videos")
        self.index_path = self.cache_dir / "index.json"
        self.index = read_json(self.index_path, {}) or {}
        self.brave_key = (brave_key or "").strip()
        self.pexels_key = (pexels_key or "").strip()
        self.mode = mode
        self.language = (language or "en")[:2]
        self.log = log
        self.brave_rl = RateLimiter(1.15)   # ücretsiz plan: 1 istek/sn
        self.pexels_rl = RateLimiter(0.35)
        self.stats = {"brave_queries": 0, "pexels_queries": 0, "downloads": 0,
                      "download_failures": 0, "api_errors": 0, "reused": 0}

        self.used_assets: set = set()
        self.last_good: dict = {"image": None, "video": None}

    # ------------------------------------------------------------------ önbellek
    def _save_index(self):
        write_json(self.index_path, self.index)

    def _norm_query(self, q: str) -> str:
        return " ".join((q or "").lower().split())

    # ------------------------------------------------------------------ Brave
    def _brave_search(self, query: str, count: int):
        self.brave_rl.wait()
        try:
            r = requests.get(
                BRAVE_URL,
                params={"q": query, "count": min(count, 50), "safesearch": "off",
                        "search_lang": self.language, "country": "all", "spellcheck": "false"},
                headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                         "X-Subscription-Token": self.brave_key},
                timeout=25,
            )
        except Exception as e:
            self.stats["api_errors"] += 1
            self.log(f"  [brave] ağ hatası: {e}")
            return []
        if r.status_code == 429:
            self.log("  [brave] 429 kota/limit — 3 sn beklenip tekrar denenecek")
            time.sleep(3.2)
            self.stats["api_errors"] += 1
            try:
                r = requests.get(
                    BRAVE_URL,
                    params={"q": query, "count": min(count, 50), "safesearch": "off",
                            "search_lang": self.language, "country": "all", "spellcheck": "false"},
                    headers={"Accept": "application/json", "Accept-Encoding": "gzip",
                             "X-Subscription-Token": self.brave_key},
                    timeout=25,
                )
            except Exception:
                return []
        if r.status_code != 200:
            self.stats["api_errors"] += 1
            self.log(f"  [brave] HTTP {r.status_code}: {r.text[:160]}")
            return []
        self.stats["brave_queries"] += 1
        try:
            return r.json().get("results", []) or []
        except Exception:
            return []

    def _download_image(self, url: str, dest: Path):
        try:
            with requests.get(url, headers={"User-Agent": UA}, timeout=30, stream=True) as r:
                if r.status_code != 200:
                    self.stats["download_failures"] += 1
                    return None
                ct = (r.headers.get("content-type") or "").lower()
                if ct and not ct.startswith("image/"):
                    self.stats["download_failures"] += 1
                    return None
                data = b""
                for chunk in r.iter_content(65536):
                    data += chunk
                    if len(data) > 25 * 1024 * 1024:
                        break
            if len(data) < 6_000:
                self.stats["download_failures"] += 1
                return None
            dest.write_bytes(data)
            info = probe(dest)
            if info["width"] < 500 or info["height"] < 320:
                dest.unlink(missing_ok=True)
                self.stats["download_failures"] += 1
                return None
            self.stats["downloads"] += 1
            return {"w": info["width"], "h": info["height"]}
        except Exception:
            self.stats["download_failures"] += 1
            return None

    def get_images(self, query: str, need: int = 3) -> list:
        """query → [{file, w, h}] (daha önce kullanılmayanlardan)."""
        if self.mode == "test":
            return [self._test_card(query)]
        key = "img:" + self._norm_query(query)
        pool = self.index.get(key)
        if not pool:
            results = self._brave_search(query, count=35)
            pool = []
            for item in results:
                props = item.get("properties") or {}
                url = props.get("url") or (item.get("thumbnail") or {}).get("src")
                if not url:
                    continue
                w = int(props.get("width") or 0)
                h = int(props.get("height") or 0)
                if w and h and (w < 700 or not (0.55 <= w / max(h, 1) <= 2.8)):
                    continue
                pool.append({"url": url, "w": w, "h": h})
            self.index[key] = pool
            self._save_index()
        else:
            self.stats["reused"] += 1
        fresh = []
        for cand in pool:
            if len(fresh) >= need:
                break
            fid = sha1(self._norm_query(query) + cand["url"])
            dest = self.img_dir / f"{fid}.img"
            mark = f"img:{fid}"
            if mark in self.used_assets:
                continue
            if not dest.exists():
                info = self._download_image(cand["url"], dest)
                if not info:
                    continue
                cand["w"], cand["h"] = info["w"], info["h"]
            self.used_assets.add(mark)
            fresh.append({"file": str(dest), "type": "image", "w": cand.get("w", 1920), "h": cand.get("h", 1080),
                          "source": cand["url"]})
        return fresh

    # ------------------------------------------------------------------ Pexels
    def _pexels_search(self, query: str, per_page: int):
        self.pexels_rl.wait()
        try:
            r = requests.get(PEXELS_URL,
                             params={"query": query, "per_page": min(per_page, 40),
                                     "orientation": "landscape", "size": "medium"},
                             headers={"Authorization": self.pexels_key}, timeout=25)
        except Exception as e:
            self.stats["api_errors"] += 1
            self.log(f"  [pexels] ağ hatası: {e}")
            return []
        if r.status_code != 200:
            self.stats["api_errors"] += 1
            self.log(f"  [pexels] HTTP {r.status_code}: {r.text[:160]}")
            return []
        self.stats["pexels_queries"] += 1
        try:
            return r.json().get("videos", []) or []
        except Exception:
            return []

    def _download_video(self, url: str, dest: Path):
        try:
            with requests.get(url, headers={"User-Agent": UA}, timeout=240, stream=True) as r:
                if r.status_code != 200:
                    self.stats["download_failures"] += 1
                    return None
                data = b""
                for chunk in r.iter_content(262144):
                    data += chunk
                    if len(data) > 180 * 1024 * 1024:
                        break
            if len(data) < 60_000:
                self.stats["download_failures"] += 1
                return None
            dest.write_bytes(data)
            info = probe(dest)
            if not info["duration"] or info["width"] < 600:
                dest.unlink(missing_ok=True)
                self.stats["download_failures"] += 1
                return None
            self.stats["downloads"] += 1
            return {"w": info["width"], "h": info["height"], "duration": info["duration"]}
        except Exception:
            self.stats["download_failures"] += 1
            return None

    def get_videos(self, query: str, need: int = 2) -> list:
        if self.mode == "test":
            return []  # test modunda video üretilmez; foto akar
        key = "vid:" + self._norm_query(query)
        pool = self.index.get(key)
        if not pool:
            vids = self._pexels_search(query, per_page=12)
            pool = []
            for v in vids:
                files = [f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4"]
                files.sort(key=lambda f: abs((f.get("width") or 0) - 1920))
                for f in files:
                    if 600 <= (f.get("width") or 0) <= 3840:
                        pool.append({"url": f["link"], "w": f.get("width"), "h": f.get("height"),
                                     "dur": v.get("duration", 10)})
                        break
            self.index[key] = pool
            self._save_index()
        else:
            self.stats["reused"] += 1
        fresh = []
        for cand in pool:
            if len(fresh) >= need:
                break
            fid = sha1("v" + cand["url"])
            dest = self.vid_dir / f"{fid}.mp4"
            mark = f"vid:{fid}"
            if mark in self.used_assets:
                continue
            if not dest.exists():
                info = self._download_video(cand["url"], dest)
                if not info:
                    continue
            self.used_assets.add(mark)
            fresh.append({"file": str(dest), "type": "video", "w": cand.get("w", 1920), "h": cand.get("h", 1080),
                          "source": cand["url"]})
        return fresh

    # ------------------------------------------------------------------ test kartı
    def _test_card(self, query: str) -> dict:
        from PIL import Image, ImageDraw
        prefix = "TEST GÖRSEL — " if self.mode == "test" else ""
        n = len(self.used_assets) % 360
        top = (40 + (n * 47) % 160, 90 + (n * 89) % 120, 160 + (n * 31) % 90)
        bot = (20 + (n * 13) % 90, 40 + (n * 53) % 80, 70 + (n * 71) % 120)
        img = Image.new("RGB", (1920, 1080))
        d = ImageDraw.Draw(img)
        for y in range(0, 1080, 4):
            t = y / 1080
            col = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            d.line([(0, y), (1920, y)], fill=col)
        label = (query or "görsel bulunamadı")[:38]
        overlay_band = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        bd = ImageDraw.Draw(overlay_band)
        bd.rectangle([60, 440, 1860, 640], fill=(0, 0, 0, 130))
        bd.text((100, 480), f"{prefix}{label}", fill=(255, 255, 255))
        img = Image.alpha_composite(img.convert("RGBA"), overlay_band).convert("RGB")
        fid = sha1("t" + self._norm_query(query) + str(n))
        dest = self.img_dir / f"test_{fid}.png"
        if not dest.exists():
            img.save(dest)
        self.used_assets.add(f"img:test{fid}")
        return {"file": str(dest), "type": "image", "w": 1920, "h": 1080, "source": "test-card"}

    # ------------------------------------------------------------------ genel
    def get_for_scene(self, scene, want_video: bool) -> dict:
        """Sahne için görsel seç. Öncelik: istenen tür → diğer tür → son iyi görsel → test kartı."""
        query = scene.get("query") or ""
        for want in ([True, False] if want_video else [False, True]):
            try:
                if want:
                    got = self.get_videos(query, need=1)
                else:
                    got = self.get_images(query, need=1)
            except Exception as e:
                self.log(f"  [gorsel] hata: {e}")
                got = []
            if got:
                self.last_good[want and "video" or "image"] = got[0]
                return got[0]
        if self.last_good.get("video" if want_video else "image"):
            self.stats["reused"] += 1
            return dict(self.last_good["video" if want_video else "image"])
        return self._test_card(query or "fallback")
