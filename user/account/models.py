from django.db import models
from django.contrib.auth.models import User


class OTP(models.Model):

    user = models.ForeignKey(User,on_delete=models.CASCADE)
    code = models.CharField(max_length=6)
    is_used = models.BooleanField(default=False)
    expired_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.code


from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def soft_delete(self):
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.is_active = False
        self.save()
        # Cascade soft-delete to all products associated with this category
        if hasattr(self, 'products'):
            for product in self.products.all():
                if hasattr(product, 'soft_delete'):
                    product.soft_delete()

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.is_active = True
        self.save()
        # Restore products belonging to this category
        if hasattr(self, 'products'):
            for product in self.products.filter(is_deleted=True):
                if hasattr(product, 'restore'):
                    product.restore()

    def delete(self, *args, **kwargs):
        # In case a hard delete is performed, soft-delete all products first
        if hasattr(self, 'products'):
            for product in self.products.all():
                if hasattr(product, 'soft_delete'):
                    product.soft_delete()
        super().delete(*args, **kwargs)