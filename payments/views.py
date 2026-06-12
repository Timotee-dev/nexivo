import uuid, json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings
from .models import Payment, Withdrawal
from bookings.models import Booking
from accounts.views import notify

@login_required
def initiate_payment(request, pk):
    b=get_object_or_404(Booking,pk=pk,customer=request.user,status='awaiting_payment')
    ref='NXR-'+uuid.uuid4().hex[:16].upper()
    Payment.objects.create(booking=b,amount=b.amount,reference=ref,commission=b.commission,provider_payout=b.provider_earnings)
    return render(request,'payments/pay.html',{'b':b,'ref':ref,'pk_key':settings.PAYSTACK_PUBLIC_KEY})

@login_required
def verify_payment(request, ref):
    payment=get_object_or_404(Payment,reference=ref,booking__customer=request.user)
    if payment.status=='success': return redirect('receipt',ref=ref)
    pk=settings.PAYSTACK_PUBLIC_KEY
    if 'demo' in pk or 'test' in pk:
        payment.status='success'; payment.paid_at=timezone.now(); payment.save()
        b=payment.booking; b.status='confirmed'; b.save()
        notify(b.provider,'Payment Received! 💰',f'₦{b.amount:,.0f} received for "{b.service.title}".','payment')
        notify(b.customer,'Payment Successful ✅',f'Booking for "{b.service.title}" confirmed!','success')
        messages.success(request,'Payment successful! Booking confirmed.')
        return redirect('receipt',ref=ref)
    # Real Paystack
    import urllib.request
    secret=getattr(settings,'PAYSTACK_SECRET_KEY','')
    req=urllib.request.Request(f'https://api.paystack.co/transaction/verify/{ref}',headers={'Authorization':f'Bearer {secret}'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:
            data=json.loads(r.read())
        if data.get('status') and data['data']['status']=='success':
            payment.status='success'; payment.paid_at=timezone.now(); payment.save()
            b=payment.booking; b.status='confirmed'; b.save()
            messages.success(request,'Payment verified!')
        else:
            payment.status='failed'; payment.save(); messages.error(request,'Payment failed.')
    except Exception as e:
        messages.error(request,f'Verification error: {e}')
    return redirect('receipt',ref=ref)

@login_required
def receipt(request, ref):
    payment=get_object_or_404(Payment,reference=ref)
    b=payment.booking
    if request.user not in [b.customer,b.provider] and not request.user.is_platform_admin: return redirect('dashboard')
    return render(request,'payments/receipt.html',{'payment':payment,'b':b,'pct':settings.PLATFORM_COMMISSION})

@login_required
def withdrawals(request):
    if not request.user.is_provider: return redirect('dashboard')
    pp=request.user.provider_profile
    if request.method=='POST':
        try:
            amt=float(request.POST.get('amount',0))
            if amt<=0 or amt>float(pp.available_balance): raise ValueError
            Withdrawal.objects.create(provider=request.user,amount=amt,bank_name=pp.bank_name or 'N/A',account_number=pp.account_number or 'N/A',account_name=pp.account_name or request.user.display())
            pp.available_balance-=amt; pp.save(update_fields=['available_balance'])
            messages.success(request,f'Withdrawal request for ₦{amt:,.0f} submitted!')
        except: messages.error(request,'Invalid amount or insufficient balance.')
        return redirect('withdrawals')
    wds=Withdrawal.objects.filter(provider=request.user)
    return render(request,'payments/withdrawals.html',{'pp':pp,'wds':wds})
