const PAGES = ['signin', 'signup', 'forgot'];
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
  byId(textId).textContent = message || '';
  box.classList.toggle('show', Boolean(isVisible && message));
}

function clearBox(boxId, textId) {
  setBox(boxId, textId, '', false);
}

function setFieldState(inputId, hintId, message, validState) {
  const input = byId(inputId);
  const hint = byId(hintId);

  input.classList.remove('is-invalid', 'is-valid');
  hint.textContent = message || '';

  if (message) {
    input.classList.add(validState ? 'is-valid' : 'is-invalid');
  }
}

function clearField(inputId, hintId) {
  const input = byId(inputId);
  input.classList.remove('is-invalid', 'is-valid');
  byId(hintId).textContent = '';
}

function isEmail(value) {
  return EMAIL_RE.test(String(value || '').trim());
}

function setBusy(prefix, busy, label) {
  byId(`${prefix}-spinner`).style.display = busy ? 'block' : 'none';
  byId(`${prefix}-btn-text`).textContent = busy ? 'Please wait...' : label;
  byId(`btn-${prefix}`).disabled = busy;
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

function bindNavigation() {
  byId('go-signup').addEventListener('click', () => showPage('signup'));
  byId('go-forgot').addEventListener('click', () => showPage('forgot'));
  byId('back-to-signin-from-signup').addEventListener('click', () => showPage('signin'));
  byId('back-to-signin-from-forgot').addEventListener('click', () => showPage('signin'));
}

async function handleSignIn(event) {
  event.preventDefault();
  if (!validateSignIn()) return;

  setBusy('si', true, 'Sign In');

  try {
    const res = await fetch('/auth/signin', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        email: byId('si-email').value.trim(),
        password: byId('si-pass').value,
      }),
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Invalid credentials');
    }

    if (data.access_token) {
      Auth.setToken(data.access_token);
    }

    window.location.href = '/app/dashboard.html';
  } catch (error) {
    setBox('si-err', 'si-err-text', error.message, true);
  } finally {
    setBusy('si', false, 'Sign In');
  }
}

async function handleSignUp(event) {
  event.preventDefault();
  if (!validateSignUp()) return;

  setBusy('su', true, 'Sign Up');

  try {
    await new Promise((resolve) => setTimeout(resolve, 450));
    setPageDefaultsForSignIn(byId('su-email').value.trim());
    showPage('signin');
    setBox('si-err', 'si-err-text', 'Account created. Please sign in.', true);
  } catch (error) {
    setBox('su-err', 'su-err-text', error.message, true);
  } finally {
    setBusy('su', false, 'Sign Up');
  }
}

async function handleForgot(event) {
  event.preventDefault();
  if (!validateForgot()) return;

  setBusy('fo', true, 'Send reset link');

  try {
    await new Promise((resolve) => setTimeout(resolve, 450));
    setBox('fo-ok', 'fo-ok-text', 'Reset link sent. Check your inbox.', true);
  } catch (error) {
    setBox('fo-err', 'fo-err-text', error.message, true);
  } finally {
    setBusy('fo', false, 'Send reset link');
  }
}

function setPageDefaultsForSignIn(email) {
  byId('si-email').value = email;
  byId('si-pass').value = '';
  clearBox('si-err', 'si-err-text');
  clearField('si-email', 'si-email-hint');
  clearField('si-pass', 'si-pass-hint');
}

function init() {
  bindNavigation();
  makeToggle('toggle-si-pass', 'si-pass', 'eye-icon-si');
  makeToggle('toggle-su-pass', 'su-pass', 'eye-icon-su');
  makeToggle('toggle-su-confirm', 'su-confirm', 'eye-icon-su-confirm');

  wireFieldClears([
    ['si-email', 'si-email-hint'],
    ['si-pass', 'si-pass-hint'],
    ['su-name', 'su-name-hint'],
    ['su-email', 'su-email-hint'],
    ['su-pass', 'su-pass-hint'],
    ['su-confirm', 'su-confirm-hint'],
    ['fo-email', 'fo-email-hint'],
  ]);

  byId('form-signin').addEventListener('submit', handleSignIn);
  byId('form-signup').addEventListener('submit', handleSignUp);
  byId('form-forgot').addEventListener('submit', handleForgot);

  showPage('signin');
  clearBox('si-err', 'si-err-text');

  if (typeof requireAuth === 'function') {
    requireAuth();
  }
}

init();
