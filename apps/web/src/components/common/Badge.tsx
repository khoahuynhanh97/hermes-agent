import React from 'react'

export type BadgeVariant = 'success' | 'active' | 'running' | 'error' | 'blocked' | 'neutral' | 'timeline'

interface BadgeProps {
  variant?: BadgeVariant
  children: React.ReactNode
  size?: 'sm' | 'md'
  className?: string
  dot?: boolean
  style?: React.CSSProperties
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  children,
  size = 'md',
  className = '',
  dot = false,
  style,
}) => {
  const getColors = () => {
    switch (variant) {
      case 'success':
        return {
          bg: 'var(--status-success-bg)',
          border: 'var(--status-success-border)',
          color: 'var(--status-success)',
          dotColor: 'var(--status-success)',
        }
      case 'active':
        return {
          bg: 'var(--status-active-bg)',
          border: 'var(--status-active-border)',
          color: 'var(--status-active)',
          dotColor: 'var(--status-active)',
        }
      case 'running':
        return {
          bg: 'var(--status-running-bg)',
          border: 'var(--status-running-border)',
          color: 'var(--status-running)',
          dotColor: 'var(--status-running)',
        }
      case 'error':
        return {
          bg: 'var(--status-error-bg)',
          border: 'var(--status-error-border)',
          color: 'var(--status-error)',
          dotColor: 'var(--status-error)',
        }
      case 'timeline':
        return {
          bg: 'rgba(245, 158, 11, 0.12)',
          border: 'rgba(245, 158, 11, 0.3)',
          color: 'var(--accent-timeline)',
          dotColor: 'var(--accent-timeline)',
        }
      case 'blocked':
        return {
          bg: 'var(--status-blocked-bg)',
          border: 'var(--status-blocked-border)',
          color: 'var(--status-blocked)',
          dotColor: 'var(--status-blocked)',
        }
      default:
        return {
          bg: 'var(--bg-surface-hover)',
          border: 'var(--border-default)',
          color: 'var(--text-secondary)',
          dotColor: 'var(--text-muted)',
        }
    }
  }

  const { bg, border, color, dotColor } = getColors()

  return (
    <span
      className={`inline-flex items-center gap-1 font-mono font-medium ${className}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        backgroundColor: bg,
        border: `1px solid ${border}`,
        color: color,
        borderRadius: 'var(--radius-sm)',
        padding: size === 'sm' ? '1px 6px' : '3px 8px',
        fontSize: size === 'sm' ? '11px' : '12px',
        lineHeight: 1.3,
        letterSpacing: '0',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {dot && (
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: dotColor,
            flexShrink: 0,
          }}
        />
      )}
      {children}
    </span>
  )
}
