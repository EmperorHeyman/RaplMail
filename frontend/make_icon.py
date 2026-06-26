"""Generate the 1024x1024 RaplMail app-icon source PNG — the "Stack" concept.

Layered cards resolving into one front envelope (the unified inbox), on a
diagonal violet gradient. Mirrors frontend/src/lib/icons.js styling.

Rendered on a 512-unit grid at 4x supersampling, then downscaled to 1024 for
clean anti-aliased edges. Run `npx tauri icon icon-source.png` afterwards to
regenerate every platform icon in src-tauri/icons.
"""

import numpy as np
from PIL import Image, ImageDraw

GRID = 512          # design grid (matches the SVG viewBox)
SS = 8              # supersample factor -> render at 4096, downscale to 1024
OUT = 1024
k = SS              # coord scale: design units -> render pixels
W = GRID * SS

VIOLET_TOP = (0x8f, 0x7b, 0xff)   # gradient start (top-left)
VIOLET_BOT = (0x5a, 0x6f, 0xe6)   # gradient end   (bottom-right)
FLAP = (0x5a, 0x6f, 0xe6)         # flap stroke, matches gradient end


def s(*vals):
    """Scale design units to render pixels."""
    return [v * k for v in vals] if len(vals) > 1 else vals[0] * k


def rounded_card(base, x, y, w, h, r, alpha):
    """Composite a white rounded rectangle at the given alpha over `base`."""
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle(s(x, y, x + w, y + h), radius=s(r),
                        fill=(255, 255, 255, alpha))
    return Image.alpha_composite(base, overlay)


# --- diagonal gradient, clipped to the rounded tile -------------------------
yy, xx = np.mgrid[0:W, 0:W]
t = (xx + yy) / (2 * (W - 1))                      # 0 at top-left -> 1 bottom-right
grad = np.empty((W, W, 3), dtype=np.uint8)
for i in range(3):
    grad[..., i] = (VIOLET_TOP[i] + (VIOLET_BOT[i] - VIOLET_TOP[i]) * t).astype(np.uint8)
grad_img = Image.fromarray(grad).convert("RGBA")

tile_mask = Image.new("L", (W, W), 0)
ImageDraw.Draw(tile_mask).rounded_rectangle([0, 0, W - 1, W - 1], radius=s(116), fill=255)

img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
img.paste(grad_img, (0, 0), tile_mask)

# --- the stack: two faded cards, then the opaque front envelope -------------
img = rounded_card(img, 146, 112, 220, 120, 22, int(255 * 0.32))
img = rounded_card(img, 124, 146, 264, 140, 24, int(255 * 0.55))
img = rounded_card(img, 100, 190, 312, 186, 30, 255)

# --- flap: V from the front card's top corners to its centre ----------------
flap = Image.new("RGBA", (W, W), (0, 0, 0, 0))
fd = ImageDraw.Draw(flap)
pts = [tuple(s(124, 220)), tuple(s(256, 318)), tuple(s(388, 220))]
fd.line(pts, fill=FLAP + (255,), width=s(26), joint="curve")
# round caps + join (Pillow lines are butt-capped)
r = s(13)
for cx, cy in pts:
    fd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FLAP + (255,))
img = Image.alpha_composite(img, flap)

# --- downscale and save -----------------------------------------------------
img.resize((OUT, OUT), Image.LANCZOS).save("icon-source.png")
print(f"wrote icon-source.png ({OUT}x{OUT})")
