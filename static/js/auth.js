const PAGES = ['signin', 'signup', 'forgot', 'reset'];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function byId(id) {
  return document.getElementById(id);
}

function showPage(name) {
  PAGES.forEach((page) => {
    byId(`page-${page}`).classList.toggle('hidden', page !== name);
  });
}

function setBox(boxId, textId, message, isVisible) {
  const box = byId(boxId);
  const text = byId(textId);
  if (!box || !text) return;
  text.textContent = message || '';
  box.classList.toggle('show', Boolean(isVisible && message));
}

function persistUserProfile(user) {
  if (!user) return;
  const name = user.display_name || (user.email ? user.email.split('@')[0] : '');
  try { if (name) localStorage.setItem('displayName', name); } catch(e) {}
  // Hydrate event/cluster cache from the server-confirmed profile value.
  // This is read-only sync — not a write intent. UserPrefs owns the write path.
  UserPrefs.hydrateFromProfile(user);
}

function setEmailConfirmationHelp(visible, message) {
  const wrap = byId('si-resend-wrap');
  if (wrap) wrap.classList.toggle('hidden', !visible);
  if (message) {
    setBox('si-ok', 'si-ok-text', message, true);
  }
}

function clearEmailConfirmationHelp() {
  setEmailConfirmationHelp(false);
  clearBox('si-ok', 'si-ok-text');
}

function clearBox(boxId, textId) {
  setBox(boxId, textId, '', false);
}

function setFieldState(inputId, hintId, message, validState) {
  if (typeof ErrorManager !== 'undefined') {
    ErrorManager.showFieldError(inputId, message, validState ? 'success' : 'error');
  } else {
    const input = byId(inputId);
    const hint = byId(hintId);
    input.classList.remove('is-invalid', 'is-valid');
    hint.textContent = message || '';
    if (message) {
      input.classList.add(validState ? 'is-valid' : 'is-invalid');
    }
  }
}

function clearField(inputId, hintId) {
  if (typeof ErrorManager !== 'undefined') {
    ErrorManager.clearField(inputId);
  } else {
    const input = byId(inputId);
    input.classList.remove('is-invalid', 'is-valid');
    byId(hintId).textContent = '';
  }
}

function isEmail(value) {
  return EMAIL_RE.test(String(value || '').trim());
}

function setBusy(prefix, busy, label) {
  const buttonIds = {
    si: 'btn-signin',
    su: 'btn-signup',
    fo: 'btn-forgot',
    rp: 'btn-reset',
    google: 'btn-google',
    apple: 'btn-apple',
  };

  const spinner = byId(`${prefix}-spinner`);
  const text = byId(`${prefix}-btn-text`);
  const button = byId(buttonIds[prefix] || `btn-${prefix}`);

  if (spinner) spinner.style.display = busy ? 'block' : 'none';
  if (text) text.textContent = busy ? 'Please wait...' : label;
  if (button) button.disabled = busy;
}

function transitionToOpening(triggerEl, source = 'signin') {
  clearReturnPath();
  const button = triggerEl || byId('btn-signin');
  const rect = button ? button.getBoundingClientRect() : null;
  const startX = rect ? rect.left + rect.width / 2 : window.innerWidth * 0.5;
  const startY = rect ? rect.top + rect.height / 2 : window.innerHeight * 0.55;
  const startWidth = rect ? rect.width : 22;
  const startHeight = rect ? rect.height : 22;
  const startedAt = Date.now();

  if (button) {
    button.classList.add('launching');
  }

  try {
    sessionStorage.setItem('ct_opening_intro', JSON.stringify({
      startedAt,
      source,
      startX,
      startY,
      startWidth,
      startHeight,
    }));
  } catch (error) {}

  let layer = document.querySelector('.route-transition-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.className = 'route-transition-layer';
    layer.innerHTML = '<div class="route-orb"></div><div class="route-burst"></div>';
    document.body.appendChild(layer);
  }

  const orb = layer.querySelector('.route-orb');
  const burst = layer.querySelector('.route-burst');
  const duration = 520;
  const targetX = window.innerWidth * 0.5;
  const targetY = window.innerHeight * 0.5;

  const clamp01 = (value) => Math.max(0, Math.min(1, value));
  const easeOutCubic = (value) => 1 - Math.pow(1 - value, 3);

  const render = () => {
    const elapsed = Date.now() - startedAt;
    const progress = clamp01(elapsed / duration);
    const eased = easeOutCubic(progress);

    let x = startX + (targetX - startX) * eased;
    let y = startY + (targetY - startY) * eased;
    y += Math.sin(progress * 18 * Math.PI) * (14 * (1 - progress * 0.4));

    if (progress > 0.7) {
      const orbitProgress = clamp01((progress - 0.7) / 0.3);
      const angle = orbitProgress * Math.PI * 5;
      const radiusX = 36 * (1 - orbitProgress) + 14;
      const radiusY = 22 * (1 - orbitProgress) + 8;
      x = targetX + Math.cos(angle) * radiusX;
      y = targetY + Math.sin(angle) * radiusY * 0.8;
    }

    if (progress > 0.96) {
      const settle = clamp01((progress - 0.96) / 0.04);
      x += (targetX - x) * settle;
      y += (targetY - y) * settle;
    }

    const size = Math.max(56, startHeight * (1 - eased * 0.18) + 56 * eased);
    orb.style.opacity = '1';
    orb.style.width = `${size}px`;
    orb.style.height = `${size}px`;
    orb.style.transform = `translate3d(${x - size / 2}px, ${y - size / 2}px, 0)`;

    if (progress > 0.9) {
      const burstScale = 0.45 + (progress - 0.9) * 8;
      burst.style.opacity = String(Math.min(1, (progress - 0.9) / 0.1));
      burst.style.transform = `translate3d(${targetX - 70}px, ${targetY - 70}px, 0) scale(${burstScale})`;
    }

    if (progress < 1) {
      requestAnimationFrame(render);
    }
  };

  requestAnimationFrame(render);

  requestAnimationFrame(() => {
    document.body.classList.add('auth-route-opening');
  });
  window.setTimeout(() => {
    // Redirect to appropriate page based on auth source
    const redirectUrl = '/app/opening.html';
    window.location.href = redirectUrl;
  }, duration);
}

function updatePasswordStrength() {
  const v = byId('su-pass').value;
  let score = 0;

  if (v.length >= 6) score++;
  if (v.length >= 10) score++;
  if (/[A-Z]/.test(v) && /[0-9]/.test(v)) score++;
  if (/[^a-zA-Z0-9]/.test(v)) score++;

  const colors = ['', '#f87171', '#fb923c', '#facc15', '#4ade80'];
  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong'];
  const label = byId('strength-label');

  ['s1', 's2', 's3', 's4'].forEach((id, index) => {
    const bar = byId(id);
    if (!bar) return;
    bar.style.background = index < score ? (colors[score] || 'var(--border)') : 'var(--border)';
    bar.style.boxShadow = index < score && score >= 3 ? `0 0 10px ${colors[score]}33` : 'none';
  });

  if (label) {
    label.textContent = v.length ? labels[score] || 'Weak' : '';
    label.style.color = colors[score] || 'var(--muted)';
  }
}

async function handleAuthCallback() {
  const url = new URL(window.location.href);
  const type = url.searchParams.get('type') || url.hash.match(/type=([^&]+)/)?.[1] || '';
  let token =
    url.searchParams.get('access_token') ||
    url.searchParams.get('token') ||
    url.hash.match(/access_token=([^&]+)/)?.[1] ||
    url.hash.match(/token=([^&]+)/)?.[1];
  const refreshToken =
    url.searchParams.get('refresh_token') ||
    url.hash.match(/refresh_token=([^&]+)/)?.[1] ||
    url.hash.match(/refresh=([^&]+)/)?.[1];
  const tokenHash =
    url.searchParams.get('token_hash') ||
    url.hash.match(/token_hash=([^&]+)/)?.[1];

  if (!token && tokenHash && type === 'recovery') {
    try {
      const verifyResponse = await fetch('/auth/password-reset/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          token_hash: decodeURIComponent(tokenHash),
          type: 'recovery',
        }),
      });
      const verifyData = await verifyResponse.json().catch(() => ({}));
      if (!verifyResponse.ok || !verifyData.access_token) {
        throw new Error(
          verifyData.detail || 'This password recovery link is invalid or expired.',
        );
      }
      token = verifyData.access_token;
    } catch (error) {
      showPage('reset');
      setBox('rp-err', 'rp-err-text', error.message, true);
      return 'recovery-error';
    }
  }

  if (!token) {
    if (type === 'recovery' || url.pathname === '/reset-password') {
      showPage('reset');
      setBox(
        'rp-err',
        'rp-err-text',
        'This password recovery link is invalid or expired. Request a new link.',
        true,
      );
      return 'recovery-error';
    }
    return null;
  }

  const decodedToken = decodeURIComponent(token);
  const rememberMe = Auth.getRememberPreference();
  Auth.setToken(decodedToken, rememberMe ?? true);

  if (refreshToken) {
    try {
      await fetch('/auth/session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          refresh_token: decodeURIComponent(refreshToken),
          remember_me: rememberMe ?? true,
        }),
      });
    } catch (error) {
      // If session sync fails, the access token still works for this browser session.
    }
  }

  if (type === 'recovery') {
    window.history.replaceState({}, document.title, url.pathname);
    showPage('reset');
    clearBox('rp-err', 'rp-err-text');
    clearBox('rp-ok', 'rp-ok-text');
    return 'recovery';
  }

  window.history.replaceState({}, document.title, url.pathname);
  transitionToOpening(null, 'oauth');
  return 'login';
}

async function fetchJsonWithTimeout(url, options = {}, timeoutMs = 6000) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      credentials: 'same-origin',
      ...options,
      signal: controller.signal,
    });
    return response;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function makeToggle(btnId, inputId, iconId) {
  const eyeOpen = '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
  const eyeClose = '<line x1="1" y1="1" x2="23" y2="23"></line><path d="M3.5 8.5C5.5 5.5 8.4 4 12 4c4 0 8 3 10.5 8-1 2-2.4 3.8-4.1 5.1"></path>';
  let visible = false;

  byId(btnId).addEventListener('click', () => {
    visible = !visible;
    byId(inputId).type = visible ? 'text' : 'password';
    byId(iconId).innerHTML = visible ? eyeClose : eyeOpen;
    byId(btnId).setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
  });

  byId(iconId).innerHTML = eyeOpen;
}

function wireFieldClears(pairs) {
  pairs.forEach(([inputId, hintId]) => {
    const input = byId(inputId);
    input.addEventListener('input', () => clearField(inputId, hintId));
    input.addEventListener('blur', () => clearField(inputId, hintId));
  });
}

function validateSignIn() {
  let ok = true;
  const email = byId('si-email').value.trim();
  const password = byId('si-pass').value;

  clearBox('si-err', 'si-err-text');
  clearBox('si-ok', 'si-ok-text');
  clearEmailConfirmationHelp();

  if (!email) {
    setFieldState('si-email', 'si-email-hint', 'Email is required.');
    ok = false;
  } else if (!isEmail(email)) {
    setFieldState('si-email', 'si-email-hint', 'Enter a valid email address.');
    ok = false;
  } else {
    clearField('si-email', 'si-email-hint');
  }

  if (!password) {
    setFieldState('si-pass', 'si-pass-hint', 'Password is required.');
    ok = false;
  } else {
    clearField('si-pass', 'si-pass-hint');
  }

  const captchaWrap = byId('si-captcha-wrap');
  if (captchaWrap && !captchaWrap.classList.contains('hidden')) {
    const answer = byId('si-captcha-answer').value.trim();
    if (!answer) {
      setFieldState('si-captcha-answer', 'si-captcha-hint', 'Please complete the security check.');
      ok = false;
    } else {
      clearField('si-captcha-answer', 'si-captcha-hint');
    }
  }

  return ok;
}

function validateSignUp() {
  let ok = true;
  const name = byId('su-name').value.trim();
  const email = byId('su-email').value.trim();
  const password = byId('su-pass').value;
  const confirm = byId('su-confirm').value;
  const terms = byId('su-terms').checked;

  clearBox('su-err', 'su-err-text');
  clearBox('su-ok', 'su-ok-text');

  if (!name) {
    setFieldState('su-name', 'su-name-hint', 'Full name is required.');
    ok = false;
  } else {
    clearField('su-name', 'su-name-hint');
  }

  if (!email) {
    setFieldState('su-email', 'su-email-hint', 'Email is required.');
    ok = false;
  } else if (!isEmail(email)) {
    setFieldState('su-email', 'su-email-hint', 'Enter a valid email address.');
    ok = false;
  } else {
    clearField('su-email', 'su-email-hint');
  }

  if (!password) {
    setFieldState('su-pass', 'su-pass-hint', 'Password is required.');
    ok = false;
  } else if (password.length < 8) {
    setFieldState('su-pass', 'su-pass-hint', 'Use at least 8 characters.');
    ok = false;
  } else {
    clearField('su-pass', 'su-pass-hint');
  }

  if (!confirm) {
    setFieldState('su-confirm', 'su-confirm-hint', 'Please confirm your password.');
    ok = false;
  } else if (confirm !== password) {
    setFieldState('su-confirm', 'su-confirm-hint', 'Passwords do not match.');
    ok = false;
  } else {
    clearField('su-confirm', 'su-confirm-hint');
  }

  if (!terms) {
    byId('su-terms-hint').textContent = 'You need to agree before creating an account.';
    ok = false;
  } else {
    byId('su-terms-hint').textContent = '';
  }

  return ok;
}

function validateForgot() {
  let ok = true;
  const email = byId('fo-email').value.trim();
  clearBox('fo-err', 'fo-err-text');
  clearBox('fo-ok', 'fo-ok-text');

  if (!email) {
    setFieldState('fo-email', 'fo-email-hint', 'Email is required.');
    ok = false;
  } else if (!isEmail(email)) {
    setFieldState('fo-email', 'fo-email-hint', 'Enter a valid email address.');
    ok = false;
  } else {
    clearField('fo-email', 'fo-email-hint');
  }

  return ok;
}

function validateReset() {
  let ok = true;
  const password = byId('rp-pass').value;
  const confirm = byId('rp-confirm').value;

  clearBox('rp-err', 'rp-err-text');
  clearBox('rp-ok', 'rp-ok-text');

  if (!password) {
    setFieldState('rp-pass', 'rp-pass-hint', 'Password is required.');
    ok = false;
  } else if (password.length < 8) {
    setFieldState('rp-pass', 'rp-pass-hint', 'Use at least 8 characters.');
    ok = false;
  } else {
    clearField('rp-pass', 'rp-pass-hint');
  }

  if (!confirm) {
    setFieldState('rp-confirm', 'rp-confirm-hint', 'Please confirm your password.');
    ok = false;
  } else if (confirm !== password) {
    setFieldState('rp-confirm', 'rp-confirm-hint', 'Passwords do not match.');
    ok = false;
  } else {
    clearField('rp-confirm', 'rp-confirm-hint');
  }

  return ok;
}

function bindNavigation() {
  byId('go-signup').addEventListener('click', () => showPage('signup'));
  byId('go-forgot').addEventListener('click', () => showPage('forgot'));
  byId('back-to-signin-from-signup').addEventListener('click', () => showPage('signin'));
  byId('back-to-signin-from-forgot').addEventListener('click', () => showPage('signin'));
  const backFromReset = byId('back-to-signin-from-reset');
  if (backFromReset) {
    backFromReset.addEventListener('click', () => showPage('signin'));
  }
}

async function handleSocialLogin(provider) {
  setBusy(provider, true, `Sign in with ${provider === 'google' ? 'Google' : 'Apple'}`);

  try {
    const res = await fetchJsonWithTimeout(`/auth/oauth/${provider}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || `${provider} sign in failed`);
    }

    if (data.url) {
      window.location.href = data.url;
    }
  } catch (error) {
    const errorMessage = typeof ErrorManager !== 'undefined'
      ? ((error.name === 'AbortError' || String(error.message || '').toLowerCase().includes('fetch'))
          ? ErrorManager.formatNetworkError(error)
          : ErrorManager.formatAuthError(error))
      : (error.name === 'AbortError' ? 'Connection error, please try again.' : error.message);
    setBox('si-err', 'si-err-text', errorMessage, true);
  } finally {
    setBusy(provider, false, `Sign in with ${provider === 'google' ? 'Google' : 'Apple'}`);
  }
}

async function handleSignIn(event) {
  event.preventDefault();
  if (!validateSignIn()) return;

  setBusy('si', true, 'Sign In');
  const rememberMe = byId('si-remember').checked;
  const captchaAnswer = byId('si-captcha-answer').value.trim();
  let openingLaunchStarted = false;

  try {
    const res = await fetchJsonWithTimeout('/auth/signin', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: byId('si-email').value.trim(),
        password: byId('si-pass').value,
        remember_me: rememberMe,
        captcha_answer: captchaAnswer,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      if (data.requires_email_confirmation) {
        setEmailConfirmationHelp(true, data.detail || 'Please confirm your email before signing in.');
        return;
      }
      const err = new Error(data.detail || 'Invalid credentials');
      err.retryAfterSeconds = data.retry_after_seconds;
      err.captchaRequired = data.captcha_required;
      err.captchaPrompt = data.captcha_prompt;
      err.requiresEmailConfirmation = Boolean(data.requires_email_confirmation);
      throw err;
    }

    if (!data.access_token) {
      const pendingMsg = data.detail || 'Please confirm your email before signing in.';
      if (res.status === 202 || data.requires_email_confirmation) {
        setEmailConfirmationHelp(true, pendingMsg);
        return;
      }
      throw new Error(pendingMsg);
    }

    clearEmailConfirmationHelp();
    Auth.setToken(data.access_token, rememberMe);
    Auth.setRememberPreference(rememberMe);
    persistUserProfile(data.user);

    if (typeof ErrorManager !== 'undefined') {
      ErrorManager.showSuccess(ErrorManager.getSuccessMessage('SIGN_IN'), { duration: 2000 });
    }

    transitionToOpening(byId('btn-signin'), 'signin');
    openingLaunchStarted = true;
    return;
  } catch (error) {
    const lockSeconds = Number(error.retryAfterSeconds || 0);
    const errorMessage = lockSeconds > 0
      ? `Too many login attempts. Try again in ${Math.ceil(lockSeconds / 60)} minute${Math.ceil(lockSeconds / 60) === 1 ? '' : 's'}.`
      : (typeof ErrorManager !== 'undefined'
          ? ((error.name === 'AbortError' || String(error.message || '').toLowerCase().includes('fetch'))
              ? ErrorManager.formatNetworkError(error)
              : ErrorManager.formatAuthError(error))
          : (error.name === 'AbortError' ? 'Connection error, please try again.' : error.message));
    if (error.captchaRequired) {
      const wrap = byId('si-captcha-wrap');
      const question = byId('si-captcha-question');
      if (wrap) wrap.classList.remove('hidden');
      if (question) question.textContent = error.captchaPrompt || 'Please complete the security check.';
      clearField('si-captcha-answer', 'si-captcha-hint');
    }
    if (error.requiresEmailConfirmation) {
      setEmailConfirmationHelp(true, errorMessage);
      return;
    }
    setBox('si-err', 'si-err-text', errorMessage, true);
  } finally {
    if (!openingLaunchStarted) {
      setBusy('si', false, 'Sign In');
    }
  }
}

async function handleSignUp(event) {
  event.preventDefault();
  if (!validateSignUp()) return;

  setBusy('su', true, 'Sign Up');
  let openingLaunchStarted = false;

  try {
    const res = await fetchJsonWithTimeout('/auth/signup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        display_name: byId('su-name').value.trim(),
        email: byId('su-email').value.trim(),
        password: byId('su-pass').value,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || 'Sign up failed');
    }

    if (data.access_token) {
      Auth.setToken(data.access_token, true);
      Auth.setRememberPreference(true);
      persistUserProfile(data.user);
      if (typeof ErrorManager !== 'undefined') {
        ErrorManager.showSuccess(ErrorManager.getSuccessMessage('SIGN_UP'), { duration: 2000 });
      }
      transitionToOpening(byId('btn-signup'), 'signup');
      openingLaunchStarted = true;
      return;
    }

    showPage('signin');
    const successMsg = data.detail || (typeof ErrorManager !== 'undefined'
      ? ErrorManager.getSuccessMessage('SIGN_UP_CONFIRM')
      : 'Check your email to confirm your account.');
    if (data.requires_email_confirmation) {
      setEmailConfirmationHelp(true, successMsg);
    } else {
      setBox('si-ok', 'si-ok-text', successMsg, true);
    }
    if (typeof ErrorManager !== 'undefined') {
      ErrorManager.showSuccess(successMsg);
    }
  } catch (error) {
    const errorMessage = typeof ErrorManager !== 'undefined'
      ? ((error.name === 'AbortError' || String(error.message || '').toLowerCase().includes('fetch'))
          ? ErrorManager.formatNetworkError(error)
          : ErrorManager.formatAuthError(error))
      : (error.name === 'AbortError' ? 'Connection error, please try again.' : error.message);
    setBox('su-err', 'su-err-text', errorMessage, true);
  } finally {
    if (!openingLaunchStarted) {
      setBusy('su', false, 'Sign Up');
    }
  }
}

async function handleResendConfirmation() {
  const email = byId('si-email').value.trim();
  if (!email || !isEmail(email)) {
    setFieldState('si-email', 'si-email-hint', 'Enter a valid email to resend confirmation.');
    return;
  }

  const button = byId('btn-resend-confirm');
  if (button) button.disabled = true;

  try {
    const res = await fetchJsonWithTimeout('/auth/resend-confirmation', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || 'Unable to resend confirmation email.');
    }
    setEmailConfirmationHelp(true, data.message || 'Confirmation email sent. Check spam and Promotions.');
  } catch (error) {
    setBox('si-err', 'si-err-text', error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function handleForgot(event) {
  event.preventDefault();
  const email = byId('fo-email').value.trim();
  if (!validateForgot()) return;

  setBusy('fo', true, 'Send reset link');

  try {
    const res = await fetchJsonWithTimeout('/auth/password-reset/request', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || 'Unable to send reset link');
    }

    const successMsg = data.message || ErrorManager.getSuccessMessage('PASSWORD_RESET_REQUEST');
    setBox('fo-ok', 'fo-ok-text', successMsg, true);
    if (typeof ErrorManager !== 'undefined') {
      ErrorManager.showSuccess(successMsg);
    }
  } catch (error) {
    const errorMessage = typeof ErrorManager !== 'undefined' 
      ? ErrorManager.formatNetworkError(error)
      : (error.name === 'AbortError' ? 'Supabase is taking too long to respond. Please try again.' : error.message);
    setBox('fo-err', 'fo-err-text', errorMessage, true);
  } finally {
    setBusy('fo', false, 'Send reset link');
  }
}

async function handleReset(event) {
  event.preventDefault();
  if (!validateReset()) return;

  setBusy('rp', true, 'Update password');

  try {
    const res = await fetchJsonWithTimeout('/auth/password-reset/complete', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        password: byId('rp-pass').value,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.detail || 'Unable to update password');
    }

    const successMsg = data.message || ErrorManager.getSuccessMessage('PASSWORD_RESET_COMPLETE');
    setBox('rp-ok', 'rp-ok-text', successMsg, true);
    if (typeof ErrorManager !== 'undefined') {
      ErrorManager.showSuccess(successMsg, { duration: 2000 });
    }
    transitionToOpening(byId('btn-reset'), 'reset');
  } catch (error) {
    const errorMessage = typeof ErrorManager !== 'undefined' 
      ? ErrorManager.formatNetworkError(error)
      : (error.name === 'AbortError' ? 'Supabase is taking too long to respond. Please try again.' : error.message);
    setBox('rp-err', 'rp-err-text', errorMessage, true);
  } finally {
    setBusy('rp', false, 'Update password');
  }
}

function setPageDefaultsForSignIn(email) {
  byId('si-email').value = email;
  byId('si-pass').value = '';
  byId('si-captcha-answer').value = '';
  clearBox('si-err', 'si-err-text');
  clearBox('si-ok', 'si-ok-text');
  clearField('si-email', 'si-email-hint');
  clearField('si-pass', 'si-pass-hint');
  clearField('si-captcha-answer', 'si-captcha-hint');
  byId('si-captcha-wrap').classList.add('hidden');
  byId('si-captcha-question').textContent = '';
}

function init() {
  const authModePromise = handleAuthCallback();
  if (typeof applyClientEnvironment === 'function') {
    applyClientEnvironment();
  }
  
  // Check if user is already logged in and auto-redirect
  const existingToken = Auth.getToken();
  if (existingToken) {
    // Verify token is valid by checking /auth/me
    fetch('/auth/me', {
      headers: {
        'Authorization': `Bearer ${existingToken}`,
        'Content-Type': 'application/json',
      },
      credentials: 'same-origin',
    })
      .then(res => {
        if (res.ok) {
          // Token is valid, redirect to the opening flow
          transitionToOpening(null, 'signin');
          return;
        }
        // Token expired, clear it and show signin form
        Auth.clear();
        setupSigninForm();
      })
      .catch(() => {
        // Network error, clear and show signin form
        Auth.clear();
        setupSigninForm();
      });
    return;
  }
  
  setupSigninForm();
}

function setupSigninForm() {
  if (typeof applyClientEnvironment === 'function') {
    applyClientEnvironment();
  }
  bindNavigation();
  makeToggle('toggle-si-pass', 'si-pass', 'eye-icon-si');
  makeToggle('toggle-su-pass', 'su-pass', 'eye-icon-su');
  makeToggle('toggle-su-confirm', 'su-confirm', 'eye-icon-su-confirm');
  makeToggle('toggle-rp-pass', 'rp-pass', 'eye-icon-rp');
  makeToggle('toggle-rp-confirm', 'rp-confirm', 'eye-icon-rp-confirm');

  wireFieldClears([
    ['si-email', 'si-email-hint'],
    ['si-pass', 'si-pass-hint'],
    ['si-captcha-answer', 'si-captcha-hint'],
    ['su-name', 'su-name-hint'],
    ['su-email', 'su-email-hint'],
    ['su-pass', 'su-pass-hint'],
    ['su-confirm', 'su-confirm-hint'],
    ['fo-email', 'fo-email-hint'],
    ['rp-pass', 'rp-pass-hint'],
    ['rp-confirm', 'rp-confirm-hint'],
  ]);

  byId('form-signin').addEventListener('submit', handleSignIn);
  byId('form-signup').addEventListener('submit', handleSignUp);
  byId('form-forgot').addEventListener('submit', handleForgot);
  byId('form-reset').addEventListener('submit', handleReset);
  byId('su-pass').addEventListener('input', updatePasswordStrength);
  byId('btn-google').addEventListener('click', () => handleSocialLogin('google'));
  byId('btn-apple').addEventListener('click', () => handleSocialLogin('apple'));
  const resendBtn = byId('btn-resend-confirm');
  if (resendBtn) resendBtn.addEventListener('click', handleResendConfirmation);

  const storedRemember = Auth.getRememberPreference();
  if (storedRemember !== null) {
    byId('si-remember').checked = storedRemember;
  }

  handleAuthCallback().then((authMode) => {
    const isRecovery = authMode === 'recovery' || authMode === 'recovery-error';
    if (isRecovery) {
      showPage('reset');
    } else {
      showPage('signin');
    }
    clearBox('si-err', 'si-err-text');
    clearBox('si-ok', 'si-ok-text');
    clearBox('su-err', 'su-err-text');
    clearBox('su-ok', 'su-ok-text');
    clearBox('fo-err', 'fo-err-text');
    clearBox('fo-ok', 'fo-ok-text');
    if (authMode !== 'recovery-error') {
      clearBox('rp-err', 'rp-err-text');
    }
    clearBox('rp-ok', 'rp-ok-text');
    updatePasswordStrength();

    if (typeof requireAuth === 'function' && !isRecovery) {
      requireAuth();
    }
  });
}

init();
