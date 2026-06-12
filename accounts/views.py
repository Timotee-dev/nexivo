from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import User, ProviderProfile, Notification, SavedProvider
from .forms import LoginForm, CustomerRegForm, ProviderRegForm, CustomerProfileForm, ProviderProfileForm

def notify(user, title, body, ntype='info'):
    Notification.objects.create(user=user, title=title, body=body, ntype=ntype)

def login_view(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get('next','dashboard'))
    return render(request, 'accounts/login.html', {'form': form})

def logout_view(request):
    logout(request); return redirect('home')

def register_customer(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form = CustomerRegForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        u = form.save()
        login(request, u)
        notify(u, 'Welcome to Nexora! 🎉', 'Start browsing services and make your first booking.', 'success')
        messages.success(request, f'Welcome, {u.first_name or "friend"}!')
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form, 'role': 'Customer'})

def register_provider(request):
    if request.user.is_authenticated: return redirect('dashboard')
    form = ProviderRegForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        u = form.save()
        login(request, u)
        notify(u, 'Provider account created! 🚀', 'Complete your profile and add your first service.', 'success')
        messages.success(request, 'Provider account ready! Add your first service.')
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form, 'role': 'Provider'})

@login_required
def profile_view(request):
    u = request.user
    if u.is_provider:
        pp, _ = ProviderProfile.objects.get_or_create(user=u, defaults={'business_name': u.display()})
        form = ProviderProfileForm(request.POST or None, instance=pp, user=u)
        if request.method == 'POST' and form.is_valid():
            pp = form.save()
            u.first_name = form.cleaned_data['first_name']
            u.last_name  = form.cleaned_data['last_name']
            u.save()
            messages.success(request, 'Profile updated!')
            return redirect('profile')
    else:
        form = CustomerProfileForm(request.POST or None, request.FILES or None, instance=u)
        if request.method == 'POST' and form.is_valid():
            form.save(); messages.success(request, 'Profile updated!'); return redirect('profile')
    return render(request, 'accounts/profile.html', {'form': form})

@login_required
@require_POST
def toggle_save(request, pk):
    provider = get_object_or_404(User, pk=pk, role='provider')
    obj, created = SavedProvider.objects.get_or_create(customer=request.user, provider=provider)
    if not created: obj.delete()
    return redirect(request.META.get('HTTP_REFERER','/'))

@login_required
def notifications_page(request):
    notifs = Notification.objects.filter(user=request.user)
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return render(request, 'accounts/notifications.html', {'notifs': notifs})

@login_required
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect(request.META.get('HTTP_REFERER','/'))
