import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/api'
import { ProjectSelector } from './features/projects/ProjectSelector'
import { PromptStudioPage } from './features/prompt-studio/PromptStudioPage'
import { VideoFactoryPage } from './features/video-factory/VideoFactoryPage'

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Navigate to="/projects" replace />} />
          <Route path="/projects" element={<ProjectSelector />} />
          <Route path="/projects/:projectId/prompt-studio" element={<PromptStudioPage />} />
          <Route path="/video-factory" element={<VideoFactoryPage />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(<App />)
}