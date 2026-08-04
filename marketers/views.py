"""
Marketer app views.
marketers/views.py
"""
import uuid
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from marketers.models import Marketer, MarketerCommission, MarketerWithdrawal


# ── Registration ──────────────────────────────────────────────────────────

class MarketerRegisterView(APIView):
    """POST /api/v1/marketers/register/ — register as a marketer"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if hasattr(user, 'marketer_profile'):
            return Response({"detail": "Already registered as a marketer."}, status=400)
        marketer = Marketer.objects.create(user=user)
        return Response({
            "referral_code": marketer.referral_code,
            "wallet_balance": str(marketer.wallet_balance),
            "message": "Welcome to the Nexivo Marketer Program! Share your referral code with event organizers.",
        }, status=201)


# ── Profile & Dashboard ───────────────────────────────────────────────────

class MarketerDashboardView(APIView):
    """GET /api/v1/marketers/dashboard/ — marketer stats"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            marketer = request.user.marketer_profile
        except Marketer.DoesNotExist:
            return Response({"detail": "Not a marketer."}, status=404)

        recent_commissions = marketer.commissions.order_by('-created_at')[:10]
        recent_withdrawals = marketer.withdrawals.order_by('-created_at')[:5]

        return Response({
            "referral_code": marketer.referral_code,
            "wallet_balance": str(marketer.wallet_balance),
            "total_earned": str(marketer.total_earned),
            "total_withdrawn": str(marketer.total_withdrawn),
            "bank_details": {
                "bank_name": marketer.bank_name,
                "account_number": marketer.account_number,
                "account_name": marketer.account_name,
                "is_set": bool(marketer.account_number),
            },
            "recent_commissions": [
                {
                    "event": c.event.title if c.event else "Unknown",
                    "amount": str(c.commission_amount),
                    "date": c.created_at.isoformat(),
                    "status": c.status,
                }
                for c in recent_commissions
            ],
            "recent_withdrawals": [
                {
                    "amount": str(w.amount),
                    "status": w.status,
                    "date": w.created_at.isoformat(),
                }
                for w in recent_withdrawals
            ],
        })


# ── Bank Account ──────────────────────────────────────────────────────────

class MarketerBankAccountView(APIView):
    """POST /api/v1/marketers/bank-account/ — save bank account"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            marketer = request.user.marketer_profile
        except Exception:
            return Response({"detail": "Not a marketer."}, status=404)

        bank_code = request.data.get('bank_code', '').strip()
        account_number = request.data.get('account_number', '').strip()

        if not bank_code or not account_number:
            return Response({"detail": "bank_code and account_number are required."}, status=400)

        # Verify account with Paystack
        try:
            r = requests.get(
                f"https://api.paystack.co/bank/resolve?account_number={account_number}&bank_code={bank_code}",
                headers={"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"},
                timeout=10,
            )
            data = r.json()
            if not data.get('status'):
                return Response({"detail": "Invalid account details. Please check and try again."}, status=400)
            account_name = data['data']['account_name']
        except Exception:
            return Response({"detail": "Could not verify account. Please try again."}, status=400)

        # Create Paystack transfer recipient
        try:
            r = requests.post(
                "https://api.paystack.co/transferrecipient",
                json={
                    "type": "nuban",
                    "name": account_name,
                    "account_number": account_number,
                    "bank_code": bank_code,
                    "currency": "NGN",
                },
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
            recipient_data = r.json()
            recipient_code = recipient_data.get('data', {}).get('recipient_code', '')
        except Exception:
            recipient_code = ''

        marketer.bank_code = bank_code
        marketer.account_number = account_number
        marketer.account_name = account_name
        marketer.paystack_recipient_code = recipient_code
        marketer.save(update_fields=['bank_code', 'account_number', 'account_name', 'paystack_recipient_code'])

        return Response({
            "detail": "Bank account saved successfully.",
            "account_name": account_name,
            "recipient_code": recipient_code,
        })


# ── Withdrawal ────────────────────────────────────────────────────────────

class MarketerWithdrawView(APIView):
    """POST /api/v1/marketers/withdraw/ — withdraw to bank account"""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        try:
            marketer = request.user.marketer_profile
        except Exception:
            return Response({"detail": "Not a marketer."}, status=404)

        if not marketer.paystack_recipient_code:
            return Response({"detail": "Please add your bank account before withdrawing."}, status=400)

        amount = Decimal(str(request.data.get('amount', marketer.wallet_balance)))

        if amount <= 0:
            return Response({"detail": "Invalid amount."}, status=400)

        if amount > marketer.wallet_balance:
            return Response({"detail": f"Insufficient balance. Available: ₦{marketer.wallet_balance}"}, status=400)

        if amount < 100:
            return Response({"detail": "Minimum withdrawal is ₦100."}, status=400)

        # Create withdrawal record
        withdrawal = MarketerWithdrawal.objects.create(
            marketer=marketer,
            amount=amount,
            status=MarketerWithdrawal.Status.PROCESSING,
        )

        # Initiate Paystack transfer
        reference = f"NXM-WD-{uuid.uuid4().hex[:10].upper()}"
        try:
            r = requests.post(
                "https://api.paystack.co/transfer",
                json={
                    "source": "balance",
                    "amount": int(amount * 100),  # Paystack uses kobo
                    "recipient": marketer.paystack_recipient_code,
                    "reason": f"Nexivo Marketer Commission Withdrawal - {marketer.referral_code}",
                    "reference": reference,
                },
                headers={
                    "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            data = r.json()

            if data.get('status'):
                transfer_code = data.get('data', {}).get('transfer_code', '')
                withdrawal.status = MarketerWithdrawal.Status.SUCCESS
                withdrawal.paystack_transfer_code = transfer_code
                withdrawal.paystack_reference = reference
                withdrawal.save()

                # Deduct from wallet
                marketer.wallet_balance -= amount
                marketer.total_withdrawn += amount
                marketer.save(update_fields=['wallet_balance', 'total_withdrawn'])

                return Response({
                    "detail": f"₦{amount:,.0f} transferred to your bank account successfully.",
                    "transfer_code": transfer_code,
                    "new_balance": str(marketer.wallet_balance),
                })
            else:
                withdrawal.status = MarketerWithdrawal.Status.FAILED
                withdrawal.failure_reason = data.get('message', 'Transfer failed')
                withdrawal.save()
                return Response({"detail": data.get('message', 'Transfer failed. Please try again.')}, status=400)

        except Exception as e:
            withdrawal.status = MarketerWithdrawal.Status.FAILED
            withdrawal.failure_reason = str(e)
            withdrawal.save()
            return Response({"detail": "Transfer failed. Please try again later."}, status=500)


# ── Public — validate referral code ──────────────────────────────────────

class ValidateReferralCodeView(APIView):
    """GET /api/v1/marketers/validate/<code>/ — check if referral code is valid"""
    permission_classes = [AllowAny]

    def get(self, request, code):
        try:
            marketer = Marketer.objects.get(referral_code=code.upper(), is_active=True)
            return Response({
                "valid": True,
                "marketer_name": marketer.user.get_full_name() or marketer.user.username,
            })
        except Marketer.DoesNotExist:
            return Response({"valid": False, "detail": "Invalid referral code."}, status=404)