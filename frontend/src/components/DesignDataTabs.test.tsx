import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { DesignDataTabs } from './DesignDataTabs'

const { api } = vi.hoisted(() => ({ api: { get: vi.fn(), blob: vi.fn() } }))

vi.mock('../api/client', () => ({ api }))

describe('DesignDataTabs ask AI', () => {
  beforeEach(() => {
    api.get.mockReset()
    api.get.mockImplementation((path: string) => {
      if (path === '/files/projects/p1/svgs') return Promise.resolve([])
      if (path.startsWith('/files/projects/p1/components')) {
        return Promise.resolve({
          items: [{ designator: 'R1', value: '10k', footprint: '0603', description: '电阻', sheet: 'Sheet1' }],
          total: 1,
        })
      }
      return Promise.resolve({ items: [], total: 0 })
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('asks about a component row with its context', async () => {
    const onAskAI = vi.fn()
    render(<DesignDataTabs projectId="p1" onAskAI={onAskAI} />)
    await userEvent.click(await screen.findByRole('button', { name: /^问 AI：请分析元件 R1/ }))
    expect(onAskAI).toHaveBeenCalledTimes(1)
    expect(onAskAI.mock.calls[0][0]).toContain('R1')
    expect(onAskAI.mock.calls[0][0]).toContain('10k')
  })

  it('offers SVG and PNG downloads for rendered sheets', async () => {
    api.get.mockImplementation((path: string) =>
      path === '/files/projects/p1/svgs'
        ? Promise.resolve([{ svgId: 'sch_0', kind: 'sch', title: 'Main', file: 'sch_0.svg' }])
        : Promise.resolve({ items: [], total: 0 }),
    )
    api.blob.mockResolvedValue('blob:svg')
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    render(<DesignDataTabs projectId="p1" />)
    await userEvent.click(await screen.findByRole('tab', { name: '原理图' }))
    expect(await screen.findByRole('button', { name: '下载 SVG' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '下载 PNG（2×）' })).toBeTruthy()
    await userEvent.click(screen.getByRole('button', { name: '下载 SVG' }))
    expect(click).toHaveBeenCalled()
    expect(api.blob).toHaveBeenCalledWith('/files/projects/p1/svgs/sch_0')
  })
})
