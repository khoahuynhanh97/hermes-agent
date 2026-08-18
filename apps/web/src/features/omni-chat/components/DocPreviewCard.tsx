import React, { useState } from 'react'
import { BookOpen, Copy, Check, ChevronDown, ChevronUp, FileCode } from 'lucide-react'
import { Button } from '../../../components/common/Button'
import { Badge } from '../../../components/common/Badge'

interface DocPreviewCardProps {
  filePath: string
  content?: string
  linesCount?: number
}

export const DocPreviewCard: React.FC<DocPreviewCardProps> = ({
  filePath,
  content,
  linesCount,
}) => {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)

  const handleCopy = () => {
    if (!content) return
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!content) return null

  const previewLines = content.split('\n')
  const displayContent = expanded ? content : previewLines.slice(0, 8).join('\n')

  return (
    <div
      style={{
        margin: '10px 0',
        backgroundColor: 'var(--bg-panel)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        maxWidth: '640px',
      }}
    >
      {/* Top Header */}
      <div
        style={{
          padding: '8px 14px',
          borderBottom: '1px solid var(--border-subtle)',
          backgroundColor: 'var(--bg-surface)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <FileCode size={14} color="var(--accent-primary)" />
          <code style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 600 }}>
            {filePath}
          </code>
          {linesCount && (
            <Badge variant="neutral" size="sm">
              {linesCount} lines
            </Badge>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Button
            variant="ghost"
            size="sm"
            icon={copied ? <Check size={12} color="var(--status-success)" /> : <Copy size={12} />}
            onClick={handleCopy}
          >
            {copied ? 'Copied' : 'Copy'}
          </Button>

          <Button
            variant="ghost"
            size="sm"
            icon={expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </Button>
        </div>
      </div>

      {/* Code / Markdown View */}
      <div
        style={{
          padding: '12px 16px',
          backgroundColor: 'var(--bg-app)',
          fontFamily: 'var(--font-mono)',
          fontSize: '12px',
          lineHeight: '1.6',
          color: 'var(--text-secondary)',
          whiteSpace: 'pre-wrap',
          maxHeight: expanded ? '420px' : '160px',
          overflowY: 'auto',
        }}
      >
        {displayContent}
        {!expanded && previewLines.length > 8 && (
          <div
            onClick={() => setExpanded(true)}
            style={{
              marginTop: '6px',
              color: 'var(--accent-primary)',
              cursor: 'pointer',
              fontSize: '11px',
              fontStyle: 'italic',
            }}
          >
            ... Click to view all {previewLines.length} lines ...
          </div>
        )}
      </div>
    </div>
  )
}
