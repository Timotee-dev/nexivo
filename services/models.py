from django.db import models
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    emoji = models.CharField(max_length=10, default='⚡')
    is_active = models.BooleanField(default=True)
    class Meta: ordering = ['name']
    def __str__(self): return self.name

class Service(models.Model):
    provider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='services')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='services')
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    duration = models.IntegerField(default=60)
    image = models.ImageField(upload_to='services/', blank=True, null=True)
    tags = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ['-created_at']
    def __str__(self): return self.title
    def tag_list(self): return [t.strip() for t in self.tags.split(',') if t.strip()]
    @property
    def pp(self): return self.provider.provider_profile
