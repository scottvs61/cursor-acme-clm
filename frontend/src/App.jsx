import React, { useState } from 'react'
import Certificates from './Certificates'
import BulkEnroll from './BulkEnroll'
import SCEP from './SCEP'

const PAGES = [
  { id: 'certificates', label: 'Certificates', component: Certificates },
  { id: 'bulk', label: 'Bulk Enroll', component: BulkEnroll },
  { id: 'scep', label: 'SCEP', component: SCEP },
]

export default function App() {
  const [page, setPage] = useState('certificates')

  const PageComponent = PAGES.find(p => p.id === page)?.component || Certificates

  return (
    <div className="app">
      <aside className="sidebar">
        <h2>CLM</h2>
        <nav>
          {PAGES.map(({ id, label }) => (
            <button
              key={id}
              className={page === id ? 'active' : ''}
              onClick={() => setPage(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <PageComponent />
      </main>
    </div>
  )
}
