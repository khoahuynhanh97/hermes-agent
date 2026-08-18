import React, { useState } from 'react'
import {
  BookOpen,
  Film,
  Globe,
  Video,
  CheckCircle2,
  Loader2,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Terminal,
} from 'lucide-react'
import { ToolCall } from '../../../types/omniChat'

interface ToolBadgeProps {
  tool: ToolCall
}

export const ToolBadge: React.FC<ToolBadgeProps> = ({ tool }) => {
  const [expanded, setExpanded] = useState(false)

  const getToolMeta = () => {
    switch (tool.name) {
      case 'read_file':
        return {
          icon: <BookOpen size={13} color="var(--accent-primary)" />,
          label: 'read_file',
          title: tool.args?.path ? `Read ${tool.args.path}` : 'Reading Document',
          bgColor: 'rgba(56, 189, 248, 0.1)',
          borderColor: 'rgba(56, 189, 248, 0.25)',
          badgeColor: 'var(--accent-primary)',
        }
      case 'product_to_video':
        return {
          icon: <Film size={13} color="var(--accent-timeline)" />,
          label: 'product_to_video',
          title: tool.args?.product ? `Review Video for ${tool.args.product}` : 'Generating Product Video',
          bgColor: 'rgba(245, 158, 11, 0.1)',
          borderColor: 'rgba(245, 158, 11, 0.25)',
          badgeColor: 'var(--accent-timeline)',
        }
      case 'web_search':
        return {
          icon: <Globe size={13} color="var(--status-success)" />,
          label: 'web_search',
          title: tool.args?.query ? `Search: ${tool.args.query}` : 'Web Search',
          bgColor: 'rgba(16, 185, 129, 0.1)',
          borderColor: 'rgba(16, 185, 129, 0.25)',
          badgeColor: 'var(--status-success)',
        }
      default:
        return {
          icon: <Video size={13} color="var(--text-secondary)" />,
          label: tool.name,
          title: tool.title || tool.name,
          bgColor: 'var(--bg-surface)',
          borderColor: 'var(--border-default)',
          badgeColor: 'var(--text-secondary)',
        }
    }
  }

  const meta = getToolMeta()
  const isRunning = tool.status === 'running'
  const isCompleted = tool.status === 'completed'
  const isFailed = tool.status === 'failed'

  return (
    <div
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        backgroundColor: meta.bgColor,
        border: `1px solid ${meta.borderColor}`,
        borderRadius: 'var(--radius-md)',
        margin: '6px 0',
        maxWidth: '100%',
        overflow: 'hidden',
        transition: 'all 0.2s ease',
      }}
    >
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 10px',
          cursor: 'pointer',
          userSelect: 'none',
          fontSize: '12px',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center' }}>{meta.icon}</span>

        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600, color: meta.badgeColor }}>
          {meta.label}
        </span>

        <span
          style={{
            color: 'var(--text-secondary)',
            fontSize: '11px',
            maxWidth: '280px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {meta.title}
        </span>

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
          {isRunning && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                color: 'var(--accent-timeline)',
                fontSize: '11px',
                fontWeight: 500,
              }}
            >
              <Loader2 size={11} className="animate-spin" style={{ animation: 'spin 1s linear infinite' }} />
              Executing...
            </span>
          )}

          {isCompleted && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                color: 'var(--status-success)',
                fontSize: '11px',
              }}
            >
              <CheckCircle2 size={12} />
              Done
            </span>
          )}

          {isFailed && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                color: 'var(--status-error)',
                fontSize: '11px',
              }}
            >
              <AlertCircle size={12} />
              Error
            </span>
          )}

          <button
            type="button"
            aria-label="Toggle tool details"
            style={{
              padding: '2px',
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
              background: 'none',
              border: 'none',
            }}
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {expanded && (
        <div
          style={{
            padding: '8px 12px',
            borderTop: `1px solid ${meta.borderColor}`,
            backgroundColor: 'var(--bg-app)',
            fontSize: '11px',
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-secondary)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', color: 'var(--text-muted)' }}>
            <Terminal size={12} />
            <span>EXECUTION PAYLOAD & OUTPUT</span>
          </div>

          {tool.args && Object.keys(tool.args).length > 0 && (
            <div style={{ marginBottom: '6px' }}>
              <span style={{ color: 'var(--text-muted)' }}>Arguments:</span>
              <pre
                style={{
                  margin: '2px 0',
                  padding: '4px 8px',
                  backgroundColor: 'var(--bg-panel)',
                  borderRadius: 'var(--radius-sm)',
                  overflowX: 'auto',
                }}
              >
                {JSON.stringify(tool.args, null, 2)}
              </pre>
            </div>
          )}

          {tool.data && (
            <div>
              <span style={{ color: 'var(--text-muted)' }}>Result Output:</span>
              <pre
                style={{
                  margin: '2px 0',
                  padding: '4px 8px',
                  backgroundColor: 'var(--bg-panel)',
                  borderRadius: 'var(--radius-sm)',
                  overflowX: 'auto',
                  maxHeight: '140px',
                }}
              >
                {typeof tool.data === 'string' ? tool.data : JSON.stringify(tool.data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
