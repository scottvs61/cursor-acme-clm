import React, { useState } from 'react'
import { apiFetch } from './api'

const MODE_OWN_CSR = 'own_csr'
const MODE_GENERATE = 'generate'

export default function Enroll() {
  const [mode, setMode] = useState(MODE_OWN_CSR)
  const [csrPem, setCsrPem] = useState('')
  const [productId, setProductId] = useState('')
  const [commonName, setCommonName] = useState('')
  const [organizationalUnits, setOrganizationalUnits] = useState('')
  const [sansDns, setSansDns] = useState('')
  const [p12Password, setP12Password] = useState('')
  const [p12Format, setP12Format] = useState('p12')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  function handleSubmit(e) {
    e.preventDefault()
    if (!productId.trim()) {
      setError('Product ID is required for all enrollments.')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)

    if (mode === MODE_GENERATE) {
      if (!commonName.trim()) {
        setError('Common name is required when generating key and CSR.')
        setLoading(false)
        return
      }
      if (!p12Password) {
        setError('PKCS#12 password is required to protect the key bundle.')
        setLoading(false)
        return
      }
      const sans = sansDns
        .split(/[\n,]+/)
        .map(s => s.trim())
        .filter(Boolean)
      const ouList = organizationalUnits
        .split(/[\n,]+/)
        .map(s => s.trim())
        .filter(Boolean)
      apiFetch('/enroll', {
        method: 'POST',
        body: JSON.stringify({
          generate: true,
          common_name: commonName.trim(),
          organizational_units: ouList.length ? ouList : null,
          sans_dns: sans.length ? sans : null,
          product_id: productId.trim(),
          p12_password: p12Password,
          p12_format: p12Format,
        }),
      })
        .then(async r => {
          if (!r.ok) {
            const data = await r.json().catch(() => ({}))
            const msg = Array.isArray(data.detail)
              ? data.detail.map(d => d.msg || d).join('; ')
              : data.detail || data.message || 'Enrollment failed'
            throw new Error(msg)
          }
          const blob = await r.blob()
          const disposition = r.headers.get('Content-Disposition')
          let filename = p12Format === 'pfx' ? 'certificate.pfx' : 'certificate.p12'
          if (disposition) {
            const match = /filename="?([^";\n]+)"?/.exec(disposition)
            if (match) filename = match[1].trim()
          }
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = filename
          a.click()
          URL.revokeObjectURL(url)
          setResult({ download: filename })
        })
        .catch(err => setError(err.message))
        .finally(() => setLoading(false))
      return
    }

    if (!csrPem.trim() || !csrPem.includes('BEGIN CERTIFICATE REQUEST')) {
      setError('Paste a PEM CSR (-----BEGIN CERTIFICATE REQUEST----- ... -----END CERTIFICATE REQUEST-----)')
      setLoading(false)
      return
    }
    apiFetch('/enroll', {
      method: 'POST',
      body: JSON.stringify({
        csr_pem: csrPem.trim(),
        product_id: productId.trim(),
      }),
    })
      .then(r => r.json().then(data => ({ ok: r.ok, data })))
      .then(({ ok, data }) => {
        if (ok) setResult(data)
        else setError(Array.isArray(data.detail) ? data.detail.map(d => d.msg || d).join('; ') : data.detail || data.message || 'Enrollment failed')
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  return (
    <>
      <h1 className="page-title">Manual enroll</h1>
      <div className="alert alert-info">
        Choose how to enroll: provide your own CSR (certificate returned in the response), or have the CLM generate the private key and CSR and receive a password-protected PKCS#12 (.pfx or .p12) file.
      </div>

      <div className="form-group" style={{ marginBottom: '1.5rem' }}>
        <label style={{ display: 'block', marginBottom: '0.75rem', fontWeight: 600, fontSize: '1rem' }}>
          How do you want to enroll?
        </label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0.75rem 1.25rem',
              border: '2px solid ' + (mode === MODE_OWN_CSR ? 'var(--primary, #0d6efd)' : 'var(--border, #dee2e6)'),
              borderRadius: '8px',
              cursor: 'pointer',
              backgroundColor: mode === MODE_OWN_CSR ? 'rgba(13, 110, 253, 0.08)' : 'transparent',
              minWidth: '200px',
            }}
          >
            <input
              type="radio"
              name="mode"
              checked={mode === MODE_OWN_CSR}
              onChange={() => setMode(MODE_OWN_CSR)}
              style={{ marginRight: '0.5rem' }}
            />
            <span><strong>I have my own CSR</strong></span>
          </label>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0.75rem 1.25rem',
              border: '2px solid ' + (mode === MODE_GENERATE ? 'var(--primary, #0d6efd)' : 'var(--border, #dee2e6)'),
              borderRadius: '8px',
              cursor: 'pointer',
              backgroundColor: mode === MODE_GENERATE ? 'rgba(13, 110, 253, 0.08)' : 'transparent',
              minWidth: '200px',
            }}
          >
            <input
              type="radio"
              name="mode"
              checked={mode === MODE_GENERATE}
              onChange={() => setMode(MODE_GENERATE)}
              style={{ marginRight: '0.5rem' }}
            />
            <span><strong>Generate key and CSR</strong> – get .pfx/.p12</span>
          </label>
        </div>
        {mode === MODE_GENERATE && (
          <p style={{ marginTop: '0.5rem', color: 'var(--muted, #6c757d)', fontSize: '0.9rem' }}>
            CLM will create the private key and CSR, request the cert from the CA, then give you a single password-protected file (.pfx for Windows, .p12 for Linux/macOS).
          </p>
        )}
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Product ID (required)</label>
          <input
            type="text"
            value={productId}
            onChange={e => setProductId(e.target.value)}
            placeholder="e.g. my-product"
            required
          />
        </div>

        {mode === MODE_OWN_CSR && (
          <div className="form-group">
            <label>CSR (PEM)</label>
            <textarea
              value={csrPem}
              onChange={e => setCsrPem(e.target.value)}
              placeholder="-----BEGIN CERTIFICATE REQUEST-----&#10;...&#10;-----END CERTIFICATE REQUEST-----"
              rows={8}
            />
          </div>
        )}

        {mode === MODE_GENERATE && (
          <>
            <div className="form-group">
              <label>Common name (required)</label>
              <input
                type="text"
                value={commonName}
                onChange={e => setCommonName(e.target.value)}
                placeholder="e.g. myserver.example.com"
                required
              />
            </div>
            <div className="form-group">
              <label>Organizational unit(s) (optional, one per line or comma-separated)</label>
              <input
                type="text"
                value={organizationalUnits}
                onChange={e => setOrganizationalUnits(e.target.value)}
                placeholder="e.g. IT Security, PKI"
              />
            </div>
            <div className="form-group">
              <label>SANs – DNS names (optional, one per line or comma-separated)</label>
              <textarea
                value={sansDns}
                onChange={e => setSansDns(e.target.value)}
                placeholder="www.example.com&#10;api.example.com"
                rows={3}
              />
            </div>
            <div className="form-group">
              <label>PKCS#12 password (required)</label>
              <input
                type="password"
                value={p12Password}
                onChange={e => setP12Password(e.target.value)}
                placeholder="Password to protect the .pfx/.p12 file"
                autoComplete="new-password"
              />
              <small style={{ display: 'block', marginTop: '0.25rem', color: 'var(--muted)' }}>
                The private key and certificate are packaged into a single file protected by this password. Not stored by the server.
              </small>
            </div>
            <div className="form-group">
              <label>Bundle format</label>
              <label style={{ marginRight: '1rem' }}>
                <input
                  type="radio"
                  name="p12_format"
                  checked={p12Format === 'pfx'}
                  onChange={() => setP12Format('pfx')}
                />
                {' '}.pfx (Windows)
              </label>
              <label>
                <input
                  type="radio"
                  name="p12_format"
                  checked={p12Format === 'p12'}
                  onChange={() => setP12Format('p12')}
                />
                {' '}.p12 (Linux / macOS)
              </label>
            </div>
          </>
        )}

        <button type="submit" className="btn btn-success" disabled={loading}>
          {loading ? (mode === MODE_GENERATE ? 'Generating & enrolling…' : 'Enrolling…') : 'Enroll'}
        </button>
      </form>

      {error && <div className="alert alert-error" style={{ marginTop: '1rem' }}>{error}</div>}
      {result && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <div className="card-header">
            {result.download ? 'Certificate issued – download started' : 'Certificate issued'}
          </div>
          <div className="card-body">
            {result.download ? (
              <p>Your PKCS#12 file <strong>{result.download}</strong> should have been downloaded. Use the password you entered to import it. The private key and password are not stored by the server.</p>
            ) : (
              <>
                <p><strong>ID:</strong> {result.id}</p>
                <p><strong>Common name:</strong> {result.common_name || '—'}</p>
                <p><strong>Product ID:</strong> {result.product_id || '—'}</p>
                <p><strong>Not after:</strong> {result.not_after ? new Date(result.not_after).toLocaleString() : '—'}</p>
              </>
            )}
          </div>
        </div>
      )}
    </>
  )
}
