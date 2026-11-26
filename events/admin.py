import io
import re
import urllib.request

from django.contrib import admin
from django.db import transaction
from django.utils import timezone

from events.models import Category, Event, EventGallery, TicketType


class TicketTypeInline(admin.TabularInline):
    model = TicketType
    extra = 0
    fields = ["name", "price", "is_free", "quantity_total", "quantity_remaining", "is_active"]
    readonly_fields = ["quantity_remaining"]


class EventGalleryInline(admin.TabularInline):
    model = EventGallery
    extra = 0
    fields = ["image", "caption", "display_order"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "display_order"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


# ── Ticket recovery from Cloudinary ───────────────────────────────────────
#
# Deleting an Event cascades to its bookings and tickets, but it does NOT
# delete the ticket PDFs already uploaded to Cloudinary. Every PDF prints
# "Ticket: NXV..." plus the holder name and ticket type as real text
# (see tickets/pdf_generation.py), so the original ticket_code values can be
# read back out of them.
#
# That matters because the QR a customer is holding encodes
#   {FRONTEND_URL}/checkin/verify/{ticket_code}.{stamp}/
# where stamp = sha256(ticket_code + SECRET_KEY) — derived, not stored. Recreate
# a Ticket row with the original code and the QR already in their inbox
# validates again. No re-issuing, no new emails.
#
# Requires `pypdf` in requirements.txt.

CODE_LINE = re.compile(r"Ticket:\s*(NXV[0-9A-F]+)", re.IGNORECASE)
TICKET_PDF_PREFIX = "ticket_pdf/"
BATCH_LIMIT = 20  # keep each run inside the web request timeout


def _extract_pdf_lines(pdf_bytes):
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_ticket_pdf(lines, ticket_type_names):
    """
    Returns (ticket_code, holder_name, ticket_type_name) or None.

    The PDF is drawn in a fixed order — event title, date, venue, holder name,
    ticket type, then the code — so the two lines before the ticket type are
    reliable anchors. We locate the ticket type by matching it against the
    event's real ticket type names rather than trusting line positions alone,
    because extractors reorder text more often than they drop it.
    """
    code = None
    for line in lines:
        match = CODE_LINE.search(line)
        if match:
            code = match.group(1).upper()
            break
    if not code:
        return None

    lowered = {name.lower(): name for name in ticket_type_names}
    holder_name = ""
    ticket_type_name = ""
    for index, line in enumerate(lines):
        if line.lower() in lowered:
            ticket_type_name = lowered[line.lower()]
            if index > 0:
                holder_name = lines[index - 1]
            break

    return code, holder_name, ticket_type_name


def _cloudinary_ticket_pdfs():
    """Every PDF under ticket_pdf/ in Cloudinary, newest first."""
    import cloudinary.api

    resources = []
    cursor = None
    while True:
        kwargs = {
            "type": "upload",
            "resource_type": "image",  # Cloudinary serves these PDFs from /image/upload/
            "prefix": TICKET_PDF_PREFIX,
            "max_results": 500,
        }
        if cursor:
            kwargs["next_cursor"] = cursor
        page = cloudinary.api.resources(**kwargs)
        resources.extend(page.get("resources", []))
        cursor = page.get("next_cursor")
        if not cursor:
            break
    resources.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return resources


def _find_user(holder_name):
    """
    Map a printed holder name back to the User who bought the ticket.

    Users are not cascade-deleted with an event, so the accounts created at
    guest checkout are all still present — the name on the PDF is enough to
    find them.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    name = (holder_name or "").strip()
    if not name:
        return None

    parts = name.split()
    if len(parts) >= 2:
        user = User.objects.filter(
            first_name__iexact=parts[0], last_name__iexact=" ".join(parts[1:])
        ).first()
        if user:
            return user
        user = User.objects.filter(
            first_name__iexact=parts[0], last_name__iexact=parts[-1]
        ).first()
        if user:
            return user
    return User.objects.filter(first_name__iexact=name).first()


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        "title", "host", "event_type", "status", "city", "start_datetime",
        "is_featured", "tickets_sold_count", "average_rating",
    ]
    list_filter = ["event_type", "status", "is_featured", "country"]
    search_fields = ["title", "host__email", "city", "venue_name"]
    readonly_fields = [
        "id", "slug", "view_count", "tickets_sold_count", "favorite_count",
        "average_rating", "review_count", "published_at", "created_at", "updated_at",
    ]
    inlines = [TicketTypeInline, EventGalleryInline]
    actions = [
        "suspend_events", "feature_events", "unfeature_events",
        "recover_tickets_from_cloudinary",
    ]

    @admin.action(description="Suspend selected events")
    def suspend_events(self, request, queryset):
        updated = queryset.update(status=Event.Status.SUSPENDED)
        self.message_user(request, f"{updated} event(s) suspended.")

    @admin.action(description="Feature selected events")
    def feature_events(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} event(s) featured.")

    @admin.action(description="Unfeature selected events")
    def unfeature_events(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} event(s) unfeatured.")

    @admin.action(description="🛟 Recover deleted tickets from Cloudinary into this event")
    def recover_tickets_from_cloudinary(self, request, queryset):
        """
        Rebuild Ticket rows for a re-created event by reading the original
        ticket codes out of the PDFs still stored in Cloudinary.

        Select exactly one event — the re-created one. Safe to run repeatedly:
        a ticket code that already exists is skipped, so nobody gets two
        tickets and re-running simply continues where the last run stopped.
        """
        from bookings.models import Booking, BookingItem
        from tickets.models import Ticket

        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one event — the one you re-created.",
                level="error",
            )
            return

        event = queryset.first()
        ticket_types = list(event.ticket_types.all())
        if not ticket_types:
            self.message_user(
                request,
                f"'{event.title}' has no ticket types yet. Create the ticket type first, "
                "then run this again.",
                level="error",
            )
            return

        type_by_name = {t.name.lower(): t for t in ticket_types}
        default_type = ticket_types[0]
        title_prefix = event.title[:30].lower()

        try:
            resources = _cloudinary_ticket_pdfs()
        except Exception as exc:
            self.message_user(request, f"Could not list Cloudinary files: {exc}", level="error")
            return

        existing = set(
            Ticket.objects.filter(ticket_code__isnull=False).values_list("ticket_code", flat=True)
        )

        recovered = 0
        skipped_existing = 0
        unmatched_user = []
        other_events = 0
        failures = 0

        for resource in resources:
            if recovered >= BATCH_LIMIT:
                break

            url = resource.get("secure_url") or resource.get("url")
            if not url:
                continue

            try:
                with urllib.request.urlopen(url, timeout=20) as response:
                    pdf_bytes = response.read()
                lines = _extract_pdf_lines(pdf_bytes)
            except Exception:
                failures += 1
                continue

            # Only touch PDFs belonging to this event. The title is drawn
            # truncated at 30 characters, so compare on that prefix.
            blob = " ".join(lines).lower()
            if title_prefix not in blob:
                other_events += 1
                continue

            parsed = _parse_ticket_pdf(lines, [t.name for t in ticket_types])
            if not parsed:
                failures += 1
                continue

            code, holder_name, ticket_type_name = parsed
            if code in existing:
                skipped_existing += 1
                continue

            user = _find_user(holder_name)
            if user is None:
                unmatched_user.append(f"{code} ({holder_name or 'no name on PDF'})")
                continue

            ticket_type = type_by_name.get((ticket_type_name or "").lower(), default_type)

            try:
                with transaction.atomic():
                    booking = Booking.objects.create(
                        customer=user,
                        event=event,
                        status=Booking.Status.CONFIRMED,
                        subtotal=ticket_type.price,
                        discount_amount=0,
                        processing_fee=0,
                        total_amount=ticket_type.price,
                        confirmed_at=timezone.now(),
                        reserved_until=timezone.now(),
                        customer_name=holder_name or f"{user.first_name} {user.last_name}".strip(),
                        customer_email=user.email,
                        customer_phone=getattr(user, "phone_number", "") or "",
                    )
                    item = BookingItem.objects.create(
                        booking=booking,
                        ticket_type=ticket_type,
                        quantity=1,
                        unit_price=ticket_type.price,
                        line_total=ticket_type.price,
                    )
                    Ticket.objects.create(
                        booking_item=item,
                        event=event,
                        ticket_type=ticket_type,
                        holder=user,
                        holder_name=holder_name or f"{user.first_name} {user.last_name}".strip(),
                        holder_email=user.email,
                        ticket_code=code,          # the original — this is what makes the old QR work
                        status=Ticket.Status.VALID,
                    )
                existing.add(code)
                recovered += 1
            except Exception as exc:
                failures += 1
                self.message_user(request, f"{code}: {exc}", level="error")

        if recovered:
            self.message_user(
                request,
                f"✅ Recovered {recovered} ticket(s) with their ORIGINAL codes — "
                "the QR already in those customers' inboxes will now scan green.",
            )
        if skipped_existing:
            self.message_user(request, f"↷ {skipped_existing} already present, left alone.")
        if other_events:
            self.message_user(request, f"↷ {other_events} PDF(s) belong to other events, ignored.")
        if unmatched_user:
            self.message_user(
                request,
                "⚠️ No matching user account for: " + ", ".join(unmatched_user[:15])
                + ("…" if len(unmatched_user) > 15 else "")
                + " — create the user, then run this again.",
                level="warning",
            )
        if failures:
            self.message_user(request, f"⚠️ {failures} PDF(s) could not be read — check logs.", level="warning")
        if recovered >= BATCH_LIMIT:
            self.message_user(
                request,
                f"Stopped at {BATCH_LIMIT} to stay inside the request timeout. "
                "Run the action again to continue.",
                level="warning",
            )
        if not any([recovered, skipped_existing, unmatched_user, failures]):
            self.message_user(request, "No matching ticket PDFs found in Cloudinary.", level="warning")


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "price", "is_free", "quantity_total", "quantity_remaining", "is_active"]
    list_filter = ["is_free", "is_active", "is_early_bird"]
    search_fields = ["name", "event__title"]
