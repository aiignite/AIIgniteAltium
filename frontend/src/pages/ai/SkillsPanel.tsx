import { useCallback, useEffect, useState } from 'react'
import {
  Box,
  Button,
  Collapse,
  Group,
  Loader,
  Modal,
  NumberInput,
  Paper,
  ScrollArea,
  Select,
  SimpleGrid,
  Switch,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconCopy,
  IconPencil,
  IconPlus,
  IconSparkles,
  IconTrash,
} from '@tabler/icons-react'
import { api } from '../../api/client'
import { AVATAR_OPTIONS, AvatarIcon } from '../../components/ai/avatarIcons'
import { ToolChipSelect, type ToolInfo } from '../../components/ai/ToolChipSelect'
import { useAuth } from '../../contexts/AuthContext'

interface SkillItem {
  id: string
  code: string
  name: string
  description: string
  category: string
  icon: string
  promptTemplate: string
  keywords: string[]
  toolCodes: string[]
  priority: number
  isSystem: boolean
  enabled: boolean
  sortOrder: number
  createdAt: string
}

interface FormState {
  id: string
  code: string
  name: string
  description: string
  category: string
  icon: string
  promptTemplate: string
  keywords: string[]
  toolCodes: string[]
  priority: number
  enabled: boolean
  isSystem: boolean
}

const EMPTY: FormState = {
  id: '',
  code: '',
  name: '',
  description: '',
  category: 'business',
  icon: 'sparkles',
  promptTemplate: '',
  keywords: [],
  toolCodes: [],
  priority: 50,
  enabled: true,
  isSystem: false,
}

export function SkillsPanel() {
  const { user } = useAuth()
  const isAdmin = user?.isAdmin ?? false
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState<FormState | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [expanded, setExpanded] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, toolList] = await Promise.all([
        api.get<SkillItem[]>('/ai/skills'),
        api.get<ToolInfo[]>('/ai/tools/registry').catch(() => []),
      ])
      setSkills(list)
      setTools(toolList)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const save = async () => {
    if (!form) return
    setError('')
    setSaving(true)
    try {
      const payload = {
        code: form.code,
        name: form.name,
        description: form.description,
        category: form.category,
        icon: form.icon,
        promptTemplate: form.promptTemplate,
        keywords: form.keywords,
        toolCodes: form.toolCodes,
        priority: form.priority,
        enabled: form.enabled,
      }
      if (form.id) await api.put(`/ai/skills/${form.id}`, payload)
      else await api.post('/ai/skills', payload)
      setForm(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Box>
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
              <Box
                className="ai-gradient"
                style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
              >
                <IconSparkles size={20} color="#fff" />
              </Box>
              <Text fw={800} size="lg">
                技能库
              </Text>
            </Group>
            <Text size="sm" c="dimmed" mt={6} maw={620}>
              技能是可复用的任务级提示词模板。对话时按输入内容自动匹配（关键词命中 + 优先级加权 + 助手绑定），
              也可在工作台候选条手动选用；技能可额外限定可用工具。
            </Text>
          </Box>
          <Group gap={6} wrap="nowrap">
            <Button variant="light" color="gray" onClick={() => void load()} loading={loading}>
              刷新
            </Button>
            <Button
              leftSection={<IconPlus size={16} />}
              disabled={!isAdmin}
              title={isAdmin ? undefined : '仅管理员可新建技能'}
              onClick={() => {
                setError('')
                setForm({ ...EMPTY })
              }}
              className="ai-gradient"
              style={{ border: 0 }}
            >
              新建技能
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
          {skills.map((s) => {
            const open = expanded === s.id
            return (
              <Paper key={s.id} withBorder radius="lg" p="md" style={{ opacity: s.enabled ? 1 : 0.6 }}>
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                    <Box
                      className="ai-skill-card"
                      style={{ width: 36, height: 36, borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                    >
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
                  <Group gap={4} wrap="nowrap">
                    <Tooltip label="命中权重（越高越易被自动采纳）">
                      <span className="ai-quick-chip" style={{ cursor: 'help' }}>
                        P{s.priority}
                      </span>
                    </Tooltip>
                    {s.isSystem ? (
                      <span className="ai-badge ai-badge-system">系统</span>
                    ) : (
                      <span className="ai-badge ai-badge-custom">自定义</span>
                    )}
                  </Group>
                </Group>

                <Text size="xs" c="dimmed" mt="xs">
                  {s.description || '（暂无描述）'}
                </Text>

                <Group gap={4} mt={6} wrap="wrap">
                  {s.keywords.slice(0, 5).map((k) => (
                    <span key={k} className="ai-quick-chip" style={{ cursor: 'default' }}>
                      {k}
                    </span>
                  ))}
                  {s.toolCodes.length > 0 && (
                    <span
                      className="ai-quick-chip"
                      style={{ cursor: 'default', background: '#ecfdf5', borderColor: '#a7f3d0', color: '#047857' }}
                    >
                      工具 {s.toolCodes.length}
                    </span>
                  )}
                </Group>

                {s.promptTemplate && (
                  <>
                    <Collapse expanded={open}>
                      <ScrollArea.Autosize mah={200}>
                        <Text
                          size="10px"
                          c="dimmed"
                          mt={8}
                          style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}
                        >
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
                      onClick={() => setExpanded(open ? null : s.id)}
                    >
                      {open ? '收起提示词' : '查看提示词'}
                    </Button>
                  </>
                )}

                <Group justify="space-between" mt="sm">
                  <Switch
                    size="xs"
                    label="启用"
                    disabled={!isAdmin}
                    checked={s.enabled}
                    onChange={async (e) => {
                      await api.put(`/ai/skills/${s.id}`, { ...s, enabled: e.currentTarget.checked })
                      await load()
                    }}
                  />
                  {isAdmin && (
                    <Group gap={4}>
                      <Button
                        size="compact-xs"
                        variant="light"
                        color="gray"
                        onClick={async () => {
                          await api.post(`/ai/skills/${s.id}/duplicate`)
                          await load()
                        }}
                      >
                        <IconCopy size={11} />
                      </Button>
                      <Button
                        size="compact-xs"
                        variant="light"
                        color="blue"
                        onClick={() => {
                          setError('')
                          setForm({
                            id: s.id,
                            code: s.code,
                            name: s.name,
                            description: s.description,
                            category: s.category,
                            icon: s.icon,
                            promptTemplate: s.promptTemplate,
                            keywords: s.keywords,
                            toolCodes: s.toolCodes,
                            priority: s.priority,
                            enabled: s.enabled,
                            isSystem: s.isSystem,
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
                            await load()
                          }}
                        >
                          <IconTrash size={11} />
                        </Button>
                      )}
                    </Group>
                  )}
                </Group>
              </Paper>
            )
          })}
        </SimpleGrid>
      )}

      <Modal
        opened={form !== null}
        onClose={() => setForm(null)}
        title={form?.id ? '编辑技能' : '新建技能'}
        size="lg"
      >
        {form && (
          <>
            <Group grow mb="sm">
              <TextInput
                label="名称"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.currentTarget.value })}
              />
              <TextInput
                label="代码（唯一，如 schematic-review）"
                value={form.code}
                disabled={form.isSystem}
                onChange={(e) => setForm({ ...form, code: e.currentTarget.value })}
              />
            </Group>
            <TextInput
              label="描述"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.currentTarget.value })}
              mb="sm"
            />
            <Group grow mb="sm">
              <Select
                label="图标"
                data={AVATAR_OPTIONS.map((o) => ({ value: o.id, label: o.label }))}
                value={form.icon}
                onChange={(v) => setForm({ ...form, icon: v ?? 'sparkles' })}
                allowDeselect={false}
              />
              <NumberInput
                label="优先级（0-100）"
                min={0}
                max={100}
                step={5}
                value={form.priority}
                onChange={(v) => setForm({ ...form, priority: typeof v === 'number' ? v : 50 })}
              />
            </Group>
            <TagsInput
              label="触发关键词（命中越多匹配分越高）"
              placeholder="输入后回车"
              value={form.keywords}
              onChange={(v) => setForm({ ...form, keywords: v })}
              mb="sm"
            />
            <Text size="sm" fw={500} mb={6}>
              关联工具
            </Text>
            <Box mb="sm">
              <ToolChipSelect
                tools={tools}
                value={form.toolCodes}
                onChange={(v) => setForm({ ...form, toolCodes: v })}
                hint={`留空=不限制；技能启用时与助手工具取并集（当前 ${tools.length} 个）`}
              />
            </Box>
            <Textarea
              label="提示词模板（注入对话系统提示）"
              autosize
              minRows={5}
              maxRows={14}
              value={form.promptTemplate}
              onChange={(e) => setForm({ ...form, promptTemplate: e.currentTarget.value })}
              mb="sm"
            />
            <Switch
              label="启用"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.currentTarget.checked })}
              mb="sm"
            />
            {error && (
              <Text c="red" size="sm" mb="sm">
                {error}
              </Text>
            )}
            <Group gap="xs">
              <Button
                onClick={() => void save()}
                loading={saving}
                className="ai-gradient"
                style={{ border: 0 }}
                disabled={!form.name.trim() || !form.code.trim()}
              >
                保存
              </Button>
              <Button variant="subtle" color="gray" onClick={() => setForm(null)}>
                取消
              </Button>
            </Group>
          </>
        )}
      </Modal>
    </Box>
  )
}
