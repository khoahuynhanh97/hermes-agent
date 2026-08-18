import React, { useState } from 'react'
import { Image as ImageIcon, Film, AlertCircle, Maximize2 } from 'lucide-react'
import { formatAssetUrl, isVideoAsset } from '../../utils/formatters'

interface AssetThumbnailProps {
  assetId?: string
  alt?: string
  aspectRatio?: '16:9' | '9:16' | '1:1' | 'auto'
  roleLabel?: string
  showInspectButton?: boolean
  onInspect?: (assetId: string) => void
  className?: string
  style?: React.CSSProperties
}

export const AssetThumbnail: React.FC<AssetThumbnailProps> = ({
  assetId,
  alt = 'Asset preview',
  aspectRatio = '9:16',
  roleLabel,
  showInspectButton = true,
  onInspect,
  className = '',
  style,
}) => {
  const [hasError, setHasError] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)

  const isVideo = isVideoAsset(assetId)
  const url = formatAssetUrl(assetId)

  const getAspectPadding = () => {
    switch (aspectRatio) {
      case '9:16':
        return '177.78%'
      case '16:9':
        return '56.25%'
      case '1:1':
        return '100%'
      default:
        return '100%'
    }
  }

  if (!assetId) {
    return (
      <div
        className={`asset-thumb-empty ${className}`}
        style={{
          width: '100%',
          paddingTop: getAspectPadding(),
          position: 'relative',
          backgroundColor: 'var(--bg-panel)',
          border: '1px dashed var(--border-default)',
          borderRadius: 'var(--radius-md)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          ...style,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-muted)',
            gap: '6px',
            fontSize: '11px',
          }}
        >
          <ImageIcon size={20} strokeWidth={1.5} />
          <span>Pending Asset</span>
        </div>
      </div>
    )
  }

  return (
    <div
      className={`asset-thumb-container ${className}`}
      style={{
        position: 'relative',
        width: '100%',
        paddingTop: getAspectPadding(),
        backgroundColor: 'var(--bg-input)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        cursor: onInspect ? 'pointer' : 'default',
        ...style,
      }}
      onClick={() => onInspect?.(assetId)}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {!hasError ? (
          isVideo ? (
            <video
              src={url}
              muted
              playsInline
              preload="metadata"
              onLoadedData={() => setIsLoaded(true)}
              onError={() => setHasError(true)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
          ) : (
            <img
              src={url}
              alt={alt}
              loading="lazy"
              onLoad={() => setIsLoaded(true)}
              onError={() => setHasError(true)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: isLoaded ? 1 : 0.4,
                transition: 'opacity 0.2s ease',
              }}
            />
          )
        ) : (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--status-error)',
              gap: '4px',
              fontSize: '11px',
              textAlign: 'center',
              padding: '8px',
            }}
          >
            <AlertCircle size={16} />
            <span style={{ color: 'var(--text-muted)' }}>Asset unavailable</span>
          </div>
        )}

        {/* Media type indicator badge */}
        {roleLabel && (
          <span
            style={{
              position: 'absolute',
              top: '6px',
              left: '6px',
              backgroundColor: 'rgba(10, 12, 16, 0.75)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '1px 6px',
              fontSize: '10px',
              fontFamily: 'var(--font-mono)',
              backdropFilter: 'blur(4px)',
            }}
          >
            {roleLabel}
          </span>
        )}

        {/* Video format badge */}
        {isVideo && !roleLabel && (
          <span
            style={{
              position: 'absolute',
              top: '6px',
              left: '6px',
              backgroundColor: 'rgba(10, 12, 16, 0.8)',
              color: 'var(--accent-primary)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '2px 5px',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              fontSize: '10px',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <Film size={10} /> MP4
          </span>
        )}

        {/* Inspect icon overlay on hover */}
        {showInspectButton && onInspect && (
          <div
            className="thumb-inspect-overlay"
            style={{
              position: 'absolute',
              bottom: '6px',
              right: '6px',
              backgroundColor: 'rgba(10, 12, 16, 0.75)',
              color: 'var(--text-primary)',
              borderRadius: 'var(--radius-sm)',
              padding: '4px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title="Inspect media"
          >
            <Maximize2 size={12} />
          </div>
        )}
      </div>
    </div>
  )
}
