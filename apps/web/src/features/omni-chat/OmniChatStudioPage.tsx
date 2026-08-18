import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot,
  User,
  Sparkles,
  Send,
  Square,
  Trash2,
  Film,
  Layers,
  ExternalLink,
  RefreshCw,
  Video,
  FileCode,
  BookOpen,
} from 'lucide-react'
import { useOmniChat, PROMPT_TEMPLATES } from '../../hooks/useOmniChat'
import { ToolBadge } from './components/ToolBadge'
import { VideoProgressCard } from './components/VideoProgressCard'
import { VideoPlayerCard } from './components/VideoPlayerCard'
import { DocPreviewCard } from './components/DocPreviewCard'
import { MediaViewerModal } from '../../components/common/MediaViewerModal'
import { Badge } from '../../components/common/Badge'
import { Button } from '../../components/common/Button'
import './OmniChatStudioPage.css'

export const OmniChatStudioPage: React.FC = () => {
  const navigate = useNavigate()
  const [inputText, setInputText] = useState('')
  const [inspectModalAssetId, setInspectModalAssetId] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const {
    messages,
    isGenerating,
    activeVideoResult,
    sendMessage,
    stopGeneration,
    clearHistory,
    setActiveVideoResult,
  } = useOmniChat()

  // Auto-scroll on new message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Focus textarea on load
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSend = () => {
    if (!inputText.trim() || isGenerating) return
    const text = inputText
    setInputText('')
    sendMessage(text)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleSelectTemplate = (prompt: string) => {
    setInputText(prompt)
    textareaRef.current?.focus()
  }

  return (
    <div className="omni-studio-container">
      {/* Studio Topbar */}
      <header className="omni-studio-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div
            style={{
              width: '32px',
              height: '32px',
              borderRadius: 'var(--radius-md)',
              background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.25), rgba(14, 165, 233, 0.4))',
              border: '1px solid var(--accent-primary)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-primary)',
            }}
          >
            <Sparkles size={16} />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                Omni Chat Studio
              </h1>
              <Badge variant="active" size="sm" dot>
                Runtime Connected
              </Badge>
            </div>
            <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
              Natural Language Autonomous Video Production & Document Intelligence
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Button
            variant="outline"
            size="sm"
            icon={<Trash2 size={13} />}
            onClick={clearHistory}
            title="Clear conversation history"
          >
            Clear
          </Button>

          {isGenerating ? (
            <Button
              variant="danger"
              size="sm"
              icon={<Square size={12} />}
              onClick={stopGeneration}
            >
              Stop
            </Button>
          ) : (
            <Button
              variant="secondary"
              size="sm"
              icon={<RefreshCw size={12} />}
              onClick={() => handleSelectTemplate('Tạo video review cho Anker Soundcore Q30')}
            >
              Quick Demo
            </Button>
          )}
        </div>
      </header>

      {/* Main Studio Split Layout */}
      <div className="omni-studio-split">
        {/* Chat Studio Console */}
        <div className="omni-chat-main">
          {/* Scrollable Messages Stream */}
          <div className="omni-messages-scroll">
            {messages.map((msg) => {
              const isAssistant = msg.sender === 'assistant'
              const docTool = msg.toolCalls?.find((t) => t.name === 'read_file' && t.data?.content)

              return (
                <div key={msg.id} className={`chat-message-row ${msg.sender}`}>
                  <div className={`avatar-badge ${msg.sender}`}>
                    {isAssistant ? <Bot size={17} /> : <User size={17} />}
                  </div>

                  <div className="message-bubble-wrapper">
                    <div className={`message-bubble ${msg.sender}`}>
                      {/* Tool Execution Badges */}
                      {msg.toolCalls && msg.toolCalls.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
                          {msg.toolCalls.map((tc) => (
                            <ToolBadge key={tc.id || tc.name} tool={tc} />
                          ))}
                        </div>
                      )}

                      {/* Real-time Video Rendering Progress Card */}
                      {msg.pipelineProgress && (
                        <VideoProgressCard progress={msg.pipelineProgress} />
                      )}

                      {/* Embedded Video Player Card */}
                      {msg.videoResult && (
                        <VideoPlayerCard
                          video={msg.videoResult}
                          onInspectAsset={(id) => setInspectModalAssetId(id)}
                        />
                      )}

                      {/* Document Viewer Preview */}
                      {docTool && (
                        <DocPreviewCard
                          filePath={docTool.data?.path || 'document.md'}
                          content={docTool.data?.content}
                          linesCount={docTool.data?.lines}
                        />
                      )}

                      {/* Message Text Markdown Rendering */}
                      {msg.text && (
                        <div className="message-markdown" style={{ whiteSpace: 'pre-wrap' }}>
                          {msg.text}
                        </div>
                      )}
                    </div>

                    <span className="message-timestamp">
                      {msg.sender === 'assistant' ? 'Hermes Agent • ' : 'You • '}
                      {msg.timestamp}
                    </span>
                  </div>
                </div>
              )
            })}
            <div ref={messagesEndRef} />
          </div>

          {/* Quick Prompt Suggestion Carousel */}
          {messages.length <= 3 && !isGenerating && (
            <div className="suggestions-grid">
              {PROMPT_TEMPLATES.map((tmpl) => (
                <button
                  key={tmpl.id}
                  type="button"
                  className="suggestion-chip-btn"
                  onClick={() => handleSelectTemplate(tmpl.prompt)}
                >
                  <span style={{ fontSize: '18px' }}>{tmpl.icon}</span>
                  <div>
                    <strong>{tmpl.title}</strong>
                    <span>{tmpl.description}</span>
                  </div>
                </button>
              ))}
            </div>
          )}

          {/* Input Bar Composer */}
          <div className="omni-composer-box">
            <div className="composer-wrapper">
              <textarea
                ref={textareaRef}
                className="composer-textarea"
                rows={2}
                placeholder="Ra lệnh tự nhiên: 'Tạo video review sản phẩm...', 'Đọc tài liệu brand guidelines', v.v."
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isGenerating}
              />

              <div className="composer-bottom-bar">
                <div className="composer-hints">
                  <span>Nhấn <strong>Enter</strong> để gửi • <strong>Shift+Enter</strong> để xuống dòng</span>
                </div>

                <Button
                  variant="primary"
                  size="sm"
                  disabled={!inputText.trim() || isGenerating}
                  loading={isGenerating}
                  icon={<Send size={13} />}
                  onClick={handleSend}
                >
                  Gửi lệnh
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Right Media & Asset Inspector Sidebar */}
        <aside className="omni-inspector-sidebar">
          <div className="sidebar-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Film size={15} color="var(--accent-primary)" />
              <strong style={{ fontSize: '13px', color: 'var(--text-primary)' }}>
                Active Production & Assets
              </strong>
            </div>

            {activeVideoResult && (
              <Badge variant="success" size="sm">
                Active Master
              </Badge>
            )}
          </div>

          <div className="sidebar-content">
            {activeVideoResult ? (
              <>
                <div
                  style={{
                    backgroundColor: 'var(--bg-app)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)' }}>
                      PROJECT WORKSPACE
                    </span>
                    <Badge variant="neutral" size="sm">
                      {activeVideoResult.projectId}
                    </Badge>
                  </div>

                  <strong style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
                    {activeVideoResult.productName}
                  </strong>

                  <div style={{ display: 'flex', gap: '6px', marginTop: '4px' }}>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<ExternalLink size={12} />}
                      onClick={() => navigate(activeVideoResult.workspaceUrl)}
                    >
                      Open Pipeline Stage
                    </Button>
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-muted)', display: 'block', marginBottom: '8px' }}>
                    KEYFRAME ASSETS GALLERY
                  </span>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                    {activeVideoResult.assets?.map((asset, idx) => (
                      <div
                        key={asset.asset_id}
                        onClick={() => setInspectModalAssetId(asset.asset_id)}
                        style={{
                          backgroundColor: 'var(--bg-surface)',
                          border: '1px solid var(--border-default)',
                          borderRadius: 'var(--radius-md)',
                          padding: '8px',
                          cursor: 'pointer',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px',
                        }}
                      >
                        <div
                          style={{
                            aspectRatio: '9/16',
                            backgroundColor: 'var(--bg-app)',
                            borderRadius: 'var(--radius-sm)',
                            overflow: 'hidden',
                            position: 'relative',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                          }}
                        >
                          <img
                            src={asset.url}
                            alt={asset.label}
                            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                            onError={(e) => {
                              ;(e.target as HTMLElement).style.display = 'none'
                            }}
                          />
                          <Sparkles size={14} color="var(--accent-timeline)" style={{ position: 'absolute' }} />
                        </div>
                        <span style={{ fontSize: '11px', color: 'var(--text-primary)', fontWeight: 500 }}>
                          {asset.label || `Beat ${idx + 1}`}
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                          Duration: {asset.duration || 6}s
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  textAlign: 'center',
                  padding: '48px 16px',
                  color: 'var(--text-muted)',
                  gap: '12px',
                }}
              >
                <Layers size={32} strokeWidth={1.5} />
                <div>
                  <strong style={{ display: 'block', fontSize: '13px', color: 'var(--text-secondary)' }}>
                    No Active Video Production
                  </strong>
                  <span style={{ fontSize: '12px' }}>
                    Generate a product review video to inspect live master media, keyframes, and timeline assets here.
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleSelectTemplate('Tạo video review sản phẩm Tai nghe Anker Soundcore Q30')}
                >
                  Generate Sample Video
                </Button>
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* Full Resolution Media Inspector Modal */}
      <MediaViewerModal
        assetId={inspectModalAssetId}
        onClose={() => setInspectModalAssetId(null)}
      />
    </div>
  )
}
