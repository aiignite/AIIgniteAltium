import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { SettingsPage } from './SettingsPage'

const { api, auth } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  auth: { user: { id: 'u1', email: 'a@example.com', displayName: 'A', isAdmin: true } },
}))

vi.mock('../api/client', () => ({ api }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => auth }))

const model = {
  id: 'm1',
  name: 'OpenAI',
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  hasApiKey: true,
  modelName: 'gpt-4o-mini',
  isDefault: true,
  enabled: true,
  remark: '',
}

function renderPage() {
  api.get.mockResolvedValue([model])
  return render(<SettingsPage />)
}

describe('SettingsPage credential handling', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.post.mockReset()
    api.put.mockReset()
    api.delete.mockReset()
    api.put.mockResolvedValue({})
    api.post.mockResolvedValue({})
    api.delete.mockResolvedValue({})
    auth.user.isAdmin = true
  })

  it('hides write actions from non-admin users', async () => {
    auth.user.isAdmin = false
    renderPage()
    await screen.findByText('OpenAI')
    expect(screen.queryByRole('button', { name: '新增模型' })).toBeNull()
    expect(screen.queryByTitle('编辑')).toBeNull()
    expect(screen.queryByTitle('删除')).toBeNull()
    expect(screen.getByText('已配置')).not.toBeNull()
  })

  it('keeps the stored key when the field is untouched', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('编辑'))
    expect(await screen.findByText('已配置')).not.toBeNull()
    const keep = await screen.findByRole('radio', { name: '保留现有密钥' })
    expect(keep).not.toBeNull()
    await userEvent.click(keep)
    const name = screen.getByLabelText('名称')
    await userEvent.clear(name)
    await userEvent.type(name, 'OpenAI 正式')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/ai/models/m1')
    expect(body.name).toBe('OpenAI 正式')
    expect('apiKey' in body).toBe(false)
  })

  it('sends a replacement key only when replacing', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('编辑'))
    await userEvent.click(await screen.findByRole('radio', { name: '替换密钥' }))
    const key = await screen.findByLabelText('新 API Key')
    await userEvent.type(key, 'sk-new')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1].apiKey).toBe('sk-new')
  })

  it('clears the key with an explicit empty value', async () => {
    renderPage()
    await userEvent.click(await screen.findByTitle('编辑'))
    await userEvent.click(await screen.findByRole('radio', { name: '清除密钥' }))
    expect(screen.queryByLabelText('新 API Key')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.put).toHaveBeenCalled())
    expect(api.put.mock.calls[0][1].apiKey).toBe('')
  })

  it('creates a model with the provided key', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: '新增模型' }))
    await userEvent.type(await screen.findByLabelText('名称'), '本地 Ollama')
    await userEvent.type(screen.getByLabelText('API Key'), 'ollama')
    await userEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(api.post).toHaveBeenCalled())
    const [, body] = api.post.mock.calls[0]
    expect(body.name).toBe('本地 Ollama')
    expect(body.apiKey).toBe('ollama')
  })
})
