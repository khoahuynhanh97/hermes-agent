import React, { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Film,
  Package,
  Activity,
  BookOpen,
  Settings,
  Sparkles,
  Menu,
  X,
  Bot,
  MessageSquare,
  BarChart3,
} from 'lucide-react'
import { OmniChatDrawer } from '../common/OmniChatDrawer'
import './AppShell.css'

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  badge?: string
}

const PRIMARY_NAV: NavItem[] = [
  { path: '/dashboard', label: 'Home', icon: <LayoutDashboard size={16} /> },
  { path: '/studio', label: 'Omni Chat Studio', icon: <Sparkles size={16} />, badge: 'AI' },
  { path: '/projects', label: 'Projects', icon: <Film size={16} /> },
  { path: '/products', label: 'Product Library', icon: <Package size={16} /> },
  { path: '/operations', label: 'Operations', icon: <Activity size={16} /> },
  { path: '/analytics', label: 'Analytics', icon: <BarChart3 size={16} /> },
  { path: '/knowledge', label: 'Knowledge', icon: <BookOpen size={16} /> },
  { path: '/settings', label: 'Settings', icon: <Settings size={16} /> },
]

const SECONDARY_NAV: NavItem[] = [
  { path: '/ai-analysis', label: 'AI Sandbox', icon: <Bot size={16} /> },
]

export const AppShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)

  const isNavActive = (path: string) => {
    if (path === '/dashboard') {
      return location.pathname === '/' || location.pathname === '/dashboard'
    }
    if (path === '/studio') {
      return (
        location.pathname.startsWith('/studio') ||
        location.pathname.startsWith('/omni-studio') ||
        location.pathname.startsWith('/omni-chat') ||
        location.pathname.startsWith('/chat')
      )
    }
    if (path === '/products') {
      return location.pathname.startsWith('/products') || location.pathname.startsWith('/product-research')
    }
    if (path === '/operations') {
      return location.pathname.startsWith('/operations') || location.pathname.startsWith('/jobs')
    }
    return location.pathname.startsWith(path)
  }

  return (
    <div className="app-shell-root">
      {/* Sidebar Desktop */}
      <aside className={`app-sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
        {/* Brand Header */}
        <div className="brand-box">
          <div className="brand-logo-icon">
            <Bot size={18} color="var(--accent-primary)" />
          </div>
          <div className="brand-text">
            <span className="brand-name">HERMES AGENT</span>
            <span className="brand-sub">Production Orchestrator</span>
          </div>

          <button
            className="mobile-close-btn"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        {/* Primary Navigation Items */}
        <nav className="sidebar-nav">
          <div className="nav-group-label">OPERATIONS</div>
          {PRIMARY_NAV.map((item) => {
            const active = isNavActive(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link-row ${active ? 'active' : ''}`}
                onClick={() => setMobileOpen(false)}
              >
                <span className="nav-icon-wrap">{item.icon}</span>
                <span className="nav-label-text">{item.label}</span>
                {item.badge && <span className="nav-badge-pill">{item.badge}</span>}
              </Link>
            )
          })}

          <div className="nav-group-label" style={{ marginTop: '16px' }}>TOOLS</div>
          {SECONDARY_NAV.map((item) => {
            const active = isNavActive(item.path)
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`nav-link-row ${active ? 'active' : ''}`}
                onClick={() => setMobileOpen(false)}
              >
                <span className="nav-icon-wrap">{item.icon}</span>
                <span className="nav-label-text">{item.label}</span>
              </Link>
            )
          })}
        </nav>

        {/* Sidebar Footer Status & Quick Chat Launcher */}
        <div className="sidebar-bottom-status" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            style={{
              width: '100%',
              padding: '7px 10px',
              backgroundColor: 'var(--bg-surface-active)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '6px',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <MessageSquare size={13} color="var(--accent-primary)" />
            <span>Quick Omni Chat</span>
          </button>

          <div className="status-indicator-box">
            <div className="live-dot" />
            <div className="status-desc">
              <strong style={{ color: 'var(--text-primary)', fontSize: '11px' }}>Operator API</strong>
              <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>FastAPI Port 8000</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main App Container */}
      <div className="app-main-layout">
        {/* Mobile Header Bar */}
        <header className="mobile-topbar">
          <button
            className="hamburger-btn"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Bot size={16} color="var(--accent-primary)" />
            <span style={{ fontWeight: 600, fontSize: '13px' }}>HERMES AGENT</span>
          </div>
          <button
            type="button"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open Quick Omni Chat"
            style={{
              color: 'var(--accent-primary)',
              background: 'none',
              border: 'none',
              padding: '4px',
              cursor: 'pointer',
            }}
          >
            <Sparkles size={18} />
          </button>
        </header>

        {/* Content View */}
        <div className="app-content-body">
          {children}
        </div>
      </div>

      {/* Slide-over Global Omni Chat Drawer */}
      <OmniChatDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  )
}

