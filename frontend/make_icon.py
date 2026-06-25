"""Generate a 1024x1024 app icon source PNG (blue rounded square + envelope)."""

from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# Rounded-square background with a vertical gradient-ish two-tone.
d.rounded_rectangle([40, 40, S - 40, S - 40], radius=200, fill=(91, 141, 239, 255))

# Envelope.
m = 230
left, top, right, bottom = m, m + 70, S - m, S - m - 70
d.rounded_rectangle([left, top, right, bottom], radius=40, fill=(255, 255, 255, 255))
# Flap (two lines from top corners to center).
cx = S // 2
d.line([left + 20, top + 30, cx, (top + bottom) // 2], fill=(91, 141, 239, 255), width=34)
d.line([right - 20, top + 30, cx, (top + bottom) // 2], fill=(91, 141, 239, 255), width=34)

img.save("icon-source.png")
print("wrote icon-source.png")
