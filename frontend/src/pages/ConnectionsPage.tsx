import { useCallback, useEffect, useState } from 'react'
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Drawer,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Paper,
  PasswordInput,
  Stack,
  Table,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { IconEye, IconKey, IconPencil, IconPlugConnected, IconRefresh, IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

interface Connection {
  id: string
  name: string
  baseUrl: string
  hasToken: boolean
  status: string
  lastError: string
  info: Record<string, unknown>
  lastCheckedAt: string | null
  remark: string
  createdAt: string
}

interface UserOption {
  id: string
  email: string
  displayName: string
}

interface ConnectionForm {
  name: string
  baseUrl: string
  remark: string
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

const emptyForm: ConnectionForm = { name: '', baseUrl: '', remark: '' }

export function ConnectionsPage() {
  const { user } = useAuth()
  const isAdmin = user?.isAdmin ?? false
  const [connections, setConnections] = useState<Connection[]>([])
  const [error, setError] = useState('')
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState<ConnectionForm>(emptyForm)
  const [token, setToken] = useState('')
  const [clearToken, setClearToken] = useState(false)
  const [busy, setBusy] = useState('')
  const [panelId, setPanelId] = useState<string | null>(null)
  const [grantsId, setGrantsId] = useState<string | null>(null)

  const load = useCallback(() => api.get<Connection[]>('/altium/connections').then(setConnections), [])
  useEffect(() => {
    load().catch((e) => setError(e instanceof Error ? e.message : '加载连接失败'))
  }, [load])

  const openCreate = () => {
    setError('')
    setEditingId(null)
    setForm({ ...emptyForm, name: 'Altium 工作机', baseUrl: 'http://192.168.1.14:3296' })
    setToken('')
    setClearToken(false)
    setFormOpen(true)
  }

  const openEdit = (c: Connection) => {
    setError('')
    setEditingId(c.id)
    setForm({ name: c.name, baseUrl: c.baseUrl, remark: c.remark })
    setToken('')
    setClearToken(false)
    setFormOpen(true)
  }

  const save = async () => {
    setError('')
    setBusy('save')
    try {
      const body: Record<string, unknown> = { ...form }
      if (editingId) {
        if (clearToken) body.apiToken = ''
        else if (token) body.apiToken = token
        await api.put(`/altium/connections/${editingId}`, body)
      } else {
        if (token) body.apiToken = token
        await api.post('/altium/connections', body)
      }
      setFormOpen(false)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy('')
    }
  }

  const test = async (id: string) => {
    setError('')
    setBusy(id)
    try {
      await api.post(`/altium/connections/${id}/test`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '测试连接失败')
    } finally {
      setBusy('')
    }
  }

  const remove = async (c: Connection) => {
    setError('')
    try {
      await api.delete(`/altium/connections/${c.id}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
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

      {error && <Alert color="red">{error}</Alert>}

      <Paper withBorder p="md">
        <Group justify="space-between" mb="md">
          <Group gap="xs">
            <IconPlugConnected size={18} />
            <Text fw={600}>Altium 网关连接</Text>
            {!isAdmin && (
              <Badge size="sm" variant="light" color="gray">
                仅显示已授权连接
              </Badge>
            )}
          </Group>
          {isAdmin && <Button onClick={openCreate}>新增连接</Button>}
        </Group>
        <Table.ScrollContainer minWidth={840}>
          <Table verticalSpacing="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>名称</Table.Th>
                <Table.Th>Base URL</Table.Th>
                <Table.Th>状态</Table.Th>
                <Table.Th>令牌</Table.Th>
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
                  <Table.Td>{c.hasToken ? '已配置' : '未配置'}</Table.Td>
                  <Table.Td>
                    {c.lastCheckedAt ? new Date(c.lastCheckedAt).toLocaleTimeString('zh-CN') : '-'}
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right' }}>
                    <ActionIcon variant="subtle" title="测试连接" disabled={busy === c.id} onClick={() => test(c.id)}>
                      {busy === c.id ? <Loader size={14} /> : <IconRefresh size={16} />}
                    </ActionIcon>
                    <ActionIcon variant="subtle" title="实时面板" onClick={() => setPanelId(c.id)}>
                      <IconEye size={16} />
                    </ActionIcon>
                    {isAdmin && (
                      <>
                        <ActionIcon variant="subtle" title="编辑" onClick={() => openEdit(c)}>
                          <IconPencil size={16} />
                        </ActionIcon>
                        <ActionIcon variant="subtle" title="授权用户" onClick={() => setGrantsId(c.id)}>
                          <IconKey size={16} />
                        </ActionIcon>
                        <ActionIcon variant="subtle" color="red" title="删除" onClick={() => remove(c)}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
              {connections.length === 0 && (
                <Table.Tr>
                  <Table.Td colSpan={6}>
                    <Text c="dimmed" ta="center" size="sm">
                      {isAdmin
                        ? '暂无连接。新增一条指向 Windows 机的网关地址（默认 http://192.168.1.14:3296）。'
                        : '暂无已授权连接，请联系管理员分配。'}
                    </Text>
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Paper>

      <Modal
        opened={formOpen}
        onClose={() => setFormOpen(false)}
        title={editingId ? '编辑 Altium 网关连接' : '新增 Altium 网关连接'}
      >
        <Stack>
          <TextInput label="名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <TextInput
            label="Base URL（Windows 机 IP + 网关端口）"
            description="需在服务端 OUTBOUND_ALLOWED_URLS 中明确登记"
            value={form.baseUrl}
            onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
          />
          <PasswordInput
            label="网关令牌"
            description={editingId ? '留空表示不修改已保存令牌' : '对应 gateway 侧 GATEWAY_TOKEN，可空'}
            value={token}
            disabled={clearToken}
            onChange={(e) => setToken(e.target.value)}
            autoComplete="new-password"
          />
          {editingId && (
            <Checkbox
              label="清除已保存的网关令牌"
              checked={clearToken}
              onChange={(e) => {
                setClearToken(e.currentTarget.checked)
                if (e.currentTarget.checked) setToken('')
              }}
            />
          )}
          <TextInput label="备注" value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} />
          <Button loading={busy === 'save'} onClick={save}>
            保存
          </Button>
        </Stack>
      </Modal>

      {grantsId && (
        <GrantsModal
          connection={connections.find((c) => c.id === grantsId) ?? null}
          onClose={() => setGrantsId(null)}
        />
      )}

      {panelId && <LivePanel connectionId={panelId} onClose={() => setPanelId(null)} />}
    </Stack>
  )
}

function GrantsModal({ connection, onClose }: { connection: Connection | null; onClose: () => void }) {
  const [users, setUsers] = useState<UserOption[]>([])
  const [selected, setSelected] = useState<string[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!connection) return
    let cancelled = false
    Promise.all([
      api.get<UserOption[]>('/auth/users/options'),
      api.get<{ connectionId: string; userIds: string[] }>(`/altium/connections/${connection.id}/grants`),
    ])
      .then(([options, grants]) => {
        if (cancelled) return
        setUsers(options)
        setSelected(grants.userIds)
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : '加载授权失败'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [connection])

  const save = async () => {
    if (!connection) return
    setSaving(true)
    setError('')
    try {
      await api.put(`/altium/connections/${connection.id}/grants`, { userIds: selected })
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存授权失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal opened onClose={onClose} title={`连接授权 · ${connection?.name ?? ''}`} size="lg">
      <Stack>
        <Text size="xs" c="dimmed">
          仅被授权的用户可以使用该连接发起实时对话、查看摘要或截图；管理员始终可访问。
        </Text>
        {error && <Alert color="red">{error}</Alert>}
        {loading ? (
          <Group justify="center" py="md">
            <Loader size="sm" />
          </Group>
        ) : (
          <MultiSelect
            label="可访问用户"
            placeholder="选择用户"
            searchable
            data={users.map((u) => ({
              value: u.id,
              label: `${u.displayName || u.email}（${u.email}）`,
            }))}
            value={selected}
            onChange={setSelected}
            nothingFoundMessage="没有匹配的用户"
          />
        )}
        <Button loading={saving} disabled={loading} onClick={save}>
          保存授权
        </Button>
      </Stack>
    </Modal>
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
