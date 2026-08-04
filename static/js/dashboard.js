/**
 * NEXIVO — Dashboard (host + customer + admin)
 */

/* ── Simple chart renderer (bar + line via canvas) ─────────────────────── */
const Charts = (() => {
  function bar(canvasId, labels, values, label = '') {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * 2; canvas.style.width = '100%';
    const H = canvas.height = 200;
    const max = Math.max(...values, 1);
    const BAR = (W - 40) / (labels.length * 1.5);
    const gap = BAR / 2;
    const isLight = document.documentElement.getAttribute('data-theme') !== 'dark';
    const gold = '#C9A84C', text = isLight ? '#555' : '#aaa', bg = isLight ? '#fff' : '#1a1a1a';

    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    values.forEach((v, i) => {
      const h = (v / max) * (H - 40);
      const x = 20 + i * (BAR + gap);
      const y = H - 20 - h;
      ctx.fillStyle = gold;
      ctx.beginPath(); ctx.roundRect(x, y, BAR, h, 3); ctx.fill();
      ctx.fillStyle = text; ctx.font = `${Math.max(16, BAR * .7)}px Inter`;
      ctx.textAlign = 'center';
      if (labels[i]) ctx.fillText(labels[i].slice(5), x + BAR/2, H - 5);
    });
  }

  function line(canvasId, labels, values) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * 2; canvas.style.width = '100%';
    const H = canvas.height = 200;
    const max = Math.max(...values, 1);
    const isLight = document.documentElement.getAttribute('data-theme') !== 'dark';
    const gold = '#C9A84C', bg = isLight ? '#fff' : '#1a1a1a';
    const W0 = 20, WN = W - 20;

    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    const pts = values.map((v, i) => [
      W0 + (i / Math.max(values.length - 1, 1)) * (WN - W0),
      H - 20 - (v / max) * (H - 40)
    ]);

    // Gradient fill
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, 'rgba(201,168,76,.35)');
    grad.addColorStop(1, 'rgba(201,168,76,0)');
    ctx.beginPath(); ctx.moveTo(pts[0][0], H - 20);
    pts.forEach(([x, y]) => ctx.lineTo(x, y));
    ctx.lineTo(pts[pts.length-1][0], H - 20);
    ctx.fillStyle = grad; ctx.fill();

    // Line
    ctx.beginPath(); ctx.strokeStyle = gold; ctx.lineWidth = 3; ctx.lineJoin = 'round';
    pts.forEach(([x, y], i) => i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y));
    ctx.stroke();

    // Dots
    pts.forEach(([x, y]) => {
      ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2);
      ctx.fillStyle = gold; ctx.fill();
    });
  }

  return { bar, line };
})();


/* ── Host dashboard ─────────────────────────────────────────────────────── */
async function loadHostDashboard() {
  const page = document.getElementById('host-dashboard');
  if (!page) return;
  Auth.requireAuth();

  try {
    const data = await Api.get('/analytics/host/');
    document.getElementById('stat-events').textContent = data.total_events;
    document.getElementById('stat-tickets').textContent = data.total_tickets_sold?.toLocaleString();
    document.getElementById('stat-revenue').textContent = `₦${Number(data.total_revenue).toLocaleString()}`;
    document.getElementById('stat-revenue-30d').textContent = `₦${Number(data.revenue_last_30_days).toLocaleString()}`;
    document.getElementById('stat-rating').textContent = parseFloat(data.average_rating).toFixed(1);

    if (data.revenue_by_day?.length) {
      Charts.bar('revenue-chart', data.revenue_by_day.map(r => r.day), data.revenue_by_day.map(r => parseFloat(r.revenue)));
    }

    const topList = document.getElementById('top-events-list');
    if (topList) {
      topList.innerHTML = data.top_events.map(e => `
        <tr>
          <td>${e.title}</td>
          <td>${e.tickets_sold}</td>
          <td>₦${Number(e.revenue).toLocaleString()}</td>
          <td>⭐ ${parseFloat(e.rating).toFixed(1)}</td>
          <td><a href="/events/${e.id}/analytics/" class="btn btn--ghost btn--sm">Details</a></td>
        </tr>`).join('');
    }
  } catch { Toast.error('Failed to load dashboard data.'); }
}


/* ── Host events management ─────────────────────────────────────────────── */
async function loadHostEvents() {
  const container = document.getElementById('host-events-list');
  if (!container) return;
  Auth.requireAuth();

  try {
    const data = await Api.get('/events/mine/');
    if (!data.results.length) {
      container.innerHTML = '<tr><td colspan="4" class="text-center text-muted" style="padding:24px">No events yet. <a href="/events/create/" class="text-gold">Create your first event →</a></td></tr>';
      return;
    }
    container.innerHTML = data.results.map(event => `
      <tr>
        <td><strong>${event.title}</strong><br><small class="text-muted">${new Date(event.start_datetime).toLocaleDateString()}</small></td>
        <td><span class="badge badge--${statusBadge(event.status)}">${event.status}</span></td>
        <td>${event.tickets_sold_count}</td>
        <td>
          <div class="flex gap-8" style="flex-wrap:wrap">
            <a href="/dashboard/events/${event.slug}/edit/" class="btn btn--outline btn--sm">Edit</a>
            ${event.status === 'draft'
              ? `<button class="btn btn--gold btn--sm" onclick="publishEvent('${event.slug}', this)">Publish</button>`
              : `<a href="/events/${event.slug}/" class="btn btn--ghost btn--sm" target="_blank">View</a>`}
            <button class="btn btn--sm" style="background:rgba(239,68,68,.1);color:#ef4444;border:1px solid rgba(239,68,68,.3)" onclick="deleteEvent('${event.slug}', '${event.title.replace(/'/g,"\'")}')">Delete</button>
          </div>
        </td>
      </tr>`).join('');
  } catch { Toast.error('Failed to load your events.'); }
}

async function publishEvent(slug, btn) {
  btn.disabled = true; btn.textContent = 'Publishing…';
  try {
    await Api.post(`/events/${slug}/publish/`);
    Toast.success('Event published!');
    loadHostEvents();
  } catch(err) {
    Toast.error(err?.detail || 'Could not publish event.');
    btn.disabled = false; btn.textContent = 'Publish';
  }
}

async function deleteEvent(slug, title) {
  if (!confirm(`Are you sure you want to delete "${title}"? This cannot be undone and will remove all associated tickets and data.`)) return;
  try {
    await Api.delete(`/events/${slug}/`);
    Toast.success('Event deleted successfully.');
    loadHostEvents();
  } catch(err) {
    Toast.error(err?.detail || 'Could not delete event.');
  }
}


/* ── Customer tickets ────────────────────────────────────────────────────── */
async function loadMyTickets() {
  const container = document.getElementById('my-tickets');
  if (!container) return;
  Auth.requireAuth();

  try {
    const data = await Api.get('/tickets/mine/');
    if (!data.results.length) {
      container.innerHTML = '<p class="text-muted text-center mt-32">No tickets yet. <a href="/events/">Browse events →</a></p>';
      return;
    }
    container.innerHTML = data.results.map(ticket => `
      <div class="ticket-card ${ticket.status === 'used' ? 'ticket-card--used' : ''}">
        <div class="ticket-card__body">
          <h3 class="ticket-card__event">${ticket.event_title}</h3>
          <p class="ticket-card__meta">${ticket.ticket_type_name} · <span class="badge badge--${ticket.status === 'valid' ? 'green' : 'grey'}">${ticket.status}</span></p>
          <code class="ticket-card__code">${ticket.ticket_code}</code>
          <div class="flex gap-8 mt-16">
            <a href="/api/v1/tickets/${ticket.ticket_code}/download/" class="btn btn--outline btn--sm" download>Download PDF</a>
            ${ticket.can_be_transferred
              ? `<button class="btn btn--ghost btn--sm" onclick="showTransferModal('${ticket.id}', '${ticket.ticket_code}')">Transfer</button>`
              : ''}
          </div>
        </div>
        <div class="ticket-card__qr">
          ${ticket.qr_image ? `<img src="${ticket.qr_image}" alt="QR code" width="80">` : '<div class="spinner"></div>'}
        </div>
      </div>`).join('');
  } catch { Toast.error('Failed to load your tickets.'); }
}

function showTransferModal(ticketId, ticketCode) {
  document.getElementById('transfer-ticket-code').value = ticketCode;
  Modal.open('transfer-modal');
}


/* ── QR Scanner (host check-in dashboard) ────────────────────────────────── */
const Scanner = (() => {
  let eventId;

  async function scan(code) {
    if (!code) return;
    const resultEl = document.getElementById('scan-result');
    if (resultEl) { resultEl.className = 'scan-result'; resultEl.textContent = 'Verifying…'; }

    try {
      const data = await Api.post(`/tickets/scan/${eventId}/`, {
        code,
        client_scanned_at: new Date().toISOString(),
        device_id: navigator.userAgent.slice(0, 50),
      });

      if (resultEl) {
        resultEl.className = `scan-result scan-result--${data.result === 'success' ? 'success' : data.result === 'duplicate' ? 'duplicate' : 'error'}`;
        resultEl.textContent = data.message;
      }
      if (data.result === 'success') {
        navigator.vibrate?.([100, 50, 100]);
        updateScanStats();
      }
    } catch {
      if (resultEl) { resultEl.className = 'scan-result scan-result--error'; resultEl.textContent = 'Network error. Try again.'; }
    }
  }

  async function updateScanStats() {
    try {
      const data = await Api.get(`/analytics/event/${eventId}/`);
      document.getElementById('scan-checkedin').textContent = data.checked_in;
      document.getElementById('scan-total').textContent = data.tickets_sold;
    } catch {}
  }

  function init() {
    const page = document.getElementById('scanner-page');
    if (!page) return;
    eventId = document.getElementById('scanner-event-id')?.value;
    if (!eventId) return;
    Auth.requireAuth();

    // Manual code input
    const input = document.getElementById('manual-scan-input');
    const btn = document.getElementById('manual-scan-btn');
    if (btn && input) {
      btn.addEventListener('click', () => { scan(input.value.trim()); input.value = ''; });
      input.addEventListener('keydown', e => { if (e.key === 'Enter') { scan(input.value.trim()); input.value = ''; } });
    }
    // Simulate barcode scanner: listens for rapid keyboard input ending in Enter
    let barcodeBuffer = '', barcodeTimer;
    document.addEventListener('keypress', e => {
      if (e.target.tagName === 'INPUT') return;
      clearTimeout(barcodeTimer);
      barcodeBuffer += e.key;
      barcodeTimer = setTimeout(() => barcodeBuffer = '', 100);
      if (e.key === 'Enter' && barcodeBuffer.length > 4) {
        scan(barcodeBuffer.replace('Enter', '').trim());
        barcodeBuffer = '';
      }
    });
    updateScanStats();
  }

  return { init };
})();


/* ── Platform admin dashboard ─────────────────────────────────────────────── */
async function loadPlatformDashboard() {
  const page = document.getElementById('admin-dashboard');
  if (!page) return;
  Auth.requireAuth();

  try {
    const user = JSON.parse(localStorage.getItem('nexivo_user') || 'null');
    if (!user || user.role !== 'super_admin') return;
    const data = await Api.get('/analytics/platform/');
    document.getElementById('stat-gmv').textContent = `₦${Number(data.total_gmv).toLocaleString()}`;
    document.getElementById('stat-platform-rev').textContent = `₦${Number(data.total_platform_revenue).toLocaleString()}`;
    document.getElementById('stat-total-users').textContent = data.total_users.toLocaleString();
    document.getElementById('stat-live-events').textContent = data.live_events;
    document.getElementById('stat-open-disputes').textContent = data.open_disputes;

    if (data.revenue_by_month?.length) {
      Charts.line('platform-revenue-chart',
        data.revenue_by_month.map(r => r.month),
        data.revenue_by_month.map(r => parseFloat(r.platform_cut))
      );
    }
  } catch { Toast.error('Failed to load platform analytics.'); }
}


/* ── Helpers ──────────────────────────────────────────────────────────────── */
function statusBadge(status) {
  return { published: 'green', draft: 'grey', suspended: 'red', cancelled: 'red', completed: 'gold' }[status] || 'grey';
}


/* ── Auto-init ────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadHostDashboard();
  loadHostEvents();
  loadMyTickets();
  loadPlatformDashboard();
  Scanner.init();
});