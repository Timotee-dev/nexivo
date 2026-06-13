import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Booking, Review
from .forms import BookingForm, ReviewForm
from services.models import Service
from accounts.views import notify

logger = logging.getLogger(__name__)


@login_required
def create_booking(request, pk):
    svc = get_object_or_404(Service, pk=pk, is_active=True)

    if not request.user.is_customer:
        messages.error(request, 'Only customers can book services.')
        return redirect('service_detail', pk=pk)

    # Make sure provider has a profile
    try:
        _ = svc.provider.provider_profile
    except Exception:
        messages.error(request, 'This service is temporarily unavailable. Please try another.')
        return redirect('services')

    form = BookingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            b = form.save(commit=False)
            b.customer = request.user
            b.provider = svc.provider
            b.service = svc
            b.amount = svc.price
            b.save()
            try:
                notify(
                    svc.provider,
                    'New Booking 📅',
                    f'{request.user.display()} wants to book "{svc.title}" on {b.date}.',
                    'booking'
                )
            except Exception as e:
                logger.warning('Could not send booking notification: %s', e)
            messages.success(request, 'Booking request sent! Waiting for provider confirmation.')
            return redirect('booking_detail', pk=b.pk)
        except Exception as e:
            logger.exception('Error creating booking')
            messages.error(request, 'Something went wrong. Please try again.')

    return render(request, 'bookings/create.html', {'svc': svc, 'form': form})


@login_required
def booking_detail(request, pk):
    b = get_object_or_404(Booking, pk=pk)
    if request.user not in [b.customer, b.provider] and not request.user.is_platform_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    payment = getattr(b, 'payment', None)
    review = getattr(b, 'review', None)
    return render(request, 'bookings/detail.html', {'b': b, 'payment': payment, 'review': review})


@login_required
def my_bookings(request):
    if not request.user.is_customer:
        return redirect('dashboard')
    blist = Booking.objects.filter(customer=request.user).select_related(
        'service', 'provider', 'provider__provider_profile'
    )
    status = request.GET.get('status', '')
    if status:
        blist = blist.filter(status=status)
    return render(request, 'bookings/my_bookings.html', {
        'blist': blist, 'status': status, 'STATUS': Booking.STATUS
    })


@login_required
def manage_bookings(request):
    if not request.user.is_provider:
        return redirect('dashboard')
    blist = Booking.objects.filter(provider=request.user).select_related('service', 'customer')
    status = request.GET.get('status', '')
    if status:
        blist = blist.filter(status=status)
    return render(request, 'bookings/manage.html', {
        'blist': blist, 'status': status, 'STATUS': Booking.STATUS
    })


@login_required
@require_POST
def accept_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, provider=request.user, status='pending')
    b.status = 'awaiting_payment'
    b.save()
    try:
        notify(
            b.customer,
            'Booking Accepted! 🎉',
            f'Your booking for "{b.service.title}" has been accepted. Please make payment.',
            'payment'
        )
    except Exception as e:
        logger.warning('Notification error: %s', e)
    messages.success(request, 'Booking accepted! Customer has been notified to pay.')
    return redirect('manage_bookings')


@login_required
@require_POST
def reject_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, provider=request.user, status='pending')
    b.status = 'cancelled'
    b.reject_reason = request.POST.get('reason', 'Provider unavailable')
    b.save()
    try:
        notify(
            b.customer,
            'Booking Declined',
            f'Your booking for "{b.service.title}" was declined. Reason: {b.reject_reason}',
            'warning'
        )
    except Exception as e:
        logger.warning('Notification error: %s', e)
    messages.success(request, 'Booking rejected.')
    return redirect('manage_bookings')


@login_required
@require_POST
def mark_in_progress(request, pk):
    b = get_object_or_404(Booking, pk=pk, provider=request.user, status='confirmed')
    b.status = 'in_progress'
    b.save()
    try:
        notify(
            b.customer,
            'Service In Progress 🔧',
            f'Your service "{b.service.title}" has started!',
            'info'
        )
    except Exception as e:
        logger.warning('Notification error: %s', e)
    messages.success(request, 'Marked as In Progress.')
    return redirect('manage_bookings')


@login_required
@require_POST
def mark_completed(request, pk):
    b = get_object_or_404(Booking, pk=pk, provider=request.user)
    if b.status not in ['confirmed', 'in_progress']:
        messages.error(request, 'Cannot complete this booking at this stage.')
        return redirect('manage_bookings')
    b.status = 'completed'
    b.save()
    try:
        pp = b.provider.provider_profile
        pp.total_earnings += b.provider_earnings
        pp.available_balance += b.provider_earnings
        pp.save(update_fields=['total_earnings', 'available_balance'])
    except Exception as e:
        logger.error('Error crediting provider earnings: %s', e)
    try:
        notify(
            b.customer,
            'Service Completed ✅',
            f'"{b.service.title}" is complete! Please leave a review.',
            'success'
        )
    except Exception as e:
        logger.warning('Notification error: %s', e)
    messages.success(request, f'Completed! ₦{b.provider_earnings:,.0f} credited to your balance.')
    return redirect('manage_bookings')


@login_required
@require_POST
def cancel_booking(request, pk):
    b = get_object_or_404(Booking, pk=pk, customer=request.user)
    if b.status not in ['pending', 'awaiting_payment']:
        messages.error(request, 'This booking cannot be cancelled at this stage.')
        return redirect('booking_detail', pk=pk)
    b.status = 'cancelled'
    b.save()
    try:
        notify(
            b.provider,
            'Booking Cancelled',
            f'{b.customer.display()} cancelled their booking for "{b.service.title}".',
            'warning'
        )
    except Exception as e:
        logger.warning('Notification error: %s', e)
    messages.success(request, 'Booking cancelled.')
    return redirect('my_bookings')


@login_required
def leave_review(request, pk):
    b = get_object_or_404(Booking, pk=pk, customer=request.user, status='completed')
    if hasattr(b, 'review'):
        messages.info(request, 'You have already reviewed this booking.')
        return redirect('booking_detail', pk=pk)
    form = ReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            r = form.save(commit=False)
            r.booking = b
            r.customer = request.user
            r.provider = b.provider
            r.service = b.service
            r.save()
            try:
                b.provider.provider_profile.refresh_rating()
            except Exception as e:
                logger.warning('Could not refresh rating: %s', e)
            messages.success(request, 'Review submitted! Thank you.')
            return redirect('booking_detail', pk=pk)
        except Exception as e:
            logger.exception('Error saving review')
            messages.error(request, 'Could not save review. Please try again.')
    return render(request, 'bookings/review.html', {'b': b, 'form': form})