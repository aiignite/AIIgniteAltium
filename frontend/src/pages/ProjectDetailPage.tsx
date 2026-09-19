import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Badge, Card, Group, Loader, SimpleGrid, Text } from '@mantine/core'
import { api } from '../api/client'
import { DesignDataTabs } from '../components/DesignDataTabs'

export interface ProjectDetail extends ProjectSummaryLike {
  snapshot: Snapshot
}
interface ProjectSummaryLike {
  id: string
  name: string
  status: string
  error: string
  fileNames: string[]
  stats: Record<string, number>
  svgManifest: { svgId: string; kind: string; title: string; file: string }[]
  parseDurationMs: number
  createdAt: string
  updatedAt: string
}
export interface Snapshot {
  schema: string
  project: { name: string; filename: string }
  stats: Record<string, number>
  components: { designator: string; value: string; footprint: string; description: string; sheet: string }[]
  nets: { name: string; terminalCount: number }[]
  bom: { designator: string; value: string; footprint: string; dnp: boolean }[]
  pcbs: {
    name: string
    stats: Record<string, number>
    board: { outlineRectMils: number[] | null; layerStackupCount: number }
  }[]
  warnings: string[]
}

export function ProjectDetailPage() {
  const { projectId } = useParams()
  const [project, setProject] = useState<ProjectDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!projectId) return
    let cancelled = false
    const load = () =>
      api
        .get<ProjectDetail>(`/files/projects/${projectId}`)
        .then((p) => !cancelled && setProject(p))
        .finally(() => !cancelled && setLoading(false))
    load()
    const t = setInterval(() => {
      setProject((prev) => {
        if (prev?.status === 'parsing' || !prev) load()
        return prev
      })
    }, 2500)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [projectId])

  if (loading || !project)
    return (
      <Group justify="center" mt="xl">
        <Loader />
      </Group>
    )

  const s = project.snapshot ?? { stats: {}, components: [], nets: [], bom: [], pcbs: [], warnings: [], project: { name: '', filename: '' } }
  const pcb = s.pcbs?.[0]
  const boardSize =
    pcb?.board?.outlineRectMils && pcb.board.outlineRectMils.length === 4
      ? `${Math.round(pcb.board.outlineRectMils[2] - pcb.board.outlineRectMils[0])}×${Math.round(
          pcb.board.outlineRectMils[3] - pcb.board.outlineRectMils[1],
        )} mil`
      : '-'

  return (
    <>
      <Group mb="md" justify="space-between">
        <Group>
          <Text fz="lg" fw={600}>
            {project.name}
          </Text>
          <Badge color={project.status === 'ready' ? 'green' : project.status === 'failed' ? 'red' : 'yellow'}>
            {project.status}
          </Badge>
        </Group>
        <Text size="xs" c="dimmed">
          {project.fileNames.join('、')} · 解析 {(project.parseDurationMs / 1000).toFixed(1)}s
        </Text>
      </Group>
      {project.status === 'failed' && (
        <Text c="red" size="sm" mb="md">
          {project.error}
        </Text>
      )}
      {project.status === 'ready' && (
        <>
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} mb="md">
            {[
              { label: '元件', value: s.stats.componentCount ?? 0 },
              { label: '网络', value: s.stats.netCount ?? 0 },
              { label: 'BOM 行', value: s.stats.bomRowCount ?? 0 },
              { label: 'PCB 焊盘', value: pcb?.stats.pads ?? 0 },
              { label: 'PCB 走线/过孔', value: `${pcb?.stats.tracks ?? 0}/${pcb?.stats.vias ?? 0}` },
              { label: '板框', value: boardSize },
            ].map((item) => (
              <Card withBorder p="sm" key={item.label}>
                <Text size="xs" c="dimmed">
                  {item.label}
                </Text>
                <Text fw={700} fz="xl">
                  {item.value}
                </Text>
              </Card>
            ))}
          </SimpleGrid>
          {s.warnings?.length > 0 && (
            <Text size="xs" c="yellow" mb="sm">
              解析警告: {s.warnings.join('；')}
            </Text>
          )}
          <DesignDataTabs projectId={project.id} />
        </>
      )}
    </>
  )
}
