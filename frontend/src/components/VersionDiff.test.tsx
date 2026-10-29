import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { VersionDiff } from './VersionDiff'

const { api } = vi.hoisted(() => ({ api: { get: vi.fn() } }))

vi.mock('../api/client', () => ({ api }))

const emptySection = { added: [], removed: [], changed: [] }

const diff = {
  fromVersion: 1,
  toVersion: 2,
  summary: {
    componentAdded: 1, componentRemoved: 1, componentChanged: 1,
    netAdded: 1, netRemoved: 0, netChanged: 1,
    bomAdded: 1, bomRemoved: 1, bomChanged: 1,
    boardAdded: 0, boardRemoved: 0, boardChanged: 1,
  },
  components: {
    added: [{ designator: 'R2', value: '1k', footprint: '0402' }],
    removed: [{ designator: 'C1', value: '100nF', footprint: '0603' }],
    changed: [{ designator: 'R1', fields: { value: { from: '10k', to: '22k' } } }],
  },
  nets: {
    added: [{ name: 'N$2', terminalCount: 2 }],
    removed: [],
    changed: [{ name: 'VCC', terminalCount: { from: 2, to: 1 }, terminalsAdded: [], terminalsRemoved: ['C1-1'] }],
  },
  bom: {
    added: [{ designator: 'R2', value: '1k', footprint: '0402' }],
    removed: [{ designator: 'C1', value: '100nF', footprint: '0603' }],
    changed: [{ designator: 'R1', fields: { value: { from: '10k', to: '22k' } } }],
  },
  boards: {
    added: [],
    removed: [],
    changed: [{ name: 'BoardA.PcbDoc', fields: { widthMil: { from: 1000, to: 1200 } } }],
  },
}

describe('VersionDiff', () => {
  beforeEach(() => {
    api.get.mockReset()
  })

  it('renders changes and hands a structured summary to AI', async () => {
    const onAskAI = vi.fn()
    api.get.mockImplementation((path: string) => {
      if (path.endsWith('/versions')) {
        return Promise.resolve([
          { version: 2, createdAt: '2026-10-29T02:00:00Z' },
          { version: 1, createdAt: '2026-10-29T01:00:00Z' },
        ])
      }
      if (path.includes('/diff?from=1&to=2')) return Promise.resolve(diff)
      return Promise.reject(new Error(`unexpected ${path}`))
    })
    render(<VersionDiff projectId="p1" currentVersion={2} onAskAI={onAskAI} />)

    expect(await screen.findByText(/元件 \+1 \/ -1 \/ ~1/)).toBeTruthy()
    expect(screen.getAllByText(/R1：值 10k → 22k/).length).toBe(2)
    expect(screen.getByText(/VCC：端子 2 → 1，移除 C1-1/)).toBeTruthy()
    expect(screen.getByText(/BoardA\.PcbDoc：宽\(mil\) 1000 → 1200/)).toBeTruthy()

    await userEvent.click(screen.getByRole('button', { name: '让 AI 解读变更' }))
    const question = onAskAI.mock.calls[0][0] as string
    expect(question).toContain('v1')
    expect(question).toContain('v2')
    expect(question).toContain('R1（值 10k → 22k）')
    expect(question).toContain('VCC')
    expect(question).toContain('BoardA.PcbDoc')
  })

  it('reports an unchanged design without offering AI analysis', async () => {
    api.get.mockImplementation((path: string) => {
      if (path.endsWith('/versions')) {
        return Promise.resolve([
          { version: 2, createdAt: '2026-10-29T02:00:00Z' },
          { version: 1, createdAt: '2026-10-29T01:00:00Z' },
        ])
      }
      return Promise.resolve({
        ...diff,
        summary: Object.fromEntries(Object.keys(diff.summary).map((key) => [key, 0])),
        components: emptySection,
        nets: emptySection,
        bom: emptySection,
        boards: emptySection,
      })
    })
    render(<VersionDiff projectId="p1" currentVersion={2} onAskAI={vi.fn()} />)
    expect(await screen.findByText(/没有检测到设计数据变化/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '让 AI 解读变更' })).toBeNull()
  })

  it('stays hidden until a second snapshot exists', () => {
    render(<VersionDiff projectId="p1" currentVersion={1} />)
    expect(screen.queryByText('版本对比')).toBeNull()
    expect(api.get).not.toHaveBeenCalled()
  })
})
