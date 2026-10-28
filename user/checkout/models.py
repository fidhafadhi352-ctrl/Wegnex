from django.db import models
from django.contrib.auth.models import User
from admin_panel.product_management.models import Product, ProductVariant
from user.address_page.models import Add_Address
import uuid
import datetime


class Order(models.Model):
    PAYMENT_CHOICES = (
        ('COD', 'Cash on Delivery'),
        ('RAZORPAY', 'Razorpay'),
        ('WALLET', 'Wallet'),
    )

    ORDER_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('RETURN_REQUESTED', 'Return Requested'),
        ('RETURNED', 'Returned'),
    )

    PAYMENT_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PAID', 'Paid'),
        ('FAILED', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=60, unique=True, editable=False)

    # Shipping Address snapshot (preserved even if original address is edited or deleted)
    shipping_address = models.ForeignKey(Add_Address, on_delete=models.SET_NULL, null=True, blank=True)
    shipping_full_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=20)
    shipping_street_address = models.TextField()
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100)
    shipping_pincode = models.CharField(max_length=10)
    shipping_country = models.CharField(max_length=100, default='India')
    shipping_address_type = models.CharField(max_length=50, default='Home')

    # Price breakdown
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    shipping_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    coupon_code = models.CharField(max_length=50, blank=True, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Payment & Status
    payment_method = models.CharField(max_length=30, choices=PAYMENT_CHOICES, default='COD')
    payment_status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    order_status = models.CharField(max_length=30, choices=ORDER_STATUS_CHOICES, default='CONFIRMED')

    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.order_number} ({self.user.username})"

    @classmethod
    def generate_order_number(cls):
        date_str = datetime.date.today().strftime('%Y%m%d')
        random_suffix = uuid.uuid4().hex[:6].upper()
        order_num = f"WGX-{date_str}-{random_suffix}"
        while cls.objects.filter(order_number=order_num).exists():
            random_suffix = uuid.uuid4().hex[:6].upper()
            order_num = f"WGX-{date_str}-{random_suffix}"
        return order_num


class OrderItem(models.Model):
    ITEM_STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('CONFIRMED', 'Confirmed'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('RETURN_REQUESTED', 'Return Requested'),
        ('RETURNED', 'Returned'),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True)
    product_name = models.CharField(max_length=200)
    variant_info = models.CharField(max_length=150, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    item_total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, choices=ITEM_STATUS_CHOICES, default='CONFIRMED')
    cancellation_reason = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.product_name} x {self.quantity} (#{self.order.order_number})"
