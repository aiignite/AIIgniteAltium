import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Badge,
  Box,
  Button,
  Chip,
  ChipGroup,
  Collapse,
  Group,
  Modal,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Switch,
  Tabs,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconBrain,
  IconPencil,
  IconPlus,
  IconSparkles,
  IconStarFilled,
  IconTrash,
} from '@tabler/icons-react'
import { api } from '../api/client'
import { AVATAR_OPTIONS, AvatarIcon } from '../components/ai/avatarIcons'
import { AssistantAvatar } from '../components/ai/AssistantAvatar'

interface AssistantItem {
  id: string
  name: string
  description: string
  avatar: string
  category: string
  systemPrompt: string
  skillCodes: string[]
  modelConfigId: string | null
  isDefault: boolean
  isSystem: boolean
  enabled: boolean
  usageCount: number
  createdAt: string
}

interface SkillItem {
  id: string
  code: string
  name: string
  description: string
  category: string
  icon: string
  promptTemplate: string
  keywords: string[]
  isSystem: boolean
  enabled: boolean
  sortOrder: number
  createdAt: string
}

interface AIModelItem {
  id: string
  name: string
  enabled: boolean
}

const emptyAssistant = {
  id: '',
  name: '',
  description: '',
  avatar: 'bot',
  category: 'General',
  systemPrompt: '',
  skillCodes: [] as string[],
  modelConfigId: null as string | null,
  isDefault: false,
  enabled: true,
}

const emptySkill = {
  id: '',
  code: '',
  name: '',
  description: '',
  category: 'business',
  icon: 'sparkles',
  promptTemplate: '',
  keywords: [] as string[],
  enabled: true,
}

export function AssistantsPage() {
  const [assistants, setAssistants] = useState<AssistantItem[]>([])
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [models, setModels] = useState<AIModelItem[]>([])
  const [assistantForm, setAssistantForm] = useState<typeof emptyAssistant | null>(null)
  const [skillForm, setSkillForm] = useState<typeof emptySkill | null>(null)
  const [error, setError] = useState('')
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)

  const load = useCallback(() => {
    api.get<AssistantItem[]>('/ai/assistants').then(setAssistants).catch(() => {})
    api.get<SkillItem[]>('/ai/skills').then(setSkills).catch(() => {})
    api.get<AIModelItem[]>('/ai/models').then((ms) => setModels(ms.filter((m) => m.enabled))).catch(() => {})
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const skillName = useCallback((code: string) => skills.find((s) => s.code === code)?.name ?? code, [skills])

  const stats = useMemo(
    () => ({
      system: assistants.filter((a) => a.isSystem).length,
      custom: assistants.filter((a) => !a.isSystem).length,
      skills: skills.length,
    }),
    [assistants, skills],
  )

  const saveAssistant = async () => {
    if (!assistantForm) return
    setError('')
    try {
      if (assistantForm.id) await api.put(`/ai/assistants/${assistantForm.id}`, assistantForm)
      else await api.post('/ai/assistants', assistantForm)
      setAssistantForm(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  const saveSkill = async () => {
    if (!skillForm) return
    setError('')
    try {
      if (skillForm.id) await api.put(`/ai/skills/${skillForm.id}`, skillForm)
      else await api.post('/ai/skills', skillForm)
      setSkillForm(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
  }

  return (
    <Box>
      <Tabs defaultValue="assistants" variant="pills" radius="lg">
        <Group justify="space-between" mb="md">
          <Tabs.List>
            <Tabs.Tab value="assistants" leftSection={<IconBrain size={16} />}>
              助手管理
            </Tabs.Tab>
            <Tabs.Tab value="skills" leftSection={<IconSparkles size={16} />}>
              技能库
            </Tabs.Tab>
          </Tabs.List>
        </Group>

        {/* ================= 助手管理 ================= */}
        <Tabs.Panel value="assistants">
          {/* 介绍横幅（emerald 渐变，对齐 AIIgnitePLM AssistantsTab） */}
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
                  <Box className="ai-gradient-emerald" style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <IconBrain size={20} color="#fff" />
                  </Box>
                  <Text fw={800} size="lg">
                    AI 助手
                  </Text>
                </Group>
                <Text size="sm" c="dimmed" mt={6} maw={560}>
                  创建和管理具有专业角色的 AI 助手，每个助手拥有独立的系统提示词、技能绑定与模型配置。
                </Text>
                <Group gap="xs" mt="sm">
                  <Badge variant="light" color="blue">
                    系统 {stats.system}
                  </Badge>
                  <Badge variant="light" color="grape">
                    自定义 {stats.custom}
                  </Badge>
                  <Badge variant="light" color="teal">
                    技能 {stats.skills}
                  </Badge>
                </Group>
              </Box>
              <Button
                leftSection={<IconPlus size={16} />}
                onClick={() => {
                  setError('')
                  setAssistantForm({ ...emptyAssistant })
                }}
                className="ai-gradient-emerald"
                style={{ border: 0 }}
              >
                新建助手
              </Button>
            </Group>
          </Paper>

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

                {a.skillCodes.length > 0 && (
                  <Group gap={4} mt={6} wrap="wrap">
                    {a.skillCodes.map((code) => (
                      <span key={code} className="ai-skill-pill" style={{ maxWidth: 140 }}>
                        {skillName(code)}
                      </span>
                    ))}
                  </Group>
                )}

                <Group justify="flex-end" gap="xs" mt="sm">
                  {!a.isDefault && (
                    <Tooltip label="设为默认">
                      <Button
                        size="compact-xs"
                        variant="light"
                        color="yellow"
                        onClick={async () => {
                          await api.post(`/ai/assistants/${a.id}/default`)
                          load()
                        }}
                      >
                        <IconStarFilled size={11} />
                      </Button>
                    </Tooltip>
                  )}
                  <Tooltip label={a.isSystem ? '系统助手可编辑' : '编辑'}>
                    <Button
                      size="compact-xs"
                      variant="light"
                      color="blue"
                      onClick={() => {
                        setError('')
                        setAssistantForm({
                          id: a.id,
                          name: a.name,
                          description: a.description,
                          avatar: a.avatar,
                          category: a.category,
                          systemPrompt: a.systemPrompt,
                          skillCodes: a.skillCodes,
                          modelConfigId: a.modelConfigId,
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
                          load()
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
        </Tabs.Panel>

        {/* ================= 技能库 ================= */}
        <Tabs.Panel value="skills">
          <Paper
            radius="xl"
            p="lg"
            mb="md"
            style={{
              background: 'linear-gradient(135deg, rgba(59,130,246,.08) 0%, rgba(255,255,255,1) 50%, rgba(79,70,229,.08) 100%)',
              border: '1px solid rgba(191,219,254,.7)',
            }}
          >
            <Group justify="space-between" wrap="nowrap">
              <Box>
                <Group gap="xs">
                  <Box className="ai-gradient" style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <IconSparkles size={20} color="#fff" />
                  </Box>
                  <Text fw={800} size="lg">
                    技能库
                  </Text>
                </Group>
                <Text size="sm" c="dimmed" mt={6} maw={560}>
                  技能是可复用的任务级提示词模板。对话时按输入内容自动匹配激活，也可在助手技能候选条中手动选用。
                </Text>
              </Box>
              <Button
                leftSection={<IconPlus size={16} />}
                onClick={() => {
                  setError('')
                  setSkillForm({ ...emptySkill })
                }}
                className="ai-gradient"
                style={{ border: 0 }}
              >
                新建技能
              </Button>
            </Group>
          </Paper>

          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="md">
            {skills.map((s) => {
              const expanded = expandedSkill === s.id
              return (
                <Paper key={s.id} withBorder radius="lg" p="md" style={{ opacity: s.enabled ? 1 : 0.6 }}>
                  <Group justify="space-between" wrap="nowrap" align="flex-start">
                    <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                      <Box className="ai-skill-card" style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <AvatarIcon id={s.icon} size={18} />
                      </Box>
                      <Box style={{ minWidth: 0 }}>
                        <Text size="sm" fw={700} truncate>
                          {s.name}
                        </Text>
                        <Text size="10px" c="dimmed" style={{ fontFamily: 'monospace' }}>
                          {s.code}
                        </Text>
                      </Box>
                    </Group>
                    {s.isSystem ? <span className="ai-badge ai-badge-system">系统</span> : <span className="ai-badge ai-badge-custom">自定义</span>}
                  </Group>

                  <Text size="xs" c="dimmed" mt="xs">
                    {s.description || '（暂无描述）'}
                  </Text>

                  {s.keywords.length > 0 && (
                    <Group gap={4} mt={6} wrap="wrap">
                      {s.keywords.slice(0, 5).map((k) => (
                        <span key={k} className="ai-quick-chip" style={{ cursor: 'default' }}>
                          {k}
                        </span>
                      ))}
                    </Group>
                  )}

                  {s.promptTemplate && (
                    <>
                      <Collapse expanded={expanded}>
                        <ScrollArea.Autosize mah={200}>
                          <Text size="10px" c="dimmed" mt={8} style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                            {s.promptTemplate}
                          </Text>
                        </ScrollArea.Autosize>
                      </Collapse>
                      <Button
                        size="compact-xs"
                        variant="subtle"
                        color="gray"
                        mt={4}
                        px={4}
                        onClick={() => setExpandedSkill(expanded ? null : s.id)}
                      >
                        {expanded ? '收起提示词' : '查看提示词'}
                      </Button>
                    </>
                  )}

                  <Group justify="space-between" mt="sm">
                    <Switch
                      size="xs"
                      label="启用"
                      checked={s.enabled}
                      onChange={async (e) => {
                        await api.put(`/ai/skills/${s.id}`, { ...s, enabled: e.currentTarget.checked })
                        load()
                      }}
                    />
                    <Group gap={4}>
                      <Button
                        size="compact-xs"
                        variant="light"
                        color="blue"
                        onClick={() => {
                          setError('')
                          setSkillForm({
                            id: s.id,
                            code: s.code,
                            name: s.name,
                            description: s.description,
                            category: s.category,
                            icon: s.icon,
                            promptTemplate: s.promptTemplate,
                            keywords: s.keywords,
                            enabled: s.enabled,
                          })
                        }}
                      >
                        <IconPencil size={11} />
                      </Button>
                      {!s.isSystem && (
                        <Button
                          size="compact-xs"
                          variant="light"
                          color="red"
                          onClick={async () => {
                            await api.delete(`/ai/skills/${s.id}`)
                            load()
                          }}
                        >
                          <IconTrash size={11} />
                        </Button>
                      )}
                    </Group>
                  </Group>
                </Paper>
              )
            })}
          </SimpleGrid>
        </Tabs.Panel>
      </Tabs>

      {/* ================= 助手表单 ================= */}
      <Modal
        opened={assistantForm !== null}
        onClose={() => setAssistantForm(null)}
        title={assistantForm?.id ? '编辑助手' : '新建助手'}
        size="lg"
      >
        {assistantForm && (
          <>
            <Text size="sm" fw={500} mb={6}>
              头像
            </Text>
            <Group gap={6} mb="sm" wrap="wrap">
              {AVATAR_OPTIONS.map((opt) => {
                const Icon = opt.icon
                const active = assistantForm.avatar === opt.id
                return (
                  <button
                    key={opt.id}
                    type="button"
                    title={opt.label}
                    onClick={() => setAssistantForm({ ...assistantForm, avatar: opt.id })}
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
                value={assistantForm.name}
                onChange={(e) => setAssistantForm({ ...assistantForm, name: e.target.value })}
              />
              <TextInput
                label="分类"
                value={assistantForm.category}
                onChange={(e) => setAssistantForm({ ...assistantForm, category: e.target.value })}
                placeholder="General / Engineering / …"
              />
            </Group>
            <TextInput
              label="描述"
              value={assistantForm.description}
              onChange={(e) => setAssistantForm({ ...assistantForm, description: e.target.value })}
              mb="sm"
            />
            <Textarea
              label="系统提示词（人设与行为约束）"
              autosize
              minRows={3}
              maxRows={10}
              value={assistantForm.systemPrompt}
              onChange={(e) => setAssistantForm({ ...assistantForm, systemPrompt: e.target.value })}
              mb="sm"
            />
            <Text size="sm" fw={500} mb={6}>
              推荐技能
            </Text>
            <Box mb="sm">
              <ChipGroup multiple value={assistantForm.skillCodes} onChange={(v) => setAssistantForm({ ...assistantForm, skillCodes: v })}>
                <Group gap={6} wrap="wrap">
                  {skills.filter((s) => s.enabled).map((s) => (
                    <Chip key={s.code} value={s.code} size="xs" radius="md">
                      {s.name}
                    </Chip>
                  ))}
                </Group>
              </ChipGroup>
            </Box>
            <Select
              label="绑定模型（留空使用默认模型）"
              data={models.map((m) => ({ value: m.id, label: m.name }))}
              value={assistantForm.modelConfigId}
              onChange={(v) => setAssistantForm({ ...assistantForm, modelConfigId: v })}
              clearable
              mb="sm"
            />
            <Group mb="sm">
              <Switch
                label="设为默认助手"
                checked={assistantForm.isDefault}
                onChange={(e) => setAssistantForm({ ...assistantForm, isDefault: e.currentTarget.checked })}
              />
              <Switch
                label="启用"
                checked={assistantForm.enabled}
                onChange={(e) => setAssistantForm({ ...assistantForm, enabled: e.currentTarget.checked })}
              />
            </Group>
            {error && (
              <Text c="red" size="sm" mb="sm">
                {error}
              </Text>
            )}
            <Button fullWidth onClick={saveAssistant} className="ai-gradient-emerald" style={{ border: 0 }}>
              保存
            </Button>
          </>
        )}
      </Modal>

      {/* ================= 技能表单 ================= */}
      <Modal opened={skillForm !== null} onClose={() => setSkillForm(null)} title={skillForm?.id ? '编辑技能' : '新建技能'} size="lg">
        {skillForm && (
          <>
            <Group grow mb="sm">
              <TextInput
                label="名称"
                value={skillForm.name}
                onChange={(e) => setSkillForm({ ...skillForm, name: e.target.value })}
              />
              <TextInput
                label="代码（唯一，如 schematic-review）"
                value={skillForm.code}
                disabled={!!skillForm.id && skills.find((s) => s.id === skillForm.id)?.isSystem}
                onChange={(e) => setSkillForm({ ...skillForm, code: e.target.value })}
              />
            </Group>
            <TextInput
              label="描述"
              value={skillForm.description}
              onChange={(e) => setSkillForm({ ...skillForm, description: e.target.value })}
              mb="sm"
            />
            <Group grow mb="sm">
              <Select
                label="图标"
                data={AVATAR_OPTIONS.map((o) => ({ value: o.id, label: o.label }))}
                value={skillForm.icon}
                onChange={(v) => setSkillForm({ ...skillForm, icon: v ?? 'sparkles' })}
              />
              <TagsInput
                label="触发关键词（命中越多匹配分越高）"
                placeholder="输入后回车"
                value={skillForm.keywords}
                onChange={(v) => setSkillForm({ ...skillForm, keywords: v })}
              />
            </Group>
            <Textarea
              label="提示词模板（注入对话系统提示）"
              autosize
              minRows={5}
              maxRows={14}
              value={skillForm.promptTemplate}
              onChange={(e) => setSkillForm({ ...skillForm, promptTemplate: e.target.value })}
              mb="sm"
            />
            <Switch
              label="启用"
              checked={skillForm.enabled}
              onChange={(e) => setSkillForm({ ...skillForm, enabled: e.currentTarget.checked })}
              mb="sm"
            />
            {error && (
              <Text c="red" size="sm" mb="sm">
                {error}
              </Text>
            )}
            <Button fullWidth onClick={saveSkill} className="ai-gradient" style={{ border: 0 }}>
              保存
            </Button>
          </>
        )}
      </Modal>
    </Box>
  )
}
