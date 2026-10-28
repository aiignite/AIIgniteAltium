import { useCallback, useEffect, useState } from 'react'
import { Alert, Badge, Button, Card, Group, Stack, Table, Text } from '@mantine/core'
import { api } from '../api/client'

interface ReviewRun {
  id: string
  snapshotVersion: number
  status: string
  rulesetVersion: string
  counts: { error?: number; warning?: number; info?: number }
  createdAt: string
}

interface Finding {
  rule: string
  severity: 'error' | 'warning' | 'info'
  title: string
  detail: string
  refs: string[]
  count: number
}

interface ReviewDetail extends ReviewRun {
  findings: Finding[]
}

const SEVERITY: Record<string, { color: string; label: string }> = {
  error: { color: 'red', label: '错误' },
  warning: { color: 'yellow', label: '警告' },
  info: { color: 'blue', label: '提示' },
}

export function ReviewPanel({ projectId, currentVersion }: { projectId: string; currentVersion: number }) {
  const [runs, setRuns] = useState<ReviewRun[]>([])
  const [current, setCurrent] = useState<ReviewDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const loadDetail = useCallback(
    async (runId: string) => {
      const detail = await api.get<ReviewDetail>(`/files/projects/${projectId}/reviews/${runId}`)
      setCurrent(detail)
    },
    [projectId],
  )

  const loadRuns = useCallback(async () => {
    const list = await api.get<ReviewRun[]>(`/files/projects/${projectId}/reviews`)
    setRuns(list)
    return list
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    const init = async () => {
      try {
        const list = await loadRuns()
        if (!cancelled && list.length > 0) await loadDetail(list[0].id)
      } catch {
        if (!cancelled) setRuns([])
      }
    }
    void init()
    return () => {
      cancelled = true
    }
  }, [loadRuns, loadDetail])

  const runReview = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      const detail = await api.post<ReviewDetail>(`/files/projects/${projectId}/reviews`)
      setCurrent(detail)
      await loadRuns()
    } catch (e) {
      setError(e instanceof Error ? e.message : '审查失败')
    } finally {
      setBusy(false)
    }
  }, [projectId, loadRuns])

  return (
    <Card withBorder mt="md" p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <Text fw={600}>设计审查</Text>
          <Text size="xs" c="dimmed">
            基于当前快照 v{currentVersion} 的确定性规则检查，不消耗模型额度
          </Text>
        </Group>
        <Button size="xs" onClick={runReview} loading={busy} disabled={currentVersion === 0}>
          运行审查
        </Button>
      </Group>
      {error && (
        <Alert color="red" mb="sm" p="xs">
          <Text size="sm">{error}</Text>
        </Alert>
      )}
      {runs.length > 1 && (
        <Group gap="xs" mb="sm" wrap="wrap">
          {runs.map((run) => (
            <Button
              key={run.id}
              size="compact-xs"
              variant={current?.id === run.id ? 'filled' : 'light'}
              onClick={() => loadDetail(run.id)}
            >
              v{run.snapshotVersion} · {new Date(run.createdAt).toLocaleString()}
            </Button>
          ))}
        </Group>
      )}
      {!current ? (
        <Text size="sm" c="dimmed">
          还没有审查记录，点击「运行审查」生成。
        </Text>
      ) : current.findings.length === 0 ? (
        <Alert color="green" p="xs">
          <Text size="sm">
            v{current.snapshotVersion} 未发现问题（规则集 {current.rulesetVersion}）
          </Text>
        </Alert>
      ) : (
        <Stack gap="xs">
          <Group gap="xs">
            <Badge color="red" variant="light">
              错误 {current.counts.error ?? 0}
            </Badge>
            <Badge color="yellow" variant="light">
              警告 {current.counts.warning ?? 0}
            </Badge>
            <Badge color="blue" variant="light">
              提示 {current.counts.info ?? 0}
            </Badge>
            <Text size="xs" c="dimmed">
              规则集 {current.rulesetVersion}
            </Text>
          </Group>
          <Table.ScrollContainer minWidth={520}>
            <Table striped withTableBorder>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>级别</Table.Th>
                  <Table.Th>问题</Table.Th>
                  <Table.Th>对象</Table.Th>
                  <Table.Th>说明</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {current.findings.map((f) => (
                  <Table.Tr key={f.rule}>
                    <Table.Td>
                      <Badge color={SEVERITY[f.severity]?.color ?? 'gray'} variant="light">
                        {SEVERITY[f.severity]?.label ?? f.severity}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">{f.title}</Text>
                      <Text size="xs" c="dimmed">
                        {f.rule}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs">{f.refs.join('、')}</Text>
                      {f.count > f.refs.length && (
                        <Text size="xs" c="dimmed">
                          共 {f.count} 项
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs" c="dimmed">
                        {f.detail}
                      </Text>
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
