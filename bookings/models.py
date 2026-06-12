from django.db import models
from django.conf import settings
import uuid

class Booking(models.Model):
    STATUS = [('pending','Pending'),('awaiting_payment','Awaiting Payment'),('confirmed','Confirmed'),('in_progress','In Progress'),('completed','Completed'),('cancelled','Cancelled')]
    ref = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings_as_customer')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings_as_provider')
    service = models.ForeignKey('services.Service', on_delete=models.CASCADE, related_name='bookings')
    date = models.DateField()
    time = models.TimeField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=30, choices=STATUS, default='pending')
    notes = models.TextField(blank=True)
    reject_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def save(self, *args, **kwargs):
        if not self.ref: self.ref = 'NXR' + uuid.uuid4().hex[:7].upper()
        super().save(*args, **kwargs)
    def __str__(self): return f'{self.ref}'
    @property
    def commission(self):
        from django.conf import settings as s
        return round(self.amount * getattr(s,'PLATFORM_COMMISSION',10) / 100, 2)
    @property
    def provider_earnings(self): return round(self.amount - self.commission, 2)

class Review(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='review', null=True, blank=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_given')
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews_received')
    service = models.ForeignKey('services.Service', on_delete=models.CASCADE, related_name='reviews', null=True)
    rating = models.IntegerField(choices=[(i,str(i)) for i in range(1,6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
