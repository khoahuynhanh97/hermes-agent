import React, { useEffect, useRef } from 'react'
import { X, Film, Image as ImageIcon, Copy, Check } from 'lucide-react'
import { formatAssetUrl, isVideoAsset } from '../../utils/formatters'
import { Button } from './Button'
import { Badge } from './Badge'

interface MediaViewerModalProps {
  assetId: string | null
  title?: string
  subtitle?: string
  metadata?: Record<string, any>
  onClose: () => void
}

export const MediaViewerModal: React.FC<MediaViewerModalProps> = ({
  assetId,
  title = 'Media Inspector',
  subtitle,
  metadata,
  onClose,
}) => {
  const [copied, setCopied] = React.useState(false)
  const modalRef = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const previousActiveElementRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!assetId) return

    // Store trigger element focus
    previousActiveElementRef.current = document.activeElement as HTMLElement
    // Lock background scroll
    const originalOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    // Focus close button initially
    setTimeout(() => {
      closeBtnRef.current?.focus()
    }, 50)

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }

      // Trap Tab key
      if (e.key === 'Tab' && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
        if (focusableElements.length === 0) return

        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault()
            lastElement.focus()
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault()
            firstElement.focus()
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)

    return () => {
      document.body.style.overflow = originalOverflow
      window.removeEventListener('keydown', handleKeyDown)
      // Return focus to trigger
      previousActiveElementRef.current?.focus()
    }
  }, [assetId, onClose])

  if (!assetId) return null

  const isVideo = isVideoAsset(assetId)
  const url = formatAssetUrl(assetId)

  const handleCopyId = () => {
    navigator.clipboard.writeText(assetId)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div
      tabIndex={-1}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(10, 12, 16, 0.88)',
        backdropFilter: 'blur(8px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
      }}
      onClick={onClose}
    >
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{
          width: '100%',
          maxWidth: '960px',
          maxHeight: '90vh',
          backgroundColor: 'var(--bg-panel)',
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '12px 18px',
            borderBottom: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            {isVideo ? <Film size={18} color="var(--accent-primary)" /> : <ImageIcon size={18} color="var(--accent-primary)" />}
            <div>
              <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>{title}</strong>
              <span style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block' }}>
                {subtitle || assetId}
              </span>
            </div>
          </div>

          <button
            ref={closeBtnRef}
            onClick={onClose}
            aria-label="Close media inspector"
            style={{
              padding: '6px',
              borderRadius: 'var(--radius-sm)',
              color: 'var(--text-muted)',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Media Canvas Body */}
        <div
          style={{
            padding: '20px',
            backgroundColor: 'var(--bg-app)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '320px',
            maxHeight: '60vh',
            overflow: 'hidden',
          }}
        >
          {isVideo ? (
            <video
              src={url}
              controls
              autoPlay
              playsInline
              style={{ maxHeight: '100%', maxWidth: '100%', borderRadius: 'var(--radius-md)' }}
            />
          ) : (
            <img
              src={url}
              alt={assetId}
              style={{ maxHeight: '100%', maxWidth: '100%', objectFit: 'contain', borderRadius: 'var(--radius-md)' }}
            />
          )}
        </div>

        {/* Footer Inspector Info */}
        <div
          style={{
            padding: '14px 18px',
            borderTop: '1px solid var(--border-subtle)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: 'var(--text-muted)' }}>ASSET ID:</span>
            <code style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{assetId}</code>
            <Button variant="ghost" size="sm" icon={copied ? <Check size={13} /> : <Copy size={13} />} onClick={handleCopyId}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          </div>

          <Badge variant={isVideo ? 'timeline' : 'neutral'} size="sm">
            {isVideo ? 'MP4 Video Stream' : 'Image Asset'}
          </Badge>
        </div>
      </div>
    </div>
  )
}
