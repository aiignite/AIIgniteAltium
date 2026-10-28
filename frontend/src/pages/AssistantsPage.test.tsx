import { screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { AssistantsPage } from './AssistantsPage'

const { api, auth } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  auth: { user: { id: 'u1', email: 'a@example.com', displayName: 'A', isAdmin: false } },
}))

vi.mock('../api/client', () => ({ api }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))

const assistant = {
  id: 'a1',
  name: '原理图审查助手',
  description: '',
  avatar: 'bot',
  category: 'Engineering',
  systemPrompt: '',
  skillCodes: [],
  modelConfigId: null,
  isDefault: true,
  isSystem: false,
  enabled: true,
  usageCount: 0,
  createdAt: '2026-01-01T00:00:00Z',
}

const skill = {
  id: 's1',
  code: 'review',
  name: '审查',
  description: '',
  category: 'business',
  icon: 'sparkles',
  promptTemplate: '',
  keywords: [],
  isSystem: false,
  enabled: true,
  sortOrder: 1,
  createdAt: '2026-01-01T00:00:00Z',
}

function setup() {
  api.get.mockImplementation((path: string) => {
    if (path === '/ai/assistants') return Promise.resolve([assistant])
    if (path === '/ai/skills') return Promise.resolve([skill])
    if (path === '/ai/models') return Promise.resolve([])
    return Promise.resolve([])
  })
}

describe('AssistantsPage write permissions', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    setup()
  })

  it('hides create and edit controls for non-admin users', async () => {
    auth.user.isAdmin = false
    render(<AssistantsPage />)
    await screen.findByText('原理图审查助手')
    expect(screen.queryByRole('button', { name: '新建助手' })).toBeNull()
    expect(screen.queryByRole('button', { name: '编辑助手' })).toBeNull()
    expect(screen.queryByRole('button', { name: '删除助手' })).toBeNull()
    expect(screen.queryByRole('button', { name: '设为默认' })).toBeNull()
  })

  it('keeps create controls for admins', async () => {
    auth.user.isAdmin = true
    render(<AssistantsPage />)
    await screen.findByText('原理图审查助手')
    expect(screen.getByRole('button', { name: '新建助手' })).not.toBeNull()
    expect(screen.getByRole('button', { name: '编辑助手' })).not.toBeNull()
  })
})
