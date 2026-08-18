import React from 'react'
import { X, Sliders } from 'lucide-react'
import { Button } from './Button'

interface InspectorPanelProps {
  title?: string
  subtitle?: string
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
  className?: string
}

export const InspectorPanel: React.FC<InspectorPanelProps> = ({
  title = 'Context Inspector',
  subtitle,
  isOpen,
  onClose,
  children,
  className = '',
}) => {
  if (!isOpen) return null

  return (
    <aside
      className={`inspector-panel ${className}`}
      style={{
        width: 'var(--inspector-width)',
        backgroundColor: 'var(--bg-panel)',
        borderLeft: '1px solid var(--border-default)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        flexShrink: 0,
      }}
    >
      {/* Inspector Header */}
      <div
        style={{
          padding: '12px 16px',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: 'var(--bg-surface)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sliders size={16} color="var(--accent-primary)" />
          <div>
            <h4 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {title}
            </h4>
            {subtitle && (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {subtitle}
              </span>
            )}
          </div>
        </div>

        <Button
          variant="ghost"
          size="icon"
          icon={<X size={14} />}
          onClick={onClose}
          title="Close inspector"
        />
      </div>

      {/* Inspector Content */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        {children}
      </div>
    </aside>
  )
}
