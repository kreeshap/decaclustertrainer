var Auth = window.Auth || {
  getToken: function () {
    return localStorage.getItem('access_token');
  },

  setToken: function (token) {
    localStorage.setItem('access_token', token);
  },

  clearToken: function () {
    localStorage.removeItem('access_token');
  }
};

var requireAuth = window.requireAuth || async function () {
  if (Auth.getToken()) {
    window.location.href = '/app/dashboard.html';
  }
};

window.Auth = Auth;
window.requireAuth = requireAuth;
