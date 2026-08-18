import React, { useState, useRef, useEffect } from 'react'
import {
  X,
  Sparkles,
  Bot,
  User,
  Send,
  Trash2,
  Square,
  Maximize2,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useOmniChat, PROMPT_TEMPLATES } from '../../hooks/useOmniChat'
import { ToolBadge } from '../../features/omni-chat/components/ToolBadge'
import { VideoProgressCard } from '../../features/omni-chat/components/VideoProgressCard'
import { VideoPlayerCard } from '../../features/omni-chat/components/VideoPlayerCard'
import { DocPreviewCard } from '../../features/omni-chat/components/DocPreviewCard'
import { Button } from './Button'
import { Badge } from './Badge'
import './OmniChatDrawer.css'

interface OmniChatDrawerProps {
  isOpen: boolean
  onClose: () => void
  projectId?: string
}

export const OmniChatDrawer: React.FC<OmniChatDrawerProps> = ({
  isOpen,
  onClose,
  projectId,
}) => {
  const navigate = useNavigate()
  const [inputText, setInputText] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const {
    messages,
    isGenerating,
    sendMessage,
    stopGeneration,
    clearHistory,
  } = useOmniChat(projectId)

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => textareaRef.current?.focus(), 100)
    }
  }, [isOpen])

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isOpen])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const handleSend = () => {
    if (!inputText.trim() || isGenerating) return
    const text = inputText
    setInputText('')
    sendMessage(text, projectId)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="omni-drawer-overlay" onClick={onClose}>
      <div className="omni-drawer-panel" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="omni-drawer-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div
              style={{
                width: '26px',
                height: '26px',
                borderRadius: 'var(--radius-sm)',
                backgroundColor: 'rgba(56, 189, 248, 0.15)',
                color: 'var(--accent-primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={14} />
            </div>

            <div>
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                Hermes Omni Chat
              </strong>
              <Badge variant="active" size="sm" dot style={{ marginLeft: '6px' }}>
                Online
              </Badge>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Button
              variant="ghost"
              size="sm"
              icon={<Maximize2 size={13} />}
              onClick={() => {
                onClose()
                navigate('/studio')
              }}
              title="Open full studio"
            >
              Full Studio
            </Button>

            <Button
              variant="ghost"
              size="sm"
              icon={<Trash2 size={13} />}
              onClick={clearHistory}
              title="Clear history"
            />

            <button
              onClick={onClose}
              aria-label="Close drawer"
              style={{
                padding: '4px',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--text-muted)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Drawer Messages Stream */}
        <div className="omni-drawer-messages">
          {messages.map((msg) => {
            const isAssistant = msg.sender === 'assistant'
            const docTool = msg.toolCalls?.find((t) => t.name === 'read_file' && t.data?.content)

            return (
              <div key={msg.id} style={{ display: 'flex', gap: '8px', flexDirection: isAssistant ? 'row' : 'row-reverse' }}>
                <div
                  style={{
                    width: '26px',
                    height: '26px',
                    borderRadius: 'var(--radius-sm)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    backgroundColor: isAssistant ? 'rgba(56, 189, 248, 0.15)' : 'var(--bg-surface-active)',
                    color: isAssistant ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  }}
                >
                  {isAssistant ? <Bot size={14} /> : <User size={14} />}
                </div>

                <div style={{ maxWidth: 'calc(100% - 36px)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <div
                    style={{
                      padding: '10px 14px',
                      borderRadius: 'var(--radius-md)',
                      fontSize: '12.5px',
                      lineHeight: '1.5',
                      backgroundColor: isAssistant ? 'var(--bg-surface)' : 'var(--bg-surface-active)',
                      border: `1px solid ${isAssistant ? 'var(--border-subtle)' : 'var(--border-strong)'}`,
                      color: 'var(--text-primary)',
                    }}
                  >
                    {/* Tool Badges */}
                    {msg.toolCalls && msg.toolCalls.length > 0 && (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '6px' }}>
                        {msg.toolCalls.map((tc) => (
                          <ToolBadge key={tc.id || tc.name} tool={tc} />
                        ))}
                      </div>
                    )}

                    {/* Real-time Progress */}
                    {msg.pipelineProgress && (
                      <VideoProgressCard progress={msg.pipelineProgress} />
                    )}

                    {/* Video Player */}
                    {msg.videoResult && (
                      <VideoPlayerCard video={msg.videoResult} />
                    )}

                    {/* Doc Preview */}
                    {docTool && (
                      <DocPreviewCard
                        filePath={docTool.data?.path || 'document.md'}
                        content={docTool.data?.content}
                        linesCount={docTool.data?.lines}
                      />
                    )}

                    {msg.text && (
                      <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
                    )}
                  </div>

                  <span style={{ fontSize: '10px', color: 'var(--text-muted)', textAlign: isAssistant ? 'left' : 'right' }}>
                    {msg.timestamp}
                  </span>
                </div>
              </div>
            )
          })}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick prompt suggestions */}
        {messages.length <= 2 && (
          <div style={{ padding: '0 16px 8px 16px', display: 'flex', gap: '6px', overflowX: 'auto' }}>
            {PROMPT_TEMPLATES.slice(0, 2).map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setInputText(t.prompt)}
                style={{
                  padding: '4px 10px',
                  backgroundColor: 'var(--bg-surface)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '11px',
                  color: 'var(--text-secondary)',
                  whiteSpace: 'nowrap',
                  cursor: 'pointer',
                }}
              >
                {t.icon} {t.title}
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div className="omni-drawer-composer">
          <div
            style={{
              backgroundColor: 'var(--bg-input)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-md)',
              padding: '8px 10px',
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
            }}
          >
            <textarea
              ref={textareaRef}
              rows={2}
              placeholder="Nhập yêu cầu: 'Tạo video review...', 'Đọc tài liệu'..."
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isGenerating}
              style={{
                width: '100%',
                background: 'none',
                border: 'none',
                outline: 'none',
                resize: 'none',
                fontSize: '12.5px',
                color: 'var(--text-primary)',
              }}
            />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>Enter to send</span>

              {isGenerating ? (
                <Button variant="danger" size="sm" icon={<Square size={11} />} onClick={stopGeneration}>
                  Stop
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  disabled={!inputText.trim()}
                  icon={<Send size={11} />}
                  onClick={handleSend}
                >
                  Send
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
