import { useState, useRef, useCallback, useEffect } from 'react'
import { ChatMessage, ToolCall, PipelineProgress, VideoResult, PromptTemplate } from '../types/omniChat'

const INITIAL_WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome-1',
  sender: 'assistant',
  text: `Xin chào! Tôi là **Hermes Omni Agent** — trợ lý điều hành và sản xuất video thương mại tự động.

Bạn có thể ra lệnh trực tiếp bằng ngôn ngữ tự nhiên:
- 🎥 **Sản xuất video**: *"Tạo video review cho Anker Soundcore Q30"* hoặc *"Làm video thương mại 9:16 cho Bàn phím cơ không dây"*
- 📖 **Đọc & Phân tích tài liệu**: *"Đọc tài liệu brand guidelines"* hoặc *"Xem spec sheet sản phẩm"*
- 💡 **Ý tưởng kịch bản**: *"Lên kịch bản 4 phân cảnh đánh vào nỗi đau dân văn phòng"*

Chọn nhanh gợi ý bên dưới hoặc nhập yêu cầu của bạn để bắt đầu!`,
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  isStreaming: false,
}

export const PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: 'tmpl-1',
    icon: '🎥',
    category: 'video',
    title: 'Tạo Video Review Tai Nghe',
    prompt: 'Tạo video review sản phẩm Tai nghe Anker Soundcore Q30 định dạng 9:16 tối ưu cho TikTok',
    description: 'Chạy toàn bộ pipeline 4 bước: Lock nhận diện → Storyboard → Render cảnh → Audio Master',
  },
  {
    id: 'tmpl-2',
    icon: '📖',
    category: 'docs',
    title: 'Đọc Brand Guidelines',
    prompt: 'Đọc tài liệu Brand Guidelines và kiểm tra các tiêu chuẩn bảo toàn nhận diện thị giác',
    description: 'Trích xuất quy chuẩn màu sắc, logo, và tỷ lệ khung hình 9:16',
  },
  {
    id: 'tmpl-3',
    icon: '💡',
    category: 'creative',
    title: 'Lên Kịch Bản Review 30s',
    prompt: 'Gợi ý 3 góc Hook 3s đầu tiên và kịch bản 4 phân cảnh cho sản phẩm Chuột công thái học Ergonomic',
    description: 'Phân tích tâm lý mua hàng và đề xuất cấu trúc phân cảnh giữ chân người xem',
  },
  {
    id: 'tmpl-4',
    icon: '⚡',
    category: 'video',
    title: 'Tạo Video Bàn Phím Cơ',
    prompt: 'Tạo video review sản phẩm Bàn phím cơ Không Dây RGB với voiceover Zephyr AI',
    description: 'Sản xuất video thương mại đa phân cảnh với âm thanh gõ phím chân thực',
  },
]

export function useOmniChat(initialProjectId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([INITIAL_WELCOME_MESSAGE])
  const [isGenerating, setIsGenerating] = useState(false)
  const [activeVideoResult, setActiveVideoResult] = useState<VideoResult | null>(null)
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  const sendMessage = useCallback(
    async (text: string, customProjectId?: string) => {
      const trimmed = text.trim()
      if (!trimmed || isGenerating) return

      const userTimestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      const userMsg: ChatMessage = {
        id: `user_${Date.now()}`,
        sender: 'user',
        text: trimmed,
        timestamp: userTimestamp,
      }

      const assistantMsgId = `assistant_${Date.now()}`
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        sender: 'assistant',
        text: '',
        timestamp: userTimestamp,
        isStreaming: true,
        toolCalls: [],
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsGenerating(true)

      const activeProject = customProjectId || initialProjectId
      const controller = new AbortController()
      abortControllerRef.current = controller

      try {
        // The backend is now running on the same host, so use a relative path.
        const response = await fetch('/api/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: trimmed,
            project_id: activeProject,
          }),
          signal: controller.signal,
        })

        if (!response.ok || !response.body) {
          throw new Error('Network response was not ok.')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let streamedText = ''
        let currentToolCalls: ToolCall[] = []
        let currentProgress: PipelineProgress | undefined
        let currentVideoRes: VideoResult | undefined

        while (true) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (!line.startsWith('data:')) continue

            const jsonStr = line.substring(5).trim()
            if (!jsonStr) continue

            try {
              const event = JSON.parse(jsonStr)

              // Handle token deltas for streaming text
              if (event.token) {
                streamedText += event.token
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, text: streamedText } : m
                  )
                )
              }
              
              // Handle progress updates
              if (event.type === 'progress' && event.payload) {
                  const progressPayload = event.payload;
                  // Find the right tool call to update, or update the general pipeline progress
                  // This part needs to be aligned with how backend sends progress events.
                  // For now, we can update a general progress indicator.
                  currentProgress = {
                      step: progressPayload.step,
                      totalSteps: 8, // Assuming 8 steps now
                      stepName: progressPayload.step,
                      status: progressPayload.status,
                      percent: ((Object.keys(currentProgress || {}).length + 1) / 8) * 100,
                      message: `Processing: ${progressPayload.step}`
                  };
                  setMessages((prev) =>
                    prev.map((m) =>
                      m.id === assistantMsgId ? { ...m, pipelineProgress: currentProgress } : m
                    )
                  );
              }
              
              // Here you can add handlers for other event types like 'tool_start', 'tool_result' etc.

            } catch (err) {
              console.warn('Failed to parse SSE line:', jsonStr, err)
            }
          }
        }
      } catch (err: any) {
        if (err.name === 'AbortError') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, isStreaming: false, text: m.text + '\n\n*(Đã dừng bởi người dùng)*' }
                : m
            )
          )
        } else {
           setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? { ...m, isStreaming: false, text: `Lỗi kết nối đến backend: ${err.message}` }
                : m
            )
          )
        }
      } finally {
        setIsGenerating(false)
        abortControllerRef.current = null
      }
    },
    [isGenerating, initialProjectId]
  )

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setIsGenerating(false)
  }, [])

  const clearHistory = useCallback(() => {
    stopGeneration()
    setMessages([INITIAL_WELCOME_MESSAGE])
    setActiveVideoResult(null)
    setSelectedAssetId(null)
  }, [stopGeneration])

  return {
    messages,
    isGenerating,
    activeVideoResult,
    selectedAssetId,
    setSelectedAssetId,
    sendMessage,
    stopGeneration,
    clearHistory,
    setActiveVideoResult,
  }
}
