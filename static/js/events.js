/**
 * NEXIVO — Events browse, search, filter, detail, checkout
 */

/* ── Event listing page ───────────────────────────────────────────────── */
const EventBrowse = (() => {
  let state = { page: 1, search: '', category: '', event_type: '', loading: false };

  async function load() {
    if (state.loading) return;
    state.loading = true;
    const grid = document.getElementById('events-grid');
    const loader = document.getElementById('events-loader');
    const empty = document.getElementById('events-empty');
    if (!grid) return;

    if (loader) loader.classList.remove('hidden');
    grid.style.opacity = '.5';

    const params = new URLSearchParams();
    if (state.search)     params.set('search', state.search);
    if (state.category)   params.set('category', state.category);
    if (state.event_type) params.set('event_type', state.event_type);
    params.set('page', state.page);

    try {
      const data = await Api.get(`/events/?${params}`, true);
      grid.innerHTML = data.results.map(renderEventCard).join('');
      if (empty) empty.classList.toggle('hidden', data.count > 0);

      // Pagination
      const pagination = document.getElementById('pagination');
      if (pagination) {
        pagination.innerHTML = '';
        if (data.previous) {
          const btn = document.createElement('button');
          btn.className = 'btn btn--outline btn--sm';
          btn.textContent = '← Previous';
          btn.onclick = () => { state.page--; load(); };
          pagination.appendChild(btn);
        }
        if (data.next) {
          const btn = document.createElement('button');
          btn.className = 'btn btn--primary btn--sm';
          btn.textContent = 'Next →';
          btn.onclick = () => { state.page++; load(); };
          pagination.appendChild(btn);
        }
      }
    } catch(e) {
      Toast.error('Failed to load events. Please refresh.');
    } finally {
      grid.style.opacity = '1';
      if (loader) loader.classList.add('hidden');
      state.loading = false;
    }
  }

  function renderEventCard(event) {
    const price = event.min_price != null
      ? (parseFloat(event.min_price) === 0 ? 'Free' : `From ₦${Number(event.min_price).toLocaleString()}`)
      : 'Free';
    const date = new Date(event.start_datetime).toLocaleDateString('en-NG', { day:'numeric', month:'short', year:'numeric' });
    const badge = event.is_featured ? '<span class="card__badge card__badge--featured">Featured</span>'
                : price === 'Free' ? '<span class="card__badge card__badge--free">Free</span>'
                : `<span class="card__badge">${event.event_type}</span>`;

    return `
      <a href="/events/${event.slug}/" class="card" style="display:block; text-decoration:none;">
        <div class="card__media">
          <img src="${event.banner_image || '/static/img/event-placeholder.svg'}" alt="${event.title}" loading="lazy">
        </div>
        <div class="card__body">
          ${badge}
          <h3 class="card__title">${event.title}</h3>
          <div class="card__meta">
            <span>📅 ${date}</span>
            ${event.city ? `<span>📍 ${event.city}</span>` : ''}
            ${event.average_rating > 0 ? `<span>⭐ ${parseFloat(event.average_rating).toFixed(1)}</span>` : ''}
          </div>
          <div class="card__price">${price}</div>
        </div>
        <div class="card__footer">
          <div class="card__host">
            <img class="avatar" src="/static/img/avatar-placeholder.svg" alt="${event.host.username}">
            ${event.host.first_name || event.host.username}
          </div>
          <span class="badge ${event.tickets_sold_count > 0 ? 'badge--gold' : 'badge--grey'}">
            ${event.tickets_sold_count} sold
          </span>
        </div>
      </a>`;
  }

  function init() {
    if (!document.getElementById('events-grid')) return;

    // Read initial state from URL params (e.g. from homepage search)
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('search')) {
      state.search = urlParams.get('search');
      const searchInput = document.getElementById('search-input');
      if (searchInput) searchInput.value = state.search;
    }
    if (urlParams.get('category')) state.category = urlParams.get('category');
    if (urlParams.get('event_type')) state.event_type = urlParams.get('event_type');

    load();

    // Search
    let searchTimer;
    document.getElementById('search-input')?.addEventListener('input', e => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => { state.search = e.target.value; state.page = 1; load(); }, 350);
    });

    // Category chips
    document.querySelectorAll('.filter-chip[data-category]').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.filter-chip[data-category]').forEach(c => c.classList.remove('filter-chip--active'));
        const val = chip.dataset.category;
        state.category = state.category === val ? '' : val;
        if (state.category) chip.classList.add('filter-chip--active');
        state.page = 1; load();
      });
    });

    // Type chips
    document.querySelectorAll('.filter-chip[data-type]').forEach(chip => {
      chip.addEventListener('click', () => {
        document.querySelectorAll('.filter-chip[data-type]').forEach(c => c.classList.remove('filter-chip--active'));
        const val = chip.dataset.type;
        state.event_type = state.event_type === val ? '' : val;
        if (state.event_type) chip.classList.add('filter-chip--active');
        state.page = 1; load();
      });
    });
  }

  return { init };
})();


/* ── Event detail & checkout ──────────────────────────────────────────── */
const EventDetail = (() => {
  let selections = {};

  function initCountdown(targetDateStr) {
    const target = new Date(targetDateStr);
    const el = document.getElementById('event-countdown');
    if (!el) return;

    function tick() {
      const diff = target - Date.now();
      if (diff <= 0) { el.innerHTML = '<p class="text-gold">Event has started!</p>'; return; }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      el.innerHTML = `
        <div class="countdown">
          ${[['Days',d],['Hrs',h],['Min',m],['Sec',s]].map(([l,v]) => `
            <div class="countdown__unit">
              <div class="countdown__number">${String(v).padStart(2,'0')}</div>
              <div class="countdown__label">${l}</div>
            </div>`).join('')}
        </div>`;
      setTimeout(tick, 1000);
    }
    tick();
  }

  function updateTotal() {
    let subtotal = 0;
    Object.entries(selections).forEach(([id, {price, qty}]) => { subtotal += price * qty; });
    const subtotalEl = document.getElementById('checkout-subtotal');
    const finalEl   = document.getElementById('checkout-final');
    const btnEl     = document.getElementById('checkout-btn');
    const formatted = `₦${subtotal.toLocaleString()}`;
    if (subtotalEl) subtotalEl.textContent = formatted;
    if (finalEl)    finalEl.textContent    = formatted;
    if (btnEl) btnEl.disabled = Object.values(selections).every(s => s.qty === 0);
  }

  async function submitCheckout() {
    const items = Object.entries(selections)
      .filter(([,s]) => s.qty > 0)
      .map(([id, s]) => ({ ticket_type_id: id, quantity: s.qty }));

    if (!items.length) { Toast.error('Please select at least one ticket.'); return; }

    // If logged in proceed normally
    if (Auth.isLoggedIn()) {
      await processCheckout(items);
      return;
    }

    // Guest checkout — show modal for name and email
    showGuestModal(items);
  }

  function showGuestModal(items) {
    // Create guest modal if it doesn't exist
    let modal = document.getElementById('guest-checkout-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'guest-checkout-modal';
      modal.className = 'modal-backdrop';
      modal.innerHTML = `
        <div class="modal" style="position:relative;max-width:420px">
          <button class="modal__close" onclick="document.getElementById('guest-checkout-modal').classList.remove('is-open');document.body.classList.remove('modal-open')">×</button>
          <h2 class="modal__title" style="margin-bottom:4px">Almost there! 🎟️</h2>
          <p class="text-muted" style="margin-bottom:20px;font-size:.875rem">Enter your details to receive your ticket</p>
          <div class="form-group" style="margin-bottom:14px">
            <label class="form-label">First Name *</label>
            <input class="form-input" id="guest-firstname" type="text" placeholder="Your first name">
          </div>
          <div class="form-group" style="margin-bottom:14px">
            <label class="form-label">Last Name *</label>
            <input class="form-input" id="guest-lastname" type="text" placeholder="Your last name">
          </div>
          <div class="form-group" style="margin-bottom:20px">
            <label class="form-label">Email Address *</label>
            <input class="form-input" id="guest-email" type="email" placeholder="you@example.com">
            <p class="text-muted" style="font-size:.8125rem;margin-top:4px">Your QR code ticket will be sent here</p>
          </div>
          <p id="guest-error" style="color:var(--error);font-size:.875rem;margin-bottom:12px;display:none"></p>
          <button class="btn btn--gold btn--full" id="guest-proceed-btn" onclick="proceedAsGuest()">Continue to Payment 🔒</button>
          <div style="text-align:center;margin-top:16px">
            <span class="text-muted" style="font-size:.8125rem">Already have an account? </span>
            <a href="/auth/login/" style="font-size:.8125rem;color:var(--gold)">Sign in</a>
          </div>
        </div>`;
      document.body.appendChild(modal);
    }
    modal.classList.add('is-open');
    document.body.classList.add('modal-open');
    // Store items for later use
    modal._items = items;
  }

  window.proceedAsGuest = async function proceedAsGuest() {
    const firstName = document.getElementById('guest-firstname').value.trim();
    const lastName = document.getElementById('guest-lastname').value.trim();
    const email = document.getElementById('guest-email').value.trim();
    const errEl = document.getElementById('guest-error');
    errEl.style.display = 'none';

    if (!firstName || !lastName || !email) {
      errEl.textContent = 'Please fill in all fields.';
      errEl.style.display = '';
      return;
    }
    if (!email.includes('@')) {
      errEl.textContent = 'Please enter a valid email address.';
      errEl.style.display = '';
      return;
    }

    const btn = document.getElementById('guest-proceed-btn');
    btn.disabled = true; btn.textContent = 'Processing…';

    const modal = document.getElementById('guest-checkout-modal');
    const items = modal._items;

    await processCheckout(items, { first_name: firstName, last_name: lastName, email });

    btn.disabled = false; btn.textContent = 'Continue to Payment 🔒';
  }

  async function processCheckout(items, guestDetails = null) {
    const gateway = document.querySelector('input[name="gateway"]:checked')?.value || 'paystack';
    const couponCode = document.getElementById('coupon-input')?.value || '';
    const eventId = document.getElementById('event-id')?.value;

    const btn = document.getElementById('checkout-btn');
    btn.disabled = true; btn.textContent = 'Processing…';

    try {
      const payload = {
        event_id: eventId, items, gateway,
        coupon_code: couponCode || undefined,
      };
      if (guestDetails) {
        payload.guest_first_name = guestDetails.first_name;
        payload.guest_last_name = guestDetails.last_name;
        payload.guest_email = guestDetails.email;
      }
      const data = await Api.post('/bookings/checkout/', payload);
      if (data.payment?.checkout_url) {
        window.location.href = data.payment.checkout_url;
      } else {
        Toast.success('Booking confirmed!');
        setTimeout(() => window.location.href = '/dashboard/tickets/', 1500);
      }
    } catch (err) {
      const msg = err?.detail || err?.errors?.non_field_errors?.[0] || 'Checkout failed. Please try again.';
      Toast.error(msg);
      btn.disabled = false; btn.textContent = 'Book Now';
    }
  }

  async function toggleFavorite(slug, btn) {
    if (!Auth.isLoggedIn()) { Toast.gold('Sign in to save events'); return; }
    try {
      const data = await Api.post(`/events/${slug}/favorite/`);
      btn.textContent = data.favorited ? '❤️' : '🤍';
      Toast.gold(data.favorited ? 'Saved to favourites' : 'Removed from favourites');
    } catch { Toast.error('Could not update favourites'); }
  }

  function init() {
    const countdownDate = document.getElementById('countdown-date')?.value;
    if (countdownDate) initCountdown(countdownDate);

    document.querySelectorAll('.qty-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const row = btn.closest('.ticket-row');
        const id = row.dataset.ticketTypeId;
        const price = parseFloat(row.dataset.price);
        const display = row.querySelector('.qty-display');
        if (!selections[id]) selections[id] = { price, qty: 0 };
        const delta = btn.dataset.dir === 'up' ? 1 : -1;
        const max = parseInt(row.dataset.max || 10);
        selections[id].qty = Math.max(0, Math.min(max, selections[id].qty + delta));
        if (display) display.textContent = selections[id].qty;
        updateTotal();
      });
    });

    document.getElementById('checkout-btn')?.addEventListener('click', submitCheckout);

    const favBtn = document.getElementById('favorite-btn');
    const slug = document.getElementById('event-slug')?.value;
    if (favBtn && slug) favBtn.addEventListener('click', () => toggleFavorite(slug, favBtn));

    // Coupon validation
    document.getElementById('apply-coupon-btn')?.addEventListener('click', async () => {
      const code = document.getElementById('coupon-input')?.value;
      const eventId = document.getElementById('event-id')?.value;
      if (!code || !eventId) return;
      const subtotalStr = document.getElementById('checkout-subtotal')?.textContent.replace(/[^\d.]/g,'') || '0';
      try {
        const data = await Api.post('/coupons/validate/', { code, event_id: eventId, subtotal: parseFloat(subtotalStr) });
        Toast.success(`Coupon applied! You save ₦${Number(data.discount_amount).toLocaleString()}`);
        document.getElementById('coupon-discount').textContent = `-₦${Number(data.discount_amount).toLocaleString()}`;
        document.getElementById('checkout-final').textContent = `₦${Number(data.discounted_subtotal).toLocaleString()}`;
      } catch (err) {
        Toast.error(err?.detail || 'Invalid coupon code');
      }
    });
  }

  return { init };
})();


/* ── Auto-init ────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  EventBrowse.init();
  EventDetail.init();
});