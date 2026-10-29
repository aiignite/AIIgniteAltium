import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'

describe('api.blob', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('surfaces backend detail for failed downloads', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: '制造文件生成失败，请稍后重试或重新解析工程' }), {
          status: 500,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    )
    await expect(api.blob('/files/projects/p1/exports/pnp')).rejects.toMatchObject({
      status: 500,
      message: '制造文件生成失败，请稍后重试或重新解析工程',
    })
    await expect(api.blob('/files/projects/p1/exports/pnp')).rejects.toBeInstanceOf(ApiError)
  })
})
