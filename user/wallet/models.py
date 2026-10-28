from django.db import models
from django.conf import settings
from decimal import Decimal


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'User Wallet'
        verbose_name_plural = 'User Wallets'

    def __str__(self):
        return f"{self.user.username}'s Wallet (₹{self.balance})"

    def credit(self, amount, description, source='OTHER', order=None, reference=''):
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amount <= 0:
            raise ValueError("Credit amount must be greater than zero.")
        self.balance += amount
        self.save(update_fields=['balance', 'updated_at'])
        return WalletTransaction.objects.create(
            wallet=self,
            transaction_type='CREDIT',
            amount=amount,
            balance_after=self.balance,
            description=description,
            source=source,
            order=order,
            reference=reference or (order.order_number if order else ''),
            status='SUCCESS',
        )

    def debit(self, amount, description, source='OTHER', order=None, reference=''):
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
        if amount <= 0:
            raise ValueError("Debit amount must be greater than zero.")
        if self.balance < amount:
            raise ValueError("Insufficient wallet balance.")
        self.balance -= amount
        self.save(update_fields=['balance', 'updated_at'])
        return WalletTransaction.objects.create(
            wallet=self,
            transaction_type='DEBIT',
            amount=amount,
            balance_after=self.balance,
            description=description,
            source=source,
            order=order,
            reference=reference or (order.order_number if order else ''),
            status='SUCCESS',
        )


class WalletTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('CREDIT', 'Credit'),
        ('DEBIT', 'Debit'),
    )
    SOURCE_CHOICES = (
        ('ORDER_PAYMENT', 'Order Payment'),
        ('ORDER_CANCELLATION_REFUND', 'Cancellation Refund'),
        ('ORDER_RETURN_REFUND', 'Return Refund'),
        ('WALLET_RECHARGE', 'Wallet Recharge'),
        ('ADMIN_ADJUSTMENT', 'Admin Adjustment'),
        ('OTHER', 'Other'),
    )

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='OTHER')
    order = models.ForeignKey(
        'checkout.Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wallet_transactions',
    )
    reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, default='SUCCESS')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} ₹{self.amount} - {self.wallet.user.username}"
