from django.db import models
from django.contrib.auth.models import User


class Review(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    product = models.ForeignKey(
        'product_management.Product',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='reviews'
    )
    product_name = models.CharField(max_length=200)
    rating = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField()
    status = models.CharField(max_length=20, default='approved')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product_name} - {self.rating} Stars ({self.status})"

