"""
affiliates/views.py — API endpoints for the host affiliate program
"""
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from affiliates.models import AffiliateCommission, AffiliateWithdrawal, EventAffiliate


# ── Host manages affiliates ───────────────────────────────────────────────────

class EventAffiliateListCreateView(APIView):
    """
    GET /api/v1/affiliates/events/<event_slug>/
    POST /api/v1/affiliates/events/<event_slug>/
    Host creates and lists affiliates for their event
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        from events.models import Event
        event = Event.objects.filter(slug=slug, host=request.user).first()
        if not event:
            return Response({"detail": "Event not found."}, status=404)

        affiliates = EventAffiliate.objects.filter(event=event).order_by('-created_at')
        data = [
            {
                "id": str(a.id),
                "affiliate_name": a.affiliate_name,
                "affiliate_email": a.affiliate_email,
                "affiliate_phone": a.affiliate_phone,
                "referral_code": a.referral_code,
                "commission_rate": str(a.commission_rate),
                "wallet_balance": str(a.wallet_balance),
                "total_earned": str(a.total_earned),
                "affiliate_link": a.affiliate_link,
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat(),
            }
            for a in affiliates
        ]
        return Response({"results": data})

    def post(self, request, slug):
        from events.models import Event
        event = Event.objects.filter(slug=slug, host=request.user).first()
        if not event:
            return Response({"detail": "Event not found or you are not the host."}, status=404)

        name = request.data.get('affiliate_name', '').strip()
        email = request.data.get('affiliate_email', '').strip()
        phone = request.data.get('affiliate_phone', '').strip()
        commission_rate = request.data.get('commission_rate')

        if not name:
            return Response({"detail": "affiliate_name is required."}, status=400)
        if not commission_rate:
            return Response({"detail": "commission_rate is required."}, status=400)

        try:
            rate = Decimal(str(commission_rate))
            if rate <= 0 or rate > 50:
                return Response({"detail": "Commission rate must be between 1% and 50%."}, status=400)
        except Exception:
            return Response({"detail": "Invalid commission rate."}, status=400)

        # Check if affiliate already exists for this event
        if email and EventAffiliate.objects.filter(event=event, affiliate_email=email).exists():
            return Response({"detail": "This affiliate is already added to this event."}, status=400)

        affiliate = EventAffiliate.objects.create(
            event=event,
            host=request.user,
            affiliate_name=name,
            affiliate_email=email,
            affiliate_phone=phone,
            commission_rate=rate,
        )

        return Response({
            "id": str(affiliate.id),
            "affiliate_name": affiliate.affiliate_name,
            "referral_code": affiliate.referral_code,
            "commission_rate": str(affiliate.commission_rate),
            "affiliate_link": affiliate.affiliate_link,
            "message": f"Affiliate created! Share this link: {affiliate.affiliate_link}",
        }, status=201)


class EventAffiliateDetailView(APIView):
    """
    PATCH /api/v1/affiliates/<affiliate_id>/ — host updates commission or deactivates
    DELETE /api/v1/affiliates/<affiliate_id>/ — host removes affiliate
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, affiliate_id):
        try:
            affiliate = EventAffiliate.objects.get(id=affiliate_id, host=request.user)
        except EventAffiliate.DoesNotExist:
            return Response({"detail": "Affiliate not found."}, status=404)

        if 'commission_rate' in request.data:
            try:
                rate = Decimal(str(request.data['commission_rate']))
                if rate <= 0 or rate > 50:
                    return Response({"detail": "Commission rate must be between 1% and 50%."}, status=400)
                affiliate.commission_rate = rate
            except Exception:
                return Response({"detail": "Invalid commission rate."}, status=400)

        if 'is_active' in request.data:
            affiliate.is_active = bool(request.data['is_active'])

        affiliate.save()
        return Response({"detail": "Affiliate updated.", "commission_rate": str(affiliate.commission_rate)})

    def delete(self, request, affiliate_id):
        try:
            affiliate = EventAffiliate.objects.get(id=affiliate_id, host=request.user)
        except EventAffiliate.DoesNotExist:
            return Response({"detail": "Affiliate not found."}, status=404)
        affiliate.delete()
        return Response({"detail": "Affiliate removed."}, status=204)


# ── Affiliate views their own dashboard ──────────────────────────────────────

class AffiliateDashboardView(APIView):
    """
    GET /api/v1/affiliates/my/
    Affiliate sees all their affiliate programs across events
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        affiliates = EventAffiliate.objects.filter(
            affiliate_user=request.user
        ).select_related('event').order_by('-created_at')

        if not affiliates.exists():
            # Also check by email
            affiliates = EventAffiliate.objects.filter(
                affiliate_email=request.user.email
            ).select_related('event').order_by('-created_at')

        data = [
            {
                "id": str(a.id),
                "event_title": a.event.title,
                "event_slug": a.event.slug,
                "referral_code": a.referral_code,
                "commission_rate": str(a.commission_rate),
                "wallet_balance": str(a.wallet_balance),
                "total_earned": str(a.total_earned),
                "affiliate_link": a.affiliate_link,
                "is_active": a.is_active,
            }
            for a in affiliates
        ]
        return Response({"results": data, "count": len(data)})


# ── Public — track referral click ────────────────────────────────────────────

class TrackAffiliateClickView(APIView):
    """
    POST /api/v1/affiliates/track/
    Called when someone visits an event page via affiliate link.
    Stores the affiliate code in session so it persists through checkout.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get('ref', '').strip().upper()
        slug = request.data.get('event_slug', '').strip()

        if not code or not slug:
            return Response({"detail": "ref and event_slug are required."}, status=400)

        try:
            affiliate = EventAffiliate.objects.get(
                referral_code=code, event__slug=slug, is_active=True
            )
            # Store in session
            request.session[f'aff_{slug}'] = code
            request.session.modified = True
            return Response({
                "valid": True,
                "affiliate_name": affiliate.affiliate_name,
            })
        except EventAffiliate.DoesNotExist:
            return Response({"valid": False}, status=404)


# ── Validate referral code (public) ──────────────────────────────────────────

class ValidateAffiliateCodeView(APIView):
    """GET /api/v1/affiliates/validate/<code>/"""
    permission_classes = [AllowAny]

    def get(self, request, code):
        try:
            affiliate = EventAffiliate.objects.select_related('event').get(
                referral_code=code.upper(), is_active=True
            )
            return Response({
                "valid": True,
                "affiliate_name": affiliate.affiliate_name,
                "event_title": affiliate.event.title,
                "event_slug": affiliate.event.slug,
                "commission_rate": str(affiliate.commission_rate),
            })
        except EventAffiliate.DoesNotExist:
            return Response({"valid": False, "detail": "Invalid referral code."}, status=404)


# ── Affiliate adds bank account ───────────────────────────────────────────────

class AffiliateBankAccountView(APIView):
    """POST /api/v1/affiliates/<affiliate_id>/bank-account/"""
    permission_classes = [AllowAny]  # Affiliates may not be registered users

    def post(self, request, affiliate_id):
        try:
            affiliate = EventAffiliate.objects.get(id=affiliate_id)
        except EventAffiliate.DoesNotExist:
            return Response({"detail": "Affiliate not found."}, status=404)

        bank_code = request.data.get('bank_code', '').strip()
        account_number = request.data.get('account_number', '').strip()

        if not bank_code or not account_number:
            return Response({"detail": "bank_code and account_number are required."}, status=400)

        # Verify with Paystack
        try:
            r = requests.get(
                f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}",
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                timeout=10,
            )
            data = r.json()
            if not data.get('status'):
                return Response({"detail": "Invalid account details."}, status=400)
            account_name = data['data']['account_name']
        except Exception:
            return Response({"detail": "Could not verify account. Please try again."}, status=400)

        # Create Paystack Transfer Recipient
        try:
            r = requests.post(
                "https://api.paystack.co/transferrecipient",
                json={"type": "nuban", "name": account_name, "account_number": account_number, "bank_code": bank_code, "currency": "NGN"},
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"},
                timeout=10,
            )
            recipient_code = r.json().get('data', {}).get('recipient_code', '')
        except Exception:
            recipient_code = ''

        affiliate.bank_code = bank_code
        affiliate.account_number = account_number
        affiliate.account_name = account_name
        affiliate.paystack_recipient_code = recipient_code
        affiliate.save(update_fields=['bank_code', 'account_number', 'account_name', 'paystack_recipient_code'])

        return Response({"detail": "Bank account saved.", "account_name": account_name})


# ── Affiliate withdraws earnings ─────────────────────────────────────────────

class AffiliateWithdrawView(APIView):
    """POST /api/v1/affiliates/<affiliate_id>/withdraw/"""
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request, affiliate_id):
        try:
            affiliate = EventAffiliate.objects.get(id=affiliate_id)
        except EventAffiliate.DoesNotExist:
            return Response({"detail": "Affiliate not found."}, status=404)

        if not affiliate.paystack_recipient_code:
            return Response({"detail": "Please add your bank account before withdrawing."}, status=400)

        amount = Decimal(str(request.data.get('amount', affiliate.wallet_balance)))

        if amount <= 0:
            return Response({"detail": "Invalid amount."}, status=400)
        if amount > affiliate.wallet_balance:
            return Response({"detail": f"Insufficient balance. Available: ₦{affiliate.wallet_balance}"}, status=400)
        if amount < 100:
            return Response({"detail": "Minimum withdrawal is ₦100."}, status=400)

        withdrawal = AffiliateWithdrawal.objects.create(
            affiliate=affiliate, amount=amount, status=AffiliateWithdrawal.Status.PROCESSING,
        )

        reference = f"NXA-WD-{uuid.uuid4().hex[:10].upper()}"
        try:
            r = requests.post(
                "https://api.paystack.co/transfer",
                json={
                    "source": "balance",
                    "amount": int(amount * 100),
                    "recipient": affiliate.paystack_recipient_code,
                    "reason": f"Nexivo Affiliate Commission — {affiliate.event.title}",
                    "reference": reference,
                },
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}", "Content-Type": "application/json"},
                timeout=15,
            )
            data = r.json()
            if data.get('status'):
                withdrawal.status = AffiliateWithdrawal.Status.SUCCESS
                withdrawal.paystack_transfer_code = data.get('data', {}).get('transfer_code', '')
                withdrawal.save()
                affiliate.wallet_balance -= amount
                affiliate.total_withdrawn += amount
                affiliate.save(update_fields=['wallet_balance', 'total_withdrawn'])
                return Response({"detail": f"₦{amount:,.0f} transferred successfully.", "new_balance": str(affiliate.wallet_balance)})
            else:
                withdrawal.status = AffiliateWithdrawal.Status.FAILED
                withdrawal.failure_reason = data.get('message', '')
                withdrawal.save()
                return Response({"detail": data.get('message', 'Transfer failed.')}, status=400)
        except Exception as e:
            withdrawal.status = AffiliateWithdrawal.Status.FAILED
            withdrawal.failure_reason = str(e)
            withdrawal.save()
            return Response({"detail": "Transfer failed. Please try again."}, status=500)