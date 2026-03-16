import React, { useState, useEffect } from 'react'
import { apiFetch } from './api'

export default function Help() {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiFetch('/help')
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404 ? 'Help document not found' : `HTTP ${r.status}`)
        return r.text()
      })
      .then(setContent)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="page-title">Loading API help…</p>
  if (error) {
    return (
      <>
        <h1 className="page-title">API Help</h1>
        <div className="alert alert-error">{error}</div>
      </>
    )
  }

  return (
    <>
      <h1 className="page-title">API Help</h1>
      <div className="card">
        <div className="card-header">CLM REST API — Knowledge Document</div>
        <div
          className="card-body help-doc"
          style={{
            whiteSpace: 'pre-wrap',
            fontFamily: 'var(--font)',
            fontSize: '0.9rem',
            lineHeight: 1.6,
            maxWidth: '100%',
            overflow: 'auto',
          }}
        >
          {content}
        </div>
      </div>
    </>
  )
}
