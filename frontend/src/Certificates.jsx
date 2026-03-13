import React, { useState, useEffect } from 'react'

const API = '' // same origin when proxied

export default function Certificates() {
  const [certs, setCerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selected, setSelected] = useState(null)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetch(`${API}/health`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error('Health check failed')))
      .then(() => { if (!cancelled) setStatus('ok') })
      .catch(e => { if (!cancelled) setStatus(e.message) })
    fetch(`${API}/api/certificates`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText)))
      .then(data => { if (!cancelled) setCerts(data) })
      .catch(e => { if (!cancelled) setError(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <>
      <h1 className="page-title">Certificates</h1>
      {status && (
        <p style={{ fontSize: '0.9rem', color: status === 'ok' ? 'var(--success)' : 'var(--warning)', marginBottom: '1rem' }}>
          {status === 'ok' ? 'Connected to CLM' : `API: ${status}`}
        </p>
      )}
      {error && <div className="alert alert-error">Failed to load: {error}</div>}
      {loading ? (
        <p className="text-muted">Loading certificates…</p>
      ) : (
        <div className="card">
          <div className="card-header">All certificates ({certs.length})</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Common name</th>
                  <th>Source</th>
                  <th>Product ID</th>
                  <th>Not after</th>
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
                    <td>
                      <button className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.85rem' }} onClick={() => setSelected(c)}>
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
              No certificates yet. Issue via ACME, API, Bulk Enroll, or SCEP.
            </div>
          )}
        </div>
      )}

      {selected && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Certificate details</span>
            <button className="btn btn-secondary" onClick={() => setSelected(null)}>Close</button>
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
              }, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </>
  )
}
