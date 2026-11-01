import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { ConnectionsPage } from './ConnectionsPage'

const { api, auth } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), blob: vi.fn() },
  auth: { user: { id: 'u1', email: 'a@example.com', displayName: 'A', isAdmin: true } },
}))

vi.mock('../api/client', () => ({ api }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))

const connection = {
  id: 'c1',
  name: 'Altium 工作机',
  baseUrl: 'http://192.168.1.14:3296',
  hasToken: true,
  status: 'connected',
  lastError: '',
  info: { altiumOnline: true },
  lastCheckedAt: null,
  remark: '',
  createdAt: '2026-01-01T00:00:00Z',
}

function renderPage(list = [connection]) {
  api.get.mockImplementation((path: string) => {
    if (path === '/altium/connections') return Promise.resolve(list)
    if (path === '/auth/users/options')
      return Promise.resolve([{ id: 'u2', email: 'b@example.com', displayName: 'Bob' }])
    if (path.endsWith('/grants')) return Promise.resolve({ connectionId: 'c1', userIds: [] })
    return Promise.resolve([])
  })
  return render(<ConnectionsPage />)
}

describe('ConnectionsPage authorization UI', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.post.mockResolvedValue({})
    api.put.mockResolvedValue({})
    api.delete.mockResolvedValue({})
    auth.user.isAdmin = true
  })

  it('hides management actions from non-admin users', async () => {
    auth.user.isAdmin = false
    renderPage()
    await screen.findByText('Altium 工作机')
    expect(screen.queryByRole('button', { name: '新增连接' })).toBeNull()
    expect(screen.queryByTitle('编辑')).toBeNull()
    expect(screen.queryByTitle('授权用户')).toBeNull()
    expect(screen.queryByTitle('删除')).toBeNull()
    expect(screen.getByText('仅显示已授权连接')).not.toBeNull()
  })

  it('uses a password field and keeps the token when left empty', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('编辑'))
    const token = await screen.findByLabelText('网关令牌')
    expect(token.getAttribute('type')).toBe('password')
    await userEvent.clear(screen.getByLabelText('名称'))
    await userEvent.type(screen.getByLabelText('名称'), '车间网关')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/altium/connections/c1')
    expect(body.name).toBe('车间网关')
    expect('apiToken' in body).toBe(false)
  })

  it('sends an empty token only when clearing is confirmed', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('编辑'))
    await userEvent.click(await screen.findByRole('checkbox'))
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1].apiToken).toBe('')
  })

  it('saves explicit connection grants for selected users', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('授权用户'))
    await screen.findByText('可访问用户')
    await userEvent.click(screen.getByRole('combobox', { name: '可访问用户' }))
    await userEvent.click(await screen.findByText('Bob（b@example.com）'))
    await userEvent.click(screen.getByRole('button', { name: '保存授权' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/altium/connections/c1/grants')
    expect(body).toEqual({ userIds: ['u2'] })
  })

  it('lists command audits and undoes an executed command', async () => {
    api.get.mockImplementation((path: string) => {
      if (path === '/altium/connections') return Promise.resolve([connection])
      if (path === '/altium/connections/c1/commands/audit?limit=50')
        return Promise.resolve([
          {
            id: 'a1',
            command: 'altium_move_component',
            params: { designator: 'U1', x: 10, y: 20 },
            before: {},
            status: 'executed',
            requestId: 'r1',
            undoOfId: null,
            error: null,
            canUndo: true,
            createdAt: '2026-01-01T00:00:00Z',
            undoneAt: null,
          },
        ])
      return Promise.resolve([])
    })
    render(<ConnectionsPage />)
    await userEvent.click(await screen.findByTitle('命令历史'))
    expect(await screen.findByText('altium_move_component')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '撤销' }))
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/altium/connections/c1/commands/audit/a1/undo'),
    )
  })
})
