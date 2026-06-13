/* Nexivo — UI Scripts */
document.addEventListener('DOMContentLoaded', function () {

  /* ---- Toast auto-dismiss ---- */
  document.querySelectorAll('.toast[data-ms]').forEach(function (t) {
    var ms = parseInt(t.dataset.ms) || 5000;
    setTimeout(function () { dismissToast(t); }, ms);
    var btn = t.querySelector('.toast-x');
    if (btn) btn.addEventListener('click', function () { dismissToast(t); });
  });

  function dismissToast(t) {
    t.style.transition = 'all .3s ease';
    t.style.opacity = '0';
    t.style.transform = 'translateX(110%)';
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 320);
  }

  /* ---- Sidebar open/close ---- */
  var sidebar = document.getElementById('sidebar');
  var openBtn  = document.getElementById('sb-open');
  var closeBtn = document.getElementById('sb-close');
  var overlay  = document.getElementById('sb-overlay');

  if (openBtn && sidebar) {
    openBtn.addEventListener('click', function () {
      sidebar.classList.add('open');
      if (overlay) overlay.style.display = 'block';
    });
  }
  if (closeBtn && sidebar) {
    closeBtn.addEventListener('click', function () {
      sidebar.classList.remove('open');
      if (overlay) overlay.style.display = 'none';
    });
  }
  if (overlay) {
    overlay.addEventListener('click', function () {
      sidebar.classList.remove('open');
      overlay.style.display = 'none';
    });
  }

  /* ---- Form loading state ---- */
  document.querySelectorAll('form').forEach(function (form) {
    form.addEventListener('submit', function () {
      var btn = form.querySelector('button[type="submit"]:not(.no-load)');
      if (btn) {
        btn.disabled = true;
        var orig = btn.innerHTML;
        btn.innerHTML = '<span class="spin-icon"></span> Processing...';
        setTimeout(function () { btn.disabled = false; btn.innerHTML = orig; }, 12000);
      }
    });
  });

  /* ---- Confirm dialogs ---- */
  document.querySelectorAll('[data-confirm]').forEach(function (el) {
    el.addEventListener('click', function (e) {
      if (!confirm(el.getAttribute('data-confirm'))) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  });

  /* ---- Table search ---- */
  document.querySelectorAll('[data-search-table]').forEach(function (inp) {
    var targetId = inp.getAttribute('data-search-table');
    var table = document.getElementById(targetId);
    if (!table) return;
    inp.addEventListener('input', function () {
      var q = inp.value.toLowerCase();
      table.querySelectorAll('tbody tr').forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  });

  /* ---- Ripple on buttons ---- */
  document.querySelectorAll('.btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      var ripple = document.createElement('span');
      var rect = btn.getBoundingClientRect();
      var size = Math.max(rect.width, rect.height);
      ripple.style.cssText = [
        'position:absolute', 'border-radius:50%',
        'background:rgba(255,255,255,.2)',
        'width:' + size + 'px', 'height:' + size + 'px',
        'top:'  + (e.clientY - rect.top  - size / 2) + 'px',
        'left:' + (e.clientX - rect.left - size / 2) + 'px',
        'transform:scale(0)', 'animation:ripple .55s linear',
        'pointer-events:none'
      ].join(';');
      btn.appendChild(ripple);
      setTimeout(function () { if (ripple.parentNode) ripple.parentNode.removeChild(ripple); }, 600);
    });
  });

});

/* Inject keyframes */
(function () {
  var style = document.createElement('style');
  style.textContent = [
    '@keyframes ripple{to{transform:scale(2.5);opacity:0}}',
    '.spin-icon{display:inline-block;width:13px;height:13px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:middle;margin-right:2px}',
    '@keyframes spin{to{transform:rotate(360deg)}}'
  ].join('');
  document.head.appendChild(style);
}());
