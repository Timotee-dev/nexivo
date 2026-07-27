/**
 * NEXIVO — Core JavaScript
 * Handles: theme, API client, auth, toasts, modal, nav
 * No external dependencies beyond the page itself.
 */

/* ── Theme ────────────────────────────────────────────────────────────── */
const Theme = (() => {
  const key = 'nexivo_theme';
  const html = document.documentElement;

  function apply(t) {
    html.setAttribute('data-theme', t);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.textContent = t === 'dark' ? '☀️' : '🌙';
  }

  function init() {
    const saved = localStorage.getItem(key) ||
      (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    apply(saved);
  }

  function toggle() {
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    localStorage.setItem(key, next);
    apply(next);
  }

  return { init, toggle };
})();

/* ── API client ───────────────────────────────────────────────────────── */
const Api = (() => {
  const BASE = '/api/v1';

  function getToken() { return localStorage.getItem('nexivo_access'); }

  async function request(method, path, body = null, isPublic = false) {
    const headers = { 'Content-Type': 'application/json' };
    const token = getToken();
    if (token && !isPublic) headers['Authorization'] = `Bearer ${token}`;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${BASE}${path}`, opts);

    // 401 → attempt token refresh, then retry once
    if (res.status === 401 && !isPublic) {
      const refreshed = await refreshToken();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${getToken()}`;
        const retry = await fetch(`${BASE}${path}`, { ...opts, headers });
        if (!retry.ok) throw await retry.json();
        return retry.status === 204 ? null : retry.json();
      } else {
        Auth.logout();
        return;
      }
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Network error' }));
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }

  async function refreshToken() {
    const refresh = localStorage.getItem('nexivo_refresh');
    if (!refresh) return false;
    const res = await fetch(`${BASE}/auth/token/refresh/`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    localStorage.setItem('nexivo_access', data.access);
    if (data.refresh) localStorage.setItem('nexivo_refresh', data.refresh);
    return true;
  }

  return {
    get:    (path, pub) => request('GET', path, null, pub),
    post:   (path, body, pub) => request('POST', path, body, pub),
    patch:  (path, body) => request('PATCH', path, body),
    delete: (path) => request('DELETE', path),
    getToken,
  };
})();

/* ── Auth ─────────────────────────────────────────────────────────────── */
const Auth = (() => {
  function getUser() {
    const u = localStorage.getItem('nexivo_user');
    return u ? JSON.parse(u) : null;
  }

  function setSession(data) {
    localStorage.setItem('nexivo_access', data.access);
    localStorage.setItem('nexivo_refresh', data.refresh);
    localStorage.setItem('nexivo_user', JSON.stringify(data.user));
  }

  function logout() {
    const refresh = localStorage.getItem('nexivo_refresh');
    if (refresh) Api.post('/auth/logout/', { refresh }).catch(() => {});
    ['nexivo_access', 'nexivo_refresh', 'nexivo_user'].forEach(k => localStorage.removeItem(k));
    window.location.href = '/';
  }

  function isLoggedIn() { return !!localStorage.getItem('nexivo_access'); }

  function requireAuth() {
    if (!isLoggedIn()) { window.location.href = '/auth/login/?next=' + encodeURIComponent(window.location.pathname); }
  }

  function updateNavForUser() {
    const user = getUser();
    const authLinks = document.getElementById('auth-links');
    const userMenu = document.getElementById('user-menu');
    const userMenuName = document.getElementById('user-menu-name');
    if (!authLinks || !userMenu) return;

    if (user) {
      authLinks.classList.add('hidden');
      userMenu.classList.remove('hidden');
      if (userMenuName) userMenuName.textContent = user.first_name || user.username;
    } else {
      authLinks.classList.remove('hidden');
      userMenu.classList.add('hidden');
    }
  }

  return { getUser, setSession, logout, isLoggedIn, requireAuth, updateNavForUser };
})();

/* ── Toast ────────────────────────────────────────────────────────────── */
const Toast = (() => {
  function show(message, type = 'default', duration = 4000) {
    let container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity .3s'; setTimeout(() => toast.remove(), 300); }, duration);
  }
  return { show, success: m => show(m, 'success'), error: m => show(m, 'error'), gold: m => show(m, 'gold') };
})();

/* ── Modal ────────────────────────────────────────────────────────────── */
const Modal = (() => {
  function open(id) {
    document.getElementById(id)?.classList.add('is-open');
  }
  function close(id) {
    document.getElementById(id)?.classList.remove('is-open');
  }
  // Close on backdrop click
  document.addEventListener('click', e => {
    if (e.target.matches('.modal-backdrop')) e.target.classList.remove('is-open');
  });
  return { open, close };
})();

/* ── Mobile nav ───────────────────────────────────────────────────────── */
function initMobileNav() {
  const btn = document.querySelector('.nav__menu-btn');
  if (!btn) return;

  // Try sidebar first (dashboard pages)
  const sidebar = document.querySelector('.sidebar');

  // Create mobile drawer if it doesn't exist
  let drawer = document.getElementById('mobile-drawer');
  if (!drawer && !sidebar) {
    drawer = document.createElement('div');
    drawer.id = 'mobile-drawer';
    drawer.style.cssText = `
      display:none;position:fixed;top:60px;left:0;right:0;bottom:0;
      background:var(--primary);z-index:300;padding:20px;
      flex-direction:column;gap:4px;overflow-y:auto;
    `;

    const user = JSON.parse(localStorage.getItem('nx_user') || 'null');
    const role = user?.role || '';

    const links = [
      { href: '/', label: '🏠 Home' },
      { href: '/events/', label: '🔍 Browse Events' },
    ];
    if (role === 'customer') {
      links.push({ href: '/dashboard/customer/', label: '📋 My Dashboard' });
      links.push({ href: '/dashboard/my-tickets/', label: '🎫 My Tickets' });
      links.push({ href: '/dashboard/bookings/', label: '📦 My Bookings' });
      links.push({ href: '/dashboard/my-profile/', label: '👤 Profile' });
    }
    if (role === 'host' || role === 'super_admin') {
      links.push({ href: '/dashboard/host/', label: '📊 Host Dashboard' });
      links.push({ href: '/dashboard/events/', label: '📅 My Events' });
      links.push({ href: '/events/create/', label: '➕ Create Event' });
      links.push({ href: '/dashboard/earnings/', label: '💰 Earnings' });
      links.push({ href: '/dashboard/scanner/', label: '📷 QR Scanner' });
      links.push({ href: '/dashboard/bank-account/', label: '🏦 Bank Account' });
    }

    drawer.innerHTML = links.map(l =>
      `<a href="${l.href}" style="color:rgba(255,255,255,.85);padding:14px 16px;font-size:1rem;font-weight:500;border-radius:8px;display:block;text-decoration:none;border-bottom:1px solid rgba(255,255,255,.08)">${l.label}</a>`
    ).join('') + (user ? `<button onclick="Auth.logout()" style="color:rgba(255,255,255,.6);padding:14px 16px;font-size:1rem;background:none;border:none;cursor:pointer;text-align:left;width:100%">🚪 Sign Out</button>` : `<a href="/auth/login/" style="color:rgba(255,255,255,.85);padding:14px 16px;font-size:1rem;font-weight:500;display:block">Sign In</a><a href="/auth/register/" style="color:var(--gold);padding:14px 16px;font-size:1rem;font-weight:700;display:block">Get Started</a>`);

    document.body.appendChild(drawer);
  }

  btn.addEventListener('click', () => {
    if (sidebar) {
      sidebar.classList.toggle('is-open');
    } else if (drawer) {
      const open = drawer.style.display === 'flex';
      drawer.style.display = open ? 'none' : 'flex';
      btn.textContent = open ? '☰' : '✕';
    }
  });
}

/* ── Init ─────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  Theme.init();
  Auth.updateNavForUser();
  initMobileNav();

  document.getElementById('theme-toggle')?.addEventListener('click', Theme.toggle);
  document.getElementById('logout-btn')?.addEventListener('click', Auth.logout);
});