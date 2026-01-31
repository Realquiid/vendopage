# convert_logo_to_favicons.py
from PIL import Image
import os

# Ensure directories exist
os.makedirs('static/images', exist_ok=True)

# Load your logo
try:
    logo = Image.open('static/images/logo.jpg')
    print("✅ Logo loaded successfully!")
except FileNotFoundError:
    print("❌ Please save your logo as 'static/images/logo.jpg' first")
    exit()

# Convert to RGBA if needed
if logo.mode != 'RGBA':
    logo = logo.convert('RGBA')

# Sizes needed for favicons
sizes = {
    'favicon-16x16.png': (16, 16),
    'favicon-32x32.png': (32, 32),
    'apple-touch-icon.png': (180, 180),
    'android-chrome-192x192.png': (192, 192),
    'android-chrome-512x512.png': (512, 512),
}

# Generate all favicon sizes
for filename, size in sizes.items():
    # Resize logo maintaining quality
    resized = logo.resize(size, Image.Resampling.LANCZOS)
    
    # Save
    output_path = f'static/images/{filename}'
    resized.save(output_path, quality=95)
    print(f'✅ Created {filename} ({size[0]}x{size[1]})')

# Create OG image (1200x630) for social media
og_width, og_height = 1200, 630

# Create background with your logo's gradient colors
og_img = Image.new('RGB', (og_width, og_height))

# Paste logo in center
logo_size = 400
logo_resized = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

# Calculate center position
x = (og_width - logo_size) // 2
y = (og_height - logo_size) // 2

# Create a gradient background (purple to pink like your logo)
from PIL import ImageDraw

og_img = Image.new('RGB', (og_width, og_height), '#7C3AED')
draw = ImageDraw.Draw(og_img)

# Add gradient effect
for i in range(og_height):
    # Interpolate between purple and pink
    r = int(124 + (236 - 124) * (i / og_height))
    g = int(58 + (72 - 58) * (i / og_height))
    b = int(237 + (153 - 237) * (i / og_height))
    draw.line([(0, i), (og_width, i)], fill=(r, g, b))

# Paste logo on gradient background
og_img.paste(logo_resized, (x, y), logo_resized)

# Save social media images
og_img.save('static/images/og-image.jpg', quality=95)
og_img.save('static/images/twitter-card.jpg', quality=95)

print('✅ Created og-image.jpg (1200x630)')
print('✅ Created twitter-card.jpg (1200x630)')

print("\n🎉 All favicons created successfully!")
print("📁 Files created in: static/images/")
print("\nGenerated files:")
print("  - favicon-16x16.png")
print("  - favicon-32x32.png")
print("  - apple-touch-icon.png")
print("  - android-chrome-192x192.png")
print("  - android-chrome-512x512.png")
print("  - og-image.jpg")
print("  - twitter-card.jpg")