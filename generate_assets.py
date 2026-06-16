

from PIL import Image, ImageDraw
import numpy as np

GREEN      = (0, 200, 83)
GREEN_DARK = (0, 168, 68)
WHITE      = (255, 255, 255)

# ── Load & extract logo ──────────────────────────────────────────────────────
img = Image.open('static/images/logoo.png').convert('RGBA')
arr = np.array(img).copy()
r, g, b = arr[:,:,0].astype(int), arr[:,:,1].astype(int), arr[:,:,2].astype(int)
is_white = (r > 230) & (g > 230) & (b > 230)
result = arr.copy(); result[is_white, 3] = 0
logo_full = Image.fromarray(result, 'RGBA').crop(Image.fromarray(result,'RGBA').getbbox())

def recolor(img_rgba, color):
    a = np.array(img_rgba.copy())
    mask = a[:,:,3] > 10
    a[mask, 0] = color[0]; a[mask, 1] = color[1]; a[mask, 2] = color[2]
    return Image.fromarray(a, 'RGBA')

# ── Extract "V" letter (0..54px) ────────────────────────────────────────────
v_letter = logo_full.crop((0, 0, 55, logo_full.height))
v_letter_bbox = v_letter.getbbox()
v_letter = v_letter.crop(v_letter_bbox)
print(f"V letter size: {v_letter.size}")

# ── Helper: place image centered on square canvas ────────────────────────────
def on_square(src, size, bg=None, color=None, pad=0.15):
    canvas = Image.new('RGBA', (size, size), bg or (0,0,0,0))
    im = recolor(src, color) if color else src.copy()
    iw, ih = im.size
    inner = int(size * (1 - pad * 2))
    scale = inner / max(iw, ih)
    nw, nh = max(1, int(iw*scale)), max(1, int(ih*scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas.paste(im, ((size-nw)//2, (size-nh)//2), im)
    return canvas

def on_rect(src, W, H, bg=None, color=None, pad_frac=0.12):
    canvas = Image.new('RGBA', (W, H), bg or (0,0,0,0))
    im = recolor(src, color) if color else src.copy()
    iw, ih = im.size
    inner_w = int(W * (1 - pad_frac * 2))
    inner_h = int(H * (1 - pad_frac * 2))
    scale = min(inner_w/iw, inner_h/ih)
    nw, nh = max(1,int(iw*scale)), max(1,int(ih*scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas.paste(im, ((W-nw)//2, (H-nh)//2), im)
    return canvas

def save(img, path):
    img.save(path)
    print(f"  ✓ {path}")

OUT = '/home/claude/assets'
import os; os.makedirs(OUT, exist_ok=True)

# ── logoo.png — green on transparent ─────────────────────────────────────────
save(recolor(logo_full, GREEN), f'{OUT}/logoo.png')

# ── logo-white.png — white on transparent ───────────────────────────────────
save(recolor(logo_full, WHITE), f'{OUT}/logo-white.png')

# ── favicon-32x32.png — green "V" on transparent ────────────────────────────
save(on_square(v_letter, 32, color=GREEN, pad=0.05), f'{OUT}/favicon-32x32.png')

# ── favicon-16x16.png ────────────────────────────────────────────────────────
save(on_square(v_letter, 16, color=GREEN, pad=0.05), f'{OUT}/favicon-16x16.png')

# ── favicon.ico — multi-size ─────────────────────────────────────────────────
i32 = on_square(v_letter, 32, color=GREEN, pad=0.05)
i16 = on_square(v_letter, 16, color=GREEN, pad=0.05)
i32.save(f'{OUT}/favicon.ico', format='ICO', sizes=[(32,32),(16,16)], append_images=[i16])
print(f"  ✓ {OUT}/favicon.ico")

# ── apple-touch-icon — white "V" on green square ────────────────────────────
save(on_square(v_letter, 180, bg=GREEN+(255,), color=WHITE, pad=0.22), f'{OUT}/apple-touch-icon.png')

# ── android-chrome — white "V" on green square (rounded feel) ────────────────
save(on_square(v_letter, 192, bg=GREEN+(255,), color=WHITE, pad=0.20), f'{OUT}/android-chrome-192x192.png')
save(on_square(v_letter, 512, bg=GREEN+(255,), color=WHITE, pad=0.20), f'{OUT}/android-chrome-512x512.png')

# ── og-image.jpg — gradient bg + white logo centered ────────────────────────
OW, OH = 1200, 630
og = Image.new('RGBA', (OW, OH))
draw = ImageDraw.Draw(og)
for y in range(OH):
    t = y / OH
    cr = int(GREEN[0] + (GREEN_DARK[0]-GREEN[0])*t)
    cg = int(GREEN[1] + (GREEN_DARK[1]-GREEN[1])*t)
    cb = int(GREEN[2] + (GREEN_DARK[2]-GREEN[2])*t)
    draw.line([(0,y),(OW,y)], fill=(cr,cg,cb,255))
white_logo = recolor(logo_full, WHITE)
og_logo = on_rect(white_logo, OW, OH, color=WHITE, pad_frac=0.15)
# Paste logo onto gradient
og_arr = np.array(og); logo_arr = np.array(og_logo)
mask = logo_arr[:,:,3] > 10
og_arr[mask] = logo_arr[mask]
og_final = Image.fromarray(og_arr, 'RGBA').convert('RGB')
og_final.save(f'{OUT}/og-image.jpg', quality=95)
og_final.save(f'{OUT}/twitter-card.jpg', quality=95)
print(f"  ✓ {OUT}/og-image.jpg")
print(f"  ✓ {OUT}/twitter-card.jpg")

print("\nAll done!")
