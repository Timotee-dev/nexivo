from django.db import models
from django.conf import settings


class Payment(models.Model):
    STATUS = [('pending','Pending'),('success','Success'),('failed','Failed')]
    booking = models.OneToOneField('bookings.Booking', on_delete=models.CASCADE, related_name='payment')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=200, unique=True)
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    commission = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    provider_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    paystack_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f'{self.reference} — {self.status}'


class Withdrawal(models.Model):
    STATUS = [('pending','Pending'),('approved','Approved'),('rejected','Rejected')]
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS, default='pending')
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return f'₦{self.amount} — {self.provider.email} — {self.status}'