import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useSearchParams } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from './lib/api'
import { AppShell } from './components/shell/AppShell'

// Feature Pages
import { DashboardPage } from './features/dashboard/DashboardPage'
import { AnalyticsDashboard } from './features/dashboard/AnalyticsDashboard'
import { OmniChatStudioPage } from './features/omni-chat/OmniChatStudioPage'
import { ProjectsPage } from './features/projects/ProjectsPage'
import { ProjectWorkspace } from './features/project-workspace/ProjectWorkspace'
import { ProductLibraryPage } from './features/product-library/ProductLibraryPage'
import { OperationsPage } from './features/operations/OperationsPage'
import { KnowledgePage } from './features/knowledge/KnowledgePage'
import { AIAnalysisPage } from './features/ai-analysis/AIAnalysisPage'
import { SettingsPage } from './features/settings/SettingsPage'
import { PromptStudioPage } from './features/prompt-studio/PromptStudioPage'

// Global Styles
import './styles/globals.css'

function VideoFactoryLegacyRedirect() {
  const [params] = useSearchParams()
  const projectId = params.get('projectId')
  if (projectId) {
    return <Navigate to={`/projects/${encodeURIComponent(projectId)}/workflow/resources`} replace />
  }
  return <Navigate to="/projects" replace />
}

import { SessionProvider } from './context/SessionContext'

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <SessionProvider>
        <BrowserRouter>
          <AppShell>
            <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />

            {/* Analytics */}
            <Route path="/analytics" element={<AnalyticsDashboard />} />
            <Route path="/analytics/:projectId" element={<AnalyticsDashboard />} />

            {/* Omni Chat Studio */}
            <Route path="/studio" element={<OmniChatStudioPage />} />
            <Route path="/omni-studio" element={<Navigate to="/studio" replace />} />
            <Route path="/omni-chat" element={<Navigate to="/studio" replace />} />
            <Route path="/chat" element={<Navigate to="/studio" replace />} />

            {/* Project Catalog & Unified Workspace */}
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<Navigate to="workflow/resources" replace />} />
            <Route path="/projects/:projectId/workflow" element={<Navigate to="resources" replace />} />
            <Route path="/projects/:projectId/workflow/:stage" element={<ProjectWorkspace />} />
            <Route path="/projects/:projectId/prompt-studio" element={<PromptStudioPage />} />

            {/* Product Library */}
            <Route path="/products" element={<ProductLibraryPage />} />
            <Route path="/product-research" element={<Navigate to="/products" replace />} />

            {/* Video Factory Legacy Redirect */}
            <Route path="/video-factory" element={<VideoFactoryLegacyRedirect />} />

            {/* Operations & Diagnostic Jobs */}
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/jobs" element={<Navigate to="/operations" replace />} />

            {/* Secondary Services */}
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/ai-analysis" element={<AIAnalysisPage />} />
            <Route path="/settings" element={<SettingsPage />} />

            {/* Catch-all */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </AppShell>
      </BrowserRouter>
      </SessionProvider>
    </QueryClientProvider>
  )
}

const root = document.getElementById('root')
if (root) {
  createRoot(root).render(<App />)
}