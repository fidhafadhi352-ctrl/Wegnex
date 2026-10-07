from django.db import models
from user.account.models import Category
from django.utils import timezone


class Product(models.Model):
    """Main product — holds brand, name, description, category."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
    )
    brand = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Products'

    def __str__(self):
        return self.name

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()
        if hasattr(self, 'variants'):
            for variant in self.variants.all():
                if hasattr(variant, 'soft_delete'):
                    variant.soft_delete()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.is_active = True
        self.save()
        if hasattr(self, 'variants'):
            for variant in self.variants.filter(is_deleted=True):
                if hasattr(variant, 'restore'):
                    variant.restore()

    @property
    def variant_count(self):
        return self.variants.filter(is_deleted=False).count()

    @property
    def thumbnail(self):
        """Return primary image from the default variant, else the first active variant."""
        # Prefer the default variant
        variant = (
            self.variants.filter(is_deleted=False, is_default=True).first()
            or self.variants.filter(is_deleted=False).first()
        )
        if variant:
            img = variant.images.filter(is_primary=True).first() or variant.images.first()
            if img:
                return img.image
        return None


class ProductVariant(models.Model):
    """A variant of a product — holds price, stock, color, size, images."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    color = models.CharField(max_length=80, blank=True)
    strap_material = models.CharField(max_length=80, blank=True)
    case_size = models.CharField(max_length=40, blank=True, help_text='e.g. 41mm')
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True,
        help_text='Original / MRP price for showing discount',
    )
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False, help_text='Default variant shown in product listing')
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        verbose_name_plural = 'Product Variants'

    def __str__(self):
        parts = [self.product.name]
        if self.color:
            parts.append(self.color)
        if self.case_size:
            parts.append(self.case_size)
        return ' | '.join(parts)

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.is_active = True
        self.save()

    @property
    def primary_image(self):
        return (
            self.images.filter(is_primary=True).first()
            or self.images.first()
        )

    @property
    def discount_percent(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return int(((self.compare_at_price - self.price) / self.compare_at_price) * 100)
        return 0


class VariantImage(models.Model):
    """One image belonging to a ProductVariant. Minimum 3 required."""

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='products/variants/')
    is_primary = models.BooleanField(default=False)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.variant} – Image {self.order}"

    def save(self, *args, **kwargs):
        # Ensure only one image is primary per variant
        if self.is_primary:
            VariantImage.objects.filter(
                variant=self.variant, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)
