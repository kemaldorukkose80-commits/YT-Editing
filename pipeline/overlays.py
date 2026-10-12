"""Overlay yazı PNG'leri: temiz, sade; yumuşak gölge + beyaz yazı, alt üçte birde görünür."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .fonts import font_for_text

MAX_W = 1600          # 1920 genişlik içinde kullanılabilir alan
MAX_FONT = 92
MIN_FONT = 42
PAD = 28


def _shape_arabic(text: str) -> str:
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def render_text_png(text: str, out_path, base_h: int = 1080) -> int:
    """Yazıyı PNG'ye bas (şeffaf zemin). Dönen değer: PNG piksel yüksekliği."""
    text = text.strip()
    font_path, shaping = font_for_text(text)
    if shaping:
        text = _shape_arabic(text)

    def load(sz):
        if font_path:
            return ImageFont.truetype(font_path, sz)
        return ImageFont.load_default()

    size = MAX_FONT
    while size > MIN_FONT:
        font = load(size)
        try:
            w = font.getlength(text)
        except Exception:
            w = font.getbbox(text)[2]
        if w <= MAX_W:
            break
        size -= 4
    font = load(size)
    try:
        text_w = int(font.getlength(text))
        asc, desc = font.getmetrics()
        text_h = asc + desc
    except Exception:
        bb = font.getbbox(text)
        text_w, text_h = bb[2] - bb[0], bb[3] - bb[1]

    W = min(MAX_W, text_w + PAD * 2)
    H = text_h + PAD * 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # yumuşak gölge
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((PAD + 3, PAD + 5), text, font=font, fill=(0, 0, 0, 235))
    shadow = shadow.filter(ImageFilter.GaussianBlur(7))
    img.alpha_composite(shadow)

    d = ImageDraw.Draw(img)
    d.text((PAD, PAD), text, font=font, fill=(255, 255, 255, 255))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return H
