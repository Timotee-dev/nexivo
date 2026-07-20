"""
Reconciliation: compares our local Payment records against each gateway's
transaction list for a given date range and records discrepancies for
super-admin/finance review. Intended to run on a daily schedule.
"""

from decimal import Decimal

from django.utils import timezone

from payments.gateways.registry import get_gateway_client
from payments.models import Payment, ReconciliationRecord


def reconcile_gateway(gateway, from_date=None, to_date=None):
    to_date = to_date or timezone.now()
    from_date = from_date or (to_date - timezone.timedelta(days=1))
    run_date = to_date.date()

    client = get_gateway_client(gateway)
    gateway_transactions = client.list_transactions(from_date=from_date, to_date=to_date)

    gateway_by_ref = {}
    for txn in gateway_transactions:
        ref = txn.get("reference") or txn.get("tx_ref") or txn.get("id")
        gateway_by_ref[str(ref)] = txn

    local_payments = Payment.objects.filter(
        gateway=gateway, status=Payment.Status.SUCCESSFUL,
        paid_at__gte=from_date, paid_at__lte=to_date,
    )
    local_by_ref = {p.gateway_reference: p for p in local_payments}

    records = []

    for ref, payment in local_by_ref.items():
        gw_txn = gateway_by_ref.get(ref)
        if not gw_txn:
            records.append(ReconciliationRecord(
                gateway=gateway, payment=payment, gateway_transaction_id=ref,
                local_amount=payment.amount, gateway_amount=None,
                discrepancy_type=ReconciliationRecord.Discrepancy.MISSING_ON_GATEWAY,
                run_date=run_date,
                notes="Marked successful locally but not found in gateway transaction list for this period.",
            ))
            continue

        gw_amount = Decimal(str(gw_txn.get("amount", 0)))
        if gateway in (Payment.Gateway.PAYSTACK,):
            gw_amount = gw_amount / 100  # paystack reports in kobo

        if abs(gw_amount - payment.amount) > Decimal("0.01"):
            records.append(ReconciliationRecord(
                gateway=gateway, payment=payment, gateway_transaction_id=ref,
                local_amount=payment.amount, gateway_amount=gw_amount,
                discrepancy_type=ReconciliationRecord.Discrepancy.AMOUNT_MISMATCH,
                run_date=run_date,
            ))

    for ref, gw_txn in gateway_by_ref.items():
        if ref not in local_by_ref:
            gw_amount = Decimal(str(gw_txn.get("amount", 0)))
            if gateway in (Payment.Gateway.PAYSTACK,):
                gw_amount = gw_amount / 100
            records.append(ReconciliationRecord(
                gateway=gateway, payment=None, gateway_transaction_id=ref,
                local_amount=None, gateway_amount=gw_amount,
                discrepancy_type=ReconciliationRecord.Discrepancy.MISSING_LOCALLY,
                run_date=run_date,
                notes="Found on gateway but no matching local payment record.",
            ))

    ReconciliationRecord.objects.bulk_create(records)
    return {"gateway": gateway, "discrepancies_found": len(records), "run_date": str(run_date)}


def reconcile_all_gateways(from_date=None, to_date=None):
    return [
        reconcile_gateway(gw, from_date, to_date)
        for gw in [Payment.Gateway.PAYSTACK, Payment.Gateway.FLUTTERWAVE, Payment.Gateway.STRIPE]
    ]
