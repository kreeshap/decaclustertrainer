// Extra learn mode UI and feature stubs
(function () {
  function $(id) { return document.getElementById(id); }

  function initLearnExtra() {
    // Wire the single consolidated search input
    const searchInput = $('learn-search');
    const searchPanel = $('search-results');

    if (searchInput) {
      searchInput.addEventListener('input', async (e) => {
        const q = (e.target.value || '').trim();
        if (!q) {
          searchPanel.classList.add('hidden');
          return;
        }
        searchPanel.classList.remove('hidden');
        searchPanel.textContent = 'Searching...';
        try {
          const res = await fetch('/api/kpis');
          const data = await res.json();
          const kpis = data.kpis || [];
          const matched = kpis.filter(k => (k.code + ' ' + k.text + ' ' + (k.cluster||'')).toLowerCase().includes(q.toLowerCase()));
          if (!matched.length) {
            searchPanel.textContent = 'No results';
            return;
          }
          searchPanel.innerHTML = '';
          matched.slice(0, 25).forEach(k => {
            const row = document.createElement('div');
            row.className = 'search-row';
            row.innerHTML = `<strong>${escapeHtml(k.code)}</strong> — ${escapeHtml(k.text)}`;
            row.addEventListener('click', () => {
              // UserPrefs.setEvent owns all event writes
              if (k.event_name) UserPrefs.setEvent(k.event_name, k.cluster_name || '');
              window.location.href = '/app/learn.html';
            });
            searchPanel.appendChild(row);
          });
        } catch (e) {
          searchPanel.textContent = 'Search failed.';
        }
      });
    }

    // Admin panel visibility — already wired in learn.js to check admin status
    // Admin upload + review handlers
    const adminPanel = $('admin-tools-panel');
    const kpiImportBtn = $('kpi-import-btn');
    const kpiEditBtn = $('kpi-edit-open-btn');
    const reviewQsBtn = $('btn-review-questions');
    const reviewScBtn = $('btn-review-scenarios');

    // Get file input from admin panel
    function _getAdminFileInput() {
      if (adminPanel) {
        return adminPanel.querySelector('input[type=file]');
      }
      return null;
    }

    if (kpiImportBtn) {
      kpiImportBtn.addEventListener('click', async () => {
        const input = _getAdminFileInput();
        if (!input || !input.files || !input.files.length) {
          alert('Select a KPI JSON file to upload.');
          return;
        }
        const f = input.files[0];
        const fd = new FormData();
        fd.append('file', f);
        kpiImportBtn.disabled = true;
        kpiImportBtn.textContent = 'Uploading...';
        try {
          const res = await fetch('/api/admin/kpis/import', { method: 'POST', body: fd });
          const data = await res.json();
          if (res.ok) {
            alert('Import saved: ' + (data.saved_file || '') + '\nTotal KPIs: ' + (data.kpis_total || data.imported || 0));
          } else {
            alert('Import failed: ' + JSON.stringify(data));
          }
        } catch (e) {
          alert('Upload error');
        } finally {
          kpiImportBtn.disabled = false;
          kpiImportBtn.textContent = 'Upload KPIs';
        }
      });
    }

    if (kpiEditBtn) {
      kpiEditBtn.addEventListener('click', () => {
        // Open admin KPI editor route (if exists) or show admin panel
        window.location.href = '/admin/kpis';
      });
    }

    if (reviewQsBtn) {
      reviewQsBtn.addEventListener('click', async () => {
        try {
          const res = await fetch('/api/admin/questions');
          const data = await res.json();
          console.log('questions', data);
          alert('Fetched ' + (data.total || (data.questions || []).length) + ' questions. See console for details.');
        } catch (e) { alert('Failed to fetch questions'); }
      });
    }

    if (reviewScBtn) {
      reviewScBtn.addEventListener('click', async () => {
        try {
          const res = await fetch('/api/admin/analytics');
          const data = await res.json();
          console.log('analytics', data);
          alert('Fetched analytics. See console for details.');
        } catch (e) { alert('Failed to fetch analytics'); }
      });
    }
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Expose init to global so learn.js can call if desired
  window.initLearnExtra = initLearnExtra;

  // Auto-init when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initLearnExtra(), { once: true });
  } else {
    initLearnExtra();
  }
})();
