const Auth = {
  tokenKey: 'ct_token',

  getToken() {
    return localStorage.getItem(this.tokenKey);
  },

  setToken(token) {
    localStorage.setItem(this.tokenKey, token);
  },

  clear() {
    localStorage.removeItem(this.tokenKey);
  },

  clearToken() {
    this.clear();
  },
};

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
      Auth.setToken(data.access_token);
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

  if (res.status === 401 && path !== '/auth/refresh' && path !== '/auth/logout') {
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
        window.location.href = '/';
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
      window.location.href = '/app/dashboard.html';
      return null;
    }

    return user;
  } catch (error) {
    Auth.clear();
    if (!isLoginPage()) {
      window.location.href = '/';
    }
    return null;
  }
}

function getDisplayName(user) {
  if (!user) return '';
  return user.display_name || (user.email ? user.email.split('@')[0] : 'User');
}

function initTopbar(user) {
  if (!user) return;

  const nameEl = document.getElementById('topbar-name');
  if (nameEl) nameEl.textContent = getDisplayName(user);

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
        await fetch('/auth/logout', {
          method: 'POST',
          credentials: 'same-origin',
        });
      } catch (error) {
        // Ignore logout transport errors and clear local session anyway.
      }
      Auth.clear();
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

window.Auth = Auth;
window.refreshSession = refreshSession;
window.apiFetch = apiFetch;
window.requireAuth = requireAuth;
window.getDisplayName = getDisplayName;
window.initTopbar = initTopbar;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.Store = Store;
