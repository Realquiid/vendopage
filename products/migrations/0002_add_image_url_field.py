from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        # Add field as nullable first
        migrations.AddField(
            model_name='productimage',
            name='image_url',
            field=models.URLField(max_length=500, blank=True, default=''),
        ),
    ]