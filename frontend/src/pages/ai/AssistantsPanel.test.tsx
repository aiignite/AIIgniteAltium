import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../../test/render'
import { AssistantsPanel } from './AssistantsPanel'

const { api, auth } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  auth: { user: { id: 'u1', email: 'a@example.com', displayName: 'A', isAdmin: false } },
}))

vi.mock('../../api/client', () => ({ api }))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => auth }))

const assistant = {
  id: 'a1',
  name: '原理图审查助手',
  description: '',
  avatar: 'bot',
  category: 'Engineering',
  systemPrompt: '',
  greeting: '',
  skillCodes: [],
  toolCodes: [],
  modelConfigId: null,
  temperature: null,
  maxTokens: null,
  isDefault: true,
  isSystem: false,
  enabled: true,
  usageCount: 0,
  sortOrder: 1,
  createdAt: '2026-01-01T00:00:00Z',
}

function setup() {
  api.get.mockImplementation((path: string) => {
    if (path === '/ai/assistants') return Promise.resolve([assistant])
    if (path === '/ai/skills') return Promise.resolve([])
    if (path === '/ai/models') return Promise.resolve([])
    if (path === '/ai/tools/registry') return Promise.resolve([])
    return Promise.resolve([])
  })
}

describe('AssistantsPanel write permissions', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    setup()
  })

  it('disables create for non-admin users', async () => {
    auth.user.isAdmin = false
    render(<AssistantsPanel />)
    await screen.findByText('原理图审查助手')
    expect((screen.getByRole('button', { name: '新建助手' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('keeps create controls for admins', async () => {
    auth.user.isAdmin = true
    render(<AssistantsPanel />)
    await screen.findByText('原理图审查助手')
    expect((screen.getByRole('button', { name: '新建助手' }) as HTMLButtonElement).disabled).toBe(false)
  })
})
