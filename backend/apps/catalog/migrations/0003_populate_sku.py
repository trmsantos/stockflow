# Generated migration to populate SKU with short_name

from django.db import migrations


def populate_sku(apps, schema_editor):
    """Populate sku with short_name for existing products (idempotent)."""
    Product = apps.get_model('catalog', 'Product')
    for product in Product.objects.filter(sku=''):
        product.sku = product.short_name
    Product.objects.bulk_update(
        Product.objects.filter(sku=''),
        ['sku'],
        batch_size=1000
    )


def reverse_populate_sku(apps, schema_editor):
    """Reverse: clear SKU if it matches short_name."""
    Product = apps.get_model('catalog', 'Product')
    for product in Product.objects.all():
        if product.sku == product.short_name:
            product.sku = ''
    Product.objects.bulk_update(Product.objects.all(), ['sku'], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_add_sku_to_product'),
    ]

    operations = [
        migrations.RunPython(populate_sku, reverse_populate_sku),
    ]
