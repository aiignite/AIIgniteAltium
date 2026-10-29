import { useEffect, useMemo, useState } from 'react'
import { Alert, Badge, Button, Card, Group, Loader, Select, Stack, Table, Text } from '@mantine/core'
import { IconArrowRight, IconSparkles } from '@tabler/icons-react'
import { api } from '../api/client'

interface VersionRow {
  version: number
  createdAt: string
}

interface FieldChange {
  from: unknown
  to: unknown
}

interface NamedEntry {
  designator: string
  value: string
  footprint: string
}

interface ComponentChange {
  designator: string
  fields: Record<string, FieldChange>
}

interface NetEntry {
  name: string
  terminalCount: number
}

interface NetChange {
  name: string
  terminalCount?: FieldChange
  terminalsAdded: string[]
  terminalsRemoved: string[]
}

interface BoardChange {
  name: string
  fields: Record<string, FieldChange>
}

interface BoardEntry {
  name: string
  values?: Record<string, unknown>
}

export interface DiffData {
  fromVersion: number
  toVersion: number
  summary: Record<string, number>
  components: { added: NamedEntry[]; removed: NamedEntry[]; changed: ComponentChange[] }
  bom: { added: NamedEntry[]; removed: NamedEntry[]; changed: ComponentChange[] }
  nets: { added: NetEntry[]; removed: NetEntry[]; changed: NetChange[] }
  boards: { added: BoardEntry[]; removed: BoardEntry[]; changed: BoardChange[] }
}

const FIELD_LABELS: Record<string, string> = {
  value: '值',
  footprint: '封装',
  description: '描述',
  sheet: '图纸',
  libraryRef: '库引用',
  dnp: 'DNP',
  widthMil: '宽(mil)',
  heightMil: '高(mil)',
  layerStackupCount: '层数',
  pads: '焊盘',
  tracks: '走线',
  vias: '过孔',
}

function show(value: unknown): string {
  if (value === null || value === undefined || value === '') return '空'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

function fieldText(fields: Record<string, FieldChange>, limit = 4): string {
  const parts = Object.entries(fields)
    .slice(0, limit)
    .map(([key, change]) => `${FIELD_LABELS[key] ?? key} ${show(change.from)} → ${show(change.to)}`)
  const rest = Object.keys(fields).length - parts.length
  return parts.join('，') + (rest > 0 ? `，另 ${rest} 项` : '')
}

function entryText(entry: NamedEntry): string {
  return [entry.designator, entry.value, entry.footprint].filter(Boolean).join(' · ')
}

function diffLines(diff: DiffData): string[] {
  const lines: string[] = []
  const group = (label: string, name: (e: NamedEntry) => string, section: DiffData['components']) => {
    if (section.added.length) lines.push(`- ${label}新增：${section.added.slice(0, 10).map(name).join('、')}`)
    if (section.removed.length) lines.push(`- ${label}移除：${section.removed.slice(0, 10).map(name).join('、')}`)
    if (section.changed.length) {
      lines.push(
        `- ${label}变更：${section.changed.slice(0, 10).map((c) => `${c.designator}（${fieldText(c.fields, 2)}）`).join('；')}`,
      )
    }
  }
  group('元件', entryText, diff.components)
  group('BOM', entryText, diff.bom)
  if (diff.nets.added.length) lines.push(`- 网络新增：${diff.nets.added.slice(0, 10).map((n) => `${n.name}（${n.terminalCount} 端子）`).join('、')}`)
  if (diff.nets.removed.length) lines.push(`- 网络移除：${diff.nets.removed.slice(0, 10).map((n) => n.name).join('、')}`)
  if (diff.nets.changed.length) {
    lines.push(
      `- 网络变更：${diff.nets.changed
        .slice(0, 10)
        .map((n) => {
          const count = n.terminalCount ? `端子 ${show(n.terminalCount.from)}→${show(n.terminalCount.to)}` : '连接变化'
          const terminals = [
            n.terminalsAdded.length ? `新增 ${n.terminalsAdded.slice(0, 4).join('、')}` : '',
            n.terminalsRemoved.length ? `移除 ${n.terminalsRemoved.slice(0, 4).join('、')}` : '',
          ].filter(Boolean)
          return `${n.name}（${[count, ...terminals].join('，')}）`
        })
        .join('；')}`,
    )
  }
  if (diff.boards.added.length) lines.push(`- PCB 新增：${diff.boards.added.slice(0, 10).map((b) => b.name).join('、')}`)
  if (diff.boards.removed.length) lines.push(`- PCB 移除：${diff.boards.removed.slice(0, 10).map((b) => b.name).join('、')}`)
  if (diff.boards.changed.length) {
    lines.push(
      `- PCB 变更：${diff.boards.changed.slice(0, 10).map((b) => `${b.name}（${fieldText(b.fields, 2)}）`).join('；')}`,
    )
  }
  return lines
}

function hasChanges(diff: DiffData): boolean {
  return Object.values(diff.summary).some((value) => value > 0)
}

export function VersionDiff({
  projectId,
  currentVersion,
  onAskAI,
}: {
  projectId: string
  currentVersion: number
  onAskAI?: (question: string) => void
}) {
  const [versions, setVersions] = useState<VersionRow[]>([])
  const [fromVersion, setFromVersion] = useState<number | null>(null)
  const [toVersion, setToVersion] = useState<number | null>(null)
  const [diff, setDiff] = useState<DiffData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (currentVersion < 2) return
    let cancelled = false
    api
      .get<VersionRow[]>(`/files/projects/${projectId}/versions`)
      .then((rows) => {
        if (cancelled) return
        setVersions(rows)
        const latest = rows.find((r) => r.version === currentVersion)?.version ?? rows[0]?.version
        if (latest && latest > 1) {
          setToVersion(latest)
          setFromVersion(latest - 1)
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : '版本加载失败'))
    return () => {
      cancelled = true
    }
  }, [projectId, currentVersion])

  useEffect(() => {
    if (fromVersion === null || toVersion === null) return
    let cancelled = false
    api
      .get<DiffData>(`/files/projects/${projectId}/diff?from=${fromVersion}&to=${toVersion}`)
      .then((data) => !cancelled && setDiff(data))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : '版本对比失败'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [projectId, fromVersion, toVersion])

  const options = useMemo(
    () => versions.map((v) => ({ value: String(v.version), label: `v${v.version}` })),
    [versions],
  )

  if (currentVersion < 2) return null

  const lines = diff ? diffLines(diff) : []
  const question =
    diff && lines.length
      ? `请解读工程从快照 v${diff.fromVersion} 到 v${diff.toVersion} 的设计变更，评估潜在风险并给出验证与整改建议：\n${lines.join('\n')}`
      : ''

  return (
    <Card withBorder mt="md" p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <Text fw={600}>版本对比</Text>
          <Text size="xs" c="dimmed">
            对比两次离线解析的设计数据变化
          </Text>
        </Group>
        {onAskAI && diff && hasChanges(diff) && (
          <Button
            size="xs"
            variant="light"
            leftSection={<IconSparkles size={14} />}
            onClick={() => onAskAI(question)}
          >
            让 AI 解读变更
          </Button>
        )}
      </Group>
      <Group gap="xs" mb="sm">
        <Select
          aria-label="起始版本"
          size="xs"
          w={110}
          data={options}
          value={fromVersion === null ? null : String(fromVersion)}
          onChange={(value) => setFromVersion(value ? Number(value) : null)}
          allowDeselect={false}
        />
        <IconArrowRight size={14} />
        <Select
          aria-label="目标版本"
          size="xs"
          w={110}
          data={options}
          value={toVersion === null ? null : String(toVersion)}
          onChange={(value) => setToVersion(value ? Number(value) : null)}
          allowDeselect={false}
        />
        {diff && (
          <Text size="xs" c="dimmed">
            v{diff.fromVersion} → v{diff.toVersion}
          </Text>
        )}
      </Group>
      {error && (
        <Alert color="red" p="xs">
          <Text size="sm">{error}</Text>
        </Alert>
      )}
      {loading && !diff && <Loader size="sm" />}
      {diff && !hasChanges(diff) && (
        <Alert color="gray" p="xs">
          <Text size="sm">
            v{diff.fromVersion} 与 v{diff.toVersion} 之间没有检测到设计数据变化。
          </Text>
        </Alert>
      )}
      {diff && hasChanges(diff) && (
        <Stack gap="sm">
          <Group gap="xs" wrap="wrap">
            {[
              ['元件', diff.components],
              ['网络', diff.nets],
              ['BOM', diff.bom],
              ['PCB', diff.boards],
            ].map(([label, section]) => {
              const typed = section as { added: unknown[]; removed: unknown[]; changed: unknown[] }
              const total = typed.added.length + typed.removed.length + typed.changed.length
              if (!total) return null
              return (
                <Badge key={label as string} color="blue" variant="light">
                  {label as string} +{typed.added.length} / -{typed.removed.length} / ~{typed.changed.length}
                </Badge>
              )
            })}
          </Group>
          <Table.ScrollContainer minWidth={560}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th style={{ width: 90 }}>类别</Table.Th>
                  <Table.Th>变化</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {diff.components.added.map((c) => (
                  <Table.Tr key={`c+${c.designator}`}>
                    <Table.Td>元件</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="green" variant="light">新增</Badge> {entryText(c)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.components.removed.map((c) => (
                  <Table.Tr key={`c-${c.designator}`}>
                    <Table.Td>元件</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="red" variant="light">移除</Badge> {entryText(c)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.components.changed.map((c) => (
                  <Table.Tr key={`c~${c.designator}`}>
                    <Table.Td>元件</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="yellow" variant="light">变更</Badge> {c.designator}：{fieldText(c.fields)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.nets.added.map((n) => (
                  <Table.Tr key={`n+${n.name}`}>
                    <Table.Td>网络</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="green" variant="light">新增</Badge> {n.name}（{n.terminalCount} 端子）
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.nets.removed.map((n) => (
                  <Table.Tr key={`n-${n.name}`}>
                    <Table.Td>网络</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="red" variant="light">移除</Badge> {n.name}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.nets.changed.map((n) => (
                  <Table.Tr key={`n~${n.name}`}>
                    <Table.Td>网络</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="yellow" variant="light">变更</Badge> {n.name}
                      {n.terminalCount && `：端子 ${show(n.terminalCount.from)} → ${show(n.terminalCount.to)}`}
                      {n.terminalsAdded.length > 0 && `，新增 ${n.terminalsAdded.join('、')}`}
                      {n.terminalsRemoved.length > 0 && `，移除 ${n.terminalsRemoved.join('、')}`}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.bom.added.map((b) => (
                  <Table.Tr key={`b+${b.designator}`}>
                    <Table.Td>BOM</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="green" variant="light">新增</Badge> {entryText(b)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.bom.removed.map((b) => (
                  <Table.Tr key={`b-${b.designator}`}>
                    <Table.Td>BOM</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="red" variant="light">移除</Badge> {entryText(b)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.bom.changed.map((b) => (
                  <Table.Tr key={`b~${b.designator}`}>
                    <Table.Td>BOM</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="yellow" variant="light">变更</Badge> {b.designator}：{fieldText(b.fields)}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.boards.added.map((b) => (
                  <Table.Tr key={`p+${b.name}`}>
                    <Table.Td>PCB</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="green" variant="light">新增</Badge> {b.name}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.boards.removed.map((b) => (
                  <Table.Tr key={`p-${b.name}`}>
                    <Table.Td>PCB</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="red" variant="light">移除</Badge> {b.name}
                    </Table.Td>
                  </Table.Tr>
                ))}
                {diff.boards.changed.map((b) => (
                  <Table.Tr key={`p~${b.name}`}>
                    <Table.Td>PCB</Table.Td>
                    <Table.Td>
                      <Badge size="xs" color="yellow" variant="light">变更</Badge> {b.name}：{fieldText(b.fields)}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      )}
    </Card>
  )
}
