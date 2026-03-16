import React, { useState, useEffect, useCallback } from 'react'
import { apiFetch } from './api'

export default function Certificates() {
  const [certs, setCerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState(null)
  const [productIdFilter, setProductIdFilter] = useState('')
  const [renewCsr, setRenewCsr] = useState('')
  const [renewing, setRenewing] = useState(false)
  const [revoking, setRevoking] = useState(false)

  const loadCerts = useCallback(() => {
    const path = productIdFilter.trim()
      ? `/certificates?product_id=${encodeURIComponent(productIdFilter.trim())}`
      : '/certificates'
    setLoading(true)
    setError(null)
    fetch('/health')
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Health check failed')))
      .then(() => setStatus('ok'))
      .catch(e => setStatus(e.message))
    apiFetch(path)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText)))
      .then(setCerts)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [productIdFilter])

  useEffect(() => {
    loadCerts()
  }, [loadCerts])

  function handleRevoke() {
    if (!selected) return
    if (!confirm('Revoke this certificate? It will be marked revoked in CLM and revoked at DigiCert One TLM when configured.')) return
    setRevoking(true)
    apiFetch(`/certificates/${selected.id}/revoke`, { method: 'POST' })
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(new Error(d.detail || 'Revoke failed'))))
      .then(() => {
        loadCerts()
        setSelected(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setRevoking(false))
  }

  function handleRenew() {
    if (!selected || !renewCsr.trim() || !renewCsr.includes('BEGIN CERTIFICATE REQUEST')) {
      setError('Paste a PEM CSR for the renewed certificate.')
      return
    }
    setRenewing(true)
    setError(null)
    apiFetch(`/certificates/${selected.id}/renew`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ csr_pem: renewCsr.trim() }),
    })
      .then(r => r.ok ? r.json() : r.json().then(d => Promise.reject(new Error(d.detail || 'Renew failed'))))
      .then((newCert) => {
        loadCerts()
        setSelected(null)
        setRenewCsr('')
      })
      .catch(e => setError(e.message))
      .finally(() => setRenewing(false))
  }

  return (
    <>
      <h1 className="page-title">Certificates</h1>
      {status && (
        <p style={{ fontSize: '0.9rem', color: status === 'ok' ? 'var(--success)' : 'var(--warning)', marginBottom: '1rem' }}>
          {status === 'ok' ? 'Connected to CLM' : `API: ${status}`}
        </p>
      )}
      <div className="toolbar" style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
        <label style={{ fontSize: '0.9rem' }}>
          Product ID filter:
          <input
            type="text"
            value={productIdFilter}
            onChange={e => setProductIdFilter(e.target.value)}
            placeholder="e.g. my-product"
            style={{ marginLeft: '0.5rem', padding: '0.35rem 0.5rem', width: '200px' }}
          />
        </label>
        <button type="button" className="btn btn-secondary" onClick={loadCerts}>Refresh</button>
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {loading ? (
        <p className="text-muted">Loading certificates…</p>
      ) : (
        <div className="card">
          <div className="card-header">
            {productIdFilter.trim() ? `Certificates (product: ${productIdFilter.trim()})` : 'All certificates'} ({certs.length})
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Common name</th>
                  <th>Source</th>
                  <th>Product ID</th>
                  <th>Not after</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {certs.map(c => (
                  <tr key={c.id}>
                    <td>{c.common_name || '(no CN)'}</td>
                    <td><span className={`badge ${c.source}`}>{c.source}</span></td>
                    <td>{c.product_id || '—'}</td>
                    <td>{c.not_after ? new Date(c.not_after).toLocaleString() : '—'}</td>
                    <td>{c.revoked_at ? <span className="badge" style={{ background: 'var(--error)', color: '#fff' }}>Revoked</span> : '—'}</td>
                    <td>
                      <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }} onClick={() => { setSelected(c); setRenewCsr(''); setError(null) }}>
                        Details
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {certs.length === 0 && (
            <div className="card-body" style={{ color: 'var(--text-muted)' }}>
              {productIdFilter.trim() ? 'No certificates for this product ID.' : 'No certificates yet. Issue via ACME, Enroll, Bulk Enroll, or SCEP.'}
            </div>
          )}
        </div>
      )}

      {selected && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Certificate details</span>
            <button className="btn btn-secondary" onClick={() => { setSelected(null); setRenewCsr('') }}>Close</button>
          </div>
          <div className="card-body">
            <pre className="detail-pre">
              {JSON.stringify({
                id: selected.id,
                common_name: selected.common_name,
                sans_dns: selected.sans_dns,
                source: selected.source,
                product_id: selected.product_id,
                serial_number: selected.serial_number,
                not_before: selected.not_before,
                not_after: selected.not_after,
                sha256_fingerprint: selected.sha256_fingerprint,
                revoked_at: selected.revoked_at || null,
              }, null, 2)}
            </pre>
            {!selected.revoked_at && (
              <>
                <h3 style={{ fontSize: '1rem', marginTop: '1rem' }}>Renew</h3>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Submit a new CSR to issue a renewed certificate (same product ID).</p>
                <textarea
                  value={renewCsr}
                  onChange={e => setRenewCsr(e.target.value)}
                  placeholder="-----BEGIN CERTIFICATE REQUEST----- ... -----END CERTIFICATE REQUEST-----"
                  rows={4}
                  style={{ width: '100%', marginTop: '0.5rem', padding: '0.5rem', fontFamily: 'monospace', fontSize: '0.8rem' }}
                />
                <button type="button" className="btn btn-success" style={{ marginTop: '0.5rem' }} onClick={handleRenew} disabled={renewing}>
                  {renewing ? 'Renewing…' : 'Renew'}
                </button>
                <h3 style={{ fontSize: '1rem', marginTop: '1.5rem' }}>Revoke</h3>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>Mark this certificate as revoked in CLM and revoke it at DigiCert One TLM when configured.</p>
                <button type="button" className="btn" style={{ marginTop: '0.5rem', background: 'var(--error)', color: '#fff' }} onClick={handleRevoke} disabled={revoking}>
                  {revoking ? 'Revoking…' : 'Revoke'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
