import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from bookings.models import Booking, Review
from payments.models import Payment, Withdrawal
from services.models import Service
from accounts.models import User, ProviderProfile, SavedProvider

@login_required
def dashboard(request):
    u=request.user
    if u.is_platform_admin: return redirect('admin_dash')
    if u.is_provider: return redirect('provider_dash')
    return redirect('customer_dash')

@login_required
def customer_dash(request):
    if not request.user.is_customer: return redirect('dashboard')
    u=request.user
    bookings=Booking.objects.filter(customer=u)
    upcoming=bookings.filter(status__in=['confirmed','awaiting_payment','in_progress'],date__gte=timezone.now().date()).order_by('date')[:5]
    recent=bookings.order_by('-created_at')[:6]
    saved=SavedProvider.objects.filter(customer=u).select_related('provider__provider_profile')[:5]
    spent=Payment.objects.filter(booking__customer=u,status='success').aggregate(t=Sum('amount'))['t'] or 0
    return render(request,'dashboard/customer.html',{'upcoming':upcoming,'recent':recent,'saved':saved,'total':bookings.count(),'spent':spent})

@login_required
def provider_dash(request):
    if not request.user.is_provider: return redirect('dashboard')
    u=request.user; pp=u.provider_profile
    bookings=Booking.objects.filter(provider=u)
    pending=bookings.filter(status='pending').order_by('-created_at')[:5]
    upcoming=bookings.filter(status__in=['confirmed','in_progress'],date__gte=timezone.now().date()).order_by('date')[:5]
    completed=bookings.filter(status='completed').count()
    reviews=Review.objects.filter(provider=u).order_by('-created_at')[:4]
    months,amounts=[],[]
    for i in range(5,-1,-1):
        d=timezone.now()-timedelta(days=30*i)
        t=Payment.objects.filter(booking__provider=u,status='success',paid_at__year=d.year,paid_at__month=d.month).aggregate(t=Sum('provider_payout'))['t'] or 0
        months.append(d.strftime('%b')); amounts.append(float(t))
    wds=Withdrawal.objects.filter(provider=u)[:5]
    return render(request,'dashboard/provider.html',{'pp':pp,'pending':pending,'upcoming':upcoming,'completed':completed,'reviews':reviews,'months':json.dumps(months),'amounts':json.dumps(amounts),'wds':wds})

@login_required
def admin_dash(request):
    if not request.user.is_platform_admin: return redirect('dashboard')
    total_users=User.objects.filter(role='customer').count()
    total_providers=User.objects.filter(role='provider').count()
    total_bookings=Booking.objects.count()
    rev=Payment.objects.filter(status='success').aggregate(t=Sum('commission'))['t'] or 0
    pending_wds=Withdrawal.objects.filter(status='pending').count()
    recent_bookings=Booking.objects.select_related('customer','service','provider__provider_profile').order_by('-created_at')[:10]
    recent_payments=Payment.objects.filter(status='success').select_related('booking__customer','booking__service').order_by('-paid_at')[:8]
    wd_list=Withdrawal.objects.filter(status='pending').select_related('provider__provider_profile')[:8]
    months,rev_data=[],[]
    for i in range(5,-1,-1):
        d=timezone.now()-timedelta(days=30*i)
        r=Payment.objects.filter(status='success',paid_at__year=d.year,paid_at__month=d.month).aggregate(t=Sum('commission'))['t'] or 0
        months.append(d.strftime('%b')); rev_data.append(float(r))
    statuses=Booking.objects.values('status').annotate(n=Count('id'))
    return render(request,'dashboard/admin.html',{'total_users':total_users,'total_providers':total_providers,'total_bookings':total_bookings,'rev':rev,'pending_wds':pending_wds,'recent_bookings':recent_bookings,'recent_payments':recent_payments,'wd_list':wd_list,'months':json.dumps(months),'rev_data':json.dumps(rev_data),'s_labels':json.dumps([s['status'].replace('_',' ').title() for s in statuses]),'s_data':json.dumps([s['n'] for s in statuses])})

@login_required
def admin_users(request):
    if not request.user.is_platform_admin: return redirect('dashboard')
    users=User.objects.all().order_by('-date_joined')
    role=request.GET.get('role','')
    if role: users=users.filter(role=role)
    return render(request,'dashboard/admin_users.html',{'users':users,'role':role})

@login_required
def admin_providers(request):
    if not request.user.is_platform_admin: return redirect('dashboard')
    providers=ProviderProfile.objects.select_related('user').order_by('-created_at')
    return render(request,'dashboard/admin_providers.html',{'providers':providers})

@login_required
def admin_bookings(request):
    if not request.user.is_platform_admin: return redirect('dashboard')
    blist=Booking.objects.select_related('customer','service','provider__provider_profile').order_by('-created_at')
    status=request.GET.get('status','')
    if status: blist=blist.filter(status=status)
    return render(request,'dashboard/admin_bookings.html',{'blist':blist,'status':status,'STATUS':Booking.STATUS})

@login_required
def admin_withdrawals(request):
    if not request.user.is_platform_admin: return redirect('dashboard')
    wds=Withdrawal.objects.select_related('provider__provider_profile').order_by('-created_at')
    return render(request,'dashboard/admin_withdrawals.html',{'wds':wds})

@login_required
def approve_wd(request, pk):
    if not request.user.is_platform_admin: return redirect('dashboard')
    wd=get_object_or_404(Withdrawal,pk=pk,status='pending'); wd.status='approved'; wd.save()
    messages.success(request,f'₦{wd.amount:,.0f} approved.'); return redirect('admin_withdrawals')

@login_required
def reject_wd(request, pk):
    if not request.user.is_platform_admin: return redirect('dashboard')
    wd=get_object_or_404(Withdrawal,pk=pk,status='pending'); wd.status='rejected'; wd.save()
    pp=wd.provider.provider_profile; pp.available_balance+=wd.amount; pp.save()
    messages.success(request,'Rejected, balance refunded.'); return redirect('admin_withdrawals')

@login_required
def verify_provider(request, pk):
    if not request.user.is_platform_admin: return redirect('dashboard')
    pp=get_object_or_404(ProviderProfile,pk=pk); pp.is_verified=True; pp.save()
    messages.success(request,f'{pp.business_name} verified!'); return redirect('admin_providers')
