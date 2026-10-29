import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ActionIcon, Badge, Button, Group, Image, Loader, Modal, Pagination, Table, Tabs, Text, TextInput, Tooltip } from '@mantine/core'
import { IconSparkles } from '@tabler/icons-react'
import { api } from '../api/client'
import { safeFilename, svgUrlToPngBlob, triggerDownload } from '../utils/download'

interface SvgItem {
  svgId: string
  kind: string
  title: string
}
interface Paged<T> {
  items: T[]
  total: number
}
interface ComponentRow {
  designator: string
  value: string
  footprint: string
  description: string
  sheet: string
}
interface NetRow {
  name: string
  terminalCount: number
  terminals?: { designator: string; pin: string; pinName: string; pinType: string }[]
}
interface BomRow {
  value: string
  footprint: string
  libraryRef: string
  description: string
  dnp: boolean
  designators: string[]
  quantity: number
}

function SvgView({ projectId, svgId, title }: { projectId: string; svgId: string; title: string }) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [pngBusy, setPngBusy] = useState(false)
  const [pngError, setPngError] = useState('')
  useEffect(() => {
    let revoke: string | null = null
    api
      .blob(`/files/projects/${projectId}/svgs/${svgId}`)
      .then((u) => {
        revoke = u
        setUrl(u)
      })
      .catch((e) => setError(e.message))
    return () => {
      if (revoke) URL.revokeObjectURL(revoke)
    }
  }, [projectId, svgId])

  const baseName = safeFilename(title || svgId)

  const downloadPng = async () => {
    if (!url || pngBusy) return
    setPngBusy(true)
    setPngError('')
    try {
      const blob = await svgUrlToPngBlob(url, 2)
      const pngUrl = URL.createObjectURL(blob)
      triggerDownload(pngUrl, `${baseName}@2x.png`)
      window.setTimeout(() => URL.revokeObjectURL(pngUrl), 1500)
    } catch (e) {
      setPngError(e instanceof Error ? e.message : 'PNG 导出失败')
    } finally {
      setPngBusy(false)
    }
  }

  if (error) return <Text c="red" size="sm">{error}</Text>
  if (!url) return <Loader size="sm" />
  return (
    <>
      <Group justify="flex-end" gap="xs" mb={6}>
        <Button size="compact-xs" variant="light" onClick={() => triggerDownload(url, `${baseName}.svg`)}>
          下载 SVG
        </Button>
        <Button size="compact-xs" variant="light" loading={pngBusy} onClick={downloadPng}>
          下载 PNG（2×）
        </Button>
      </Group>
      {pngError && (
        <Text c="red" size="xs" mb={4}>
          {pngError}
        </Text>
      )}
      <div className="svg-viewer" style={{ maxHeight: 'calc(100vh - 320px)', overflow: 'auto', border: '1px solid var(--mantine-color-gray-3)' }}>
        <Image src={url} alt={title || svgId} />
      </div>
    </>
  )
}

function DataList<T extends object>({
  projectId,
  kind,
  render,
  columns,
  searchPlaceholder,
  askQuestion,
  onAskAI,
}: {
  projectId: string
  kind: 'components' | 'nets' | 'bom'
  render: (row: T) => ReactNode
  columns: string[]
  searchPlaceholder: string
  askQuestion?: (row: T) => string
  onAskAI?: (question: string) => void
}) {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [data, setData] = useState<Paged<T> | null>(null)
  const [detail, setDetail] = useState<T | null>(null)

  const load = () =>
    api
      .get<Paged<T>>(`/files/projects/${projectId}/${kind}${buildQuery()}`)
      .then(setData)

  function buildQuery() {
    const q = new URLSearchParams()
    q.set('page', String(page))
    q.set('page_size', '30')
    if (search) q.set('search', search)
    return `?${q.toString()}`
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, kind, page, search])

  const totalPages = data ? Math.max(1, Math.ceil(data.total / 30)) : 1

  return (
    <>
      <Group mb="xs" justify="space-between">
        <TextInput
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => {
            setPage(1)
            setSearch(e.target.value)
          }}
          w={280}
        />
        {data && (
          <Text size="sm" c="dimmed">
            共 {data.total} 行
          </Text>
        )}
      </Group>
      {data && data.total > 0 && (
        <>
          <Table.ScrollContainer minWidth={500} maxHeight="calc(100vh - 380px)">
            <Table verticalSpacing="xs" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  {columns.map((c) => (
                    <Table.Th key={c}>{c}</Table.Th>
                  ))}
                  {onAskAI && askQuestion && <Table.Th style={{ width: 1 }}>问 AI</Table.Th>}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((row, i) => (
                  <Table.Tr
                    key={i}
                    onClick={() => kind === 'nets' && setDetail(row)}
                    style={kind === 'nets' ? { cursor: 'pointer' } : undefined}
                  >
                    {render(row)}
                    {onAskAI && askQuestion && (
                      <Table.Td style={{ width: 1 }} onClick={(e) => e.stopPropagation()}>
                        <Tooltip label="问 AI">
                          <ActionIcon
                            size="sm"
                            variant="subtle"
                            color="blue"
                            aria-label={`问 AI：${askQuestion(row).slice(0, 24)}`}
                            onClick={() => onAskAI(askQuestion(row))}
                          >
                            <IconSparkles size={14} />
                          </ActionIcon>
                        </Tooltip>
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group justify="space-between" mt="sm">
            <Text size="xs" c="dimmed">{kind === 'nets' ? '点击行查看网络连接明细' : ''}</Text>
            <Pagination total={totalPages} value={page} onChange={setPage} size="sm" />
          </Group>
        </>
      )}
      {data && data.total === 0 && (
        <Text c="dimmed" size="sm" ta="center" mt="lg">
          无数据（该工程可能未包含此类型内容）
        </Text>
      )}
      <Modal opened={detail !== null} onClose={() => setDetail(null)} title={`网络 ${(detail as unknown as NetRow)?.name ?? ''}`}>
        {(detail as unknown as NetRow)?.terminals?.length ? (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>元件</Table.Th>
                <Table.Th>引脚</Table.Th>
                <Table.Th>名称</Table.Th>
                <Table.Th>类型</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {(detail as unknown as NetRow).terminals!.map((t, i) => (
                <Table.Tr key={i}>
                  <Table.Td>{t.designator}</Table.Td>
                  <Table.Td>{t.pin}</Table.Td>
                  <Table.Td>{t.pinName}</Table.Td>
                  <Table.Td>{t.pinType}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text size="sm">该网络无终端明细</Text>
        )}
      </Modal>
    </>
  )
}

export function DesignDataTabs({
  projectId,
  onAskAI,
}: {
  projectId: string
  onAskAI?: (question: string) => void
}) {
  const [svgs, setSvgs] = useState<SvgItem[]>([])
  useEffect(() => {
    api.get<SvgItem[]>(`/files/projects/${projectId}/svgs`).then(setSvgs)
  }, [projectId])
  const sch = svgs.find((s) => s.kind === 'sch')
  const pcb = svgs.find((s) => s.kind === 'pcb')

  return (
    <Tabs defaultValue={sch ? 'sch' : pcb ? 'pcb' : 'components'} keepMounted={false}>
      <Tabs.List mb="sm">
        {sch && <Tabs.Tab value="sch">原理图</Tabs.Tab>}
        {pcb && <Tabs.Tab value="pcb">PCB</Tabs.Tab>}
        <Tabs.Tab value="components">元件</Tabs.Tab>
        <Tabs.Tab value="nets">网络</Tabs.Tab>
        <Tabs.Tab value="bom">BOM</Tabs.Tab>
      </Tabs.List>
      {sch && (
        <Tabs.Panel value="sch">
          <SvgView projectId={projectId} svgId={sch.svgId} title={sch.title} />
        </Tabs.Panel>
      )}
      {pcb && (
        <Tabs.Panel value="pcb">
          <SvgView projectId={projectId} svgId={pcb.svgId} title={pcb.title} />
        </Tabs.Panel>
      )}
      <Tabs.Panel value="components">
        <DataList<ComponentRow>
          projectId={projectId}
          kind="components"
          columns={['位号', '值', '封装', '描述', '图纸']}
          searchPlaceholder="搜索位号/值/封装…"
          askQuestion={(r) =>
            `请分析元件 ${r.designator}（值 ${r.value || '未标注'}，封装 ${r.footprint || '未标注'}）在本设计中的作用与潜在风险。`
          }
          onAskAI={onAskAI}
          render={(r) => (
            <>
              <Table.Td>{r.designator}</Table.Td>
              <Table.Td>{r.value}</Table.Td>
              <Table.Td>{r.footprint}</Table.Td>
              <Table.Td>{r.description}</Table.Td>
              <Table.Td>{r.sheet}</Table.Td>
            </>
          )}
        />
      </Tabs.Panel>
      <Tabs.Panel value="nets">
        <DataList<NetRow>
          projectId={projectId}
          kind="nets"
          columns={['网络名', '连接数']}
          searchPlaceholder="搜索网络名…"
          askQuestion={(r) => `请分析网络 ${r.name}（${r.terminalCount} 个连接点）的连接关系，是否存在悬空或异常？`}
          onAskAI={onAskAI}
          render={(r) => (
            <>
              <Table.Td>{r.name}</Table.Td>
              <Table.Td>
                {r.terminalCount}
                {r.terminalCount <= 1 && (
                  <Badge color="red" variant="light" size="sm" ml={6}>
                    可疑单端
                  </Badge>
                )}
              </Table.Td>
            </>
          )}
        />
      </Tabs.Panel>
      <Tabs.Panel value="bom">
        <DataList<BomRow>
          projectId={projectId}
          kind="bom"
          columns={['值', '封装', '数量', '位号', 'DNP']}
          searchPlaceholder="搜索 BOM…"
          askQuestion={(r) =>
            `请分析 BOM 项 ${r.value || '未标注'}（封装 ${r.footprint || '未标注'}，数量 ${r.quantity}）的选型、采购与替代风险。`
          }
          onAskAI={onAskAI}
          render={(r) => (
            <>
              <Table.Td>{r.value}</Table.Td>
              <Table.Td>{r.footprint}</Table.Td>
              <Table.Td>{r.quantity}</Table.Td>
              <Table.Td>{r.designators.join(', ')}</Table.Td>
              <Table.Td>{r.dnp ? <Badge color="orange" variant="light">DNP</Badge> : ''}</Table.Td>
            </>
          )}
        />
      </Tabs.Panel>
    </Tabs>
  )
}
