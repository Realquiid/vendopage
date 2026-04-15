"""
generate_assets.py
==================
Run once from your Django project root:

    python generate_assets.py

Reads  static/images/logo.png  (your green VendoPage logo, white background is fine)
Writes all image assets base.html needs — with proper transparent backgrounds.

Requirements:  pip install Pillow
"""

from PIL import Image, ImageDraw, ImageColor
import os, sys

LOGO_PATH  = 'static/images/logoo.png'
OUT_DIR    = 'static/images'
GREEN      = '#00C853'
GREEN_DARK = '#00a844'

if not os.path.exists(LOGO_PATH):
    print(f'ERROR: Cannot find {LOGO_PATH}')
    print('       Save your green logo as static/images/logo.png first.')
    sys.exit(1)

os.makedirs(OUT_DIR, exist_ok=True)
print(f'Reading {LOGO_PATH} ...')
src = Image.open(LOGO_PATH).convert('RGBA')

# ── Step 1: tight crop (remove surrounding whitespace) ───────────────────────
def is_bg(r, g, b, a, t=240):
    return r >= t and g >= t and b >= t

W, H = src.size
min_x, min_y, max_x, max_y = W, H, 0, 0
for y in range(H):
    for x in range(W):
        r, g, b, a = src.getpixel((x, y))
        if not is_bg(r, g, b, a):
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y

pad = 4
cropped = src.crop((max(0, min_x-pad), max(0, min_y-pad),
                    min(W, max_x+pad+1), min(H, max_y+pad+1)))
print(f'   Tight crop: {cropped.size}')

# ── Step 2: remove white/near-white background → transparent ────────────────
def remove_white_bg(img, threshold=240):
    result = img.copy()
    pixels = list(result.getdata())
    result.putdata([
        (r, g, b, 0) if (r >= threshold and g >= threshold and b >= threshold)
        else (r, g, b, a)
        for r, g, b, a in pixels
    ])
    return result

logo = remove_white_bg(cropped)

# ── Step 3: recolor all visible pixels ───────────────────────────────────────
def recolor(img, hex_color):
    rgb = ImageColor.getrgb(hex_color)
    result = img.copy()
    pixels = list(result.getdata())
    result.putdata([
        rgb + (a,) if (a := px[3]) > 10 else (0, 0, 0, 0)
        for px in pixels
    ])
    return result

# ── Step 4: find icon mark (top section above wordmark) ──────────────────────
iW, iH = logo.size
split_y = None
for y in range(iH):
    row_empty = all(
        logo.getpixel((x, y))[3] < 10
        for x in range(0, iW, 3)
    )
    if row_empty and y > iH * 0.2:
        split_y = y
        break

if split_y:
    print(f'   Icon/wordmark split at y={split_y}')
    icon = logo.crop((0, 0, iW, split_y))
else:
    print('   No gap found, using top 45% as icon')
    icon = logo.crop((0, 0, iW, int(iH * 0.45)))

# ── Step 5: helper to place image on square canvas ───────────────────────────
def on_square(img, size, bg_hex=None, tint_hex=None, pad_ratio=0.15):
    bg = (ImageColor.getrgb(bg_hex) + (255,)) if bg_hex else (0, 0, 0, 0)
    canvas = Image.new('RGBA', (size, size), bg)
    src_img = recolor(img, tint_hex) if tint_hex else img.copy()
    iw, ih = img.size
    inner = int(size * (1 - pad_ratio * 2))
    scale = inner / max(iw, ih)
    nw, nh = int(iw * scale), int(ih * scale)
    resized = src_img.resize((nw, nh), Image.LANCZOS)
    canvas.paste(resized, ((size-nw)//2, (size-nh)//2), resized)
    return canvas

def save(img, path):
    img.save(path)
    print(f'   OK  {path}  ({os.path.getsize(path)/1024:.1f} KB)')

# ── OUTPUT FILES ─────────────────────────────────────────────────────────────

# logo.png → green on transparent (navbar light mode, footer)
save(logo, f'{OUT_DIR}/logo.png')

# logo-white.png → white on transparent (navbar dark mode, footer dark)
save(recolor(logo, '#ffffff'), f'{OUT_DIR}/logo-white.png')

# favicons — icon mark only
for size, fname in [(32, 'favicon-32x32.png'), (16, 'favicon-16x16.png')]:
    save(on_square(icon, size, pad_ratio=0.04), f'{OUT_DIR}/{fname}')

# apple-touch-icon — green square + white icon
save(on_square(icon, 180, bg_hex=GREEN, tint_hex='#ffffff', pad_ratio=0.20),
     f'{OUT_DIR}/apple-touch-icon.png')

# android chrome icons
for size, fname in [(192,'android-chrome-192x192.png'),(512,'android-chrome-512x512.png')]:
    save(on_square(icon, size, bg_hex=GREEN, tint_hex='#ffffff', pad_ratio=0.18),
         f'{OUT_DIR}/{fname}')

# og-image + twitter-card — gradient bg + white full logo centered
OW, OH = 1200, 630
og = Image.new('RGBA', (OW, OH))
draw = ImageDraw.Draw(og)
gs, ge = ImageColor.getrgb(GREEN), ImageColor.getrgb(GREEN_DARK)
for y in range(OH):
    t = y / OH
    draw.line([(0,y),(OW,y)], fill=tuple(int(gs[i]+(ge[i]-gs[i])*t) for i in range(3))+(255,))
wl = recolor(logo, '#ffffff')
tw = 500; th = int(wl.height * (tw / wl.width))
wl = wl.resize((tw, th), Image.LANCZOS)
og.paste(wl, ((OW-tw)//2, (OH-th)//2), wl)
og_rgb = og.convert('RGB')
og_rgb.save(f'{OUT_DIR}/og-image.jpg', quality=95)
og_rgb.save(f'{OUT_DIR}/twitter-card.jpg', quality=95)
print(f'   OK  {OUT_DIR}/og-image.jpg')
print(f'   OK  {OUT_DIR}/twitter-card.jpg')

# favicon.ico
i16 = on_square(icon, 16, pad_ratio=0.04)
i32 = on_square(icon, 32, pad_ratio=0.04)
i32.save(f'{OUT_DIR}/favicon.ico', format='ICO', sizes=[(16,16),(32,32)], append_images=[i16])
print(f'   OK  {OUT_DIR}/favicon.ico')

print('\nDone! All assets in', OUT_DIR)