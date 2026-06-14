import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

from .models import Payment, Withdrawal
from bookings.models import Booking
from accounts.views import notify
from accounts.paystack import (
    create_subaccount, initialize_transaction, verify_transaction,
    get_bank_list, resolve_account,
)

logger = logging.getLogger(__name__)


def _is_demo_mode():
    pk = getattr(settings, 'PAYSTACK_PUBLIC_KEY', '')
    sk = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
    return (not sk) or ('demo' in pk) or (pk == 'pk_test_demo')


def _confirm_payment(payment):
    """Mark payment success, confirm booking, notify both parties."""
    payment.status = 'success'
    payment.paid_at = timezone.now()
    payment.save()

    b = payment.booking
    b.status = 'confirmed'
    b.save()

    # Notify provider
    try:
        notify(
            b.provider,
            'Payment Received! 💰',
            f'₦{payment.provider_payout:,.0f} payment received for "{b.service.title}" '
            f'from {b.customer.display()}. Booking #{b.ref} is confirmed. '
            f'Funds will be settled to your bank account by Paystack.',
            'payment'
        )
    except Exception as e:
        logger.warning('Provider notification error: %s', e)

    # Notify customer
    try:
        notify(
            b.customer,
            'Payment Successful ✅',
            f'Your payment of ₦{b.amount:,.0f} for "{b.service.title}" was successful. '
            f'Booking #{b.ref} confirmed!',
            'success'
        )
    except Exception as e:
        logger.warning('Customer notification error: %s', e)


def _ensure_subaccount(provider):
    """
    Make sure the provider has a Paystack subaccount.
    Returns (ok, subaccount_code or error message).
    """
    pp = provider.provider_profile

    if pp.paystack_subaccount_code:
        return True, pp.paystack_subaccount_code

    if not pp.bank_name or not pp.account_number:
        return False, 'Provider has not added bank details yet.'

    # bank_name is expected to store the Paystack bank code (e.g. "058" for GTBank)
    # If it's not a code, this will fail gracefully and the provider needs to re-save
    # their bank details using the bank selector.
    ok, result = create_subaccount(
        business_name=pp.business_name or provider.display(),
        bank_code=pp.bank_name,
        account_number=pp.account_number,
        percentage_charge=settings.PLATFORM_COMMISSION,
    )
    if ok:
        pp.paystack_subaccount_code = result
        pp.save(update_fields=['paystack_subaccount_code'])
        return True, result
    return False, result


@login_required
def initiate_payment(request, pk):
    b = get_object_or_404(Booking, pk=pk, customer=request.user, status='awaiting_payment')

    existing = Payment.objects.filter(booking=b, status='pending').first()

    if _is_demo_mode():
        if existing:
            ref = existing.reference
        else:
            import uuid
            ref = 'NXR-' + uuid.uuid4().hex[:16].upper()
            Payment.objects.create(
                booking=b, amount=b.amount, reference=ref,
                commission=b.commission, provider_payout=b.provider_earnings,
            )
        return render(request, 'payments/pay.html', {
            'b': b, 'ref': ref, 'is_demo': True,
        })

    # ── Real Paystack split payment ──
    ok, sub_code = _ensure_subaccount(b.provider)
    if not ok:
        messages.error(
            request,
            f"Payment cannot be processed: {sub_code}. "
            f"Ask the provider to add valid bank details in their profile."
        )
        return redirect('booking_detail', pk=b.pk)

    if existing and existing.paystack_data.get('authorization_url'):
        return redirect(existing.paystack_data['authorization_url'])

    import uuid
    ref = 'NXR-' + uuid.uuid4().hex[:16].upper()
    payment = Payment.objects.create(
        booking=b, amount=b.amount, reference=ref,
        commission=b.commission, provider_payout=b.provider_earnings,
    )

    callback_url = request.build_absolute_uri(
        f'/payments/verify/{ref}/'
    )

    ok, data = initialize_transaction(
        email=request.user.email,
        amount_kobo=int(b.amount * 100),
        reference=ref,
        subaccount_code=sub_code,
        platform_percentage=settings.PLATFORM_COMMISSION,
        callback_url=callback_url,
    )

    if not ok:
        payment.status = 'failed'
        payment.save()
        messages.error(request, f'Could not start payment: {data}')
        return redirect('booking_detail', pk=b.pk)

    payment.paystack_data = {'authorization_url': data.get('authorization_url')}
    payment.save()

    return redirect(data['authorization_url'])


@login_required
def verify_payment(request, ref):
    payment = get_object_or_404(Payment, reference=ref, booking__customer=request.user)

    if payment.status == 'success':
        return redirect('receipt', ref=ref)

    if payment.status == 'failed':
        messages.error(request, 'This payment was marked as failed. Please contact support.')
        return redirect('booking_detail', pk=payment.booking.pk)

    if _is_demo_mode():
        _confirm_payment(payment)
        messages.success(request, '✅ Payment successful! Booking confirmed.')
        return redirect('receipt', ref=ref)

    ok, result = verify_transaction(ref)
    if ok:
        payment.paystack_data.update({
            'id': result.get('id'),
            'channel': result.get('channel'),
            'gateway_response': result.get('gateway_response'),
            'paid_at': result.get('paid_at'),
        })
        _confirm_payment(payment)
        messages.success(request, '✅ Payment verified! Booking confirmed.')
    else:
        payment.status = 'failed'
        payment.save()
        logger.warning('Payment %s failed: %s', ref, result)
        messages.error(request, f'Payment could not be verified: {result}')

    return redirect('receipt', ref=ref)


@login_required
def receipt(request, ref):
    payment = get_object_or_404(Payment, reference=ref)
    b = payment.booking
    if request.user != b.customer and request.user != b.provider and not request.user.is_platform_admin:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    return render(request, 'payments/receipt.html', {
        'payment': payment, 'b': b, 'pct': settings.PLATFORM_COMMISSION,
    })


@login_required
def withdrawals(request):
    """
    With split payments, providers get paid directly to their bank account
    by Paystack on each transaction. This page now shows payout history
    instead of manual withdrawal requests.
    """
    if not request.user.is_provider:
        messages.error(request, 'Only providers can view this page.')
        return redirect('dashboard')

    pp = request.user.provider_profile
    payments = Payment.objects.filter(
        booking__provider=request.user, status='success'
    ).select_related('booking', 'booking__service').order_by('-paid_at')

    return render(request, 'payments/withdrawals.html', {
        'pp': pp,
        'payments': payments,
        'has_subaccount': bool(pp.paystack_subaccount_code),
    })


@login_required
def bank_setup(request):
    """Provider sets up their bank account for direct Paystack payouts."""
    if not request.user.is_provider:
        return redirect('dashboard')

    pp = request.user.provider_profile
    banks = get_bank_list()

    if request.method == 'POST':
        bank_code = request.POST.get('bank_code', '').strip()
        account_number = request.POST.get('account_number', '').strip()
        bank_name_display = request.POST.get('bank_name_display', '').strip()

        if not bank_code or not account_number:
            messages.error(request, 'Please select a bank and enter account number.')
            return redirect('bank_setup')

        ok, account_name = resolve_account(account_number, bank_code)
        if not ok:
            messages.error(request, f'Could not verify account: {account_name}')
            return redirect('bank_setup')

        pp.bank_name = bank_code
        pp.account_number = account_number
        pp.account_name = account_name
        pp.paystack_subaccount_code = ''  # reset so it's recreated with new details
        pp.save(update_fields=['bank_name', 'account_number', 'account_name', 'paystack_subaccount_code'])

        messages.success(request, f'Bank account verified: {account_name}. You can now receive payments!')
        return redirect('withdrawals')

    return render(request, 'payments/bank_setup.html', {'pp': pp, 'banks': banks})
