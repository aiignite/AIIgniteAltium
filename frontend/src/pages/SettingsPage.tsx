import { useEffect, useState } from 'react'
import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  PasswordInput,
  Radio,
  Select,
  Switch,
  Table,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import { IconPencil, IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'
import { useAuth } from '../contexts/AuthContext'

interface AIModel {
  id: string
  name: string
  provider: string
  baseUrl: string
  hasApiKey: boolean
  modelName: string
  isDefault: boolean
  enabled: boolean
  remark: string
}

interface ModelForm {
  id: string
  name: string
  provider: string
  baseUrl: string
  modelName: string
  isDefault: boolean
  enabled: boolean
  remark: string
}

type KeyMode = 'keep' | 'replace' | 'clear'

const PROVIDER_LABEL: Record<string, string> = {
  mock: '演示引擎（内置）',
  openai: 'OpenAI 兼容（OpenAI/Ollama/DeepSeek…）',
  anthropic: 'Anthropic',
}

const emptyForm: ModelForm = {
  id: '',
  name: '',
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  modelName: 'gpt-4o-mini',
  isDefault: false,
  enabled: true,
  remark: '',
}

export function SettingsPage() {
  const { user } = useAuth()
  const isAdmin = user?.isAdmin ?? false
  const [models, setModels] = useState<AIModel[]>([])
  const [opened, setOpened] = useState(false)
  const [form, setForm] = useState<ModelForm>(emptyForm)
  const [keyMode, setKeyMode] = useState<KeyMode>('replace')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () => api.get<AIModel[]>('/ai/models').then(setModels)
  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setError('')
    setForm(emptyForm)
    setKeyMode('replace')
    setApiKey('')
    setOpened(true)
  }

  const openEdit = (m: AIModel) => {
    setError('')
    setForm({
      id: m.id,
      name: m.name,
      provider: m.provider,
      baseUrl: m.baseUrl,
      modelName: m.modelName,
      isDefault: m.isDefault,
      enabled: m.enabled,
      remark: m.remark,
    })
    setKeyMode(m.hasApiKey ? 'keep' : 'replace')
    setApiKey('')
    setOpened(true)
  }

  const save = async () => {
    setError('')
    setBusy(true)
    try {
      const body: Record<string, unknown> = { ...form }
      delete body.id
      if (form.id) {
        if (keyMode === 'replace') body.apiKey = apiKey
        else if (keyMode === 'clear') body.apiKey = ''
      } else if (apiKey) {
        body.apiKey = apiKey
      }
      if (form.id) await api.put(`/ai/models/${form.id}`, body)
      else await api.post('/ai/models', body)
      setOpened(false)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (m: AIModel) => {
    setError('')
    try {
      await api.delete(`/ai/models/${m.id}`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="md">
        <Group gap="xs">
          <Text fw={600}>AI 模型配置</Text>
          {!isAdmin && (
            <Badge size="sm" variant="light" color="gray">
              只读
            </Badge>
          )}
        </Group>
        {isAdmin && <Button onClick={openCreate}>新增模型</Button>}
      </Group>
      {!isAdmin && (
        <Text size="xs" c="dimmed" mb="sm">
          模型配置由管理员维护；你可以查看当前可用的模型。
        </Text>
      )}
      {error && !opened && (
        <Text c="red" size="sm" mb="sm">
          {error}
        </Text>
      )}
      <Table.ScrollContainer minWidth={700}>
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>Provider</Table.Th>
              <Table.Th>模型</Table.Th>
              <Table.Th>Base URL</Table.Th>
              <Table.Th>密钥</Table.Th>
              <Table.Th>状态</Table.Th>
              {isAdmin && <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {models.map((m) => (
              <Table.Tr key={m.id}>
                <Table.Td>
                  {m.name} {m.isDefault && <Badge size="sm" variant="light">默认</Badge>}
                </Table.Td>
                <Table.Td>{PROVIDER_LABEL[m.provider] ?? m.provider}</Table.Td>
                <Table.Td>{m.modelName}</Table.Td>
                <Table.Td>{m.baseUrl || '-'}</Table.Td>
                <Table.Td>
                  {m.provider === 'mock' ? '-' : m.hasApiKey ? '已配置' : '未配置'}
                </Table.Td>
                <Table.Td>
                  <Badge color={m.enabled ? 'green' : 'gray'} variant="light">
                    {m.enabled ? '启用' : '停用'}
                  </Badge>
                </Table.Td>
                {isAdmin && (
                  <Table.Td style={{ textAlign: 'right' }}>
                    <ActionIcon variant="subtle" title="编辑" onClick={() => openEdit(m)}>
                      <IconPencil size={16} />
                    </ActionIcon>
                    <ActionIcon variant="subtle" color="red" title="删除" onClick={() => remove(m)}>
                      <IconTrash size={16} />
                    </ActionIcon>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      <Modal opened={opened} onClose={() => setOpened(false)} title={form.id ? '编辑模型' : '新增模型'} size="lg">
        <TextInput label="名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} mb="sm" />
        <Select
          label="Provider"
          data={Object.entries(PROVIDER_LABEL).map(([v, l]) => ({ value: v, label: l }))}
          value={form.provider}
          onChange={(v) => {
            const provider = v ?? 'openai'
            setForm({
              ...form,
              provider,
              baseUrl: provider === 'anthropic' ? 'https://api.anthropic.com' : provider === 'openai' ? 'https://api.openai.com/v1' : '',
              modelName: provider === 'mock' ? 'mock-1' : form.modelName,
            })
          }}
          mb="sm"
        />
        {form.provider !== 'mock' && (
          <>
            <TextInput
              label="Base URL（Ollama 可填 http://localhost:11434/v1）"
              description="需在服务端 OUTBOUND_ALLOWED_URLS 中明确登记"
              value={form.baseUrl}
              onChange={(e) => setForm({ ...form, baseUrl: e.target.value })}
              mb="sm"
            />
            {!!form.id && (
              <Radio.Group
                value={keyMode}
                onChange={(v) => {
                  setKeyMode(v as KeyMode)
                  if (v !== 'replace') setApiKey('')
                }}
                label="API Key"
                mb="xs"
              >
                <Group gap="md" mt={4}>
                  <Radio value="keep" label="保留现有密钥" />
                  <Radio value="replace" label="替换密钥" />
                  <Radio value="clear" label="清除密钥" />
                </Group>
              </Radio.Group>
            )}
            {(keyMode === 'replace' || !form.id) && (
              <PasswordInput
                label={form.id ? '新 API Key' : 'API Key'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="new-password"
                mb="sm"
              />
            )}
            <TextInput label="模型名" value={form.modelName} onChange={(e) => setForm({ ...form, modelName: e.target.value })} mb="sm" />
          </>
        )}
        <Group mb="sm">
          <Switch
            label="设为默认"
            checked={form.isDefault}
            onChange={(e) => setForm({ ...form, isDefault: e.currentTarget.checked })}
          />
          <Switch label="启用" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.currentTarget.checked })} />
        </Group>
        <Textarea label="备注" value={form.remark} onChange={(e) => setForm({ ...form, remark: e.target.value })} mb="sm" />
        {error && (
          <Alert color="red" mb="sm" p="xs">
            <Text size="sm">{error}</Text>
          </Alert>
        )}
        <Button fullWidth onClick={save} loading={busy}>
          保存
        </Button>
      </Modal>
    </Paper>
  )
}
