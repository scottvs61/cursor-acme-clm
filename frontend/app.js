(function () {
  const API_BASE = window.location.origin;
  const listEl = document.getElementById('cert-list');
  const loadingEl = document.getElementById('loading');
  const detailEl = document.getElementById('detail');
  const detailBody = document.getElementById('detail-body');
  const statusEl = document.getElementById('api-status');
  const refreshBtn = document.getElementById('refresh');
  const detailCloseBtn = document.getElementById('detail-close');

  function setStatus(ok, text) {
    statusEl.textContent = text || (ok ? 'Connected' : 'API error');
    statusEl.className = 'api-status ' + (ok ? 'ok' : 'err');
  }

  async function checkHealth() {
    try {
      const r = await fetch(API_BASE + '/health');
      setStatus(r.ok, r.ok ? 'Connected' : 'Health check failed');
      return r.ok;
    } catch (e) {
      setStatus(false, 'Cannot reach API');
      return false;
    }
  }

  async function loadCertificates() {
    loadingEl.hidden = false;
    listEl.querySelectorAll('.cert-item').forEach((n) => n.remove());
    try {
      const r = await fetch(API_BASE + '/api/certificates');
      if (!r.ok) throw new Error(r.statusText);
      const certs = await r.json();
      loadingEl.hidden = true;
      if (certs.length === 0) {
        listEl.innerHTML = '<p class="loading">No certificates yet. Issue via ACME or POST /api/certificates.</p>';
        return;
      }
      certs.forEach((c) => {
        const item = document.createElement('div');
        item.className = 'cert-item';
        item.dataset.id = c.id;
        const cn = c.common_name || '(no CN)';
        const meta = [c.source, c.product_id ? `product: ${c.product_id}` : null, c.not_after ? new Date(c.not_after).toLocaleDateString() : ''].filter(Boolean).join(' · ');
        item.innerHTML = '<div><span class="cn">' + escapeHtml(cn) + '</span><div class="meta">' + escapeHtml(meta) + '</div></div><span class="source">' + escapeHtml(c.source) + '</span>';
        item.addEventListener('click', () => showDetail(c));
        listEl.appendChild(item);
      });
    } catch (e) {
      loadingEl.textContent = 'Failed to load: ' + e.message;
      setStatus(false, e.message);
    }
  }

  function escapeHtml(s) {
    if (s == null) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  function showDetail(cert) {
    detailBody.textContent = JSON.stringify(
      {
        id: cert.id,
        common_name: cert.common_name,
        sans_dns: cert.sans_dns,
        source: cert.source,
        product_id: cert.product_id,
        serial_number: cert.serial_number,
        not_before: cert.not_before,
        not_after: cert.not_after,
        sha256_fingerprint: cert.sha256_fingerprint,
      },
      null,
      2
    );
    detailEl.hidden = false;
  }

  detailCloseBtn.addEventListener('click', () => {
    detailEl.hidden = true;
  });
  refreshBtn.addEventListener('click', () => {
    checkHealth();
    loadCertificates();
  });

  checkHealth();
  loadCertificates();
})();
