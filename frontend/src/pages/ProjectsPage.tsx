import { useEffect, useState } from 'react'
import {
  Badge,
  Button,
  FileInput,
  Group,
  Paper,
  Table,
  TextInput,
  Text,
  ActionIcon,
  Tooltip,
} from '@mantine/core'
import { useNavigate } from 'react-router-dom'
import { IconEye, IconRefresh, IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'
import type { ProjectSummary } from './WorkbenchPage'

const STATUS: Record<string, { color: string; label: string }> = {
  uploaded: { color: 'gray', label: '待解析' },
  parsing: { color: 'yellow', label: '解析中' },
  ready: { color: 'green', label: '就绪' },
  failed: { color: 'red', label: '失败' },
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [name, setName] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const load = () => api.get<ProjectSummary[]>('/files/projects').then(setProjects)
  useEffect(() => {
    load()
  }, [])

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

  const poll = projects.some((p) => p.status === 'parsing')
  useEffect(() => {
    if (!poll) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [poll])

  return (
    <Paper withBorder p="md">
      <Group mb="md" align="flex-end" gap="sm">
        <TextInput
          label="工程名称"
          placeholder="默认取第一个文件名"
          value={name}
          onChange={(e) => setName(e.target.value)}
          w={260}
        />
        <FileInput
          label="Altium 文件（可多选：.PrjPcb/.SchDoc/.PcbDoc/.SchLib/.PcbLib）"
          placeholder="选择文件"
          multiple
          value={files}
          onChange={setFiles}
          w={420}
        />
        <Button onClick={upload} loading={busy} disabled={files.length === 0}>
          上传并解析
        </Button>
      </Group>
      {error && (
        <Text c="red" size="sm" mb="sm">
          {error}
        </Text>
      )}
      <Table.ScrollContainer minWidth={700}>
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
            {projects.map((p) => (
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
                    onClick={() => navigate(`/projects/${p.id}`)}
                    title="查看"
                  >
                    <IconEye size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    title="重新解析"
                    onClick={async () => {
                      await api.post(`/files/projects/${p.id}/reparse`)
                      load()
                    }}
                  >
                    <IconRefresh size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    title="删除"
                    onClick={async () => {
                      await api.delete(`/files/projects/${p.id}`)
                      load()
                    }}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
            {projects.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text c="dimmed" ta="center" size="sm">
                    还没有工程。上传 Altium 文件开始使用。
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Paper>
  )
}
