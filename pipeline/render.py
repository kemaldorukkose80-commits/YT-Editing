"""ffmpeg sahne render: Ken Burns (foto), geçiş fade'leri, overlay PNG, concat + ses miks."""

from __future__ import annotations

import math
from pathlib import Path

from .utils import ffbin, probe

# Ken Burns varyantları: (zoom-ifade parçaları). p = on/N ilerleme (0..1)
def _kb_expr(variant: int, n_frames: int):
    N = max(n_frames, 2)
    p = f"(on/{N})"
    if variant % 6 == 0:    # içine zoom
        z = f"1+0.13*{p}"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif variant % 6 == 1:  # dışarı zoom
        z = f"1.13-0.13*{p}"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif variant % 6 == 2:  # sola→sağa kay + hafif zoom
        z = f"1.08+0.06*{p}"
        x, y = f"(iw-iw/zoom)*{p}", "ih/2-(ih/zoom/2)"
    elif variant % 6 == 3:  # sağa→sola kay + hafif zoom
        z = f"1.08+0.06*{p}"
        x, y = f"(iw-iw/zoom)*(1-{p})", "ih/2-(ih/zoom/2)"
    elif variant % 6 == 4:  # yukarıdan aşağıya
        z = "1.10"
        x, y = "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*{p}"
    else:                    # aşağıdan yukarıya
        z = "1.10"
        x, y = "iw/2-(iw/zoom/2)", f"(ih-ih/zoom)*(1-{p})"
    return z, x, y


def scene_filter(spec: dict, W: int, H: int, fps: int):
    """Sahne filtre grafiği üret → (filter_complex, map_label)"""
    dur = spec["duration"]
    frames = max(int(round(dur * fps)), 3)
    fd = min(spec.get("transition", 0.35), dur / 3)
    parts = []
    if spec["type"] == "image":
        SW, SH = W * 2, H * 2  # süperörnekleme → zoompan titremesini azaltır
        z, x, y = _kb_expr(spec.get("kb_variant", 0), frames)
        parts.append(
            f"[0:v]scale={SW}:{SH}:force_original_aspect_ratio=increase,"
            f"crop={SW}:{SH},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={fps}"
        )
    else:
        parts.append(
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},fps={fps}"
        )
    parts[-1] += f",setsar=1,fade=t=in:st=0:d={fd:.3f},fade=t=out:st={max(dur - fd, 0):.3f}:d={fd:.3f}[base]"

    ov = spec.get("overlay")
    inputs_extra = 0
    if ov:
        ts, te = ov["start_in_scene"], ov["start_in_scene"] + ov["duration"]
        te = min(te, dur - 0.05)
        parts.append(
            f"[1:v]format=rgba,fade=t=in:st={ts:.3f}:d=0.30:alpha=1,"
            f"fade=t=out:st={max(te - 0.30, 0):.3f}:d=0.30:alpha=1[ov]"
        )
        parts.append(f"[base][ov]overlay=x=(W-w)/2:y=H*0.66:format=auto[vout]")
        inputs_extra = 1
    else:
        parts.append("[base]null[vout]")
    fc = ";".join(parts)
    return fc, inputs_extra


def render_scene(spec: dict, out_path: Path, W=1920, H=1080, fps=30,
                 preset="veryfast", crf=20, log=None, threads=1) -> bool:
    cmd = [ffbin(), "-y", "-hide_banner", "-loglevel", "error"]
    if spec["type"] == "image":
        cmd += ["-i", spec["file"]]
    else:
        cmd += ["-stream_loop", "-1", "-t", f"{spec['duration']:.3f}", "-i", spec["file"]]
    if spec.get("overlay"):
        cmd += ["-loop", "1", "-t", f"{spec['duration']:.3f}", "-i", spec["overlay"]["png"]]
    fc, _ = scene_filter(spec, W, H, fps)
    cmd += ["-filter_complex", fc, "-map", "[vout]", "-an",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps),
            "-video_track_timescale", "15360",
            "-threads", str(threads), "-t", f"{spec['duration']:.3f}",
            str(out_path)]
    import subprocess
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", timeout=900)
    if p.returncode != 0:
        if log:
            log(f"  [sahne {spec['index']}] hata: {p.stdout[-500:]}")
        return False
    info = probe(out_path)
    return bool(info["duration"] and info["duration"] > 0.1)


def concat_scenes(scene_paths, out_path: Path, log=None) -> bool:
    import subprocess
    list_file = out_path.with_suffix(".txt")
    # concat demuxer girdileri liste dosyasının konumuna göre çözer → mutlak yol şart
    list_file.write_text("\n".join(f"file '{Path(p).resolve().as_posix()}'" for p in scene_paths), encoding="utf-8")
    cmd = [ffbin(), "-y", "-hide_banner", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out_path)]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if p.returncode != 0 and log:
        log(f"[concat] hata: {p.stdout[-500:]}")
    return p.returncode == 0


def normalize_audio(audio_in: Path, out_path: Path, log=None) -> bool:
    """Tek geçiş loudnorm (konuşma için -16 LUFS), 48k stereo."""
    import subprocess
    cmd = [ffbin(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(audio_in),
           "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "48000", "-ac", "2",
           "-c:a", "pcm_s16le", str(out_path)]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if p.returncode != 0 and log:
        log(f"[audio] normalleştirme hatası: {p.stdout[-500:]}")
    return p.returncode == 0


def mux_final(video: Path, audio: Path, out_path: Path, log=None) -> bool:
    import subprocess
    cmd = [ffbin(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", str(video), "-i", str(audio),
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
           "-shortest", "-movflags", "+faststart", str(out_path)]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    if p.returncode != 0 and log:
        log(f"[mux] hata: {p.stdout[-500:]}")
    return p.returncode == 0
