/* Nexora JS */
document.addEventListener('DOMContentLoaded', () => {

  // Auto-dismiss toasts
  document.querySelectorAll('.toast[data-ms]').forEach(t => {
    const close = () => { t.style.cssText += ';opacity:0;transform:translateX(120%);transition:all .35s'; setTimeout(() => t.remove(), 350) };
    setTimeout(close, +t.dataset.ms || 5000);
    t.querySelector('.toast-x')?.addEventListener('click', close);
  });

  // Sidebar toggle (mobile)
  const sb = document.getElementById('sidebar');
  document.getElementById('sbtog')?.addEventListener('click', () => sb?.classList.add('open'));
  document.getElementById('sbclose')?.addEventListener('click', () => sb?.classList.remove('open'));
  document.addEventListener('click', e => {
    if (sb?.classList.contains('open') && !sb.contains(e.target) && !document.getElementById('sbtog')?.contains(e.target))
      sb.classList.remove('open');
  });

  // Form loading
  document.querySelectorAll('form').forEach(f => {
    f.addEventListener('submit', function () {
      const btn = this.querySelector('button[type=submit]:not(.nol)');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spin"></span> Processing...`;
        setTimeout(() => btn.disabled = false, 12000);
      }
    });
  });

  // Confirm
  document.querySelectorAll('[data-confirm]').forEach(el =>
    el.addEventListener('click', e => { if (!confirm(el.dataset.confirm)) e.preventDefault() }));

  // Ripple
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', e => {
      const r = document.createElement('span');
      const rect = btn.getBoundingClientRect();
      const s = Math.max(rect.width, rect.height);
      r.style.cssText = `position:absolute;width:${s}px;height:${s}px;border-radius:50%;background:rgba(255,255,255,.22);top:${e.clientY-rect.top-s/2}px;left:${e.clientX-rect.left-s/2}px;transform:scale(0);animation:ripple .6s linear;pointer-events:none`;
      btn.style.position = 'relative'; btn.style.overflow = 'hidden';
      btn.appendChild(r); setTimeout(() => r.remove(), 700);
    });
  });

  // Animate stat numbers
  document.querySelectorAll('.stat-val[data-n]').forEach(el => {
    const target = parseFloat(el.dataset.n), pre = el.dataset.pre || '';
    let cur = 0; const step = target / 60;
    const t = setInterval(() => {
      cur = Math.min(cur + step, target);
      el.textContent = pre + Math.floor(cur).toLocaleString('en-NG');
      if (cur >= target) clearInterval(t);
    }, 16);
  });

  // Table search
  document.querySelectorAll('[data-search]').forEach(inp => {
    inp.addEventListener('input', () => {
      const q = inp.value.toLowerCase();
      document.querySelectorAll(inp.dataset.search + ' tbody tr').forEach(tr =>
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none');
    });
  });

  // Active sidebar link
  const path = location.pathname;
  document.querySelectorAll('.sb-link').forEach(a => {
    if (a.getAttribute('href') === path) a.classList.add('active');
  });
});

// Inject ripple + spin keyframes
const s = document.createElement('style');
s.textContent = `@keyframes ripple{to{transform:scale(2.5);opacity:0}} .spin{width:13px;height:13px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;display:inline-block;animation:sp .7s linear infinite} @keyframes sp{to{transform:rotate(360deg)}}`;
document.head.appendChild(s);
