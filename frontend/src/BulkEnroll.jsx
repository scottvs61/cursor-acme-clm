import React, { useState } from 'react'

const API = ''

export default function BulkEnroll() {
  const [csrText, setCsrText] = useState('')
  const [defaultProductId, setDefaultProductId] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function parseCSRs(text) {
    const blocks = []
    let current = []
    const lines = text.split(/\r?\n/)
    for (const line of lines) {
      if (line.includes('BEGIN CERTIFICATE REQUEST')) {
        current = [line]
      } else if (current.length) {
        current.push(line)
        if (line.includes('END CERTIFICATE REQUEST')) {
          blocks.push(current.join('\n'))
          current = []
        }
      }
    }
    if (current.length) blocks.push(current.join('\n'))
    return blocks
  }

  function handleSubmit(e) {
    e.preventDefault()
    const pems = parseCSRs(csrText.trim())
    if (!pems.length) {
      setError('No PEM CSRs found. Paste one or more -----BEGIN CERTIFICATE REQUEST----- ... -----END CERTIFICATE REQUEST----- blocks.')
      return
    }
    if (pems.length > 100) {
      setError('Maximum 100 CSRs per request.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)
    fetch(`${API}/api/bulk/enroll`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requests: pems.map(csr_pem => ({ csr_pem, product_id: null })),
        default_product_id: defaultProductId.trim() || null,
      }),
    })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (ok) setResult(data)
        else setError(data.detail || data.message || 'Request failed')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <>
      <h1 className="page-title">Bulk enrollment</h1>
      <div className="alert alert-info">
        Paste one or more PEM CSRs below (each starting with <code>-----BEGIN CERTIFICATE REQUEST-----</code>). Optional: set a default Product ID for all. Maximum 100 per request.
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Default Product ID (optional)</label>
          <input
            type="text"
            value={defaultProductId}
            onChange={e => setDefaultProductId(e.target.value)}
            placeholder="e.g. my-product"
          />
        </div>
        <div className="form-group">
          <label>CSRs (PEM, one or more)</label>
          <textarea
            value={csrText}
            onChange={e => setCsrText(e.target.value)}
            placeholder="-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----"
            rows={12}
          />
        </div>
        <button type="submit" className="btn btn-success" disabled={loading}>
          {loading ? 'Enrolling…' : 'Enroll'}
        </button>
      </form>

      {error && <div className="alert alert-error" style={{ marginTop: '1rem' }}>{error}</div>}

      {result && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div className="card-header">
            Result: {result.succeeded} succeeded, {result.failed} failed (total {result.total})
          </div>
          <div className="card-body">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Status</th>
                    <th>Certificate ID / Error</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.map((r, i) => (
                    <tr key={i}>
                      <td>{i + 1}</td>
                      <td>
                        <span style={{ color: r.success ? 'var(--success)' : 'var(--error)' }}>
                          {r.success ? 'OK' : 'Failed'}
                        </span>
                      </td>
                      <td style={{ wordBreak: 'break-all' }}>
                        {r.success ? r.certificate_id : r.error}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
