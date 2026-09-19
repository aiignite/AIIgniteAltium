import { useEffect, useState } from 'react'
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Drawer,
  Group,
  Loader,
  Modal,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { IconEye, IconPlugConnected, IconRefresh, IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'

interface Connection {
  id: string
  name: string
  baseUrl: string
  status: string
  lastError: string
  info: Record<string, unknown>
  lastCheckedAt: string | null
  remark: string
  createdAt: string
}

interface LiveSummary {
  ok: boolean
  project?: string
  document?: { kind?: string; name?: string }
  pcbStats?: Record<string, number>
  board?: { widthMils?: number; heightMils?: number; layers?: number }
  schematic?: { componentCount?: number; netCount?: number }
  errors?: string[]
}

const STATUS: Record<string, { color: string; label: string }> = {
  connected: { color: 'green', label: '已连接' },
  unreachable: { color: 'red', label: '不可达' },
  disabled: { color: 'gray', label: '已停用' },
}

export function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [addOpened, setAddOpened] = useState(false)
  const [name, setName] = useState('Altium 工作机')
  const [baseUrl, setBaseUrl] = useState('http://192.168.1.14:3296')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState('')
  const [panelId, setPanelId] = useState<string | null>(null)

  const load = () => api.get<Connection[]>('/altium/connections').then(setConnections)
  useEffect(() => {
    load()
  }, [])

  const add = async () => {
    setBusy('add')
    try {
      await api.post('/altium/connections', { name, baseUrl, apiToken: token })
      setAddOpened(false)
      load()
    } finally {
      setBusy('')
    }
  }

  const test = async (id: string) => {
    setBusy(id)
    try {
      await api.post(`/altium/connections/${id}/test`)
      await load()
    } finally {
      setBusy('')
    }
  }

  return (
    <Stack gap="md">
      <Alert title="实时连接部署说明" color="indigo">
        网关（altium-gateway）需要部署在<b>装有 Altium Designer 的 Windows 机器</b>上：
        ① 安装 Python 3.10+；② 运行 <code>pip install altium-gateway</code>（或使用 deploy/install.bat）；
        ③ 启动 <code>altium-gateway</code>（默认端口 3296）；④ 在 Altium 中运行 AIDriveBridge 驻留脚本。
        详见仓库 <code>gateway/README.md</code>。网关支持 mock 模式，可先在任意机器联调。
      </Alert>

      <Paper withBorder p="md">
        <Group justify="space-between" mb="md">
          <Group gap="xs">
            <IconPlugConnected size={18} />
            <Text fw={600}>Altium 网关连接</Text>
          </Group>
          <Button onClick={() => setAddOpened(true)}>新增连接</Button>
        </Group>
        <Table.ScrollContainer minWidth={720}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>名称</Table.Th>
                <Table.Th>Base URL</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>最近检查</Table.Th>
                <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {connections.map((c) => (
                <Table.Tr key={c.id}>
                  <Table.Td>
                    {c.name}
                    {c.lastError && (
                      <Tooltip label={c.lastError}>
                        <Text span c="red" size="xs" ml={6}>
                          ⚠
                        </Text>
                      </Tooltip>
                    )}
                  </Table.Td>
                  <Table.Td>{c.baseUrl}</Table.Td>
                  <Table.Td>
                    <Badge color={STATUS[c.status]?.color ?? 'gray'} variant="light">
                      {STATUS[c.status]?.label ?? c.status}
                    </Badge>
                    {c.info?.altiumOnline === true && (
                      <Badge color="teal" variant="light" size="sm" ml={6}>
                        Altium 在线
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {c.lastCheckedAt ? new Date(c.lastCheckedAt).toLocaleTimeString('zh-CN') : '-'}
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <ActionIcon
                      variant="subtle"
                      title="测试连接"
                      disabled={busy === c.id}
                      onClick={() => test(c.id)}
                    >
                      {busy === c.id ? <Loader size={14} /> : <IconRefresh size={16} />}
                    </ActionIcon>
                    <ActionIcon variant="subtle" title="实时面板" onClick={() => setPanelId(c.id)}>
                      <IconEye size={16} />
                    </ActionIcon>
                    <ActionIcon
                      variant="subtle"
                      color="red"
                      title="删除"
                      onClick={async () => {
                        await api.delete(`/altium/connections/${c.id}`)
                        load()
                      }}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Table.Td>
                </Table.Tr>
              ))}
              {connections.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={5}>
                    <Text c="dimmed" ta="center" size="sm">
                      暂无连接。新增一条指向 Windows 机的网关地址（默认 http://192.168.1.14:3296）。
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      <Modal opened={addOpened} onClose={() => setAddOpened(false)} title="新增 Altium 网关连接">
        <Stack>
          <TextInput label="名称" value={name} onChange={(e) => setName(e.target.value)} />
          <TextInput
            label="Base URL（Windows 机 IP + 网关端口）"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
          <TextInput
            label="网关令牌（gateway 侧 GATEWAY_TOKEN，可空）"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <Button loading={busy === 'add'} onClick={add}>
            保存
          </Button>
        </Stack>
      </Modal>

      {panelId && <LivePanel connectionId={panelId} onClose={() => setPanelId(null)} />}
    </Stack>
  )
}

function LivePanel({ connectionId, onClose }: { connectionId: string; onClose: () => void }) {
  const [summary, setSummary] = useState<LiveSummary | null>(null)
  const [screenshot, setScreenshot] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const s = await api.get<LiveSummary>(`/altium/connections/${connectionId}/live/summary`)
      setSummary(s)
      const shot = await api.blob(`/altium/connections/${connectionId}/screenshot`)
      setScreenshot((prev) => {
        if (prev) URL.revokeObjectURL(prev)
        return shot
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : '实时面板加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId])

  return (
    <Drawer opened position="right" onClose={onClose} title="Altium 实时面板" size="xl">
      {error && (
        <Alert color="red" mb="md" title="无法连接">
          {error}
        </Alert>
      )}
      {loading && !summary && (
        <Group justify="center" mt="xl">
          <Loader />
        </Group>
      )}
      {summary && (
        <Stack gap="sm">
          <Group justify="space-between">
            <Text fw={600}>{summary.project || '（未打开工程）'}</Text>
            <Button size="compact-sm" variant="light" onClick={load}>
              刷新
            </Button>
          </Group>
          {summary.document?.kind && (
            <Text size="sm" c="dimmed">
              活动文档：[{summary.document.kind}] {summary.document.name}
            </Text>
          )}
          {summary.pcbStats && (
            <Group grow>
              {[
                ['元件', summary.pcbStats.components],
                ['焊盘', summary.pcbStats.pads],
                ['走线', summary.pcbStats.tracks],
                ['过孔', summary.pcbStats.vias],
                ['网络', summary.pcbStats.nets],
              ].map(([label, value]) => (
                <Card withBorder p="xs" key={label as string}>
                  <Text size="xs" c="dimmed">
                    {label}
                  </Text>
                  <Text fw={700}>{String(value ?? '-')}</Text>
                </Card>
              ))}
            </Group>
          )}
          {summary.schematic && (
            <Text size="sm">
              原理图：{summary.schematic.componentCount ?? 0} 元件 / {summary.schematic.netCount ?? 0} 网络
            </Text>
          )}
          {screenshot && (
            <div className="svg-viewer" style={{ border: '1px solid var(--mantine-color-gray-3)' }}>
              <img src={screenshot} alt="Altium 截图" style={{ width: '100%' }} />
            </div>
          )}
        </Stack>
      )}
    </Drawer>
  )
}
