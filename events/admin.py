import base64
import logging
import re
import time
import urllib.request
import zlib

from django.contrib import admin
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("nexivo")

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
# No third-party PDF library is needed. ReportLab writes each visible string as
# a `(text) Tj` operator inside a content stream filtered through
# /ASCII85Decode then /FlateDecode, so the standard library can undo both and
# read the strings directly. That keeps the recovery working on a deploy where
# an extra requirement has not been installed.

CODE_LINE = re.compile(r"Ticket:\s*(NXV[0-9A-F]+)", re.IGNORECASE)
TICKET_PDF_PREFIX = "ticket_pdf/"

# A web request gets killed by the server long before 66 PDFs can be fetched,
# so each run takes a small bite and stops. The wall-clock budget is the real
# guard — BATCH_LIMIT alone is not enough, because a slow network makes even a
# few downloads overrun. Each recovered ticket records the Cloudinary file it
# came from, so later runs skip it WITHOUT downloading it again; that is what
# lets repeated runs make progress instead of redoing the same work.
BATCH_LIMIT = 8
TIME_BUDGET_SECONDS = 20
DOWNLOAD_TIMEOUT_SECONDS = 8

_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
_PDF_SHOW_TEXT = re.compile(rb"\((?:[^()\\]|\\.)*\)\s*Tj")
_PDF_ESCAPES = {
    b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
    b"(": b"(", b")": b")", b"\\": b"\\",
}


def _unescape_pdf_string(raw):
    """Resolve the backslash escapes a PDF literal string may contain."""
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _PDF_ESCAPES:
                out += _PDF_ESCAPES[nxt]
                i += 2
                continue
            if nxt.isdigit():  # octal escape, e.g. \251
                digits = raw[i + 1:i + 4]
                try:
                    out.append(int(digits, 8) & 0xFF)
                    i += 1 + len(digits)
                    continue
                except ValueError:
                    pass
            out += nxt
            i += 2
            continue
        out += ch
        i += 1
    return bytes(out)


def _decoded_stream_candidates(raw):
    """
    Yield each plausible decoding of a content stream.

    We do not parse the /Filter entry — we simply try the pipelines ReportLab
    and other writers use and let the caller keep whichever one actually
    contains text operators. Cheap, and it tolerates files written by a
    different version than the one running now.
    """
    raw = raw.strip()
    yield raw

    ascii85 = None
    try:
        payload = raw if raw.startswith(b"<~") else b"<~" + raw
        ascii85 = base64.a85decode(payload, adobe=True)
        yield ascii85
    except Exception:
        pass

    for blob in (ascii85, raw):
        if blob is None:
            continue
        try:
            yield zlib.decompress(blob)
        except zlib.error:
            try:
                yield zlib.decompressobj().decompress(blob)
            except zlib.error:
                pass


def _extract_pdf_lines(pdf_bytes):
    """Every visible string in the PDF, in the order it was drawn."""
    pieces = []
    for raw in _PDF_STREAM.findall(pdf_bytes):
        for blob in _decoded_stream_candidates(raw):
            hits = list(_PDF_SHOW_TEXT.finditer(blob))
            if not hits:
                continue
            for match in hits:
                token = match.group(0)
                inner = token[token.index(b"(") + 1: token.rindex(b")")]
                pieces.append(_unescape_pdf_string(inner).decode("latin-1").strip())
            break  # this decoding worked; don't try the others
    return [piece for piece in pieces if piece]


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
        # Cloudinary files already turned into tickets by an earlier run. Each
        # recovered ticket stores the public_id it came from, so we can skip it
        # here for free instead of paying for the download to find out.
        already_done = {
            name for name in Ticket.objects.exclude(pdf_file="").exclude(pdf_file__isnull=True)
            .values_list("pdf_file", flat=True) if name
        }

        recovered = 0
        skipped_existing = 0
        unmatched_user = []
        other_events = 0
        failures = 0
        # Keep the first real error so the admin page can show WHAT went wrong.
        # A bare "could not be read" count sends you to logs you may not be able
        # to reach, which is exactly the wrong thing during an incident.
        first_error = None
        empty_text = 0
        skipped_done = 0
        ran_out_of_time = False
        started = time.monotonic()

        for resource in resources:
            if recovered >= BATCH_LIMIT:
                break
            if time.monotonic() - started > TIME_BUDGET_SECONDS:
                ran_out_of_time = True
                break

            url = resource.get("secure_url") or resource.get("url")
            if not url:
                continue

            public_id = resource.get("public_id") or ""
            stored_name = f"{public_id}.{resource['format']}" if resource.get("format") else public_id
            if public_id in already_done or stored_name in already_done:
                skipped_done += 1
                continue

            try:
                with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
                    pdf_bytes = response.read()
                lines = _extract_pdf_lines(pdf_bytes)
            except Exception as exc:
                failures += 1
                if first_error is None:
                    first_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Ticket recovery could not read %s", url)
                continue

            if not lines:
                empty_text += 1
                if first_error is None:
                    first_error = f"no text found in {url.rsplit('/', 1)[-1]}"
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
                if first_error is None:
                    first_error = f"no 'Ticket: NXV…' line in {url.rsplit('/', 1)[-1]}"
                logger.warning("Ticket recovery found no code in %s; lines=%r", url, lines[:12])
                continue

            code, holder_name, ticket_type_name = parsed
            if code in existing:
                skipped_existing += 1
                continue

            # Ticket.holder cannot be null, so a name we can't match to an
            # account would otherwise block the ticket from being restored at
            # all. A ticket parked on the host with the real name preserved
            # still scans green at the door, which is the thing that matters;
            # the owner can be corrected afterwards. Every fallback is reported.
            user = _find_user(holder_name)
            orphaned = user is None
            if orphaned:
                user = event.host
                unmatched_user.append(f"{holder_name or 'no name on PDF'} ({code})")

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
                        customer_email="" if orphaned else user.email,
                        customer_phone="" if orphaned else (getattr(user, "phone_number", "") or ""),
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
                        holder_email="" if orphaned else user.email,
                        ticket_code=code,          # the original — this is what makes the old QR work
                        status=Ticket.Status.VALID,
                        # Remember which Cloudinary file this came from: it gives
                        # the ticket its original PDF back AND marks the file as
                        # done so later runs don't re-download it.
                        pdf_file=stored_name,
                    )
                existing.add(code)
                already_done.add(stored_name)
                recovered += 1
            except Exception as exc:
                failures += 1
                if first_error is None:
                    first_error = f"{type(exc).__name__}: {exc}"
                logger.exception("Ticket recovery could not save %s", code)
                self.message_user(request, f"{code}: {exc}", level="error")

        if recovered:
            self.message_user(
                request,
                f"✅ Recovered {recovered} ticket(s) with their ORIGINAL codes — "
                "the QR already in those customers' inboxes will now scan green.",
            )
        if skipped_done:
            self.message_user(request, f"↷ {skipped_done} already recovered by an earlier run.")
        if skipped_existing:
            self.message_user(request, f"↷ {skipped_existing} already present, left alone.")
        if other_events:
            self.message_user(request, f"↷ {other_events} PDF(s) belong to other events, ignored.")
        if unmatched_user:
            self.message_user(
                request,
                "⚠️ Recovered but parked on the host — no matching account for: "
                + ", ".join(unmatched_user[:15])
                + ("…" if len(unmatched_user) > 15 else "")
                + ". These tickets DO scan green; reassign the holder when you have time.",
                level="warning",
            )
        if empty_text:
            self.message_user(
                request,
                f"⚠️ {empty_text} PDF(s) held no readable text.",
                level="warning",
            )
        if failures:
            self.message_user(request, f"⚠️ {failures} PDF(s) failed.", level="warning")
        if first_error:
            # The actual reason, on screen, rather than a pointer to the logs.
            self.message_user(request, f"First error was — {first_error}", level="warning")
        if recovered >= BATCH_LIMIT or ran_out_of_time:
            reason = "hit the batch limit" if recovered >= BATCH_LIMIT else "ran out of time"
            self.message_user(
                request,
                f"⏱ Stopped early ({reason}) so the request wouldn't be killed. "
                f"{len(resources) - skipped_done - recovered} file(s) still to check — "
                "RUN THIS ACTION AGAIN. It picks up where it left off.",
                level="warning",
            )
        if not any([recovered, skipped_existing, skipped_done, unmatched_user, failures, empty_text]):
            self.message_user(
                request,
                f"No ticket PDFs under '{TICKET_PDF_PREFIX}' matched '{event.title}' in Cloudinary.",
                level="warning",
            )


@admin.register(TicketType)
class TicketTypeAdmin(admin.ModelAdmin):
    list_display = ["name", "event", "price", "is_free", "quantity_total", "quantity_remaining", "is_active"]
    list_filter = ["is_free", "is_active", "is_early_bird"]
    search_fields = ["name", "event__title"]
