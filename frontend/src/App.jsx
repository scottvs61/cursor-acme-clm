import React, { useState } from 'react'
import Certificates from './Certificates'
import Enroll from './Enroll'
import BulkEnroll from './BulkEnroll'
import SCEP from './SCEP'
import Help from './Help'
import Login from './Login'
import ChangePassword from './ChangePassword'
import Admin from './Admin'
import { AuthProvider, useAuth } from './AuthContext'

const PAGES = [
  { id: 'certificates', label: 'Certificates', component: Certificates },
  { id: 'enroll', label: 'Enroll', component: Enroll },
  { id: 'bulk', label: 'Bulk Enroll', component: BulkEnroll },
  { id: 'scep', label: 'SCEP', component: SCEP },
  { id: 'help', label: 'Help', component: Help },
  { id: 'admin', label: 'Administration', component: Admin, adminOnly: true },
]

function AppContent() {
  const { token, loading, user, mustChangePassword, isAdmin, logout } = useAuth()
  const [page, setPage] = useState('certificates')

  if (loading) {
    return <div className="app"><main className="main"><p>Loading…</p></main></div>
  }
  if (!token) {
    return <Login />
  }
  if (mustChangePassword) {
    return <ChangePassword />
  }

  const PageComponent = PAGES.find(p => p.id === page)?.component || Certificates
  const navPages = PAGES.filter(p => !p.adminOnly || isAdmin)

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>CLM</h2>
        <p className="sidebar-user">{user?.email} · {user?.role}</p>
        <nav>
          {navPages.map(({ id, label }) => (
            <button
              key={id}
              className={page === id ? 'active' : ''}
              onClick={() => setPage(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <button type="button" className="sidebar-logout" onClick={logout}>Sign out</button>
      </aside>
      <main className="main">
        <PageComponent />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
