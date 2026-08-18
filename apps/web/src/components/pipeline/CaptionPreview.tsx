import React, { useEffect, useRef } from 'react'

export type CaptionStyle = 'tiktok-yellow' | 'clean-white' | 'neon-green'
export type CaptionSize = 'small' | 'medium' | 'large'
export type CaptionPosition = 'bottom-center' | 'top-center'

interface CaptionPreviewProps {
  words: string[]
  activeWordIndex?: number
  style?: CaptionStyle
  size?: CaptionSize
  position?: CaptionPosition
  isPlaying?: boolean
}

const STYLE_MAP: Record<CaptionStyle, { color: string; shadow: string; bg?: string }> = {
  'tiktok-yellow': { color: '#fef08a', shadow: '0 0 8px rgba(250,204,21,0.4)' },
  'clean-white': { color: '#ffffff', shadow: '0 1px 3px rgba(0,0,0,0.7)' },
  'neon-green': { color: '#4ade80', shadow: '0 0 10px rgba(74,222,128,0.5)' },
}

const SIZE_MAP: Record<CaptionSize, string> = {
  small: '16px',
  medium: '22px',
  large: '30px',
}

export const CaptionPreview: React.FC<CaptionPreviewProps> = ({
  words,
  activeWordIndex = 0,
  style = 'tiktok-yellow',
  size = 'medium',
  position = 'bottom-center',
  isPlaying = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const activeRef = useRef<HTMLSpanElement>(null)
  const { color, shadow } = STYLE_MAP[style]

  useEffect(() => {
    if (activeRef.current && containerRef.current) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
    }
  }, [activeWordIndex])

  const posStyle: React.CSSProperties = position === 'top-center'
    ? { top: 0, bottom: 'auto' }
    : { bottom: 0, top: 'auto' }

  return (
    <div
      ref={containerRef}
      className="caption-preview"
      style={{
        position: 'relative',
        width: '100%',
        height: '48px',
        overflow: 'hidden',
        display: 'flex',
        alignItems: position === 'top-center' ? 'flex-start' : 'flex-end',
        justifyContent: 'center',
        padding: '6px 12px',
      }}
    >
      <div
        className="caption-preview__track"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          ...posStyle,
          display: 'flex',
          gap: '6px',
          flexWrap: 'nowrap',
          overflowX: 'auto',
          padding: '4px 12px',
          scrollbarWidth: 'none',
          justifyContent: 'center',
        }}
      >
        {words.map((word, i) => (
          <span
            key={i}
            ref={i === activeWordIndex ? activeRef : undefined}
            style={{
              fontSize: SIZE_MAP[size],
              fontWeight: i === activeWordIndex ? 700 : 500,
              color: i === activeWordIndex ? color : 'rgba(255,255,255,0.5)',
              textShadow: i === activeWordIndex ? shadow : 'none',
              transition: 'all 0.15s ease',
              whiteSpace: 'nowrap',
              fontFamily: 'var(--font-sans)',
            }}
          >
            {word}
          </span>
        ))}
      </div>
    </div>
  )
}
