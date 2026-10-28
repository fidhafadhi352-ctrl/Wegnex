from django.db import models
from django.utils import timezone
from decimal import Decimal
from user.account.models import Category
from admin_panel.product_management.models import Product


class Offer(models.Model):
    DISCOUNT_TYPES = [
        ('percentage', 'Percentage (%)'),
        ('fixed', 'Fixed Amount (₹)'),
    ]

    TARGET_TYPES = [
        ('category', 'Category Offer'),
        ('products', 'Product Offer'),
    ]

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=50, blank=True, null=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    offer_type = models.CharField(max_length=20, choices=TARGET_TYPES, default='category')

    category = models.ForeignKey(Category, on_delete=models.CASCADE, null=True, blank=True, related_name='offers')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='offers')

    minimum_purchase = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    maximum_discount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_discount_display()})"

    @property
    def is_currently_valid(self):
        if not self.is_active or self.is_deleted:
            return False
        today = timezone.now().date()
        if self.start_date and today < self.start_date:
            return False
        if self.end_date and today > self.end_date:
            return False
        return True

    def get_discount_display(self):
        if self.discount_type == 'percentage':
            val = int(self.discount_value) if self.discount_value % 1 == 0 else self.discount_value
            return f"{val}% OFF"
        return f"₹{int(self.discount_value):,} OFF"

    def calculate_discount(self, original_price):
        """
        Given an original Decimal price, calculate:
        (discount_amount, final_price, is_applicable)
        """
        try:
            original_price = Decimal(str(original_price))
        except Exception:
            return Decimal('0.00'), Decimal('0.00'), False

        if not self.is_currently_valid:
            return Decimal('0.00'), original_price, False

        if self.minimum_purchase and original_price < self.minimum_purchase:
            return Decimal('0.00'), original_price, False

        if self.discount_type == 'percentage':
            discount = (original_price * self.discount_value) / Decimal('100.00')
            if self.maximum_discount and discount > self.maximum_discount:
                discount = self.maximum_discount
        else:
            discount = self.discount_value

        if discount > original_price:
            discount = original_price

        final_price = original_price - discount
        return round(discount, 2), round(final_price, 2), True
