import React, { useCallback, useEffect, useState } from 'react'
import { useAuth } from './AuthContext'
import { apiFetch, apiUrl } from './api'
import './Admin.css'

export default function Admin() {
  const { user, isAdmin } = useAuth()
  const [tab, setTab] = useState('keys')
  const [keys, setKeys] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [generatedKey, setGeneratedKey] = useState(null)
  const [generateScope, setGenerateScope] = useState('api')
  const [generateRole, setGenerateRole] = useState('admin')
  const [addUserEmail, setAddUserEmail] = useState('')
  const [addUserPassword, setAddUserPassword] = useState('')
  const [addUserRole, setAddUserRole] = useState('user')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const loadKeys = useCallback(async () => {
    const res = await apiFetch('/admin/keys')
    const data = await res.json()
    setKeys(data)
  }, [])

  const loadUsers = useCallback(async () => {
    const res = await apiFetch('/admin/users')
    const data = await res.json()
    setUsers(data)
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    setLoading(true)
    Promise.all([loadKeys(), loadUsers()]).finally(() => setLoading(false))
  }, [isAdmin, loadKeys, loadUsers])

  async function handleGenerateKey() {
    setError('')
    setGeneratedKey(null)
    try {
      const body = { scope: generateScope }
      if (generateScope === 'api') body.role = generateRole
      const res = await apiFetch('/admin/keys/generate', {
        method: 'POST',
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setGeneratedKey(data)
      await loadKeys()
    } catch (err) {
      setError(err.message || 'Failed to generate key')
    }
  }

  async function handleAddUser(e) {
    e.preventDefault()
    setError('')
    setMessage('')
    if (!addUserEmail.trim() || addUserPassword.length < 8) {
      setError('Email and password (min 8 characters) required')
      return
    }
    try {
      await apiFetch('/admin/users', {
        method: 'POST',
        body: JSON.stringify({
          email: addUserEmail.trim().toLowerCase(),
          password: addUserPassword,
          role: addUserRole,
          must_change_password: true,
        }),
      })
      setAddUserEmail('')
      setAddUserPassword('')
      setMessage('User added. They must change password on first login.')
      await loadUsers()
    } catch (err) {
      setError(err.message || 'Failed to add user')
    }
  }

  async function handleUpdateRole(u, newRole) {
    setError('')
    try {
      await apiFetch(`/admin/users/${u.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ role: newRole }),
      })
      setMessage(`Role updated to ${newRole}`)
      await loadUsers()
    } catch (err) {
      setError(err.message || 'Failed to update')
    }
  }

  async function handleDeleteUser(u) {
    if (u.id === user?.user_id) {
      setError('You cannot delete your own user')
      return
    }
    if (!confirm(`Remove user ${u.email}?`)) return
    setError('')
    try {
      await apiFetch(`/admin/users/${u.id}`, { method: 'DELETE' })
      setMessage('User removed')
      await loadUsers()
    } catch (err) {
      setError(err.message || 'Failed to delete')
    }
  }

  function copyKey() {
    if (generatedKey?.key) {
      navigator.clipboard.writeText(generatedKey.key)
      setMessage('Key copied to clipboard. It will not be shown again.')
    }
  }

  if (!isAdmin) {
    return (
      <div className="admin-forbidden">
        <p>You need administrator access to view this page.</p>
      </div>
    )
  }

  if (loading) return <p className="admin-loading">Loading…</p>

  return (
    <div className="admin">
      <div className="admin-tabs">
        <button className={tab === 'keys' ? 'active' : ''} onClick={() => setTab('keys')}>Keys</button>
        <button className={tab === 'users' ? 'active' : ''} onClick={() => setTab('users')}>Users</button>
      </div>

      {message && <p className="admin-message">{message}</p>}
      {error && <p className="admin-error">{error}</p>}

      {tab === 'keys' && (
        <div className="admin-keys">
          <h3>Generate key</h3>
          <p className="admin-hint">Generate a key for SCEP or API. Copy it immediately; it cannot be retrieved later.</p>
          <div className="admin-generate">
            <select value={generateScope} onChange={(e) => setGenerateScope(e.target.value)}>
              <option value="scep">SCEP</option>
              <option value="api">API</option>
            </select>
            {generateScope === 'api' && (
              <select value={generateRole} onChange={(e) => setGenerateRole(e.target.value)}>
                <option value="admin">Admin</option>
                <option value="user">User</option>
              </select>
            )}
            <button type="button" onClick={handleGenerateKey}>Generate</button>
          </div>
          {generatedKey && (
            <div className="admin-generated-key">
              <p><strong>Key generated.</strong> Copy it now:</p>
              <div className="admin-key-row">
                <code>{generatedKey.key}</code>
                <button type="button" onClick={copyKey}>Copy</button>
              </div>
              <p className="admin-key-meta">Scope: {generatedKey.scope}{generatedKey.role ? ` · Role: ${generatedKey.role}` : ''}</p>
            </div>
          )}
          <h3>Existing keys</h3>
          <p className="admin-hint">Plaintext keys are not stored. Only scope, role, and creation time are shown.</p>
          <table className="admin-table">
            <thead>
              <tr><th>Scope</th><th>Role</th><th>Created</th></tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k.id}>
                  <td>{k.scope}</td>
                  <td>{k.role || '—'}</td>
                  <td>{new Date(k.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {keys.length === 0 && <p className="admin-empty">No keys generated yet.</p>}
        </div>
      )}

      {tab === 'users' && (
        <div className="admin-users">
          <h3>Add user</h3>
          <form onSubmit={handleAddUser} className="admin-add-user">
            <input
              type="email"
              placeholder="Email"
              value={addUserEmail}
              onChange={(e) => setAddUserEmail(e.target.value)}
            />
            <input
              type="password"
              placeholder="Temporary password (min 8 chars)"
              value={addUserPassword}
              onChange={(e) => setAddUserPassword(e.target.value)}
              minLength={8}
            />
            <select value={addUserRole} onChange={(e) => setAddUserRole(e.target.value)}>
              <option value="user">User</option>
              <option value="admin">Administrator</option>
            </select>
            <button type="submit">Add user</button>
          </form>
          <h3>Users</h3>
          <table className="admin-table">
            <thead>
              <tr><th>Email</th><th>Role</th><th>Must change password</th><th>Actions</th></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.email}</td>
                  <td>
                    <select
                      value={u.role}
                      onChange={(e) => handleUpdateRole(u, e.target.value)}
                      disabled={u.id === user?.user_id}
                    >
                      <option value="user">User</option>
                      <option value="admin">Administrator</option>
                    </select>
                  </td>
                  <td>{u.must_change_password ? 'Yes' : 'No'}</td>
                  <td>
                    {u.id !== user?.user_id && (
                      <button type="button" className="admin-delete" onClick={() => handleDeleteUser(u)}>Remove</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
