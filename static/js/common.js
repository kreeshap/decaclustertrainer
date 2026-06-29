// ── Theme bootstrap — apply saved theme before any paint ────────────────────
(function() {
  try {
    var theme = localStorage.getItem('ct_theme') || 'dark';
    var root = document.documentElement;
    root.classList.remove('theme-light', 'theme-dark', 'theme-system');
    var effective = theme;
    if (theme === 'system') {
      effective = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    root.classList.add('theme-' + effective);
    root.style.colorScheme = effective;
  } catch(e) {}
})();

const Auth = {
  tokenKey: 'ct_token',
  rememberKey: 'ct_remember_me',

  getToken() {
    return localStorage.getItem(this.tokenKey) || sessionStorage.getItem(this.tokenKey);
  },

  setToken(token, persistent = true) {
    if (persistent) {
      localStorage.setItem(this.tokenKey, token);
      sessionStorage.removeItem(this.tokenKey);
    } else {
      sessionStorage.setItem(this.tokenKey, token);
      localStorage.removeItem(this.tokenKey);
    }
  },

  isPersistent() {
    const value = this.getRememberPreference();
    return value !== null ? value : true;
  },

  setRememberPreference(persistent) {
    const value = persistent ? '1' : '0';
    if (persistent) {
      localStorage.setItem(this.rememberKey, value);
      sessionStorage.removeItem(this.rememberKey);
    } else {
      sessionStorage.setItem(this.rememberKey, value);
      localStorage.removeItem(this.rememberKey);
    }
  },

  getRememberPreference() {
    const value = localStorage.getItem(this.rememberKey) ?? sessionStorage.getItem(this.rememberKey);
    if (value === '1') return true;
    if (value === '0') return false;
    return null;
  },

  clear() {
    localStorage.removeItem(this.tokenKey);
    sessionStorage.removeItem(this.tokenKey);
  },

  clearToken() {
    this.clear();
  },
};

function getCookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : '';
}

function getAuthReturnPath() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get('next') || sessionStorage.getItem('ct_return_to') || '';
  if (next && next.startsWith('/') && !next.startsWith('//')) {
    return next;
  }
  return '/app/opening.html';
}

function rememberReturnPath(path) {
  if (path && path.startsWith('/') && !path.startsWith('//')) {
    sessionStorage.setItem('ct_return_to', path);
  }
}

function clearReturnPath() {
  sessionStorage.removeItem('ct_return_to');
}

function detectClientEnvironment() {
  const ua = navigator.userAgent || '';
  const browser = navigator.userAgentData?.brands?.[0]?.brand || (
    /Chrome/i.test(ua) ? 'Chrome' :
    /Safari/i.test(ua) && !/Chrome/i.test(ua) ? 'Safari' :
    /Firefox/i.test(ua) ? 'Firefox' :
    /Edg/i.test(ua) ? 'Edge' :
    /Opera|OPR/i.test(ua) ? 'Opera' :
    'Unknown'
  );

  const device = navigator.userAgentData?.mobile || /Mobi|Android|iPhone|iPad/i.test(ua) ? 'mobile' : 'desktop';
  const platform = navigator.userAgentData?.platform || navigator.platform || 'unknown';
  return { browser, device, platform };
}

function applyClientEnvironment() {
  const info = detectClientEnvironment();
  document.documentElement.dataset.browser = info.browser.toLowerCase();
  document.documentElement.dataset.device = info.device;
  document.documentElement.dataset.platform = String(info.platform).toLowerCase();

  if (document.body) {
    document.body.dataset.browser = info.browser.toLowerCase();
    document.body.dataset.device = info.device;
    document.body.dataset.platform = String(info.platform).toLowerCase();
    document.body.classList.toggle('is-mobile', info.device === 'mobile');
  }

  window.ClientInfo = info;
  return info;
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => applyClientEnvironment(), { once: true });
} else {
  applyClientEnvironment();
}

async function refreshSession() {
  try {
    const res = await fetch('/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });

    if (!res.ok) {
      return false;
    }

    const data = await res.json().catch(() => ({}));
    if (data.access_token) {
      Auth.setToken(data.access_token, Auth.isPersistent());
    }

    return Boolean(data.access_token);
  } catch (error) {
    return false;
  }
}

async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  const token = Auth.getToken();
  const fetchOptions = Object.assign({ credentials: 'same-origin' }, options, { headers });

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let res = await fetch(path, fetchOptions);

  if (res.status === 401 && path !== '/auth/refresh' && path !== '/auth/logout' && path !== '/auth/signout') {
    const refreshed = await refreshSession();
    if (refreshed) {
      const freshToken = Auth.getToken();
      if (freshToken) {
        headers.Authorization = `Bearer ${freshToken}`;
      } else {
        delete headers.Authorization;
      }
      res = await fetch(path, fetchOptions);
    }
  }

  return res;
}

function isLoginPage() {
  const path = window.location.pathname;
  return (
    path === '/' ||
    path === '/app/' ||
    path === '/app/index.html' ||
    path === '/reset-password' ||
    path.endsWith('signon.html') ||
    path.endsWith('index.html') ||
    path.endsWith('index')
  );
}

async function requireAuth() {
  let token = Auth.getToken();

  if (!token) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      if (!isLoginPage()) {
        rememberReturnPath(window.location.pathname + window.location.search);
        window.location.href = `/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
      }
      return null;
    }
    token = Auth.getToken();
  }

  try {
    const res = await apiFetch('/auth/me');
    if (!res.ok) {
      throw new Error('bad token');
    }

    const data = await res.json().catch(() => ({}));
    const user = data?.user || null;

    if (!user) {
      throw new Error('no user');
    }

  if (isLoginPage()) {
      window.location.href = getAuthReturnPath();
      return null;
    }

    return user;
  } catch (error) {
    Auth.clear();
    if (!isLoginPage()) {
      rememberReturnPath(window.location.pathname + window.location.search);
      window.location.href = `/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    }
    return null;
  }
}

function getDisplayName(user) {
  if (!user) return '';
  return user.display_name || (user.email ? user.email.split('@')[0] : 'User');
}

function isAdminEmail(email) {
  return String(email || '').trim().toLowerCase() === 'kreesha.patel0831@gmail.com';
}

function renderTopNav(user) {
  const nav = document.getElementById('dashboard-nav');
  if (!nav) return;

  const currentPath = window.location.pathname;
  const items = [
    {
      label: 'Dashboard',
      href: '/app/dashboard.html',
      active: currentPath.endsWith('/app/dashboard.html') || currentPath.endsWith('/app/index.html'),
    },
    {
      label: 'Learn',
      href: '/app/learn.html',
      active: currentPath.endsWith('/app/learn.html'),
    },
    {
      label: 'Questions',
      href: '/app/practicequestions.html',
      active: currentPath.endsWith('/app/practicequestions.html'),
    },
    {
      label: 'Roleplays',
      href: '/app/practiceroleplays.html',
      active: currentPath.endsWith('/app/practiceroleplays.html'),
    },
  ];

  if (isAdminEmail(user && user.email)) {
    items.push({
      label: 'Admin',
      href: '/app/adminpanel.html',
      active: currentPath.endsWith('/app/adminpanel.html'),
    });
  }

  nav.innerHTML = items.map((item) => (
    `<a class="topbar-link${item.active ? ' active' : ''}" href="${item.href}" data-nav-label="${item.label}">${item.label}</a>`
  )).join('');

  const links = Array.from(nav.querySelectorAll('.topbar-link'));
  links.forEach((link) => {
    link.addEventListener('click', () => {
      links.forEach((other) => {
        other.classList.remove('active', 'is-pressing');
      });
      link.classList.add('active', 'is-pressing');

      window.setTimeout(() => {
        link.classList.remove('is-pressing');
      }, 180);
    });
  });
}

function initTopbar(user) {
  if (!user) return;

  const nameEl = document.getElementById('topbar-name');
  if (nameEl) nameEl.textContent = getDisplayName(user);

  renderTopNav(user);

  const brand = document.querySelector('.topbar-brand, .app-brand');
  if (brand) {
    brand.onclick = () => {
      window.location.href = '/app/dashboard.html';
    };
  }

  const btnSettings = document.getElementById('btn-settings');
  if (btnSettings) {
    btnSettings.onclick = () => {
      window.location.href = '/app/settings.html';
    };
  }

  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.onclick = async () => {
      showLoading('Logging out...');
      try {
        await fetch('/auth/signout', {
          method: 'POST',
          credentials: 'same-origin',
        });
      } catch (error) {
        // Ignore logout transport errors and clear local session anyway.
      }
      Auth.clear();
      clearReturnPath();
      window.location.href = '/';
    };
  }
}

function showLoading(msg = 'Loading...') {
  let el = document.getElementById('loading-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'loading-overlay';
    el.className = 'loading-overlay';
    el.innerHTML = `
      <div class="spinner-container">
        <div class="spinner"></div>
        <p class="loading-text"></p>
      </div>`;
    document.body.appendChild(el);
  }

  const text = el.querySelector('.loading-text');
  if (text) text.textContent = msg;
  el.classList.remove('hidden');
}

function hideLoading() {
  const el = document.getElementById('loading-overlay');
  if (el) el.classList.add('hidden');
}

const Store = {
  set(key, val) {
    sessionStorage.setItem('ct_' + key, JSON.stringify(val));
  },

  get(key) {
    try {
      const item = sessionStorage.getItem('ct_' + key);
      return item ? JSON.parse(item) : null;
    } catch (error) {
      return null;
    }
  },

  del(key) {
    sessionStorage.removeItem('ct_' + key);
  },
};

// ── UserPrefs — single authority for user preference state ───────────────────
//
// IDENTITY CONTRACT: event_id (slug) is the single canonical identifier.
//   - ct_selected_event_id  → slug, e.g. "accounting_application_series"
//   - ct_selected_event     → display name (derived/cached for UI only)
//   - ct_selected_cluster   → cluster display name
//
// Write path:  UserPrefs.setEvent(eventId, eventName, clusterName)  →  server first, then cache
// Login path:  UserPrefs.hydrateFromProfile(user)  →  cache only (server already confirmed)
// Read path:   UserPrefs.getEventId()   →  slug (use for all API calls and logic)
//              UserPrefs.getEventName() →  display name only
//
const UserPrefs = {
  _eventIdKey:   'ct_selected_event_id',
  _eventNameKey: 'ct_selected_event',    // display only — never used for identity
  _clusterKey:   'ct_selected_cluster',

  // Slug — use this for all API calls and logic
  getEventId()   { try { return localStorage.getItem(this._eventIdKey)   || ''; } catch(e) { return ''; } },
  // Display name — use only for UI text
  getEventName() { try { return localStorage.getItem(this._eventNameKey) || ''; } catch(e) { return ''; } },
  // Kept for backward-compat callers; returns slug
  getEvent()     { return this.getEventId(); },
  getCluster()   { try { return localStorage.getItem(this._clusterKey)   || ''; } catch(e) { return ''; } },

  // The one function allowed to write event state.
  // eventId   = slug, e.g. "accounting_application_series"  (required)
  // eventName = display name, e.g. "Accounting Application Series" (required for UI)
  // clusterName = display name of the cluster (optional)
  // Saves to server first; only updates cache on success.
  async setEvent(eventId, eventName, clusterName) {
    if (!eventId) return null;
    const token = Auth.getToken();
    if (!token) {
      // Not logged in — cache only (opening screen before signup completes)
      this._writeCache(eventId, eventName, clusterName);
      return { eventId, eventName, clusterName };
    }
    try {
      const res = await fetch('/auth/profile', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          default_event_id:  eventId,
          default_event:     eventName   || '',   // keep name for display restore
          default_cluster:   clusterName || '',
        }),
      });
      if (!res.ok) return null;
      this._writeCache(eventId, eventName, clusterName);
      return { eventId, eventName, clusterName };
    } catch(e) {
      return null;
    }
  },

  // Called at login/page-load from a confirmed server profile.
  // Prefers default_event_id (slug); falls back to deriving slug from default_event name
  // via the CLUSTERS map if needed (migration path for existing profiles).
  hydrateFromProfile(user) {
    if (!user) return;
    let eventId   = user.default_event_id || '';
    const eventName = user.default_event  || '';
    const clusterName = user.default_cluster || '';

    if (typeof getEventIdByName === 'function') {
      eventId = getEventIdByName(eventId || eventName || '');
    }

    // Migration: old profiles stored name in default_event, no slug yet
    if (!eventId && eventName && typeof CLUSTERS !== 'undefined') {
      for (const c of CLUSTERS) {
        for (const ev of c.events) {
          const name = typeof ev === 'string' ? ev : ev.name;
          if (name === eventName) {
            // Derive slug using the shared canonicalizer
            eventId = (typeof getEventIdByName === 'function')
              ? getEventIdByName(name)
              : name.toLowerCase().replace(/ /g, '_');
            break;
          }
        }
        if (eventId) break;
      }
    }

    if (eventId) this._writeCache(eventId, eventName, clusterName);
    // If server has nothing, leave existing cache alone
  },

  // Internal — the only place localStorage gets written
  _writeCache(eventId, eventName, clusterName) {
    try {
      if (eventId)     localStorage.setItem(this._eventIdKey,   eventId);
      if (eventName)   localStorage.setItem(this._eventNameKey, eventName);
      if (clusterName) localStorage.setItem(this._clusterKey,   clusterName);
    } catch(e) {}
  },
};

const ErrorManager = {
  errorTypes: {
    VALIDATION: 'validation',
    NETWORK: 'network',
    AUTH: 'auth',
    SERVER: 'server',
    SUCCESS: 'success',
    INFO: 'info',
  },

  toastContainer: null,
  activeToasts: new Set(),

  init() {
    if (!this.toastContainer) {
      this.toastContainer = document.createElement('div');
      this.toastContainer.id = 'toast-container';
      this.toastContainer.className = 'toast-container';
      document.body.appendChild(this.toastContainer);
    }
  },

  show(message, type = 'error', options = {}) {
    this.init();

    const {
      duration = 5000,
      dismissible = true,
      fieldId = null,
      formId = null,
    } = options;

    if (fieldId) {
      this.showFieldError(fieldId, message, type);
      return;
    }

    if (formId) {
      this.showFormError(formId, message, type);
      return;
    }

    this.showToast(message, type, { duration, dismissible });
  },

  showToast(message, type, options = {}) {
    const { duration = 5000, dismissible = true } = options;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <div class="toast-content">
        <span class="toast-message">${this.escapeHtml(message)}</span>
        ${dismissible ? '<button class="toast-close" aria-label="Close">&times;</button>' : ''}
      </div>
    `;

    this.toastContainer.appendChild(toast);
    this.activeToasts.add(toast);

    if (dismissible) {
      const closeBtn = toast.querySelector('.toast-close');
      closeBtn.addEventListener('click', () => this.dismissToast(toast));
    }

    if (duration > 0) {
      setTimeout(() => this.dismissToast(toast), duration);
    }

    return toast;
  },

  dismissToast(toast) {
    if (this.activeToasts.has(toast)) {
      toast.classList.add('toast-dismissing');
      setTimeout(() => {
        toast.remove();
        this.activeToasts.delete(toast);
      }, 300);
    }
  },

  showFieldError(fieldId, message, type = 'error') {
    const field = document.getElementById(fieldId);
    if (!field) return;

    const hintId = fieldId.replace(/^(si|su|fo|rp)-/, '$1-') + fieldId.split('-')[1] + '-hint';
    const hint = document.getElementById(hintId);

    field.classList.remove('is-invalid', 'is-valid');
    if (hint) hint.textContent = '';

    if (type === 'error') {
      field.classList.add('is-invalid');
      if (hint) hint.textContent = message;
    } else if (type === 'success') {
      field.classList.add('is-valid');
    }
  },

  showFormError(formId, message, type = 'error') {
    const prefix = formId.replace('form-', '');
    const boxId = `${prefix}-err`;
    const textId = `${prefix}-err-text`;
    const okBoxId = `${prefix}-ok`;
    const okTextId = `${prefix}-ok-text`;

    const errBox = document.getElementById(boxId);
    const errText = document.getElementById(textId);
    const okBox = document.getElementById(okBoxId);
    const okText = document.getElementById(okTextId);

    if (errBox && errText) {
      errBox.classList.remove('show');
    }
    if (okBox && okText) {
      okBox.classList.remove('show');
    }

    if (type === 'error' && errBox && errText) {
      errText.textContent = message;
      errBox.classList.add('show');
    } else if (type === 'success' && okBox && okText) {
      okText.textContent = message;
      okBox.classList.add('show');
    }
  },

  clearField(fieldId) {
    const field = document.getElementById(fieldId);
    if (!field) return;

    const hintId = fieldId.replace(/^(si|su|fo|rp)-/, '$1-') + fieldId.split('-')[1] + '-hint';
    const hint = document.getElementById(hintId);

    field.classList.remove('is-invalid', 'is-valid');
    if (hint) hint.textContent = '';
  },

  clearForm(formId) {
    const prefix = formId.replace('form-', '');
    const boxId = `${prefix}-err`;
    const textId = `${prefix}-err-text`;
    const okBoxId = `${prefix}-ok`;
    const okTextId = `${prefix}-ok-text`;

    const errBox = document.getElementById(boxId);
    const errText = document.getElementById(textId);
    const okBox = document.getElementById(okBoxId);
    const okText = document.getElementById(okTextId);

    if (errBox) errBox.classList.remove('show');
    if (errText) errText.textContent = '';
    if (okBox) okBox.classList.remove('show');
    if (okText) okText.textContent = '';
  },

  clearAll() {
    this.activeToasts.forEach(toast => this.dismissToast(toast));
    ['signin', 'signup', 'forgot', 'reset'].forEach(form => {
      this.clearForm(`form-${form}`);
    });
  },

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  },

  formatNetworkError(error) {
    if (error.name === 'AbortError') {
      return 'Connection error, please try again.';
    }
    if (error.message.includes('fetch')) {
      return 'Connection error, please try again.';
    }
    return error.message || 'An unexpected error occurred.';
  },

  formatAuthError(error) {
    const message = error.message?.toLowerCase() || '';
    if (message.includes('invalid') || message.includes('credentials')) {
      return 'Invalid email or password.';
    }
    if (message.includes('exists')) {
      return 'An account with this email already exists.';
    }
    if (message.includes('not found')) {
      return 'Account not found.';
    }
    return error.message || 'Authentication failed.';
  },

  showSuccess(message, options = {}) {
    return this.show(message, 'success', options);
  },

  showInfo(message, options = {}) {
    return this.show(message, 'info', options);
  },

  showFieldSuccess(fieldId) {
    this.showFieldError(fieldId, '', 'success');
  },

  showFormSuccess(formId, message) {
    this.showFormError(formId, message, 'success');
  },

  successMessages: {
    SIGN_IN: 'Successfully signed in!',
    SIGN_UP: 'Account created successfully!',
    SIGN_UP_CONFIRM: 'Check your email to confirm your account.',
    SIGN_OUT: 'Successfully signed out.',
    PASSWORD_RESET_REQUEST: 'Reset link sent. Check your email.',
    PASSWORD_RESET_COMPLETE: 'Password updated successfully.',
    PROFILE_UPDATED: 'Profile updated successfully.',
    SETTINGS_SAVED: 'Settings saved successfully.',
  },

  getSuccessMessage(key) {
    return this.successMessages[key] || 'Action completed successfully.';
  },
};

window.Auth = Auth;
window.getCookie = getCookie;
window.getAuthReturnPath = getAuthReturnPath;
window.rememberReturnPath = rememberReturnPath;
window.clearReturnPath = clearReturnPath;
window.detectClientEnvironment = detectClientEnvironment;
window.applyClientEnvironment = applyClientEnvironment;
window.refreshSession = refreshSession;
window.apiFetch = apiFetch;
window.requireAuth = requireAuth;
window.getDisplayName = getDisplayName;
window.initTopbar = initTopbar;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.Store = Store;
window.ErrorManager = ErrorManager;
