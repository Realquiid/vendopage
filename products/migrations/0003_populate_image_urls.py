from django.db import migrations

def populate_urls(apps, schema_editor):
    ProductImage = apps.get_model('products', 'ProductImage')
    
    for img in ProductImage.objects.all():
        if hasattr(img, 'image') and img.image:
            try:
                if hasattr(img.image, 'url'):
                    img.image_url = img.image.url
                else:
                    img.image_url = str(img.image)
                img.save(update_fields=['image_url'])
                print(f"✅ {img.id}: {img.image_url}")
            except Exception as e:
                print(f"⚠️ {img.id}: {e}")
                img.image_url = 'https://res.cloudinary.com/dqxlkie1i/image/upload/v1/placeholder.jpg'
                img.save(update_fields=['image_url'])

class Migration(migrations.Migration):
    dependencies = [
        ('products', '0002_add_image_url_field'),
    ]

    operations = [
        migrations.RunPython(populate_urls, migrations.RunPython.noop),
    ]