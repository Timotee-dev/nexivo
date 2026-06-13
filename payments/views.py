import uuid
import json
import urllib.request
import urllib.error
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse

from .models import Payment, Withdrawal
from bookings.models import Booking
from accounts.views import notify

logger = logging.getLogger(__name__)


def _is_demo_mode():
    pk = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
    sk = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    return (not sk) or ('demo' in pk) or (pk == 'pk_test_demo')


def _paystack_verify(reference):
    """
    Call the Paystack verify endpoint.
    Returns (True, data_dict) on success or (False, error_message) on failure.
    """
    secret = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    if not secret:
        return False, 'No Paystack secret key configured.'

    url = f'https://api.paystack.co/transaction/verify/{reference}'
    req = urllib.request.Request(
        url,
        headers={
            'Authorization': f'Bearer {secret}',
            'Content-Type': 'application/json',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            data = json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        logger.error('Paystack HTTPError %s: %s', e.code, body)
        return False, f'Paystack returned HTTP {e.code}. Please contact support.'
    except urllib.error.URLError as e:
        logger.error('Paystack URLError: %s', e.reason)
        return False, 'Could not reach Paystack. Please check your internet connection.'
    except json.JSONDecodeError:
        logger.error('Paystack returned non-JSON response')
        return False, 'Unexpected response from Paystack. Please try again.'
    except Exception as e:
        logger.exception('Unexpected error verifying payment')
        return False, f'Unexpected error: {str(e)}'

    if not data.get('status'):
        msg = data.get('message', 'Verification failed.')
        return False, msg

    tx = data.get('data', {})
    if tx.get('status') == 'success':
        return True, tx
    else:
        return False, f"Payment status is '{tx.get('status', 'unknown')}'. Not successful."


@login_required
def initiate_payment(request, pk):
    """Create a pending Payment record and show the pay page."""
    b = get_object_or_404(
        Booking, pk=pk,
        customer=request.user,
        status='awaiting_payment'
    )

    # Reuse existing pending payment if one exists
    existing = Payment.objects.filter(booking=b, status='pending').first()
    if existing:
        ref = existing.reference
    else:
        ref = 'NXR-' + uuid.uuid4().hex[:16].upper()
        Payment.objects.create(
            booking=b,
            amount=b.amount,
            reference=ref,
            commission=b.commission,
            provider_payout=b.provider_earnings,
        )

    return render(request, 'payments/pay.html', {
        'b': b,
        'ref': ref,
        'pk_key': settings.PAYSTACK_PUBLIC_KEY,
        'amount_kobo': int(b.amount * 100),   # Paystack uses kobo
        'customer_email': request.user.email,
        'is_demo': _is_demo_mode(),
    })


@login_required
def verify_payment(request, ref):
    """Verify payment with Paystack and confirm the booking."""
    payment = get_object_or_404(
        Payment,
        reference=ref,
        booking__customer=request.user,
    )

    # Already verified — just go to receipt
    if payment.status == 'success':
        return redirect('receipt', ref=ref)

    # Already failed — show error
    if payment.status == 'failed':
        messages.error(request, 'This payment has already been marked as failed.')
        return redirect('booking_detail', pk=payment.booking.pk)

    demo = _is_demo_mode()

    if demo:
        # ── Demo mode: auto-confirm ──
        payment.status = 'success'
        payment.paid_at = timezone.now()
        payment.save()

        b = payment.booking
        b.status = 'confirmed'
        b.save()

        notify(
            b.provider,
            'Payment Received! 💰',
            f'₦{b.amount:,.0f} received for "{b.service.title}". Booking confirmed.',
            'payment',
        )
        notify(
            b.customer,
            'Payment Successful ✅',
            f'Your booking for "{b.service.title}" is confirmed!',
            'success',
        )
        messages.success(request, '✅ Payment successful! Your booking is confirmed.')
        return redirect('receipt', ref=ref)

    # ── Real Paystack verification ──
    ok, result = _paystack_verify(ref)

    if ok:
        payment.status = 'success'
        payment.paid_at = timezone.now()
        # Store useful Paystack metadata
        payment.paystack_data = {
            'id': result.get('id'),
            'channel': result.get('channel'),
            'currency': result.get('currency'),
            'paid_at': result.get('paid_at'),
            'gateway_response': result.get('gateway_response'),
        }
        payment.save()

        b = payment.booking
        b.status = 'confirmed'
        b.save()

        notify(
            b.provider,
            'Payment Received! 💰',
            f'₦{b.amount:,.0f} received for "{b.service.title}". Booking confirmed.',
            'payment',
        )
        notify(
            b.customer,
            'Payment Successful ✅',
            f'Your booking for "{b.service.title}" is confirmed!',
            'success',
        )
        messages.success(request, '✅ Payment verified and booking confirmed!')

    else:
        payment.status = 'failed'
        payment.save()
        logger.warning('Payment %s failed: %s', ref, result)
        messages.error(request, f'Payment could not be verified: {result}')

    return redirect('receipt', ref=ref)


@login_required
def receipt(request, ref):
    """Show the payment receipt."""
    payment = get_object_or_404(Payment, reference=ref)
    b = payment.booking

    # Only customer, provider, or admin can see receipt
    if (request.user != b.customer
            and request.user != b.provider
            and not request.user.is_platform_admin):
        messages.error(request, 'You do not have access to this receipt.')
        return redirect('dashboard')

    return render(request, 'payments/receipt.html', {
        'payment': payment,
        'b': b,
        'pct': settings.PLATFORM_COMMISSION,
    })


@login_required
def withdrawals(request):
    """Provider withdrawal request page."""
    if not request.user.is_provider:
        messages.error(request, 'Only providers can request withdrawals.')
        return redirect('dashboard')

    pp = request.user.provider_profile

    if request.method == 'POST':
        raw = request.POST.get('amount', '').strip()
        try:
            amt = float(raw)
            if amt <= 0:
                raise ValueError('Amount must be greater than zero.')
            if amt > float(pp.available_balance):
                raise ValueError(
                    f'Amount ₦{amt:,.0f} exceeds available balance ₦{pp.available_balance:,.0f}.'
                )
            if amt < 1000:
                raise ValueError('Minimum withdrawal is ₦1,000.')

            Withdrawal.objects.create(
                provider=request.user,
                amount=amt,
                bank_name=pp.bank_name or 'Not Set',
                account_number=pp.account_number or 'Not Set',
                account_name=pp.account_name or request.user.display(),
            )
            pp.available_balance -= amt
            pp.save(update_fields=['available_balance'])
            messages.success(request, f'Withdrawal request for ₦{amt:,.0f} submitted! We will process it shortly.')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.exception('Error creating withdrawal')
            messages.error(request, 'Something went wrong. Please try again.')

        return redirect('withdrawals')

    wds = Withdrawal.objects.filter(provider=request.user)
    return render(request, 'payments/withdrawals.html', {'pp': pp, 'wds': wds})