from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Booking, Review
from .forms import BookingForm, ReviewForm
from services.models import Service
from accounts.views import notify

@login_required
def create_booking(request, pk):
    svc = get_object_or_404(Service, pk=pk, is_active=True)
    if not request.user.is_customer: messages.error(request,'Only customers can book.'); return redirect('service_detail',pk=pk)
    form = BookingForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        b=form.save(commit=False); b.customer=request.user; b.provider=svc.provider; b.service=svc; b.amount=svc.price; b.save()
        notify(svc.provider,'New Booking 📅',f'{request.user.display()} wants to book "{svc.title}" on {b.date}.','booking')
        messages.success(request,'Booking sent! Waiting for provider.'); return redirect('booking_detail',pk=b.pk)
    return render(request,'bookings/create.html',{'svc':svc,'form':form})

@login_required
def booking_detail(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    if request.user not in [b.customer,b.provider] and not request.user.is_platform_admin:
        messages.error(request,'Access denied.'); return redirect('dashboard')
    payment = getattr(b,'payment',None); review = getattr(b,'review',None)
    return render(request,'bookings/detail.html',{'b':b,'payment':payment,'review':review})

@login_required
def my_bookings(request):
    if not request.user.is_customer: return redirect('dashboard')
    blist = Booking.objects.filter(customer=request.user).select_related('service','provider','provider__provider_profile')
    status=request.GET.get('status','')
    if status: blist=blist.filter(status=status)
    return render(request,'bookings/my_bookings.html',{'blist':blist,'status':status,'STATUS':Booking.STATUS})

@login_required
def manage_bookings(request):
    if not request.user.is_provider: return redirect('dashboard')
    blist = Booking.objects.filter(provider=request.user).select_related('service','customer')
    status=request.GET.get('status','')
    if status: blist=blist.filter(status=status)
    return render(request,'bookings/manage.html',{'blist':blist,'status':status,'STATUS':Booking.STATUS})

@login_required
@require_POST
def accept_booking(request, pk):
    b=get_object_or_404(Booking,pk=pk,provider=request.user,status='pending')
    b.status='awaiting_payment'; b.save()
    notify(b.customer,'Booking Accepted! 🎉',f'Book for "{b.service.title}" accepted. Please pay now.','payment')
    messages.success(request,'Accepted! Customer notified to pay.'); return redirect('manage_bookings')

@login_required
@require_POST
def reject_booking(request, pk):
    b=get_object_or_404(Booking,pk=pk,provider=request.user,status='pending')
    b.status='cancelled'; b.reject_reason=request.POST.get('reason','Unavailable'); b.save()
    notify(b.customer,'Booking Declined',f'Your booking for "{b.service.title}" was declined: {b.reject_reason}','warning')
    messages.success(request,'Rejected.'); return redirect('manage_bookings')

@login_required
@require_POST
def mark_in_progress(request, pk):
    b=get_object_or_404(Booking,pk=pk,provider=request.user,status='confirmed')
    b.status='in_progress'; b.save()
    notify(b.customer,'Service In Progress 🔧',f'"{b.service.title}" has started!','info')
    messages.success(request,'Marked as In Progress.'); return redirect('manage_bookings')

@login_required
@require_POST
def mark_completed(request, pk):
    b=get_object_or_404(Booking,pk=pk,provider=request.user)
    if b.status not in ['confirmed','in_progress']: messages.error(request,'Cannot complete.'); return redirect('manage_bookings')
    b.status='completed'; b.save()
    pp=b.provider.provider_profile; pp.total_earnings+=b.provider_earnings; pp.available_balance+=b.provider_earnings; pp.save()
    notify(b.customer,'Service Completed ✅',f'"{b.service.title}" done! Please leave a review.','success')
    messages.success(request,f'Done! ₦{b.provider_earnings:,.0f} credited.'); return redirect('manage_bookings')

@login_required
@require_POST
def cancel_booking(request, pk):
    b=get_object_or_404(Booking,pk=pk,customer=request.user)
    if b.status not in ['pending','awaiting_payment']: messages.error(request,'Cannot cancel now.'); return redirect('booking_detail',pk=pk)
    b.status='cancelled'; b.save()
    notify(b.provider,'Booking Cancelled',f'{b.customer.display()} cancelled "{b.service.title}".','warning')
    messages.success(request,'Booking cancelled.'); return redirect('my_bookings')

@login_required
def leave_review(request, pk):
    b=get_object_or_404(Booking,pk=pk,customer=request.user,status='completed')
    if hasattr(b,'review'): messages.info(request,'Already reviewed.'); return redirect('booking_detail',pk=pk)
    form=ReviewForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        r=form.save(commit=False); r.booking=b; r.customer=request.user; r.provider=b.provider; r.service=b.service; r.save()
        b.provider.provider_profile.refresh_rating()
        messages.success(request,'Review submitted!'); return redirect('booking_detail',pk=pk)
    return render(request,'bookings/review.html',{'b':b,'form':form})
