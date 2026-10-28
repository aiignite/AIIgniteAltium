import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { ReviewPanel } from './ReviewPanel'

const { api } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('../api/client', () => ({ api }))

const run = {
  id: 'r1',
  snapshotVersion: 1,
  status: 'completed',
  rulesetVersion: 'p1.1',
  counts: { error: 1, warning: 1, info: 0 },
  createdAt: '2026-10-29T00:00:00Z',
  findings: [
    {
      rule: 'duplicate_designator',
      severity: 'error',
      title: '位号重复',
      detail: '同一工程内多个元件使用相同位号',
      refs: ['R1'],
      count: 1,
    },
    {
      rule: 'missing_footprint',
      severity: 'warning',
      title: '元件缺少封装',
      detail: '缺少封装将影响 PCB 布局与 BOM 准确性',
      refs: ['R1'],
      count: 1,
    },
  ],
}

describe('ReviewPanel', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.post.mockReset()
  })

  it('runs a review and renders findings with version binding', async () => {
    api.get.mockResolvedValueOnce([])
    api.get.mockResolvedValueOnce([run])
    api.post.mockResolvedValue(run)
    render(<ReviewPanel projectId="p1" currentVersion={1} />)
    expect(await screen.findByText('还没有审查记录，点击「运行审查」生成。')).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '运行审查' }))
    expect(await screen.findByText('位号重复')).toBeTruthy()
    expect(screen.getByText('元件缺少封装')).toBeTruthy()
    expect(screen.getByText('错误 1')).toBeTruthy()
    expect(screen.getByText('规则集 p1.1')).toBeTruthy()
    expect(api.post).toHaveBeenCalledWith('/files/projects/p1/reviews')
  })

  it('loads the latest stored review on mount', async () => {
    api.get.mockResolvedValueOnce([run]).mockResolvedValueOnce(run)
    render(<ReviewPanel projectId="p1" currentVersion={1} />)
    expect(await screen.findByText('位号重复')).toBeTruthy()
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/files/projects/p1/reviews/r1'))
  })

  it('disables review when no snapshot is ready', () => {
    api.get.mockResolvedValue([])
    render(<ReviewPanel projectId="p1" currentVersion={0} />)
    expect(screen.getByRole('button', { name: '运行审查' })).toHaveProperty('disabled', true)
  })
})
