from django import forms
from .models import Service
class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['category','title','description','price','duration','image','tags','is_active']
        widgets = {
            'description': forms.Textarea(attrs={'rows':4}),
            'tags': forms.TextInput(attrs={'placeholder':'e.g. haircut, coloring, styling'}),
        }
