import { Link, useLocation } from 'react-router-dom'
import './Layout.css'

const navItems = [
  { path: '/projects', label: '📁 Projects', icon: '📁' },
  { path: '/jobs', label: '⚡ Jobs', icon: '⚡' },
  { path: '/knowledge', label: '📚 Knowledge', icon: '📚' },
  { path: '/ai-analysis', label: '🤖 AI Analysis', icon: '🤖' },
  { path: '/settings', label: '⚙️ Settings', icon: '⚙️' },
]

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">
          <h1>🤖 Hermes</h1>
          <p>AI Assistant Platform</p>
        </div>
        <nav>
          {navItems.map(item => (
            <Link
              key={item.path}
              to={item.path}
              className={`nav-item ${location.pathname.startsWith(item.path) ? 'active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          <p>Version 1.0.0</p>
        </div>
      </aside>
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}