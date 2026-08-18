import React from 'react'
import { Loader2 } from 'lucide-react'

export type ButtonVariant = 'primary' | 'secondary' | 'success' | 'timeline' | 'danger' | 'ghost' | 'outline'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg' | 'icon'
  loading?: boolean
  icon?: React.ReactNode
  title?: string
  children?: React.ReactNode
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  title,
  children,
  disabled,
  className = '',
  style,
  ...rest
}) => {
  const getVariantStyles = (): React.CSSProperties => {
    switch (variant) {
      case 'primary':
        return {
          backgroundColor: 'var(--accent-primary)',
          color: 'var(--text-inverse)',
          border: '1px solid var(--accent-primary)',
          fontWeight: 600,
        }
      case 'success':
        return {
          backgroundColor: 'var(--status-success)',
          color: 'var(--text-inverse)',
          border: '1px solid var(--status-success)',
          fontWeight: 600,
        }
      case 'timeline':
        return {
          backgroundColor: 'var(--accent-timeline)',
          color: 'var(--text-inverse)',
          border: '1px solid var(--accent-timeline)',
          fontWeight: 600,
        }
      case 'danger':
        return {
          backgroundColor: 'var(--status-error)',
          color: '#ffffff',
          border: '1px solid var(--status-error)',
          fontWeight: 600,
        }
      case 'outline':
        return {
          backgroundColor: 'transparent',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-default)',
        }
      case 'ghost':
        return {
          backgroundColor: 'transparent',
          color: 'var(--text-secondary)',
          border: '1px solid transparent',
        }
      default: // secondary
        return {
          backgroundColor: 'var(--bg-surface)',
          color: 'var(--text-primary)',
          border: '1px solid var(--border-default)',
        }
    }
  }

  const getSizeStyles = (): React.CSSProperties => {
    if (size === 'icon') {
      return {
        padding: '6px',
        width: '32px',
        height: '32px',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }
    }
    switch (size) {
      case 'sm':
        return { padding: '4px 10px', fontSize: '12px', height: '28px' }
      case 'lg':
        return { padding: '10px 18px', fontSize: '14px', height: '40px' }
      default:
        return { padding: '6px 14px', fontSize: '13px', height: '34px' }
    }
  }

  const baseStyles: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    borderRadius: 'var(--radius-md)',
    fontFamily: 'inherit',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'all 0.15s ease',
    whiteSpace: 'nowrap',
    userSelect: 'none',
    ...getVariantStyles(),
    ...getSizeStyles(),
    ...style,
  }

  return (
    <button
      disabled={disabled || loading}
      title={title || (typeof children === 'string' ? children : undefined)}
      aria-label={title || (typeof children === 'string' ? children : undefined)}
      className={`btn-interactive ${className}`}
      style={baseStyles}
      {...rest}
    >
      {loading ? <Loader2 size={size === 'sm' ? 12 : 14} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} /> : icon}
      {children}
    </button>
  )
}
