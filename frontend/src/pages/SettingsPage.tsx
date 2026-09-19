import { useEffect, useState } from 'react'
import {
  ActionIcon,
  Badge,
  Button,
  Group,
  Modal,
  Paper,
  Select,
  Switch,
  Table,
  Text,
  TextInput,
  Textarea,
} from '@mantine/core'
import { IconPencil, IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'

interface AIModel {
  id: string
  name: string
  provider: string
  baseUrl: string
  apiKey: string
  modelName: string
  isDefault: boolean
  enabled: boolean
  remark: string
}

const PROVIDER_LABEL: Record<string, string> = {
  mock: '演示引擎（内置）',
  openai: 'OpenAI 兼容（OpenAI/Ollama/DeepSeek…）',
  anthropic: 'Anthropic',
}

const emptyModel: AIModel = {
  id: '',
  name: '',
  provider: 'openai',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  modelName: 'gpt-4o-mini',
  isDefault: false,
  enabled: true,
  remark: '',
}

export function SettingsPage() {
  const [models, setModels] = useState<AIModel[]>([])
  const [opened, setOpened] = useState(false)
  const [editing, setEditing] = useState<AIModel>(emptyModel)
  const [error, setError] = useState('')

  const load = () => api.get<AIModel[]>('/ai/models').then(setModels)
  useEffect(() => {
    load()
  }, [])

  const save = async () => {
    setError('')
    try {
      const body = { ...editing }
      if (editing.id) await api.put(`/ai/models/${editing.id}`, body)
      else await api.post('/ai/models', body)
      setOpened(false)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  return (
    <Paper withBorder p="md">
      <Group justify="space-between" mb="md">
        <Text fw={600}>AI 模型配置</Text>
        <Button
          onClick={() => {
            setEditing(emptyModel)
            setOpened(true)
          }}
        >
          新增模型
        </Button>
      </Group>
      <Table.ScrollContainer minWidth={700}>
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>Provider</Table.Th>
              <Table.Th>模型</Table.Th>
              <Table.Th>Base URL</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>
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
                  <Badge color={m.enabled ? 'green' : 'gray'} variant="light">
                    {m.enabled ? '启用' : '停用'}
                  </Badge>
                </Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>
                  <ActionIcon
                    variant="subtle"
                    title="编辑"
                    onClick={() => {
                      setEditing(m)
                      setOpened(true)
                    }}
                  >
                    <IconPencil size={16} />
                  </ActionIcon>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    title="删除"
                    onClick={async () => {
                      await api.delete(`/ai/models/${m.id}`)
                      load()
                    }}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      <Modal opened={opened} onClose={() => setOpened(false)} title={editing.id ? '编辑模型' : '新增模型'} size="lg">
        <TextInput label="名称" value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} mb="sm" />
        <Select
          label="Provider"
          data={Object.entries(PROVIDER_LABEL).map(([v, l]) => ({ value: v, label: l }))}
          value={editing.provider}
          onChange={(v) => {
            const provider = v ?? 'openai'
            setEditing({
              ...editing,
              provider,
              baseUrl: provider === 'anthropic' ? 'https://api.anthropic.com' : provider === 'openai' ? 'https://api.openai.com/v1' : '',
              modelName: provider === 'mock' ? 'mock-1' : editing.modelName,
            })
          }}
          mb="sm"
        />
        {editing.provider !== 'mock' && (
          <>
            <TextInput
              label="Base URL（Ollama 可填 http://localhost:11434/v1）"
              value={editing.baseUrl}
              onChange={(e) => setEditing({ ...editing, baseUrl: e.target.value })}
              mb="sm"
            />
            <TextInput
              label="API Key"
              value={editing.apiKey}
              onChange={(e) => setEditing({ ...editing, apiKey: e.target.value })}
              mb="sm"
            />
            <TextInput label="模型名" value={editing.modelName} onChange={(e) => setEditing({ ...editing, modelName: e.target.value })} mb="sm" />
          </>
        )}
        <Group mb="sm">
          <Switch
            label="设为默认"
            checked={editing.isDefault}
            onChange={(e) => setEditing({ ...editing, isDefault: e.currentTarget.checked })}
          />
          <Switch label="启用" checked={editing.enabled} onChange={(e) => setEditing({ ...editing, enabled: e.currentTarget.checked })} />
        </Group>
        <Textarea label="备注" value={editing.remark} onChange={(e) => setEditing({ ...editing, remark: e.target.value })} mb="sm" />
        {error && (
          <Text c="red" size="sm" mb="sm">
            {error}
          </Text>
        )}
        <Button fullWidth onClick={save}>
          保存
        </Button>
      </Modal>
    </Paper>
  )
}
