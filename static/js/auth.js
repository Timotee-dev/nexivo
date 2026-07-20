/**
 * NEXIVO — Authentication (login, register, social)
 */
document.addEventListener('DOMContentLoaded', () => {

  /* ── Login form ─────────────────────────────────────────────────────── */
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = loginForm.querySelector('button[type=submit]');
      const identifier = document.getElementById('identifier').value.trim();
      const password = document.getElementById('password').value;
      clearErrors(loginForm);
      btn.disabled = true; btn.textContent = 'Signing in…';

      try {
        const data = await Api.post('/auth/login/', { identifier, password }, true);
        Auth.setSession(data);
        const next = new URLSearchParams(location.search).get('next') || dashboardUrl(data.user.role);
        window.location.href = next;
      } catch(err) {
        const msg = err?.errors?.non_field_errors?.[0] || err?.detail || 'Login failed. Check your credentials.';
        showError(loginForm, 'identifier', msg);
        btn.disabled = false; btn.textContent = 'Sign In';
      }
    });
  }

  /* ── Register form ──────────────────────────────────────────────────── */
  const registerForm = document.getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = registerForm.querySelector('button[type=submit]');
      clearErrors(registerForm);
      btn.disabled = true; btn.textContent = 'Creating account…';

      const body = {
        email:            document.getElementById('email').value.trim(),
        first_name:       document.getElementById('first_name').value.trim(),
        last_name:        document.getElementById('last_name').value.trim(),
        phone_number:     document.getElementById('phone_number')?.value.trim() || undefined,
        password:         document.getElementById('password').value,
        password_confirm: document.getElementById('password_confirm').value,
        role:             document.getElementById('role')?.value || 'customer',
      };

      try {
        const data = await Api.post('/auth/register/', body, true);
        Auth.setSession(data);
        window.location.href = dashboardUrl(data.user.role);
      } catch(err) {
        if (err.errors) {
          Object.entries(err.errors).forEach(([field, msgs]) => {
            const arr = Array.isArray(msgs) ? msgs : [msgs];
            showError(registerForm, field, arr[0]);
          });
        } else {
          showError(registerForm, 'email', err.detail || 'Registration failed.');
        }
        btn.disabled = false; btn.textContent = 'Create Account';
      }
    });
  }

  /* ── Password change form ───────────────────────────────────────────── */
  const pwForm = document.getElementById('change-password-form');
  if (pwForm) {
    pwForm.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = pwForm.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'Saving…';
      try {
        await Api.post('/auth/change-password/', {
          old_password: document.getElementById('old_password').value,
          new_password: document.getElementById('new_password').value,
        });
        Toast.success('Password updated successfully.');
        pwForm.reset();
      } catch(err) {
        Toast.error(err?.errors?.old_password?.[0] || err?.detail || 'Failed to update password.');
      } finally {
        btn.disabled = false; btn.textContent = 'Change Password';
      }
    });
  }

  /* ── Helpers ─────────────────────────────────────────────────────────── */
  function dashboardUrl(role) {
    if (role === 'super_admin') return '/admin-dashboard/';
    if (role === 'host') return '/dashboard/host/';
    return '/dashboard/customer/';
  }

  function showError(form, field, message) {
    const input = form.querySelector(`[name="${field}"], #${field}`);
    if (input) input.classList.add('form-input--error');
    let errEl = form.querySelector(`.form-error[data-field="${field}"]`);
    if (!errEl) {
      errEl = document.createElement('p');
      errEl.className = 'form-error';
      errEl.dataset.field = field;
      input?.parentNode?.appendChild(errEl);
    }
    errEl.textContent = message;
  }

  function clearErrors(form) {
    form.querySelectorAll('.form-input--error').forEach(el => el.classList.remove('form-input--error'));
    form.querySelectorAll('.form-error').forEach(el => el.remove());
  }
});


/* ── Google OAuth ─────────────────────────────────────────────────────── */
function initGoogleSignIn() {
  if (!window.google || !window.google.accounts) return;
  const clientId = document.getElementById('google-client-id')?.value;
  if (!clientId || clientId === 'NOT_SET') return;

  google.accounts.id.initialize({
    client_id: clientId,
    callback: async (response) => {
      try {
        const role = document.getElementById('role')?.value || 'customer';
        const data = await Api.post('/auth/oauth/google/', {
          id_token: response.credential, role,
        }, true);
        Auth.setSession(data);
        window.location.href = dashboardUrl(data.user.role);
      } catch(err) {
        Toast.error(err?.detail || 'Google sign-in failed. Please try again.');
      }
    },
    auto_select: false,
  });
  google.accounts.id.renderButton(
    document.getElementById('google-signin-btn'),
    { theme: 'outline', size: 'large', width: '100%', text: 'continue_with' }
  );
}

// Load Google Identity Services script dynamically
document.addEventListener('DOMContentLoaded', () => {
  const clientId = document.getElementById('google-client-id')?.value;
  if (clientId && clientId !== 'NOT_SET') {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    script.defer = true;
    script.onload = initGoogleSignIn;
    document.head.appendChild(script);
  }
});
