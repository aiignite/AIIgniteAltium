import { useEffect, useMemo, useState } from 'react'
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  FileInput,
  Group,
  Paper,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { IconEye, IconRefresh, IconSearch, IconTrash, IconUpload, IconX } from '@tabler/icons-react'
import { api } from '../api/client'
import type { ProjectSummary } from './WorkbenchPage'

const STATUS: Record<string, { color: string; label: string }> = {
  uploaded: { color: 'gray', label: '待解析' },
  parsing: { color: 'yellow', label: '解析中' },
  ready: { color: 'green', label: '就绪' },
  failed: { color: 'red', label: '失败' },
}

const ALTIUM_EXTENSIONS = ['.prjpcb', '.schdoc', '.pcbdoc', '.schlib', '.pcblib']

function isAltiumFile(file: File) {
  const lower = file.name.toLowerCase()
  return ALTIUM_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [name, setName] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [rowBusy, setRowBusy] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const navigate = useNavigate()

  const load = () => api.get<ProjectSummary[]>('/files/projects').then(setProjects).catch(() => setError('工程列表加载失败'))

  useEffect(() => {
    load()
  }, [])

  const addFiles = (incoming: File[]) => {
    if (incoming.length === 0) return
    const accepted = incoming.filter(isAltiumFile)
    if (accepted.length < incoming.length) setError('已忽略非 Altium 工程文件')
    setFiles((prev) => {
      const merged = [...prev]
      for (const file of accepted) {
        if (!merged.some((x) => x.name === file.name && x.size === file.size)) merged.push(file)
      }
      return merged
    })
  }

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    addFiles(Array.from(e.dataTransfer.files))
  }

  const upload = async () => {
    if (files.length === 0) return
    setBusy(true)
    setError('')
    try {
      const form = new FormData()
      if (name.trim()) form.append('name', name.trim())
      for (const f of files) form.append('files', f)
      const created = await api.postForm<ProjectSummary>('/files/projects', form)
      setFiles([])
      setName('')
      await load()
      navigate(`/projects/${created.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传失败')
    } finally {
      setBusy(false)
    }
  }

  const reparse = async (project: ProjectSummary) => {
    setRowBusy(project.id)
    setError('')
    try {
      await api.post(`/files/projects/${project.id}/reparse`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '重新解析失败')
    } finally {
      setRowBusy(null)
    }
  }

  const remove = async (project: ProjectSummary) => {
    if (!window.confirm(`删除工程「${project.name}」？该操作不可恢复。`)) return
    setRowBusy(project.id)
    setError('')
    try {
      await api.delete(`/files/projects/${project.id}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    } finally {
      setRowBusy(null)
    }
  }

  const poll = projects.some((p) => p.status === 'parsing')
  useEffect(() => {
    if (!poll) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [poll])

  const visibleProjects = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return projects.filter((p) => {
      if (statusFilter !== 'all' && p.status !== statusFilter) return false
      if (!keyword) return true
      return p.name.toLowerCase().includes(keyword) || p.fileNames.some((f) => f.toLowerCase().includes(keyword))
    })
  }, [projects, search, statusFilter])

  const totalSize = files.reduce((sum, f) => sum + f.size, 0)

  return (
    <Paper
      withBorder
      p="md"
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false)
      }}
      onDrop={onDrop}
      style={dragging ? { borderColor: '#3b82f6', borderStyle: 'dashed', background: '#eff6ff' } : undefined}
    >
      <Group mb="md" align="flex-end" gap="sm">
        <TextInput
          label="工程名称"
          placeholder="默认取第一个文件名"
          value={name}
          onChange={(e) => setName(e.target.value)}
          w={260}
        />
        <FileInput
          label="Altium 文件（可多选或拖拽到本页）"
          placeholder="选择文件"
          multiple
          accept={ALTIUM_EXTENSIONS.join(',')}
          value={files}
          onChange={(value) => addFiles(value ?? [])}
          w={360}
          leftSection={<IconUpload size={16} />}
        />
        <Button onClick={upload} loading={busy} disabled={files.length === 0}>
          上传并解析
        </Button>
      </Group>

      {files.length > 0 && (
        <Stack gap={4} mb="md">
          {files.map((file) => (
            <Group key={`${file.name}-${file.size}`} gap="xs" wrap="nowrap">
              <Badge variant="light" color="blue" size="sm">
                {formatSize(file.size)}
              </Badge>
              <Text size="sm" truncate style={{ flex: 1 }}>
                {file.name}
              </Text>
              <ActionIcon
                size="sm"
                variant="subtle"
                color="gray"
                aria-label={`移除 ${file.name}`}
                onClick={() => setFiles((prev) => prev.filter((f) => f !== file))}
              >
                <IconX size={14} />
              </ActionIcon>
            </Group>
          ))}
          <Text size="xs" c="dimmed">
            共 {files.length} 个文件 · {formatSize(totalSize)}
          </Text>
        </Stack>
      )}

      {error && (
        <Text c="red" size="sm" mb="sm">
          {error}
        </Text>
      )}

      <Group mb="sm" gap="sm">
        <TextInput
          placeholder="按工程名或文件名搜索"
          leftSection={<IconSearch size={14} />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          w={280}
          rightSection={
            search ? (
              <ActionIcon size="xs" variant="subtle" color="gray" aria-label="清除搜索" onClick={() => setSearch('')}>
                <IconX size={12} />
              </ActionIcon>
            ) : null
          }
        />
        <Select
          w={140}
          aria-label="按状态筛选"
          value={statusFilter}
          onChange={(value) => setStatusFilter(value ?? 'all')}
          allowDeselect={false}
          data={[
            { value: 'all', label: '全部状态' },
            ...Object.entries(STATUS).map(([value, meta]) => ({ value, label: meta.label })),
          ]}
        />
        <Text size="xs" c="dimmed">
          {visibleProjects.length} / {projects.length} 个工程
        </Text>
      </Group>

      <Table.ScrollContainer minWidth={760}>
        <Table verticalSpacing="xs" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th>元件</Table.Th>
              <Table.Th>网络</Table.Th>
              <Table.Th>BOM</Table.Th>
              <Table.Th>文件</Table.Th>
              <Table.Th>解析耗时</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visibleProjects.map((p) => (
              <Table.Tr key={p.id} onClick={() => navigate(`/projects/${p.id}`)} style={{ cursor: 'pointer' }}>
                <Table.Td>{p.name}</Table.Td>
                <Table.Td>
                  <Badge color={STATUS[p.status]?.color ?? 'gray'} variant="light">
                    {STATUS[p.status]?.label ?? p.status}
                  </Badge>
                  {p.status === 'failed' && (
                    <Tooltip label={p.error}>
                      <Text span c="red" size="xs" ml={6}>
                        查看原因
                      </Text>
                    </Tooltip>
                  )}
                </Table.Td>
                <Table.Td>{p.stats.componentCount ?? '-'}</Table.Td>
                <Table.Td>{p.stats.netCount ?? '-'}</Table.Td>
                <Table.Td>{p.stats.bomRowCount ?? '-'}</Table.Td>
                <Table.Td>{p.fileNames.length}</Table.Td>
                <Table.Td>{p.parseDurationMs ? `${(p.parseDurationMs / 1000).toFixed(1)}s` : '-'}</Table.Td>
                <Table.Td style={{ textAlign: 'right' }} onClick={(e) => e.stopPropagation()}>
                  <ActionIcon
                    variant="subtle"
                    aria-label="查看工程"
                    onClick={() => navigate(`/projects/${p.id}`)}
                    title="查看"
                  >
                    <IconEye size={16} />
                  </ActionIcon>
                  <Tooltip label="重新解析">
                    <ActionIcon
                      variant="subtle"
                      aria-label="重新解析"
                      loading={rowBusy === p.id}
                      disabled={p.status === 'parsing'}
                      onClick={() => reparse(p)}
                    >
                      <IconRefresh size={16} />
                    </ActionIcon>
                  </Tooltip>
                  <Tooltip label="删除">
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      aria-label="删除工程"
                      loading={rowBusy === p.id}
                      onClick={() => remove(p)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            ))}
            {visibleProjects.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text c="dimmed" ta="center" size="sm">
                    {projects.length === 0 ? '还没有工程。上传 Altium 文件开始使用。' : '没有符合筛选条件的工程。'}
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {dragging && (
        <Box
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(239, 246, 255, .75)',
            border: '2px dashed #3b82f6',
            pointerEvents: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 400,
          }}
        >
          <Text fw={600} c="blue">
            松开鼠标上传 Altium 工程文件
          </Text>
        </Box>
      )}
    </Paper>
  )
}
