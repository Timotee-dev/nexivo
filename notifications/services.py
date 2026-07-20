"""
Notification dispatch. HTML email templates are now rendered for each trigger.
WhatsApp sends a short plain-text version.
Synchronous here; wrap in .delay() via config.celery.notify_async when Celery is running.
"""

import logging

from notifications.channels.email_channel import send_email
from notifications.channels.whatsapp_channel import send_whatsapp
from notifications.models import Notification, NotificationPreference

logger = logging.getLogger("nexivo")


def _get_preference(user):
    pref, _ = NotificationPreference.objects.get_or_create(user=user)
    return pref


def _dispatch(*, user, event_type, subject, body, template=None, ctx=None,
              whatsapp_message=None):
    pref = _get_preference(user)

    if pref.email_enabled and user.email:
        n = Notification.objects.create(
            recipient=user, channel=Notification.Channel.EMAIL,
            event_type=event_type, subject=subject, body=body,
            context_data=ctx or {},
        )
        ok, err = send_email(
            to_email=user.email, subject=subject, body=body,
            template=template, context=ctx,
        )
        _record(n, ok, err)

    if pref.whatsapp_enabled and user.phone_number and whatsapp_message:
        n = Notification.objects.create(
            recipient=user, channel=Notification.Channel.WHATSAPP,
            event_type=event_type, subject=subject, body=whatsapp_message,
        )
        ok, err = send_whatsapp(to_phone=user.phone_number, message=whatsapp_message)
        _record(n, ok, err)

    Notification.objects.create(
        recipient=user, channel=Notification.Channel.IN_APP,
        event_type=event_type, subject=subject, body=body,
        status=Notification.Status.SENT,
    )


def _record(notification, success, error):
    from django.utils import timezone
    if success:
        notification.status = Notification.Status.SENT
        notification.sent_at = timezone.now()
    else:
        notification.status = Notification.Status.FAILED
        notification.error_message = error
    notification.save(update_fields=["status", "sent_at", "error_message"])


# ── Triggers ─────────────────────────────────────────────────────────────

def notify_booking_confirmed(booking):
    from tickets.models import Ticket
    tickets = Ticket.objects.filter(booking_item__booking=booking)
    ctx = {
        "customer_name": booking.customer_name,
        "event_title": booking.event.title,
        "event_date": booking.event.start_datetime.strftime("%A, %d %B %Y at %H:%M"),
        "event_location": (
            f"{booking.event.venue_name}, {booking.event.city}"
            if booking.event.is_physical else booking.event.virtual_platform
        ),
        "booking_reference": booking.booking_reference,
        "ticket_count": booking.ticket_count,
        "total_amount": f"{booking.total_amount:,.2f}",
        "tickets": [
            {
                "ticket_code": t.ticket_code,
                "ticket_type_name": t.ticket_type.name,
                "qr_url": t.qr_image.url if t.qr_image else None,
            }
            for t in tickets
        ],
    }

    # Build PDF attachments for each ticket
    attachments = []
    for t in tickets:
        try:
            if t.pdf_file and t.pdf_file.name:
                with open(t.pdf_file.path, "rb") as f:
                    attachments.append((f"ticket-{t.ticket_code}.pdf", f.read(), "application/pdf"))
            else:
                from tickets.pdf import generate_ticket_pdf
                pdf = generate_ticket_pdf(t)
                attachments.append((f"ticket-{t.ticket_code}.pdf", pdf.read(), "application/pdf"))
        except Exception as e:
            logger.warning("Could not attach PDF for ticket %s: %s", t.ticket_code, e)

    pref = _get_preference(booking.customer)
    if pref.email_enabled and booking.customer.email:
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from notifications.channels.email_channel import send_email as _send
        full_ctx = {"frontend_url": __import__("django.conf", fromlist=["settings"]).settings.FRONTEND_URL, **ctx}
        html = render_to_string("emails/booking_confirmation.html", full_ctx)
        _send(
            to_email=booking.customer.email,
            subject=f"Booking confirmed — {booking.event.title}",
            body=strip_tags(html),
            html_body=html,
            attachments=attachments,
        )

    # In-app notification
    Notification.objects.create(
        recipient=booking.customer,
        channel=Notification.Channel.IN_APP,
        event_type=Notification.EventType.BOOKING_CONFIRMATION,
        subject=f"Booking confirmed — {booking.event.title}",
        body=f"Your booking {booking.booking_reference} for {booking.event.title} is confirmed.",
        status=Notification.Status.SENT,
    )

    # WhatsApp
    pref2 = _get_preference(booking.customer)
    if pref2.whatsapp_enabled and booking.customer.phone_number:
        from notifications.channels.whatsapp_channel import send_whatsapp
        send_whatsapp(
            to_phone=booking.customer.phone_number,
            message=f"✅ Booking confirmed! {booking.event.title} · Ref: {booking.booking_reference}",
        )


def notify_payment_successful(payment):
    notify_booking_confirmed(payment.booking)
    from tickets.models import Ticket
    tickets = Ticket.objects.filter(booking_item__booking=payment.booking)
    if tickets.exists():
        notify_tickets_issued(payment.booking, tickets)


def notify_tickets_issued(booking, tickets):
    # Tickets are included in the booking confirmation email; this sends
    # an in-app notification only to avoid duplicate emails.
    Notification.objects.create(
        recipient=booking.customer,
        channel=Notification.Channel.IN_APP,
        event_type=Notification.EventType.TICKET_PURCHASED,
        subject=f"Your tickets for {booking.event.title} are ready",
        body=f"You have {tickets.count()} ticket(s) ready for {booking.event.title}. Download them from your dashboard.",
        status=Notification.Status.SENT,
    )


def notify_payment_failed(booking):
    ctx = {
        "customer_name": booking.customer_name,
        "event_title": booking.event.title,
        "booking_reference": booking.booking_reference,
        "amount": f"{booking.total_amount:,.2f}",
        "gateway": "your selected gateway",
    }
    _dispatch(
        user=booking.customer,
        event_type=Notification.EventType.PAYMENT_FAILED,
        subject=f"Payment not completed — {booking.event.title}",
        body=f"Your payment for booking {booking.booking_reference} could not be completed.",
        template="emails/payment_failed.html",
        ctx=ctx,
        whatsapp_message=f"❌ Payment failed for {booking.event.title}. Please try again.",
    )


def notify_refund_update(refund):
    booking = refund.payment.booking
    ctx = {
        "customer_name": booking.customer_name,
        "event_title": booking.event.title,
        "booking_reference": booking.booking_reference,
        "refund_amount": f"{refund.amount:,.2f}",
        "refund_status": refund.status,
        "rejection_reason": refund.rejection_reason or "",
    }
    _dispatch(
        user=refund.requested_by or booking.customer,
        event_type=Notification.EventType.REFUND_UPDATE,
        subject=f"Refund update — {booking.event.title}",
        body=f"Your refund for booking {booking.booking_reference} is now: {refund.status}.",
        template="emails/refund_update.html",
        ctx=ctx,
        whatsapp_message=f"Refund status for {booking.event.title}: {refund.status}.",
    )


def notify_event_reminder(booking):
    ctx = {
        "customer_name": booking.customer_name,
        "event_title": booking.event.title,
        "event_date": booking.event.start_datetime.strftime("%A, %d %B %Y at %H:%M"),
        "event_location": (
            f"{booking.event.venue_name}, {booking.event.city}"
            if booking.event.is_physical else booking.event.virtual_platform
        ),
        "ticket_count": booking.ticket_count,
    }
    _dispatch(
        user=booking.customer,
        event_type=Notification.EventType.EVENT_REMINDER,
        subject=f"Reminder: {booking.event.title} is tomorrow!",
        body=f"Reminder: {booking.event.title} starts {ctx['event_date']}.",
        template="emails/event_reminder.html",
        ctx=ctx,
        whatsapp_message=f"⏰ Reminder: {booking.event.title} starts tomorrow!",
    )


def notify_ticket_transfer_initiated(transfer):
    from accounts.models import User
    ctx = {
        "from_name": transfer.from_user.first_name or transfer.from_user.username,
        "event_title": transfer.ticket.event.title,
        "event_date": transfer.ticket.event.start_datetime.strftime("%A, %d %B %Y"),
        "ticket_type": transfer.ticket.ticket_type.name,
        "transfer_code": transfer.transfer_code,
        "message": transfer.message or "",
    }
    existing = User.objects.filter(email__iexact=transfer.to_email).first()
    if existing:
        _dispatch(
            user=existing,
            event_type=Notification.EventType.TICKET_TRANSFER_INITIATED,
            subject=f"{ctx['from_name']} sent you a ticket on Nexivo",
            body=f"You've been sent a ticket for {ctx['event_title']}.",
            template="emails/ticket_transfer.html",
            ctx=ctx,
            whatsapp_message=f"🎫 {ctx['from_name']} sent you a ticket for {ctx['event_title']}!",
        )
    else:
        send_email(
            to_email=transfer.to_email,
            subject=f"{ctx['from_name']} sent you a ticket on Nexivo",
            body=f"You've been sent a ticket for {ctx['event_title']}.",
            template="emails/ticket_transfer.html",
            context=ctx,
        )


def notify_ticket_transferred(transfer):
    Notification.objects.create(
        recipient=transfer.from_user,
        channel=Notification.Channel.IN_APP,
        event_type=Notification.EventType.TICKET_TRANSFERRED,
        subject=f"Ticket transferred to {transfer.to_email}",
        body=f"Your ticket for {transfer.ticket.event.title} was accepted by {transfer.to_email}.",
        status=Notification.Status.SENT,
    )


def notify_payout_completed(payout):
    ctx = {
        "host_name": payout.host.first_name or payout.host.username,
        "amount": f"{payout.amount:,.2f}",
        "currency": payout.currency,
        "gateway": payout.gateway,
        "completed_at": payout.completed_at.strftime("%d %B %Y") if payout.completed_at else "—",
    }
    _dispatch(
        user=payout.host,
        event_type=Notification.EventType.PAYOUT_COMPLETED,
        subject=f"Payout of ₦{ctx['amount']} completed",
        body=f"Your payout of {payout.amount} {payout.currency} via {payout.gateway} is complete.",
        template="emails/payout_completed.html",
        ctx=ctx,
        whatsapp_message=f"💰 Payout of ₦{ctx['amount']} completed!",
    )


def notify_host_verification_update(host_profile):
    status = host_profile.nin_verification_status
    _dispatch(
        user=host_profile.user,
        event_type=Notification.EventType.HOST_VERIFICATION_UPDATE,
        subject="Update on your host verification",
        body=f"Your NIN verification is now: {status}.",
        whatsapp_message=f"Your NIN verification status: {status}.",
    )