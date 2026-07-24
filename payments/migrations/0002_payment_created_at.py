from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="payment",
            options={
                "verbose_name": "Payment",
                "verbose_name_plural": "Payments",
                "ordering": ["-paid_at", "-created_at"],
            },
        ),
    ]

