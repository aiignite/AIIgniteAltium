import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Divider,
  Drawer,
  Group,
  Loader,
  Modal,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Switch,
  Table,
  Text,
  TextInput,
  Textarea,
  Tooltip,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconBrain,
  IconCheck,
  IconCopy,
  IconDownload,
  IconLayoutGrid,
  IconList,
  IconPencil,
  IconPlugConnected,
  IconPlus,
  IconRefresh,
  IconSearch,
  IconShieldLock,
  IconStarFilled,
  IconTrash,
  IconX,
} from '@tabler/icons-react'
import { api } from '../../api/client'
import type { AIModelItem, ModelPreset, ModelTestResult, ProvidersResponse } from '../../components/ai/types'
import { useAuth } from '../../contexts/AuthContext'

interface FormState {
  id: string
  name: string
  provider: string
  baseUrl: string
  apiKey: string
  clearApiKey: boolean
  modelName: string
  temperature: number
  maxTokens: number
  topP: number
  contextWindow: string
  supportsTools: boolean
  supportsImage: boolean
  speed: string
  cost: string
  isDefault: boolean
  enabled: boolean
  remark: string
  isSystem: boolean
}

const EMPTY_FORM: FormState = {
  id: '',
  name: '',
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  clearApiKey: false,
  modelName: 'gpt-4o-mini',
  temperature: 0.4,
  maxTokens: 4096,
  topP: 1,
  contextWindow: '128K',
  supportsTools: true,
  supportsImage: false,
  speed: 'Fast',
  cost: '$',
  isDefault: false,
  enabled: true,
  remark: '',
  isSystem: false,
}

const SPEED_LABEL: Record<string, string> = { Fast: '快', Medium: '中', Slow: '慢' }

function toForm(model: AIModelItem): FormState {
  return {
    id: model.id,
    name: model.name,
    provider: model.provider,
    baseUrl: model.baseUrl,
    apiKey: '',
    clearApiKey: false,
    modelName: model.modelName,
    temperature: model.temperature,
    maxTokens: model.maxTokens,
    topP: model.topP,
    contextWindow: model.contextWindow,
    supportsTools: model.supportsTools,
    supportsImage: model.supportsImage,
    speed: model.speed,
    cost: model.cost,
    isDefault: model.isDefault,
    enabled: model.enabled,
    remark: model.remark,
    isSystem: model.isSystem,
  }
}

export function ModelsPanel() {
  const { user } = useAuth()
  const isAdmin = user?.isAdmin ?? false
  const [models, setModels] = useState<AIModelItem[]>([])
  const [meta, setMeta] = useState<ProvidersResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [providerFilter, setProviderFilter] = useState<string>('all')
  const [onlyEnabled, setOnlyEnabled] = useState(false)
  const [onlySystem, setOnlySystem] = useState(false)
  const [view, setView] = useState<'grid' | 'list'>('grid')

  const [form, setForm] = useState<FormState | null>(null)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [formTest, setFormTest] = useState<ModelTestResult | null>(null)
  const [testingForm, setTestingForm] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<AIModelItem | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, providers] = await Promise.all([
        api.get<AIModelItem[]>('/ai/models'),
        api.get<ProvidersResponse>('/ai/models/providers'),
      ])
      setModels(list)
      setMeta(providers)
      setError('')
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const providerOptions = useMemo(() => {
    const used = new Set(models.map((m) => m.provider))
    return ['all', ...Array.from(used)]
  }, [models])

  const filtered = useMemo(() => {
    const keyword = search.trim().toLowerCase()
    return models.filter((m) => {
      if (providerFilter !== 'all' && m.provider !== providerFilter) return false
      if (onlyEnabled && !m.enabled) return false
      if (onlySystem && !m.isSystem) return false
      if (!keyword) return true
      return [m.name, m.modelName, m.provider, m.remark].join(' ').toLowerCase().includes(keyword)
    })
  }, [models, search, providerFilter, onlyEnabled, onlySystem])

  const stats = useMemo(
    () => ({
      total: models.length,
      enabled: models.filter((m) => m.enabled).length,
      keyed: models.filter((m) => m.hasKey || m.provider === 'mock').length,
      defaultName: models.find((m) => m.isDefault)?.name ?? '未设置',
    }),
    [models],
  )

  const applyPreset = (preset: ModelPreset) => {
    if (!form) return
    setForm({
      ...form,
      name: form.name || preset.name,
      provider: preset.provider,
      baseUrl: preset.baseUrl,
      modelName: preset.modelName,
      contextWindow: preset.contextWindow,
      supportsTools: preset.supportsTools,
      speed: preset.speed,
      cost: preset.cost,
    })
    setFormTest(null)
  }

  const changeProvider = (provider: string) => {
    if (!form) return
    const info = meta?.providers.find((p) => p.id === provider)
    setForm({
      ...form,
      provider,
      baseUrl: info?.defaultBaseUrl ?? form.baseUrl,
      modelName: info?.defaultModel ?? form.modelName,
      supportsTools: info?.supportsTools ?? form.supportsTools,
    })
    setFormTest(null)
  }

  const save = async () => {
    if (!form) return
    setFormError('')
    setSaving(true)
    try {
      const payload = {
        name: form.name,
        provider: form.provider,
        baseUrl: form.baseUrl,
        apiKey: form.apiKey,
        clearApiKey: form.clearApiKey,
        modelName: form.modelName,
        temperature: form.temperature,
        maxTokens: form.maxTokens,
        topP: form.topP,
        contextWindow: form.contextWindow,
        supportsTools: form.supportsTools,
        supportsImage: form.supportsImage,
        speed: form.speed,
        cost: form.cost,
        isDefault: form.isDefault,
        enabled: form.enabled,
        remark: form.remark,
      }
      if (form.id) await api.put(`/ai/models/${form.id}`, payload)
      else await api.post('/ai/models', payload)
      setForm(null)
      setFormTest(null)
      await load()
    } catch (e) {
      setFormError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const testSaved = async (model: AIModelItem) => {
    setTestingId(model.id)
    try {
      const result = await api.post<ModelTestResult>(`/ai/models/${model.id}/test`)
      setModels((prev) =>
        prev.map((m) =>
          m.id === model.id
            ? {
                ...m,
                testStatus: result.ok ? 'ok' : 'fail',
                testLatencyMs: result.latencyMs,
                lastError: result.ok ? '' : result.error,
                testedAt: new Date().toISOString(),
              }
            : m,
        ),
      )
      setError(result.ok ? '' : `${model.name} 连接失败：${result.error || result.hint}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : '测试失败')
    } finally {
      setTestingId(null)
    }
  }

  const testForm = async () => {
    if (!form) return
    setTestingForm(true)
    setFormTest(null)
    try {
      const result = await api.post<ModelTestResult>('/ai/models/test', {
        id: form.id || undefined,
        provider: form.provider,
        baseUrl: form.baseUrl,
        apiKey: form.apiKey,
        modelName: form.modelName,
      })
      setFormTest(result)
    } catch (e) {
      setFormTest({
        ok: false,
        latencyMs: 0,
        category: 'unknown',
        error: e instanceof Error ? e.message : '测试失败',
        hint: '',
        provider: form.provider,
        model: form.modelName,
      })
    } finally {
      setTestingForm(false)
    }
  }

  const setDefault = async (model: AIModelItem) => {
    await api.post(`/ai/models/${model.id}/default`)
    await load()
  }

  const duplicate = async (model: AIModelItem) => {
    await api.post(`/ai/models/${model.id}/duplicate`)
    await load()
  }

  const remove = async () => {
    if (!deleting) return
    await api.delete(`/ai/models/${deleting.id}`)
    setDeleting(null)
    await load()
  }

  const exportAs = async (format: 'csv' | 'json') => {
    const url = await api.blob(`/ai/models/export?format=${format}`)
    const a = document.createElement('a')
    a.href = url
    a.download = `ai-models-${new Date().toISOString().slice(0, 10)}.${format}`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <Box>
      {/* ===== 顶部横幅 ===== */}
      <Paper
        radius="xl"
        p="lg"
        mb="md"
        style={{
          background: 'linear-gradient(135deg, rgba(249,115,22,.08) 0%, rgba(255,255,255,1) 50%, rgba(234,88,12,.08) 100%)',
          border: '1px solid rgba(254,215,170,.7)',
        }}
      >
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Box>
            <Group gap="xs">
              <Box
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
                }}
              >
                <IconBrain size={20} color="#fff" />
              </Box>
              <Text fw={800} size="lg">
                大模型配置
              </Text>
            </Group>
            <Text size="sm" c="dimmed" mt={6} maw={600}>
              管理模型提供方、采样参数与能力开关。密钥加密存储，列表仅显示掩码；保存前可先测试连接。
            </Text>
            <Group gap="xs" mt="sm">
              <Badge variant="light" color="orange">
                共 {stats.total}
              </Badge>
              <Badge variant="light" color="green">
                启用 {stats.enabled}
              </Badge>
              <Badge variant="light" color="blue">
                已配 Key {stats.keyed}
              </Badge>
              <Badge variant="light" color="yellow" leftSection={<IconStarFilled size={9} />}>
                {stats.defaultName}
              </Badge>
            </Group>
          </Box>
          <Group gap={6} wrap="nowrap">
            <Tooltip label="刷新">
              <ActionIcon variant="light" color="gray" onClick={() => void load()} loading={loading}>
                <IconRefresh size={16} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="导出 CSV">
              <ActionIcon variant="light" color="gray" onClick={() => void exportAs('csv')}>
                <IconDownload size={16} />
              </ActionIcon>
            </Tooltip>
            <Button
              leftSection={<IconPlus size={16} />}
              disabled={!isAdmin}
              title={isAdmin ? undefined : '仅管理员可新增模型'}
              onClick={() => {
                setFormError('')
                setFormTest(null)
                setForm({ ...EMPTY_FORM })
              }}
              style={{ background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)', border: 0 }}
            >
              新增模型
            </Button>
          </Group>
        </Group>
      </Paper>

      {/* ===== 工具条 ===== */}
      <Group mb="md" gap="xs" wrap="wrap">
        <TextInput
          flex={1}
          maw={320}
          size="xs"
          placeholder="搜索名称 / 模型名 / provider / 备注"
          leftSection={<IconSearch size={14} />}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
        />
        <Select
          size="xs"
          w={150}
          data={providerOptions.map((p) => ({ value: p, label: p === 'all' ? '全部 provider' : p }))}
          value={providerFilter}
          onChange={(v) => setProviderFilter(v ?? 'all')}
        />
        <Switch size="xs" label="仅启用" checked={onlyEnabled} onChange={(e) => setOnlyEnabled(e.currentTarget.checked)} />
        <Switch size="xs" label="仅预设" checked={onlySystem} onChange={(e) => setOnlySystem(e.currentTarget.checked)} />
        <Group gap={4} ml="auto">
          <ActionIcon variant={view === 'grid' ? 'light' : 'subtle'} color="orange" onClick={() => setView('grid')}>
            <IconLayoutGrid size={16} />
          </ActionIcon>
          <ActionIcon variant={view === 'list' ? 'light' : 'subtle'} color="orange" onClick={() => setView('list')}>
            <IconList size={16} />
          </ActionIcon>
        </Group>
      </Group>

      {error && (
        <Paper withBorder radius="md" p="xs" mb="sm" style={{ borderColor: '#fecaca', background: '#fef2f2' }}>
          <Group gap={6} wrap="nowrap">
            <IconAlertTriangle size={14} color="#dc2626" />
            <Text size="xs" c="red.7" style={{ flex: 1 }}>
              {error}
            </Text>
            <IconX size={12} style={{ cursor: 'pointer' }} onClick={() => setError('')} />
          </Group>
        </Paper>
      )}

      {loading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
        </Group>
      ) : filtered.length === 0 ? (
        <Paper withBorder radius="lg" p="xl" ta="center">
          <Text size="sm" c="dimmed">
            没有匹配的模型，试着清空筛选或新增一个。
          </Text>
        </Paper>
      ) : view === 'grid' ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {filtered.map((m) => (
            <ModelCard
              key={m.id}
              model={m}
              testing={testingId === m.id}
              readOnly={!isAdmin}
              onEdit={() => {
                setFormError('')
                setFormTest(null)
                setForm(toForm(m))
              }}
              onTest={() => void testSaved(m)}
              onDefault={() => void setDefault(m)}
              onDuplicate={() => void duplicate(m)}
              onDelete={() => setDeleting(m)}
            />
          ))}
        </SimpleGrid>
      ) : (
        <Paper withBorder radius="lg" p={0} style={{ overflow: 'hidden' }}>
          <Table.ScrollContainer minWidth={860}>
            <Table verticalSpacing="xs" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>模型</Table.Th>
                  <Table.Th>Provider</Table.Th>
                  <Table.Th>能力</Table.Th>
                  <Table.Th>参数</Table.Th>
                  <Table.Th>状态</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filtered.map((m) => (
                  <Table.Tr key={m.id}>
                    <Table.Td>
                      <Group gap={6} wrap="nowrap">
                        <Text size="sm" fw={600}>
                          {m.name}
                        </Text>
                        {m.isDefault && <span className="ai-badge ai-badge-default">默认</span>}
                      </Group>
                      <Text size="10px" c="dimmed" style={{ fontFamily: 'monospace' }}>
                        {m.modelName || '—'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="xs">{m.providerName}</Text>
                      <Text size="10px" c="dimmed">
                        {m.provider}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Badge size="xs" variant="light" color={m.supportsTools ? 'teal' : 'gray'}>
                          {m.supportsTools ? '工具' : '无工具'}
                        </Badge>
                        <Badge size="xs" variant="light" color={m.supportsImage ? 'grape' : 'gray'}>
                          {m.supportsImage ? '图像' : '无图像'}
                        </Badge>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Text size="10px" c="dimmed">
                        T={m.temperature} · {m.maxTokens} tok · {m.contextWindow || '—'}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} wrap="nowrap">
                        <StatusDot model={m} />
                        <Text size="10px" c="dimmed">
                          {m.enabled ? '启用' : '停用'}
                          {m.testLatencyMs ? ` · ${m.testLatencyMs}ms` : ''}
                        </Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Group gap={4} justify="flex-end" wrap="nowrap">
                        {isAdmin && (
                          <>
                            <ActionIcon size="sm" variant="subtle" color="blue" onClick={() => {
                              setFormError('')
                              setFormTest(null)
                              setForm(toForm(m))
                            }}>
                              <IconPencil size={14} />
                            </ActionIcon>
                            <ActionIcon size="sm" variant="subtle" color="teal" loading={testingId === m.id} onClick={() => void testSaved(m)}>
                              <IconPlugConnected size={14} />
                            </ActionIcon>
                            <ActionIcon size="sm" variant="subtle" color="yellow" onClick={() => void setDefault(m)}>
                              <IconStarFilled size={14} />
                            </ActionIcon>
                            <ActionIcon size="sm" variant="subtle" color="gray" onClick={() => void duplicate(m)}>
                              <IconCopy size={14} />
                            </ActionIcon>
                            <ActionIcon size="sm" variant="subtle" color="red" onClick={() => setDeleting(m)}>
                              <IconTrash size={14} />
                            </ActionIcon>
                          </>
                        )}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Paper>
      )}

      {/* ===== 表单抽屉 ===== */}
      <Drawer
        opened={form !== null}
        onClose={() => {
          setForm(null)
          setFormTest(null)
        }}
        title={form?.id ? '编辑模型配置' : '新增模型配置'}
        position="right"
        size="md"
      >
        {form && (
          <Box>
            {meta && meta.presets.length > 0 && !form.id && (
              <Box mb="md">
                <Text size="xs" fw={600} mb={6} c="dimmed">
                  快速模板
                </Text>
                <Select
                  size="xs"
                  placeholder="选择预设，自动填充地址与模型名"
                  data={meta.presets.map((p) => ({ value: p.id, label: `${p.name}（${p.provider}）` }))}
                  value={null}
                  onChange={(id) => {
                    const preset = meta.presets.find((p) => p.id === id)
                    if (preset) applyPreset(preset)
                  }}
                  searchable
                  clearable={false}
                />
              </Box>
            )}

            <SimpleGrid cols={2} spacing="sm" mb="sm">
              <TextInput
                label="名称"
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
              />
              <Select
                label="Provider"
                data={(meta?.providers ?? []).map((p) => ({
                  value: p.id,
                  label: `${p.name}${p.requiresApiKey ? '' : '（免 Key）'}`,
                }))}
                value={form.provider}
                onChange={(v) => changeProvider(v ?? 'openai')}
                disabled={form.isSystem}
                allowDeselect={false}
              />
            </SimpleGrid>

            <TextInput
              label="Base URL"
              placeholder="https://api.deepseek.com/v1"
              value={form.baseUrl}
              onChange={(e) => setForm({ ...form, baseUrl: e.currentTarget.value })}
              mb="sm"
            />
            <SimpleGrid cols={2} spacing="sm" mb="sm">
              <TextInput
                label="模型名"
                placeholder="deepseek-chat"
                value={form.modelName}
                onChange={(e) => setForm({ ...form, modelName: e.currentTarget.value })}
              />
              <TextInput
                label="API Key"
                type="password"
                placeholder={form.id ? '留空表示不修改' : 'sk-...'}
                value={form.apiKey}
                onChange={(e) => setForm({ ...form, apiKey: e.currentTarget.value })}
                disabled={form.clearApiKey}
              />
            </SimpleGrid>
            {form.id && (
              <Group gap="xs" mb="sm">
                <Switch
                  size="xs"
                  label="清除已保存的密钥"
                  checked={form.clearApiKey}
                  onChange={(e) => setForm({ ...form, clearApiKey: e.currentTarget.checked, apiKey: '' })}
                />
                <Text size="10px" c="dimmed" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <IconShieldLock size={12} /> 密钥加密存储，不会明文回传
                </Text>
              </Group>
            )}

            <Divider my="sm" label="采样参数" labelPosition="left" />
            <SimpleGrid cols={3} spacing="sm" mb="sm">
              <NumberInput
                label="温度"
                min={0}
                max={2}
                step={0.1}
                decimalScale={2}
                value={form.temperature}
                onChange={(v) => setForm({ ...form, temperature: typeof v === 'number' ? v : 0 })}
              />
              <NumberInput
                label="Max tokens"
                min={1}
                step={256}
                value={form.maxTokens}
                onChange={(v) => setForm({ ...form, maxTokens: typeof v === 'number' ? v : 4096 })}
              />
              <NumberInput
                label="Top P"
                min={0}
                max={1}
                step={0.05}
                decimalScale={2}
                value={form.topP}
                onChange={(v) => setForm({ ...form, topP: typeof v === 'number' ? v : 1 })}
              />
            </SimpleGrid>
            <SimpleGrid cols={3} spacing="sm" mb="sm">
              <TextInput
                label="上下文窗口"
                placeholder="128K"
                value={form.contextWindow}
                onChange={(e) => setForm({ ...form, contextWindow: e.currentTarget.value })}
              />
              <Select
                label="速度"
                data={(meta?.speeds ?? ['Fast', 'Medium', 'Slow']).map((s) => ({ value: s, label: SPEED_LABEL[s] ?? s }))}
                value={form.speed}
                onChange={(v) => setForm({ ...form, speed: v ?? 'Fast' })}
                allowDeselect={false}
              />
              <Select
                label="成本"
                data={(meta?.costs ?? ['$', '$$', '$$$', 'local']).map((c) => ({ value: c, label: c }))}
                value={form.cost}
                onChange={(v) => setForm({ ...form, cost: v ?? '$' })}
                allowDeselect={false}
              />
            </SimpleGrid>

            <Divider my="sm" label="能力与状态" labelPosition="left" />
            <Group mb="sm">
              <Switch
                size="xs"
                label="支持工具调用"
                checked={form.supportsTools}
                onChange={(e) => setForm({ ...form, supportsTools: e.currentTarget.checked })}
              />
              <Switch
                size="xs"
                label="支持图像输入"
                checked={form.supportsImage}
                onChange={(e) => setForm({ ...form, supportsImage: e.currentTarget.checked })}
              />
              <Switch
                size="xs"
                label="启用"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.currentTarget.checked })}
              />
              <Switch
                size="xs"
                label="设为默认"
                checked={form.isDefault}
                onChange={(e) => setForm({ ...form, isDefault: e.currentTarget.checked })}
              />
            </Group>
            <Textarea
              label="备注"
              autosize
              minRows={2}
              maxRows={4}
              value={form.remark}
              onChange={(e) => setForm({ ...form, remark: e.currentTarget.value })}
              mb="sm"
            />

            {formTest && (
              <Paper
                withBorder
                radius="md"
                p="xs"
                mb="sm"
                style={{
                  borderColor: formTest.ok ? '#bbf7d0' : '#fecaca',
                  background: formTest.ok ? '#f0fdf4' : '#fef2f2',
                }}
              >
                <Group gap={6} wrap="nowrap">
                  {formTest.ok ? <IconCheck size={14} color="#16a34a" /> : <IconAlertTriangle size={14} color="#dc2626" />}
                  <Text size="xs" c={formTest.ok ? 'green.7' : 'red.7'} style={{ flex: 1 }}>
                    {formTest.ok
                      ? `连接成功：${formTest.model || form.modelName} · ${formTest.latencyMs}ms`
                      : `${formTest.hint || '连接失败'}：${formTest.error}`}
                  </Text>
                </Group>
              </Paper>
            )}
            {formError && (
              <Text size="xs" c="red.7" mb="sm">
                {formError}
              </Text>
            )}

            <Group gap="xs">
              <Button
                variant="light"
                color="teal"
                leftSection={<IconPlugConnected size={14} />}
                onClick={() => void testForm()}
                loading={testingForm}
              >
                测试连接
              </Button>
              <Button
                style={{ background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)', border: 0 }}
                onClick={() => void save()}
                loading={saving}
                disabled={!form.name.trim()}
              >
                保存
              </Button>
              <Button variant="subtle" color="gray" onClick={() => setForm(null)}>
                取消
              </Button>
            </Group>
          </Box>
        )}
      </Drawer>

      <Modal opened={deleting !== null} onClose={() => setDeleting(null)} title="删除模型配置" size="sm">
        <Text size="sm" mb="md">
          确定删除「{deleting?.name}」吗？该模型将不再出现在选择器中，已产生的对话记录不受影响。
        </Text>
        <Group justify="flex-end" gap="xs">
          <Button variant="subtle" color="gray" onClick={() => setDeleting(null)}>
            取消
          </Button>
          <Button color="red" onClick={() => void remove()}>
            删除
          </Button>
        </Group>
      </Modal>
    </Box>
  )
}

function StatusDot({ model }: { model: AIModelItem }) {
  if (!model.enabled) return <span style={{ width: 8, height: 8, borderRadius: 4, background: '#9ca3af' }} />
  if (model.testStatus === 'ok') return <span style={{ width: 8, height: 8, borderRadius: 4, background: '#22c55e' }} />
  if (model.testStatus === 'fail') return <span style={{ width: 8, height: 8, borderRadius: 4, background: '#ef4444' }} />
  return <span style={{ width: 8, height: 8, borderRadius: 4, background: '#f59e0b' }} />
}

interface ModelCardProps {
  model: AIModelItem
  testing: boolean
  readOnly: boolean
  onEdit: () => void
  onTest: () => void
  onDefault: () => void
  onDuplicate: () => void
  onDelete: () => void
}

function ModelCard({ model, testing, readOnly, onEdit, onTest, onDefault, onDuplicate, onDelete }: ModelCardProps) {
  const blocked = model.provider !== 'mock' && !model.hasKey
  return (
    <Paper
      withBorder
      radius="lg"
      p="md"
      className="ai-card-glow"
      style={{
        borderColor: model.isDefault ? '#fcd34d' : '#e5e7eb',
        opacity: model.enabled ? 1 : 0.6,
      }}
    >
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Box style={{ minWidth: 0 }}>
          <Group gap={6} wrap="nowrap">
            <Text size="sm" fw={700} truncate>
              {model.name}
            </Text>
            {model.isDefault && (
              <span className="ai-badge ai-badge-default">
                <IconStarFilled size={8} style={{ marginRight: 3 }} />
                默认
              </span>
            )}
            {model.isSystem && <span className="ai-badge ai-badge-system">预设</span>}
          </Group>
          <Text size="10px" c="dimmed" style={{ fontFamily: 'monospace' }} mt={2}>
            {model.modelName || '—'}
          </Text>
        </Box>
        <Badge size="xs" variant="light" color="orange">
          {model.provider}
        </Badge>
      </Group>

      <Text size="xs" c="dimmed" mt={6} mih={18} lineClamp={2}>
        {model.remark || model.providerName}
      </Text>

      <SimpleGrid cols={3} spacing={6} mt={8}>
        <MiniStat label="速度" value={SPEED_LABEL[model.speed] ?? model.speed ?? '—'} />
        <MiniStat label="成本" value={model.cost || '—'} />
        <MiniStat label="上下文" value={model.contextWindow || '—'} />
      </SimpleGrid>

      <Group gap={4} mt={8}>
        <Badge size="xs" variant="light" color={model.supportsTools ? 'teal' : 'gray'}>
          {model.supportsTools ? '工具' : '无工具'}
        </Badge>
        <Badge size="xs" variant="light" color={model.supportsImage ? 'grape' : 'gray'}>
          {model.supportsImage ? '图像' : '无图像'}
        </Badge>
        <Badge size="xs" variant="light" color={blocked ? 'red' : model.hasKey ? 'blue' : 'gray'}>
          {model.provider === 'mock' ? '免 Key' : blocked ? '未配 Key' : model.keyHint || '已配 Key'}
        </Badge>
        <Group gap={4} ml="auto" wrap="nowrap">
          <StatusDot model={model} />
          <Text size="10px" c="dimmed">
            {!model.enabled ? '停用' : model.testStatus === 'ok' ? `${model.testLatencyMs}ms` : model.testStatus === 'fail' ? '失败' : '未测'}
          </Text>
        </Group>
      </Group>

      <Group justify="flex-end" gap={4} mt="sm">
        {!readOnly && (
          <>
            <Tooltip label="编辑">
              <ActionIcon size="sm" variant="light" color="blue" onClick={onEdit}>
                <IconPencil size={13} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="测试连接">
              <ActionIcon size="sm" variant="light" color="teal" loading={testing} onClick={onTest}>
                <IconPlugConnected size={13} />
              </ActionIcon>
            </Tooltip>
            {!model.isDefault && (
              <Tooltip label="设为默认">
                <ActionIcon size="sm" variant="light" color="yellow" onClick={onDefault}>
                  <IconStarFilled size={13} />
                </ActionIcon>
              </Tooltip>
            )}
            <Tooltip label="复制">
              <ActionIcon size="sm" variant="light" color="gray" onClick={onDuplicate}>
                <IconCopy size={13} />
              </ActionIcon>
            </Tooltip>
            {!model.isSystem && (
              <Tooltip label="删除">
                <ActionIcon size="sm" variant="light" color="red" onClick={onDelete}>
                  <IconTrash size={13} />
                </ActionIcon>
              </Tooltip>
            )}
          </>
        )}
      </Group>
    </Paper>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <Box p={6} style={{ background: '#f9fafb', borderRadius: 8 }}>
      <Text size="9px" c="dimmed">
        {label}
      </Text>
      <Text size="11px" fw={600} truncate>
        {value}
      </Text>
    </Box>
  )
}
