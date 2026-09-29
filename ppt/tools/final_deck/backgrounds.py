"""Original background textures for the final deck: near-black base, fine technical grid, soft glows, vignette.
Textures only (no diagrams, no text): every diagram in the deck is a native, editable PowerPoint shape."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

W, H = 1920, 1080
CYAN, VIOLET, BLUE = (34, 211, 238), (139, 92, 246), (59, 130, 246)


def make(path: Path, glows, seed=1):
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.zeros((H, W, 3), float)
    img[:] = (5, 7, 13)
    for cx, cy, r, col, s in glows:                      # soft radial glows
        d2 = ((xx - cx * W) / (r * W)) ** 2 + ((yy - cy * H) / (r * W)) ** 2
        img += (np.exp(-d2 * 2.4) * s)[..., None] * np.array(col, float)
    v = ((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2
    img *= (1 - 0.38 * np.clip(v, 0, 1.6))[..., None]    # vignette
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    step = 72                                            # 0.5 inch at 1920 px / 13.333 in
    for i, x in enumerate(range(0, W + 1, step)):
        d.line([(x, 0), (x, H)], fill=(70, 105, 160, 60 if i % 4 == 0 else 26), width=1)
    for j, y in enumerate(range(0, H + 1, step)):
        d.line([(0, y), (W, y)], fill=(70, 105, 160, 60 if j % 4 == 0 else 26), width=1)
    rng = np.random.default_rng(seed)                    # a few "node" dots on major grid intersections
    for _ in range(26):
        gx, gy = int(rng.integers(0, W // 288 + 1)) * 288, int(rng.integers(0, H // 288 + 1)) * 288
        d.ellipse([gx - 3, gy - 3, gx + 3, gy + 3], fill=(120, 190, 230, 120))
    im = Image.alpha_composite(im, ov).convert("RGB")
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, quality=92)


def build_all(out: Path):
    specs = {
        "bg1": [(0.72, 0.45, 0.42, CYAN, 0.22), (0.15, 0.95, 0.35, VIOLET, 0.14)],
        "bg2": [(0.7, 0.62, 0.40, CYAN, 0.10), (0.05, 0.1, 0.30, VIOLET, 0.10)],
        "bg3": [(0.5, 0.42, 0.45, BLUE, 0.10), (0.95, 0.1, 0.25, VIOLET, 0.10)],
        "bg4": [(0.5, 0.15, 0.55, CYAN, 0.09), (0.9, 0.9, 0.3, VIOLET, 0.09)],
        "bg5": [(0.38, 0.52, 0.42, VIOLET, 0.11), (0.95, 0.2, 0.3, CYAN, 0.08)],
        "bg6": [(0.2, 0.3, 0.4, BLUE, 0.08), (0.9, 0.85, 0.3, CYAN, 0.08)],
    }
    for i, (name, g) in enumerate(specs.items()):
        make(out / f"{name}.jpg", g, seed=i + 3)
