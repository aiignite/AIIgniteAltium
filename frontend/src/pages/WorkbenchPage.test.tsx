import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatStreamEvent } from '../api/client'
import { render } from '../test/render'
import { WorkbenchPage } from './WorkbenchPage'

const { api, streamChat } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), blob: vi.fn() },
  streamChat: vi.fn(),
}))

vi.mock('../api/client', () => ({ api, streamChat }))

const project = {
  id: 'p1',
  name: 'Board A',
  status: 'ready',
  error: '',
  fileNames: ['a.PrjPcb'],
  stats: { componentCount: 12 },
  svgManifest: [],
  parseDurationMs: 0,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}

const connection = { id: 'c1', name: '车间网关', baseUrl: 'http://127.0.0.1:3296', status: 'connected' }

const boundConversation = {
  id: 'c9',
  title: '实时对话',
  projectId: null,
  connectionId: 'c1',
  assistantId: null,
  skill: '',
  messageCount: 2,
  updatedAt: '2026-01-01T00:00:00Z',
}

function setupApi() {
  api.get.mockImplementation((path: string) => {
    if (path === '/files/projects') return Promise.resolve([project])
    if (path === '/altium/connections') return Promise.resolve([connection])
    if (path === '/ai/assistants') return Promise.resolve([])
    if (path === '/ai/skills') return Promise.resolve([])
    if (path === '/ai/models') return Promise.resolve([{ id: 'm1', name: 'mock', enabled: true }])
    if (path === '/ai/conversations') return Promise.resolve([boundConversation])
    if (path === '/ai/conversations/c9/messages') return Promise.resolve([])
    if (path === '/files/projects/p1/svgs') return Promise.resolve([])
    return Promise.resolve([])
  })
}

async function pickOption(combo: HTMLElement) {
  await userEvent.click(combo)
  await userEvent.keyboard('{ArrowDown}{Enter}')
}

async function pickSource(option: string) {
  const combo = screen.getByRole('combobox', { name: '设计来源' })
  await userEvent.click(combo)
  const index = ['无设计来源', '离线解析工程', 'Altium 实时连接'].indexOf(option)
  for (let i = 0; i < index; i += 1) await userEvent.keyboard('{ArrowDown}')
  await userEvent.keyboard('{Enter}')
}

async function sendMessage(text: string) {
  await userEvent.type(screen.getByPlaceholderText(/对话，Enter 发送/), text)
  await userEvent.click(screen.getByRole('button', { name: '发送' }))
}

async function renderReady() {
  render(<WorkbenchPage />)
  await screen.findByRole('combobox', { name: '设计来源' })
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/altium/connections'))
  await waitFor(() => expect(api.get).toHaveBeenCalledWith('/files/projects'))
}

describe('WorkbenchPage design source selection', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.values(api).forEach((fn) => fn.mockReset())
    streamChat.mockReset()
    setupApi()
  })

  it('does not attach an implicit project or live design', async () => {
    streamChat.mockImplementation(async (_body, onEvent: (e: ChatStreamEvent) => void) => {
      onEvent({ type: 'meta', conversationId: 'conv-new' })
      onEvent({ type: 'done' })
    })
    await renderReady()
    await sendMessage('你好')
    await waitFor(() => expect(streamChat).toHaveBeenCalled())
    const body = streamChat.mock.calls[0][0]
    expect(body.projectId).toBeNull()
    expect(body.connectionId).toBeNull()
  })

  it('sends connectionId and never projectId for a live source', async () => {
    streamChat.mockImplementation(async (_body, onEvent: (e: ChatStreamEvent) => void) => {
      onEvent({ type: 'done' })
    })
    await renderReady()
    await pickSource('Altium 实时连接')
    await pickOption(await screen.findByRole('combobox', { name: '实时连接' }))
    await sendMessage('看下实时板框')
    await waitFor(() => expect(streamChat).toHaveBeenCalled())
    const body = streamChat.mock.calls[0][0]
    expect(body.connectionId).toBe('c1')
    expect(body.projectId).toBeNull()
  })

  it('restores the source of a bound conversation and locks switching while streaming', async () => {
    let finish: () => void = () => {}
    streamChat.mockImplementation(
      (_body, onEvent: (e: ChatStreamEvent) => void) =>
        new Promise<void>((resolve) => {
          finish = () => {
            onEvent({ type: 'done' })
            resolve()
          }
        }),
    )
    await renderReady()
    await userEvent.click(screen.getByRole('button', { name: '历史对话' }))
    await userEvent.click(await screen.findByText('实时对话'))
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: '设计来源' }) as HTMLInputElement).value).toBe(
        'Altium 实时连接',
      ),
    )
    expect((screen.getByRole('combobox', { name: '实时连接' }) as HTMLInputElement).value).toBe(
      '车间网关（已连接）',
    )
    await sendMessage('继续')
    await waitFor(() => expect(streamChat).toHaveBeenCalled())
    const body = streamChat.mock.calls[0][0]
    expect(body.conversationId).toBe('c9')
    expect(body.connectionId).toBe('c1')
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: '设计来源' }).hasAttribute('disabled')).toBe(true),
    )
    finish()
    await waitFor(() =>
      expect(screen.getByRole('combobox', { name: '设计来源' }).hasAttribute('disabled')).toBe(false),
    )
  })

  it('stops streaming on demand while keeping the partial answer', async () => {
    streamChat.mockImplementation(
      (_body, onEvent: (e: ChatStreamEvent) => void, signal?: AbortSignal) =>
        new Promise<void>((_resolve, reject) => {
          onEvent({ type: 'meta', conversationId: 'conv-stop' })
          onEvent({ type: 'delta', text: '部分回答' })
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    await renderReady()
    await sendMessage('帮我分析')
    await userEvent.click(await screen.findByRole('button', { name: '停止' }))
    await waitFor(() => expect(screen.getByRole('button', { name: '发送' })).toBeTruthy())
    expect(screen.getByText('部分回答')).toBeTruthy()
    expect(screen.queryByText('连接中断，请重试')).toBeNull()
  })

  it('sends a suggested question in one click', async () => {
    streamChat.mockImplementation(async (_body, onEvent: (e: ChatStreamEvent) => void) => {
      onEvent({ type: 'done' })
    })
    await renderReady()
    await userEvent.click(screen.getByRole('button', { name: '帮我审查这个工程的原理图' }))
    await waitFor(() => expect(streamChat).toHaveBeenCalled())
    expect(streamChat.mock.calls[0][0].content).toBe('帮我审查这个工程的原理图')
  })
})

describe('WorkbenchPage deep links', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.values(api).forEach((fn) => fn.mockReset())
    streamChat.mockReset()
    setupApi()
  })

  it('preselects a project from the projectId query parameter', async () => {
    render(<WorkbenchPage />, { route: '/?projectId=p1' })
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: '设计来源' }) as HTMLInputElement).value).toBe('离线解析工程'),
    )
    expect((screen.getByRole('combobox', { name: '已解析工程' }) as HTMLInputElement).value).toBe('Board A（12 元件）')
  })

  it('preselects a connection from the connectionId query parameter', async () => {
    render(<WorkbenchPage />, { route: '/?connectionId=c1' })
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: '设计来源' }) as HTMLInputElement).value).toBe('Altium 实时连接'),
    )
    expect((screen.getByRole('combobox', { name: '实时连接' }) as HTMLInputElement).value).toBe('车间网关（已连接）')
  })

  it('auto-sends the ask parameter once the project is ready', async () => {
    streamChat.mockImplementation(async (_body, onEvent: (e: ChatStreamEvent) => void) => {
      onEvent({ type: 'done' })
    })
    render(<WorkbenchPage />, { route: `/?projectId=p1&ask=${encodeURIComponent('这个工程的 BOM 有什么风险？')}` })
    await waitFor(() => expect(streamChat).toHaveBeenCalled())
    const body = streamChat.mock.calls[0][0]
    expect(body.projectId).toBe('p1')
    expect(body.content).toBe('这个工程的 BOM 有什么风险？')
  })

  it('restores the last design source on the next visit', async () => {
    const first = render(<WorkbenchPage />, { route: '/?projectId=p1' })
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: '设计来源' }) as HTMLInputElement).value).toBe('离线解析工程'),
    )
    await waitFor(() => expect(localStorage.getItem('aidrive.workbench.prefs')).toContain('"source":"project"'))
    first.unmount()
    render(<WorkbenchPage />)
    await waitFor(() =>
      expect((screen.getByRole('combobox', { name: '设计来源' }) as HTMLInputElement).value).toBe('离线解析工程'),
    )
    expect((screen.getByRole('combobox', { name: '已解析工程' }) as HTMLInputElement).value).toBe('Board A（12 元件）')
  })
})
