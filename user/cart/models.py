from django.db import models
from django.conf import settings
from admin_panel.product_management.models import Product, ProductVariant


class CartItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart_items',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='in_carts',
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name='in_carts',
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product', 'variant')
        ordering = ['-added_at']

    def __str__(self):
        return f"{self.user.username} – {self.product.name} x{self.quantity}"

    @property
    def price(self):
        if self.variant:
            return self.variant.price
        v = self.product.variants.filter(is_active=True, is_deleted=False).first()
        return v.price if v else 0

    @property
    def total(self):
        return self.price * self.quantity
