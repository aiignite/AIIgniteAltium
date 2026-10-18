import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Box,
  Button,
  Chip,
  ChipGroup,
  Group,
  Loader,
  Modal,
  NumberInput,
  Paper,
  ScrollArea,
  SimpleGrid,
  Switch,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconBrain,
  IconCopy,
  IconFileCode,
  IconPencil,
  IconPlus,
  IconStarFilled,
  IconTrash,
} from '@tabler/icons-react'
import { api } from '../../api/client'
import { AVATAR_OPTIONS } from '../../components/ai/avatarIcons'
import { AssistantAvatar } from '../../components/ai/AssistantAvatar'
import { ModelPicker } from '../../components/ai/ModelPicker'
import { ToolChipSelect, type ToolInfo } from '../../components/ai/ToolChipSelect'
import type { AIModelItem } from '../../components/ai/types'

interface AssistantItem {
  id: string
  name: string
  description: string
  avatar: string
  category: string
  systemPrompt: string
  greeting: string
  skillCodes: string[]
  toolCodes: string[]
  modelConfigId: string | null
  temperature: number | null
  maxTokens: number | null
  isDefault: boolean
  isSystem: boolean
  enabled: boolean
  usageCount: number
  sortOrder: number
  createdAt: string
}

interface SkillItem {
  id: string
  code: string
  name: string
  icon: string
  enabled: boolean
}

interface FormState {
  id: string
  name: string
  description: string
  avatar: string
  category: string
  systemPrompt: string
  greeting: string
  skillCodes: string[]
  toolCodes: string[]
  modelConfigId: string | null
  temperature: number | ''
  maxTokens: number | ''
  isDefault: boolean
  enabled: boolean
}

const EMPTY: FormState = {
  id: '',
  name: '',
  description: '',
  avatar: 'bot',
  category: 'General',
  systemPrompt: '',
  greeting: '',
  skillCodes: [],
  toolCodes: [],
  modelConfigId: null,
  temperature: '',
  maxTokens: '',
  isDefault: false,
  enabled: true,
}

export function AssistantsPanel() {
  const [assistants, setAssistants] = useState<AssistantItem[]>([])
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [models, setModels] = useState<AIModelItem[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState<FormState | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [a, s, m, t] = await Promise.all([
        api.get<AssistantItem[]>('/ai/assistants'),
        api.get<SkillItem[]>('/ai/skills'),
        api.get<AIModelItem[]>('/ai/models'),
        api.get<ToolInfo[]>('/ai/tools/registry').catch(() => []),
      ])
      setAssistants(a)
      setSkills(s)
      setModels(m)
      setTools(t)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const skillName = useCallback(
    (code: string) => skills.find((s) => s.code === code)?.name ?? code,
    [skills],
  )

  const stats = useMemo(
    () => ({
      system: assistants.filter((a) => a.isSystem).length,
      custom: assistants.filter((a) => !a.isSystem).length,
      enabled: assistants.filter((a) => a.enabled).length,
    }),
    [assistants],
  )

  const save = async () => {
    if (!form) return
    setError('')
    setSaving(true)
    try {
      const payload = {
        name: form.name,
        description: form.description,
        avatar: form.avatar,
        category: form.category,
        systemPrompt: form.systemPrompt,
        greeting: form.greeting,
        skillCodes: form.skillCodes,
        toolCodes: form.toolCodes,
        modelConfigId: form.modelConfigId,
        temperature: form.temperature === '' ? null : form.temperature,
        maxTokens: form.maxTokens === '' ? null : form.maxTokens,
        isDefault: form.isDefault,
        enabled: form.enabled,
      }
      if (form.id) await api.put(`/ai/assistants/${form.id}`, payload)
      else await api.post('/ai/assistants', payload)
      setForm(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const showPreview = async (id: string) => {
    setPreviewLoading(true)
    try {
      const data = await api.post<{ systemPrompt: string }>(`/ai/assistants/${id}/prompt-preview`)
      setPreview(data.systemPrompt)
    } catch (e) {
      setPreview(e instanceof Error ? e.message : '预览失败')
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <Box>
      <Paper
        radius="xl"
        p="lg"
        mb="md"
        style={{
          background: 'linear-gradient(135deg, rgba(16,185,129,.08) 0%, rgba(255,255,255,1) 50%, rgba(13,148,136,.08) 100%)',
          border: '1px solid rgba(167,243,208,.7)',
        }}
      >
        <Group justify="space-between" wrap="nowrap">
          <Box>
            <Group gap="xs">
              <Box
                className="ai-gradient-emerald"
                style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <IconBrain size={20} color="#fff" />
              </Box>
              <Text fw={800} size="lg">
                AI 助手
              </Text>
            </Group>
            <Text size="sm" c="dimmed" mt={6} maw={600}>
              助手 = 人设 + 技能绑定 + 模型与采样参数。温度/最大 Tokens 留空时继承所选模型配置。
            </Text>
            <Group gap="xs" mt="sm">
              <span className="ai-badge ai-badge-system">系统 {stats.system}</span>
              <span className="ai-badge ai-badge-custom">自定义 {stats.custom}</span>
              <span className="ai-badge ai-badge-default">启用 {stats.enabled}</span>
            </Group>
          </Box>
          <Group gap={6} wrap="nowrap">
            <Button
              variant="light"
              color="gray"
              onClick={() => void load()}
              loading={loading}
            >
              刷新
            </Button>
            <Button
              leftSection={<IconPlus size={16} />}
              onClick={() => {
                setError('')
                setForm({ ...EMPTY })
              }}
              className="ai-gradient-emerald"
              style={{ border: 0 }}
            >
              新建助手
            </Button>
          </Group>
        </Group>
      </Paper>

      {loading ? (
        <Group justify="center" py="xl">
          <Loader size="sm" />
        </Group>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
          {assistants.map((a) => (
            <Paper
              key={a.id}
              withBorder
              radius="lg"
              p="md"
              className="ai-card-glow"
              style={{
                borderColor: a.isDefault ? '#fcd34d' : '#e5e7eb',
                boxShadow: '0 1px 3px rgba(0,0,0,.05)',
                opacity: a.enabled ? 1 : 0.6,
              }}
            >
              <Group justify="space-between" wrap="nowrap" align="flex-start">
                <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                  <AssistantAvatar avatar={a.avatar} size={40} iconSize={20} radius={12} />
                  <Box style={{ minWidth: 0 }}>
                    <Text size="sm" fw={700} truncate>
                      {a.name}
                    </Text>
                    <Text size="10px" c="dimmed">
                      {a.category} · 使用 {a.usageCount} 次
                    </Text>
                  </Box>
                </Group>
                <Group gap={4} wrap="nowrap">
                  {a.isDefault && (
                    <span className="ai-badge ai-badge-default">
                      <IconStarFilled size={8} style={{ marginRight: 3 }} />默认
                    </span>
                  )}
                  {a.isSystem ? (
                    <span className="ai-badge ai-badge-system">系统</span>
                  ) : (
                    <span className="ai-badge ai-badge-custom">自定义</span>
                  )}
                </Group>
              </Group>

              <Text size="xs" c="dimmed" mt="xs" mih={32} lineClamp={2}>
                {a.description || '（暂无描述）'}
              </Text>

              <Group gap={4} mt={6} wrap="wrap">
                {a.skillCodes.map((code) => (
                  <span key={code} className="ai-skill-pill" style={{ maxWidth: 140 }}>
                    {skillName(code)}
                  </span>
                ))}
                {a.toolCodes.length > 0 && (
                  <span className="ai-quick-chip" style={{ cursor: 'default', background: '#ecfdf5', borderColor: '#a7f3d0', color: '#047857' }}>
                    工具 {a.toolCodes.length}
                  </span>
                )}
                <span className="ai-quick-chip" style={{ cursor: 'default' }}>
                  {a.temperature === null ? '温度继承' : `T=${a.temperature}`}
                </span>
                <span className="ai-quick-chip" style={{ cursor: 'default' }}>
                  {a.modelConfigId
                    ? models.find((m) => m.id === a.modelConfigId)?.name ?? '绑定模型'
                    : '默认模型'}
                </span>
              </Group>

              <Group justify="flex-end" gap={4} mt="sm">
                {!a.isDefault && (
                  <Tooltip label="设为默认">
                    <Button
                      size="compact-xs"
                      variant="light"
                      color="yellow"
                      onClick={async () => {
                        await api.post(`/ai/assistants/${a.id}/default`)
                        await load()
                      }}
                    >
                      <IconStarFilled size={11} />
                    </Button>
                  </Tooltip>
                )}
                <Tooltip label="预览系统提示词">
                  <Button
                    size="compact-xs"
                    variant="light"
                    color="grape"
                    loading={previewLoading}
                    onClick={() => void showPreview(a.id)}
                  >
                    <IconFileCode size={11} />
                  </Button>
                </Tooltip>
                <Tooltip label="复制">
                  <Button
                    size="compact-xs"
                    variant="light"
                    color="gray"
                    onClick={async () => {
                      await api.post(`/ai/assistants/${a.id}/duplicate`)
                      await load()
                    }}
                  >
                    <IconCopy size={11} />
                  </Button>
                </Tooltip>
                <Tooltip label="编辑">
                  <Button
                    size="compact-xs"
                    variant="light"
                    color="blue"
                    onClick={() => {
                      setError('')
                      setForm({
                        id: a.id,
                        name: a.name,
                        description: a.description,
                        avatar: a.avatar,
                        category: a.category,
                        systemPrompt: a.systemPrompt,
                        greeting: a.greeting,
                        skillCodes: a.skillCodes,
                        toolCodes: a.toolCodes,
                        modelConfigId: a.modelConfigId,
                        temperature: a.temperature ?? '',
                        maxTokens: a.maxTokens ?? '',
                        isDefault: a.isDefault,
                        enabled: a.enabled,
                      })
                    }}
                  >
                    <IconPencil size={11} />
                  </Button>
                </Tooltip>
                {!a.isSystem && (
                  <Tooltip label="删除">
                    <Button
                      size="compact-xs"
                      variant="light"
                      color="red"
                      onClick={async () => {
                        await api.delete(`/ai/assistants/${a.id}`)
                        await load()
                      }}
                    >
                      <IconTrash size={11} />
                    </Button>
                  </Tooltip>
                )}
              </Group>
            </Paper>
          ))}
        </SimpleGrid>
      )}

      <Modal
        opened={form !== null}
        onClose={() => setForm(null)}
        title={form?.id ? '编辑助手' : '新建助手'}
        size="lg"
      >
        {form && (
          <>
            <Text size="sm" fw={500} mb={6}>
              头像
            </Text>
            <Group gap={6} mb="sm" wrap="wrap">
              {AVATAR_OPTIONS.map((opt) => {
                const Icon = opt.icon
                const active = form.avatar === opt.id
                return (
                  <button
                    key={opt.id}
                    type="button"
                    title={opt.label}
                    onClick={() => setForm({ ...form, avatar: opt.id })}
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 10,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                      border: active ? '2px solid #4f46e5' : '1px solid #e5e7eb',
                      background: active ? 'rgba(79,70,229,.08)' : '#fff',
                      color: active ? '#4f46e5' : '#6b7280',
                    }}
                  >
                    <Icon size={18} stroke={1.8} />
                  </button>
                )
              })}
            </Group>

            <Group grow mb="sm">
              <TextInput
                label="名称"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
              />
              <TextInput
                label="分类"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.currentTarget.value })}
                placeholder="General / Engineering / …"
              />
            </Group>
            <TextInput
              label="描述"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.currentTarget.value })}
              mb="sm"
            />
            <Textarea
              label="系统提示词（人设与行为约束）"
              autosize
              minRows={3}
              maxRows={10}
              value={form.systemPrompt}
              onChange={(e) => setForm({ ...form, systemPrompt: e.currentTarget.value })}
              mb="sm"
            />
            <Textarea
              label="开场白（工作台欢迎卡显示，可留空）"
              autosize
              minRows={2}
              maxRows={4}
              value={form.greeting}
              onChange={(e) => setForm({ ...form, greeting: e.currentTarget.value })}
              mb="sm"
            />

            <Text size="sm" fw={500} mb={6}>
              推荐技能
            </Text>
            <Box mb="sm">
              <ChipGroup
                multiple
                value={form.skillCodes}
                onChange={(v) => setForm({ ...form, skillCodes: v })}
              >
                <Group gap={6} wrap="wrap">
                  {skills
                    .filter((s) => s.enabled)
                    .map((s) => (
                      <Chip key={s.code} value={s.code} size="xs" radius="md">
                        {s.name}
                      </Chip>
                    ))}
                </Group>
              </ChipGroup>
            </Box>

            <Group grow mb="sm" align="flex-end">
              <ModelPicker
                label="绑定模型（留空使用默认模型）"
                models={models}
                value={form.modelConfigId}
                onChange={(v) => setForm({ ...form, modelConfigId: v })}
                size="sm"
              />
            </Group>
            <Text size="sm" fw={500} mb={6}>
              可用工具
            </Text>
            <Box mb="sm">
              <ToolChipSelect
                tools={tools}
                value={form.toolCodes}
                onChange={(v) => setForm({ ...form, toolCodes: v })}
                hint={`留空=全部；当前注册 ${tools.length} 个工具`}
              />
            </Box>

            <Group grow mb="sm">
              <NumberInput
                label="温度（留空继承模型）"
                min={0}
                max={2}
                step={0.1}
                decimalScale={2}
                value={form.temperature}
                onChange={(v) => setForm({ ...form, temperature: typeof v === 'number' ? v : '' })}
              />
              <NumberInput
                label="最大 Tokens（留空继承模型）"
                min={1}
                step={256}
                value={form.maxTokens}
                onChange={(v) => setForm({ ...form, maxTokens: typeof v === 'number' ? v : '' })}
              />
            </Group>

            <Group mb="sm">
              <Switch
                label="设为默认助手"
                checked={form.isDefault}
                onChange={(e) => setForm({ ...form, isDefault: e.currentTarget.checked })}
              />
              <Switch
                label="启用"
                checked={form.enabled}
                onChange={(e) => setForm({ ...form, enabled: e.currentTarget.checked })}
              />
            </Group>
            {error && (
              <Text c="red" size="sm" mb="sm">
                {error}
              </Text>
            )}
            <Group gap="xs">
              <Button
                onClick={() => void save()}
                loading={saving}
                className="ai-gradient-emerald"
                style={{ border: 0 }}
                disabled={!form.name.trim()}
              >
                保存
              </Button>
              {form.id && (
                <Button
                  variant="light"
                  color="grape"
                  loading={previewLoading}
                  onClick={() => void showPreview(form.id)}
                >
                  预览提示词
                </Button>
              )}
              <Button variant="subtle" color="gray" onClick={() => setForm(null)}>
                取消
              </Button>
            </Group>
          </>
        )}
      </Modal>

      <Modal opened={preview !== null} onClose={() => setPreview(null)} title="系统提示词预览" size="xl">
        <ScrollArea.Autosize mah={520}>
          <Text size="11px" style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
            {preview}
          </Text>
        </ScrollArea.Autosize>
      </Modal>
    </Box>
  )
}
