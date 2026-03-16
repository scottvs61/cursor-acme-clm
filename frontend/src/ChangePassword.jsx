import React, { useState } from 'react'
import { useAuth } from './AuthContext'
import './Login.css'

export default function ChangePassword() {
  const { changePassword, user } = useAuth()
  const [current, setCurrent] = useState('')
  const [newPass, setNewPass] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    if (newPass.length < 8) {
      setError('New password must be at least 8 characters')
      return
    }
    if (newPass !== confirm) {
      setError('New passwords do not match')
      return
    }
    setSubmitting(true)
    try {
      await changePassword(current, newPass)
    } catch (err) {
      setError(err.message || 'Failed to change password')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Change password</h1>
        <p className="login-subtitle">
          {user?.must_change_password ? 'You must set a new password before continuing.' : 'Set a new password for your account.'}
        </p>
        <form onSubmit={handleSubmit}>
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </label>
          <label>
            New password (min 8 characters)
            <input
              type="password"
              autoComplete="new-password"
              value={newPass}
              onChange={(e) => setNewPass(e.target.value)}
              required
              minLength={8}
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
          </label>
          {error && <p className="login-error">{error}</p>}
          <button type="submit" disabled={submitting}>
            {submitting ? 'Updating…' : 'Update password'}
          </button>
        </form>
      </div>
    </div>
  )
}
