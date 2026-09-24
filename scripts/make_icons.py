"""Генерация assets/icon.png и assets/icon.ico (Pillow)."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
ASSETS = BASE / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

C1 = (59, 130, 246)   # #3B82F6
C2 = (34, 211, 238)   # #22D3EE


def build_icon(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size * 0.22
    # градиентная подложка
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / size
        col = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3)) + (255,)
        gd.line([(0, y), (size, y)], fill=col)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(r), fill=255)
    img.paste(grad, (0, 0), mask)
    # буква M
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(size * 0.6))
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), "M", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), "M",
           font=font, fill=(255, 255, 255, 255))
    return img


def main() -> None:
    icon = build_icon(512)
    icon.save(ASSETS / "icon.png")
    icon.resize((256, 256), Image.LANCZOS).save(ASSETS / "icon.png", sizes=[(256, 256)])
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.save(ASSETS / "icon.ico", format="ICO", sizes=sizes)
    print("OK:", ASSETS / "icon.png", "и", ASSETS / "icon.ico")


if __name__ == "__main__":
    main()
