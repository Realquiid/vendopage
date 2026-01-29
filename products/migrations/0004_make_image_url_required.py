from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('products', '0003_populate_image_urls'),
    ]

    operations = [
        # Now make it required (after data is populated)
        migrations.AlterField(
            model_name='productimage',
            name='image_url',
            field=models.URLField(max_length=500),
        ),
    ]