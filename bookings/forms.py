from django import forms
from .models import Booking, Review
class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['date','time','notes']
        widgets = {'date':forms.DateInput(attrs={'type':'date'}),'time':forms.TimeInput(attrs={'type':'time'}),'notes':forms.Textarea(attrs={'rows':3,'placeholder':'Any special requests?'})}
    def clean_date(self):
        from datetime import date
        d = self.cleaned_data['date']
        if d < date.today(): raise forms.ValidationError('Date cannot be in the past.')
        return d

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating','comment']
        widgets = {'comment':forms.Textarea(attrs={'rows':4,'placeholder':'Share your experience...'})}
