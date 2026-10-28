import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ActionIcon,
  Box,
  Button,
  Group,
  Paper,
  ScrollArea,
  Select,
  Text,
  Textarea,
  Tooltip,
} from '@mantine/core'
import {
  IconCheck,
  IconCopy,
  IconHistory,
  IconPlayerStop,
  IconPlus,
  IconSend,
  IconSparkles,
  IconX,
} from '@tabler/icons-react'
import { api, streamChat, type ActivatedSkill, type ChatStreamEvent } from '../api/client'
import { DesignDataTabs } from '../components/DesignDataTabs'
import { AssistantPicker, type AssistantItem } from '../components/ai/AssistantPicker'
import { AssistantAvatar } from '../components/ai/AssistantAvatar'
import { SkillActivationCard } from '../components/ai/SkillActivationCard'

export interface ProjectSummary {
  id: string
  name: string
  status: string
  error: string
  fileNames: string[]
  stats: Record<string, number>
  svgManifest: { svgId: string; kind: string; title: string; file: string }[]
  parseDurationMs: number
  createdAt: string
  updatedAt: string
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  error?: boolean
  skills?: ActivatedSkill[]
  assistantName?: string
}

interface SkillItem {
  id: string
  code: string
  name: string
  description: string
  icon: string
  enabled: boolean
  isSystem: boolean
}

interface Candidate {
  code: string
  name: string
  description: string
  icon: string
  score: number
  reasons: string[]
  selected: boolean
}

interface ConversationItem {
  id: string
  title: string
  projectId: string | null
  connectionId: string | null
  assistantId: string | null
  skill: string
  messageCount: number
  updatedAt: string
}

interface ConnectionItem {
  id: string
  name: string
  baseUrl: string
  status: string
}

type SourceKind = 'none' | 'project' | 'live'

const SOURCE_LABEL: Record<SourceKind, string> = {
  none: '无设计来源',
  project: '离线解析工程',
  live: 'Altium 实时连接',
}

interface AIModelItem {
  id: string
  name: string
  enabled: boolean
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m} 分钟前`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h} 小时前`
  return `${Math.floor(h / 24)} 天前`
}

export function WorkbenchPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [source, setSource] = useState<SourceKind>('none')
  const [projectId, setProjectId] = useState<string | null>(null)
  const [connections, setConnections] = useState<ConnectionItem[]>([])
  const [connectionId, setConnectionId] = useState<string | null>(null)
  const [assistants, setAssistants] = useState<AssistantItem[]>([])
  const [assistantId, setAssistantId] = useState<string | null>(null)
  const [models, setModels] = useState<AIModelItem[]>([])
  const [modelId, setModelId] = useState<string | null>(null)
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [searchParams] = useSearchParams()
  const viewportRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  const abortRef = useRef<AbortController | null>(null)

  const assistant = useMemo(
    () => assistants.find((a) => a.id === assistantId) ?? assistants.find((a) => a.isDefault) ?? null,
    [assistants, assistantId],
  )

  const loadConversations = useCallback(() => {
    api.get<ConversationItem[]>('/ai/conversations').then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    const projectParam = searchParams.get('projectId')
    const connectionParam = searchParams.get('connectionId')
    api.get<ProjectSummary[]>('/files/projects').then((ps) => {
      const ready = ps.filter((p) => p.status === 'ready')
      setProjects(ready)
      if (projectParam && ready.some((p) => p.id === projectParam)) {
        setSource('project')
        setProjectId(projectParam)
      }
    })
    api
      .get<ConnectionItem[]>('/altium/connections')
      .then((list) => {
        setConnections(list)
        if (connectionParam && list.some((c) => c.id === connectionParam)) {
          setSource('live')
          setConnectionId(connectionParam)
        }
      })
      .catch(() => setConnections([]))
    api.get<AssistantItem[]>('/ai/assistants').then((list) => {
      setAssistants(list.filter((a) => a.enabled))
      setAssistantId((prev) => prev ?? list.find((a) => a.isDefault)?.id ?? list[0]?.id ?? null)
    })
    api.get<SkillItem[]>('/ai/skills').then((list) => setSkills(list.filter((s) => s.enabled)))
    api.get<AIModelItem[]>('/ai/models').then((list) => {
      setModels(list.filter((m) => m.enabled))
      setModelId(list.find((m) => m.enabled)?.id ?? null)
    })
    loadConversations()
  }, [loadConversations, searchParams])

  useEffect(() => {
    if (stickToBottom.current) viewportRef.current?.scrollTo({ top: viewportRef.current.scrollHeight })
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  // 技能编排：输入防抖 500ms 调 /ai/skills/resolve（对齐 AIIgnitePLM useSkillOrchestrator）
  useEffect(() => {
    const q = input.trim()
    if (q.length < 2) {
      setCandidates([])
      return
    }
    const timer = window.setTimeout(async () => {
      try {
        const resolved = await api.post<{ code: string; name: string; description: string; icon: string; score: number; reasons: string[] }[]>(
          '/ai/skills/resolve',
          { query: q, assistantId: assistant?.id ?? null, excludeCodes: [], topK: 3 },
        )
        setCandidates((prev) => {
          const prevManual = prev.filter((c) => c.score >= 999)
          const merged = resolved.map(
            (r) => prev.find((p) => p.code === r.code) ?? { ...r, selected: true },
          )
          return [...merged, ...prevManual]
        })
      } catch {
        /* 静默失败，不阻塞输入 */
      }
    }, 500)
    return () => window.clearTimeout(timer)
  }, [input, assistant?.id])

  const toggleCandidate = (code: string) => {
    setCandidates((prev) => prev.map((c) => (c.code === code ? { ...c, selected: !c.selected } : c)))
  }

  const addSkillManually = useCallback(
    (code: string) => {
      setCandidates((prev) => {
        if (prev.some((c) => c.code === code)) {
          return prev.map((c) => (c.code === code ? { ...c, selected: true, score: Math.max(c.score, 999) } : c))
        }
        const s = skills.find((x) => x.code === code)
        if (!s) return prev
        return [
          ...prev,
          { code: s.code, name: s.name, description: s.description, icon: s.icon, score: 999, reasons: ['手动添加'], selected: true },
        ]
      })
    },
    [skills],
  )

  const openConversation = useCallback(
    async (c: ConversationItem) => {
      setShowHistory(false)
      try {
        const msgs = await api.get<{ role: string; content: string; skills: ActivatedSkill[]; assistantName: string }[]>(
          `/ai/conversations/${c.id}/messages`,
        )
        setMessages(
          msgs
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
              skills: m.skills,
              assistantName: m.assistantName,
            })),
        )
        setConversationId(c.id)
        setSource(c.connectionId ? 'live' : c.projectId ? 'project' : 'none')
        setProjectId(c.projectId)
        setConnectionId(c.connectionId)
        if (c.assistantId) setAssistantId(c.assistantId)
        if (c.skill) addSkillManually(c.skill)
      } catch {
        /* ignore */
      }
    },
    [addSkillManually],
  )

  const selectedSkills = useMemo(() => candidates.filter((c) => c.selected).map((c) => c.code), [candidates])

  const resetConversation = useCallback(() => {
    setMessages([])
    setConversationId(null)
    setCandidates([])
    setInput('')
  }, [])

  const changeSource = useCallback(
    (next: SourceKind) => {
      if (streaming || next === source) return
      setSource(next)
      setProjectId(null)
      setConnectionId(null)
      resetConversation()
    },
    [streaming, source, resetConversation],
  )

  const chooseProject = useCallback(
    (id: string | null) => {
      if (streaming) return
      setProjectId(id)
      if (conversationId) resetConversation()
    },
    [streaming, conversationId, resetConversation],
  )

  const chooseConnection = useCallback(
    (id: string | null) => {
      if (streaming) return
      setConnectionId(id)
      if (conversationId) resetConversation()
    },
    [streaming, conversationId, resetConversation],
  )

  const sourceReady = source === 'none' || (source === 'project' ? !!projectId : !!connectionId)

  const send = useCallback(async () => {
    const content = input.trim()
    if (!content || streaming || !sourceReady) return
    setInput('')
    setCandidates((prev) => prev.filter((c) => c.selected))
    setMessages((prev) => [...prev, { role: 'user', content }, { role: 'assistant', content: '', skills: [] }])
    const controller = new AbortController()
    abortRef.current = controller
    setStreaming(true)
    try {
      await streamChat(
        {
          content,
          conversationId,
          projectId: source === 'project' ? projectId : null,
          connectionId: source === 'live' ? connectionId : null,
          assistantId: assistant?.id ?? null,
          skills: selectedSkills.length > 0 ? selectedSkills : null,
          modelConfigId: modelId || null,
        },
        (event: ChatStreamEvent) => {
          if (event.type === 'meta' && event.conversationId) {
            setConversationId(event.conversationId)
            loadConversations()
          }
          if (event.type === 'skills_activated' && event.skills) {
            const activated = event.skills
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = { ...next[next.length - 1], skills: activated }
              return next
            })
          }
          if (event.type === 'delta' && event.text)
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                role: 'assistant',
                content: next[next.length - 1].content + event.text,
              }
              return next
            })
          if (event.type === 'error')
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = { ...next[next.length - 1], content: event.message ?? '出错了', error: true }
              return next
            })
        },
        controller.signal,
      )
    } catch (err) {
      // 用户主动停止：后端会保存已生成的部分内容，界面保留已有文本
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        setMessages((prev) => {
          const next = [...prev]
          next[next.length - 1] = { ...next[next.length - 1], content: '连接中断，请重试', error: true }
          return next
        })
      }
    } finally {
      abortRef.current = null
      setStreaming(false)
      loadConversations()
    }
  }, [input, streaming, sourceReady, conversationId, source, projectId, connectionId, assistant, selectedSkills, modelId, loadConversations])

  const stop = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const copyMessage = useCallback(async (index: number, content: string) => {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedIndex(index)
      window.setTimeout(() => setCopiedIndex((cur) => (cur === index ? null : cur)), 1500)
    } catch {
      /* 剪贴板不可用时保持无反馈 */
    }
  }, [])

  // 欢迎卡「建议这样提问」：绑定技能 → 技能式提问；否则通用引导
  const suggestions = useMemo(() => {
    if (messages.length > 0) return []
    const bound = assistant?.skillCodes ?? []
    if (bound.length > 0) {
      return bound
        .map((code) => skills.find((s) => s.code === code))
        .filter((s): s is SkillItem => !!s)
        .map((s) => `请使用【${s.name}】技能帮我处理当前设计`)
    }
    return ['帮我审查这个工程的原理图', '总结当前设计的要点与风险', '分析一下这个工程的 BOM 构成']
  }, [messages.length, assistant, skills])

  const sourceLabel =
    source === 'project'
      ? projects.find((p) => p.id === projectId)?.name ?? '未选择工程'
      : source === 'live'
        ? connections.find((c) => c.id === connectionId)?.name ?? '未选择连接'
        : '无（仅对话）'

  return (
    <Group align="flex-start" gap="md" wrap="nowrap" style={{ height: 'calc(100vh - 90px)' }}>
      {/* ===== 左：AI 对话（AIIgnitePLM 助手抽屉风格） ===== */}
      <Box
        w={{ base: '100%', md: 420 }}
        style={{
          flexShrink: 0,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 16,
          border: '1px solid #e5e7eb',
          background: '#fff',
          overflow: 'hidden',
        }}
      >
        {/* Header：助手选择器 + 历史/新对话 */}
        <Box px="sm" py={8} style={{ borderBottom: '1px solid #f3f4f6', background: 'rgba(249,250,251,.5)' }}>
          <Group justify="space-between" wrap="nowrap">
            <AssistantPicker
              assistants={assistants}
              selectedId={assistant?.id ?? null}
              onSelect={(a) => {
                setAssistantId(a.id)
                setCandidates([])
              }}
            />
            <Group gap={4} wrap="nowrap">
              <Tooltip label="历史对话">
                <Button
                  variant="subtle"
                  color="gray"
                  px={6}
                  aria-label="历史对话"
                  disabled={streaming}
                  onClick={() => setShowHistory((o) => !o)}
                  styles={{ root: { borderRadius: 8 } }}
                >
                  <IconHistory size={16} />
                </Button>
              </Tooltip>
              <Tooltip label="新对话">
                <Button
                  variant="subtle"
                  color="gray"
                  px={6}
                  aria-label="新对话"
                  disabled={streaming}
                  onClick={resetConversation}
                  styles={{ root: { borderRadius: 8 } }}
                >
                  <IconPlus size={16} />
                </Button>
              </Tooltip>
            </Group>
          </Group>
          <Group gap={6} mt={6} wrap="nowrap">
            <Select
              size="xs"
              flex={1}
              aria-label="设计来源"
              data={(Object.keys(SOURCE_LABEL) as SourceKind[]).map((value) => ({
                value,
                label: SOURCE_LABEL[value],
              }))}
              value={source}
              onChange={(v) => changeSource((v as SourceKind) ?? 'none')}
              disabled={streaming}
              allowDeselect={false}
            />
            <Select
              size="xs"
              w={130}
              placeholder="模型"
              data={models.map((m) => ({ value: m.id, label: m.name }))}
              value={modelId}
              onChange={setModelId}
              disabled={streaming}
            />
          </Group>
          {source === 'project' && (
            <Select
              size="xs"
              mt={6}
              placeholder="选择已解析工程"
              aria-label="已解析工程"
              data={projects.map((p) => ({ value: p.id, label: `${p.name}（${p.stats.componentCount ?? 0} 元件）` }))}
              value={projectId}
              onChange={chooseProject}
              disabled={streaming}
              allowDeselect={false}
              nothingFoundMessage="暂无就绪工程，请先在「工程文件」上传解析"
            />
          )}
          {source === 'live' && (
            <Select
              size="xs"
              mt={6}
              placeholder="选择已授权实时连接"
              aria-label="实时连接"
              data={connections.map((c) => ({
                value: c.id,
                label: `${c.name}（${c.status === 'connected' ? '已连接' : '未连接'}）`,
              }))}
              value={connectionId}
              onChange={chooseConnection}
              disabled={streaming}
              allowDeselect={false}
              nothingFoundMessage="暂无可用连接，请联系管理员授权"
            />
          )}

          {/* 历史面板 */}
          {showHistory && (
            <ScrollArea.Autosize mah={220} mt={6}>
              {conversations.length === 0 && (
                <Text size="xs" c="dimmed" ta="center" py="sm">
                  暂无历史对话
                </Text>
              )}
              {conversations.map((c) => (
                <Group
                  key={c.id}
                  wrap="nowrap"
                  gap="xs"
                  py={6}
                  px={8}
                  style={{
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: c.id === conversationId ? '#eff6ff' : 'transparent',
                  }}
                  onClick={() => openConversation(c)}
                  justify="space-between"
                >
                  <Box style={{ minWidth: 0 }}>
                    <Text size="xs" truncate style={{ maxWidth: 240, fontWeight: 500 }}>
                      {c.title}
                    </Text>
                    <Text size="10px" c="dimmed">
                      {assistants.find((a) => a.id === c.assistantId)?.name ?? '通用助手'} · {c.messageCount} 条 ·{' '}
                      {timeAgo(c.updatedAt)}
                    </Text>
                  </Box>
                  <Button
                    variant="subtle"
                    color="red"
                    size="compact-xs"
                    px={4}
                    onClick={async (e) => {
                      e.stopPropagation()
                      await api.delete(`/ai/conversations/${c.id}`)
                      if (c.id === conversationId) resetConversation()
                      loadConversations()
                    }}
                  >
                    <IconX size={12} />
                  </Button>
                </Group>
              ))}
            </ScrollArea.Autosize>
          )}
        </Box>

        {/* 消息区 */}
        <ScrollArea
          style={{ flex: 1 }}
          viewportRef={viewportRef}
          p="sm"
          onScrollPositionChange={({ y }) => {
            const el = viewportRef.current
            if (el) stickToBottom.current = el.scrollHeight - y - el.clientHeight < 80
          }}
        >
          {messages.length === 0 ? (
            /* 欢迎卡（复刻 AIIgnitePLM 欢迎面板） */
            <Paper
              withBorder
              p="md"
              radius="lg"
              style={{ borderColor: '#e5e7eb', boxShadow: '0 1px 2px rgba(0,0,0,.04)' }}
            >
              <Group gap="sm" wrap="nowrap">
                <AssistantAvatar avatar={assistant?.avatar} size={40} iconSize={20} radius={12} />
                <Box style={{ minWidth: 0 }}>
                  <Text size="sm" fw={700}>
                    {assistant?.name ?? '通用硬件助手'}
                  </Text>
                  <Text size="xs" c="dimmed" lineClamp={2}>
                    {assistant?.description || 'AIDriveAltium 硬件设计 AI 助手，基于设计上下文回答问题。'}
                  </Text>
                </Box>
              </Group>
              <Text size="10px" c="dimmed" mt={8}>
                设计来源：{sourceLabel}
              </Text>
              {suggestions.length > 0 && (
                <Box mt="sm">
                  <Text size="11px" fw={600} c="dark" mb={4}>
                    建议这样提问
                  </Text>
                  <Group gap={4} wrap="wrap">
                    {suggestions.map((s) => (
                      <button key={s} type="button" className="ai-quick-chip" onClick={() => setInput(s)}>
                        {s}
                      </button>
                    ))}
                  </Group>
                </Box>
              )}
              {skills.length > 0 && (
                <Box mt="sm">
                  <Group gap={4} mb={4}>
                    <IconSparkles size={12} color="#10b981" />
                    <Text size="11px" fw={600} c="dark">
                      可用技能
                    </Text>
                    <Text size="10px" c="dimmed" ml="auto">
                      {skills.length} 个 · 点击选用
                    </Text>
                  </Group>
                  <Group gap={4} wrap="wrap">
                    {skills.map((s) => {
                      const active = selectedSkills.includes(s.code)
                      return (
                        <button
                          key={s.code}
                          type="button"
                          title={s.description}
                          onClick={() => (active ? toggleCandidate(s.code) : addSkillManually(s.code))}
                          style={{
                            ...pillStyle(active),
                          }}
                        >
                          {s.name}
                        </button>
                      )
                    })}
                  </Group>
                </Box>
              )}
            </Paper>
          ) : (
            <Box>
              {messages.map((m, i) =>
                m.role === 'user' ? (
                  <Box key={i} mb="sm" className="ai-bubble ai-bubble-user">
                    {m.content}
                  </Box>
                ) : (
                  <Box key={i} mb="sm">
                    {(m.skills?.length ?? 0) > 0 && <SkillActivationCard skills={m.skills!} />}
                    <Box
                      className="ai-bubble ai-bubble-assistant"
                      style={m.error ? { border: '1px solid #fca5a5', background: '#fef2f2', color: '#b91c1c' } : undefined}
                    >
                      {m.content || (streaming && i === messages.length - 1 ? '思考中…' : '')}
                    </Box>
                    {m.content && !m.error && (
                      <Group gap={2} mt={2} justify="flex-end">
                        <Tooltip label={copiedIndex === i ? '已复制' : '复制回答'}>
                          <ActionIcon
                            size="xs"
                            variant="subtle"
                            color="gray"
                            aria-label="复制回答"
                            onClick={() => copyMessage(i, m.content)}
                          >
                            {copiedIndex === i ? <IconCheck size={12} /> : <IconCopy size={12} />}
                          </ActionIcon>
                        </Tooltip>
                      </Group>
                    )}
                  </Box>
                ),
              )}
            </Box>
          )}
        </ScrollArea>

        {/* 输入区：候选技能条 + 输入框 */}
        <Box px="sm" py="sm" style={{ borderTop: '1px solid #f3f4f6', background: 'rgba(249,250,251,.5)' }}>
          {candidates.length > 0 && (
            <Group gap={4} mb={6} wrap="wrap">
              {candidates.map((c) => (
                <Tooltip
                  key={c.code}
                  withArrow
                  events={{ hover: true, focus: true, touch: false }}
                  label={
                    <Box style={{ maxWidth: 240, fontSize: 11 }}>
                      <div style={{ fontWeight: 700 }}>{c.name}</div>
                      <div>{c.description}</div>
                      {c.reasons.length > 0 && (
                        <div style={{ opacity: 0.75, marginTop: 2 }}>{c.reasons.join(' · ')}</div>
                      )}
                    </Box>
                  }
                >
                  <button
                    type="button"
                    className="ai-skill-pill"
                    onClick={() => toggleCandidate(c.code)}
                    style={{
                      ...pillStyle(c.selected),
                      cursor: 'pointer',
                    }}
                  >
                    <IconSparkles size={10} />
                    {c.name}
                    {c.score < 999 && <span style={{ opacity: 0.7 }}>{c.score}</span>}
                  </button>
                </Tooltip>
              ))}
            </Group>
          )}
          <Group align="flex-end" gap="xs" wrap="nowrap">
            <Textarea
              flex={1}
              autosize
              minRows={2}
              maxRows={5}
              radius="lg"
              placeholder={`与 ${assistant?.name ?? '通用硬件助手'} 对话，Enter 发送，Shift+Enter 换行`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            {streaming ? (
              <Button
                onClick={stop}
                variant="light"
                color="red"
                px="sm"
                style={{ borderRadius: 12 }}
                leftSection={<IconPlayerStop size={15} />}
              >
                停止
              </Button>
            ) : (
              <Button
                onClick={send}
                disabled={!sourceReady}
                px="sm"
                className="ai-gradient"
                style={{ borderRadius: 12, border: 0 }}
                leftSection={<IconSend size={15} />}
              >
                发送
              </Button>
            )}
          </Group>
        </Box>
      </Box>

      {/* ===== 右：设计数据 ===== */}
      <Box style={{ flex: 1, minWidth: 0, height: '100%' }} visibleFrom="md">
        {source === 'project' && projectId ? (
          <DesignDataTabs projectId={projectId} />
        ) : (
          <Paper withBorder p="xl" h="100%" radius="lg">
            <Text c="dimmed" ta="center" mt="xl">
              {source === 'live'
                ? '实时连接的设计数据可在「Altium 连接」页的实时面板中查看；本页只将实时摘要作为对话上下文。'
                : '在左侧选择「离线解析工程」后，这里显示原理图/PCB 预览与元件、网络、BOM 数据。'}
              <br />
              也可在「工程文件」页上传 Altium 工程。
            </Text>
          </Paper>
        )}
      </Box>
    </Group>
  )
}

function pillStyle(active: boolean): React.CSSProperties {
  return {
    borderWidth: 1,
    borderStyle: 'solid',
    boxShadow: 'none',
    ...(active
      ? { background: '#dbeafe', borderColor: '#93c5fd', color: '#1d4ed8' }
      : { background: '#f9fafb', borderColor: '#e5e7eb', color: '#6b7280' }),
  }
}
