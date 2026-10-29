import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, Group, Loader, SimpleGrid, Text } from '@mantine/core'
import { IconRefresh, IconSparkles } from '@tabler/icons-react'
import { api } from '../api/client'
import { DesignDataTabs } from '../components/DesignDataTabs'
import { ExportPanel } from '../components/ExportPanel'
import { ReviewPanel } from '../components/ReviewPanel'
import { VersionDiff } from '../components/VersionDiff'

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
  currentVersion: number
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
  const [reparsing, setReparsing] = useState(false)
  const [actionError, setActionError] = useState('')
  const navigate = useNavigate()

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

  const reparse = async () => {
    if (!projectId || reparsing || project?.status === 'parsing') return
    setReparsing(true)
    setActionError('')
    try {
      await api.post(`/files/projects/${projectId}/reparse`)
      setProject((prev) => (prev ? { ...prev, status: 'parsing' } : prev))
    } catch (e) {
      setActionError(e instanceof Error ? e.message : '重新解析失败')
    } finally {
      setReparsing(false)
    }
  }

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
          {(project.currentVersion ?? 0) > 0 && (
            <Badge color="gray" variant="light">
              快照 v{project.currentVersion}
            </Badge>
          )}
        </Group>
        <Group gap="sm">
          <Text size="xs" c="dimmed">
            {project.fileNames.join('、')} · 解析 {(project.parseDurationMs / 1000).toFixed(1)}s
          </Text>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconRefresh size={14} />}
            onClick={reparse}
            loading={reparsing}
            disabled={project.status === 'parsing'}
          >
            重新解析
          </Button>
          <Button
            size="xs"
            className="ai-gradient"
            style={{ border: 0 }}
            leftSection={<IconSparkles size={14} />}
            onClick={() => navigate(`/?projectId=${project.id}`)}
            disabled={project.status !== 'ready'}
          >
            用 AI 分析
          </Button>
        </Group>
      </Group>
      {actionError && (
        <Text c="red" size="sm" mb="md">
          {actionError}
        </Text>
      )}
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
          <ExportPanel
            projectId={project.id}
            projectName={project.name}
            version={project.currentVersion ?? 0}
            hasPcb={(s.pcbs?.length ?? 0) > 0}
          />
          <VersionDiff
            projectId={project.id}
            currentVersion={project.currentVersion ?? 0}
            onAskAI={(question) => navigate(`/?projectId=${project.id}&ask=${encodeURIComponent(question)}`)}
          />
          <ReviewPanel
            projectId={project.id}
            currentVersion={project.currentVersion ?? 0}
            onAskAI={(question) => navigate(`/?projectId=${project.id}&ask=${encodeURIComponent(question)}`)}
          />
        </>
      )}
    </>
  )
}
