from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='productimage',
            name='image_url',
            field=models.URLField(max_length=500, default='https://via.placeholder.com/400'),
            preserve_default=False,
        ),
    ]