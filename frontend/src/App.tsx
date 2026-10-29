import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { useAuth } from './contexts/AuthContext'
import { LoginPage } from './pages/LoginPage'
import { WorkbenchPage } from './pages/WorkbenchPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { ProjectDetailPage } from './pages/ProjectDetailPage'
import { AIConfigPage } from './pages/AIConfigPage'
import { SettingsPage } from './pages/SettingsPage'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { Center, Loader } from '@mantine/core'

export default function App() {
  const { user, loading } = useAuth()
  if (loading)
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  if (!user) return <LoginPage />

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<WorkbenchPage />} />
        <Route path="/ai-config" element={<AIConfigPage />} />
        {/* 兼容旧入口与书签 */}
        <Route path="/assistants" element={<Navigate to="/ai-config?tab=assistants" replace />} />
        <Route path="/models" element={<Navigate to="/ai-config?tab=models" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="/connections" element={<ConnectionsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
