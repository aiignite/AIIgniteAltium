import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render } from '../test/render'
import { ExportPanel } from './ExportPanel'

const { api } = vi.hoisted(() => ({ api: { blob: vi.fn() } }))
vi.mock('../api/client', () => ({ api }))

describe('ExportPanel', () => {
  let anchors: HTMLAnchorElement[]

  beforeEach(() => {
    anchors = []
    api.blob.mockReset()
    api.blob.mockResolvedValue('blob:export')
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const append = document.body.appendChild.bind(document.body)
    vi.spyOn(document.body, 'appendChild').mockImplementation((node) => {
      if (node instanceof HTMLAnchorElement) anchors.push(node)
      return append(node)
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('downloads merged BOM with project and version in the file name', async () => {
    render(<ExportPanel projectId="p1" projectName="Demo/Board" version={3} hasPcb />)
    await userEvent.click(screen.getByRole('button', { name: '合并 BOM' }))
    expect(api.blob).toHaveBeenCalledWith('/files/projects/p1/exports/bom?merged=true')
    expect(await screen.findByText('已导出：合并 BOM')).toBeTruthy()
    expect(anchors.at(-1)?.download).toBe('Demo_Board-合并 BOM-v3.csv')
  })

  it('downloads the output package and detail BOM from distinct endpoints', async () => {
    render(<ExportPanel projectId="p1" projectName="demo" version={1} hasPcb />)
    await userEvent.click(screen.getByRole('button', { name: 'BOM 明细' }))
    expect(api.blob).toHaveBeenCalledWith('/files/projects/p1/exports/bom?merged=false')
    await userEvent.click(screen.getByRole('button', { name: '输出包' }))
    expect(api.blob).toHaveBeenCalledWith('/files/projects/p1/exports/package')
    expect(anchors.at(-1)?.download).toBe('demo-输出包-v1.zip')
  })

  it('disables PCB-dependent exports when the project has no PCB', () => {
    render(<ExportPanel projectId="p1" projectName="demo" version={1} hasPcb={false} />)
    expect(screen.getByRole('button', { name: '贴片坐标' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: 'Gerber 配置' })).toHaveProperty('disabled', true)
    expect(screen.getByRole('button', { name: '合并 BOM' })).toHaveProperty('disabled', false)
  })

  it('requests pick-and-place data when a PCB is present', async () => {
    render(<ExportPanel projectId="p1" projectName="demo" version={2} hasPcb />)
    await userEvent.click(screen.getByRole('button', { name: '贴片坐标' }))
    expect(api.blob).toHaveBeenCalledWith('/files/projects/p1/exports/pnp')
    expect(anchors.at(-1)?.download).toBe('demo-贴片坐标-v2.csv')
  })

  it('shows a clear error when the download fails', async () => {
    api.blob.mockRejectedValue(new Error('HTTP 500'))
    render(<ExportPanel projectId="p1" projectName="demo" version={1} hasPcb />)
    await userEvent.click(screen.getByRole('button', { name: '网络表' }))
    expect(await screen.findByText('HTTP 500')).toBeTruthy()
  })
})
