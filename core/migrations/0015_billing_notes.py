from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0014_alter_customuser_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='billing',
            name='notes',
            field=models.TextField(blank=True),
        ),
    ]
