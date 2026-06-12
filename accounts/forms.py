from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import User, ProviderProfile

W = lambda t='text', p='': forms.TextInput(attrs={'class':'nx-inp','type':t,'placeholder':p})
WP = lambda p='': forms.PasswordInput(attrs={'class':'nx-inp','placeholder':p})
WA = lambda p='', r=3: forms.Textarea(attrs={'class':'nx-inp','placeholder':p,'rows':r})

class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'class':'nx-inp','placeholder':'you@email.com'}))
    password = forms.CharField(label='Password', widget=WP('Your password'))

class CustomerRegForm(forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=WP('Min 6 characters'))
    password2 = forms.CharField(label='Confirm Password', widget=WP('Repeat password'))
    class Meta:
        model = User
        fields = ['first_name','last_name','email','phone']
        widgets = {'first_name':W(p='First name'),'last_name':W(p='Last name'),'email':W('email','you@email.com'),'phone':W('tel','08012345678')}
    def clean(self):
        d = super().clean()
        if d.get('password1') != d.get('password2'): raise forms.ValidationError('Passwords do not match')
        return d
    def save(self, commit=True):
        u = super().save(commit=False)
        u.username = self.cleaned_data['email']
        u.set_password(self.cleaned_data['password1'])
        u.role = 'customer'
        if commit: u.save()
        return u

class ProviderRegForm(forms.ModelForm):
    business_name = forms.CharField(max_length=200, widget=W(p='Your business name'))
    password1 = forms.CharField(label='Password', widget=WP('Min 6 characters'))
    password2 = forms.CharField(label='Confirm Password', widget=WP('Repeat password'))
    class Meta:
        model = User
        fields = ['first_name','last_name','email','phone']
        widgets = {'first_name':W(p='First name'),'last_name':W(p='Last name'),'email':W('email','you@email.com'),'phone':W('tel','08012345678')}
    def clean(self):
        d = super().clean()
        if d.get('password1') != d.get('password2'): raise forms.ValidationError('Passwords do not match')
        return d
    def save(self, commit=True):
        u = super().save(commit=False)
        u.username = self.cleaned_data['email']
        u.set_password(self.cleaned_data['password1'])
        u.role = 'provider'
        if commit:
            u.save()
            ProviderProfile.objects.create(user=u, business_name=self.cleaned_data['business_name'])
        return u

class CustomerProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name','last_name','phone','city','bio','avatar']
        widgets = {'first_name':W(p='First name'),'last_name':W(p='Last name'),'phone':W('tel'),'city':W(p='City'),'bio':WA('Tell customers about yourself')}

class ProviderProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=50, widget=W(p='First name'))
    last_name  = forms.CharField(max_length=50, widget=W(p='Last name'))
    class Meta:
        model = ProviderProfile
        fields = ['business_name','tagline','description','city','state','address','bank_name','account_number','account_name']
        widgets = {
            'business_name':W(p='Business name'), 'tagline':W(p='One-line tagline'),
            'description':WA('Describe your services...'),
            'city':W(p='City'), 'state':W(p='State'), 'address':WA('Full address',2),
            'bank_name':W(p='e.g. First Bank'), 'account_number':W(p='10-digit account number'), 'account_name':W(p='Account name'),
        }
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
