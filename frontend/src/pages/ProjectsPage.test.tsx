import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { ProjectsPage } from './ProjectsPage'

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn(), postForm: vi.fn() },
}))

vi.mock('../api/client', () => ({ api }))

function project(id: string, name: string, status: string) {
  return {
    id,
    name,
    status,
    error: status === 'failed' ? '解析失败原因' : '',
    fileNames: [`${name}.PrjPcb`],
    stats: { componentCount: 3 },
    svgManifest: [],
    parseDurationMs: 0,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  }
}

describe('ProjectsPage usability', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset())
    api.get.mockResolvedValue([project('p1', 'Board A', 'ready'), project('p2', 'Board B', 'failed')])
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('filters projects by name', async () => {
    render(<ProjectsPage />)
    await screen.findByText('Board A')
    await userEvent.type(screen.getByPlaceholderText('按工程名或文件名搜索'), 'Board B')
    expect(screen.queryByText('Board A')).toBeNull()
    expect(screen.getByText('Board B')).toBeTruthy()
  })

  it('asks for confirmation before deleting a project', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<ProjectsPage />)
    await screen.findByText('Board A')
    await userEvent.click(screen.getAllByRole('button', { name: '删除工程' })[0])
    expect(api.delete).not.toHaveBeenCalled()

    vi.spyOn(window, 'confirm').mockReturnValue(true)
    api.delete.mockResolvedValue({ ok: true })
    await userEvent.click(screen.getAllByRole('button', { name: '删除工程' })[0])
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith('/files/projects/p1'))
  })

  it('shows the server reason when reparse is rejected', async () => {
    api.post.mockRejectedValue(new Error('该工程已在解析队列中'))
    render(<ProjectsPage />)
    await screen.findByText('Board A')
    await userEvent.click(screen.getAllByRole('button', { name: '重新解析' })[1])
    expect(await screen.findByText('该工程已在解析队列中')).toBeTruthy()
  })
})
