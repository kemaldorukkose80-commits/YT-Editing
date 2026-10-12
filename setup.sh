#!/usr/bin/env bash
# YT-Editing ortam kurulumu (Linux/macOS).
# Sandbox/temiz makinelerde: ffmpeg imageio-ffmpeg paketiyle, fontlar repoda gömülü gelir.
set -e
cd "$(dirname "$0")"

echo "[1/3] Python paketleri kuruluyor..."
if pip3 install --break-system-packages -q -r requirements.txt 2>/dev/null || pip3 install -q -r requirements.txt; then
  echo "  OK"
else
  echo "  PIP KURULUMU BAŞARISIZ" >&2
  exit 1
fi

echo "[2/3] ffmpeg kontrolü..."
FF="$(python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())' 2>/dev/null || true)"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "  Sistem ffmpeg bulundu: $(command -v ffmpeg)"
elif [ -n "$FF" ]; then
  mkdir -p bin
  ln -sf "$FF" bin/ffmpeg
  echo "  imageio ffmpeg bağlandı: bin/ffmpeg"
else
  echo "  ffmpeg bulunamadı!" >&2
  exit 1
fi

echo "[3/3] Hazır. Web arayüzünü başlatmak için:  python3 app.py"
