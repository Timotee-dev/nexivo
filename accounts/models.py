from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    ROLES = [('customer','Customer'),('provider','Provider'),('admin','Admin')]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLES, default='customer')
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']
    def __str__(self): return self.email
    def display(self): return self.get_full_name() or self.email.split('@')[0]
    def initials(self):
        n = self.display().split()
        return ''.join(p[0].upper() for p in n[:2]) if n else 'U'
    @property
    def is_customer(self): return self.role == 'customer'
    @property
    def is_provider(self): return self.role == 'provider'
    @property
    def is_platform_admin(self): return self.role == 'admin' or self.is_superuser

class ProviderProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='provider_profile')
    business_name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=20, blank=True)
    account_name = models.CharField(max_length=200, blank=True)
    paystack_subaccount_code = models.CharField(max_length=100, blank=True)
    total_earnings = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_reviews = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.business_name
    def initials(self): return self.business_name[0].upper() if self.business_name else 'P'
    def refresh_rating(self):
        from bookings.models import Review
        from django.db.models import Avg
        rvs = Review.objects.filter(provider=self.user)
        if rvs.exists():
            self.rating = round(rvs.aggregate(a=Avg('rating'))['a'], 2)
            self.total_reviews = rvs.count()
            self.save(update_fields=['rating','total_reviews'])

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.TextField()
    ntype = models.CharField(max_length=20, default='info')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']

class SavedProvider(models.Model):
    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_providers')
    provider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_by')
    class Meta: unique_together = ['customer','provider']