import React, { useState } from 'react'

export default function SCEP() {
  const [baseUrl, setBaseUrl] = useState(() => {
    if (typeof window !== 'undefined' && window.location.port === '5173') return 'http://localhost:8002'
    return `${window.location.protocol}//${window.location.hostname}:8002`
  })

  const urls = {
    GetCACert: `${baseUrl}/GetCACert`,
    GetCACaps: `${baseUrl}/GetCACaps`,
    PKIOperation: `${baseUrl}/PKIOperation`,
  }

  return (
    <>
      <h1 className="page-title">SCEP enrollment</h1>
      <div className="alert alert-info">
        Use these endpoints for SCEP clients. Ensure the SCEP server is running on port 8002 (<code>bash run_scep.sh</code>). Issued certificates are sent to CLM automatically.
      </div>

      <div className="form-group" style={{ maxWidth: '400px' }}>
        <label>SCEP base URL</label>
        <input
          type="text"
          value={baseUrl}
          onChange={e => setBaseUrl(e.target.value)}
          placeholder="http://localhost:8002"
        />
      </div>

      <div className="card">
        <div className="card-header">Endpoints</div>
        <div className="card-body">
          <table>
            <tbody>
              <tr>
                <td><strong>GetCACert</strong></td>
                <td style={{ wordBreak: 'break-all' }}><code>{urls.GetCACert}</code></td>
              </tr>
              <tr>
                <td><strong>GetCACaps</strong></td>
                <td style={{ wordBreak: 'break-all' }}><code>{urls.GetCACaps}</code></td>
              </tr>
              <tr>
                <td><strong>PKIOperation</strong></td>
                <td style={{ wordBreak: 'break-all' }}><code>{urls.PKIOperation}</code></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <div className="card-header">Usage</div>
        <div className="card-body" style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          <p>1. Configure your device or MDM with the SCEP URL: <code>{urls.PKIOperation}</code></p>
          <p>2. For prototype testing, you can POST a CSR directly with JSON:</p>
          <pre className="detail-pre" style={{ marginTop: '0.5rem' }}>{`POST ${urls.PKIOperation}
Content-Type: application/json

{ "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\\n...\\n-----END CERTIFICATE REQUEST-----", "product_id": "required" }`}</pre>
          <p style={{ marginTop: '1rem' }}>3. <strong>Product ID is required.</strong> Provide <code>product_id</code> in the JSON body, or set <code>scep.default_product_id</code> in config (or env <code>SCEP_DEFAULT_PRODUCT_ID</code>).</p>
        </div>
      </div>
    </>
  )
}
