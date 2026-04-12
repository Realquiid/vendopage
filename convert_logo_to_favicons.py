from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs('static/images', exist_ok=True)

def make_favicon(size, bg_color='#00C853', text='V', text_color='white'):
    img = Image.new('RGBA', (size, size), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Draw circle background
    draw.ellipse([0, 0, size, size], fill=bg_color)
    
    # Draw the letter V centered
    font_size = int(size * 0.65)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2
    y = (size - text_h) // 2 - int(size * 0.05)
    
    draw.text((x, y), text, fill=text_color, font=font)
    return img

sizes = {
    'favicon-16x16.png': 16,
    'favicon-32x32.png': 32,
    'apple-touch-icon.png': 180,
    'android-chrome-192x192.png': 192,
    'android-chrome-512x512.png': 512,
}

for filename, size in sizes.items():
    img = make_favicon(size)
    img.save(f'static/images/{filename}')
    print(f'✅ Created {filename}')

# OG image — green background with VendoPage text
from PIL import ImageFont

og = Image.new('RGB', (1200, 630), '#00C853')
draw = ImageDraw.Draw(og)

# Darker green gradient effect
for i in range(630):
    shade = int(0 + (20) * (i / 630))
    r = max(0, 0 - shade)
    g = max(0, 200 - shade * 2)
    b = max(0, 83 - shade)
    draw.line([(0, i), (1200, i)], fill=(r, g + shade, b))

try:
    big_font = ImageFont.truetype("arialbd.ttf", 120)
    sub_font = ImageFont.truetype("arial.ttf", 48)
except:
    big_font = ImageFont.load_default()
    sub_font = big_font

# Main title
title = "VendoPage"
bbox = draw.textbbox((0, 0), title, font=big_font)
tw = bbox[2] - bbox[0]
draw.text(((1200 - tw) // 2, 220), title, fill='white', font=big_font)

# Subtitle
sub = "Upload Once. Sell Forever."
bbox2 = draw.textbbox((0, 0), sub, font=sub_font)
sw = bbox2[2] - bbox2[0]
draw.text(((1200 - sw) // 2, 380), sub, fill='rgba(255,255,255,180)', font=sub_font)

og.save('static/images/og-image.jpg', quality=95)
og.save('static/images/twitter-card.jpg', quality=95)
print('✅ Created og-image.jpg')
print('✅ Created twitter-card.jpg')
print('\n🎉 Done! Check static/images/')