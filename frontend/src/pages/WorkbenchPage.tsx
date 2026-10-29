import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  ActionIcon,
  Box,
  Button,
  Card,
  Group,
  Loader,
  Paper,
  ScrollArea,
  Select,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import {
  IconCheck,
  IconCopy,
  IconHistory,
  IconPlayerStop,
  IconPlus,
  IconSearch,
  IconSend,
  IconSparkles,
  IconX,
} from '@tabler/icons-react'
import { useNavigate } from 'react-router-dom'
import { api, streamChat, type ActivatedSkill, type ChatStreamEvent } from '../api/client'
import { DesignDataTabs } from '../components/DesignDataTabs'
import { AssistantPicker, type AssistantItem } from '../components/ai/AssistantPicker'
import { AssistantAvatar } from '../components/ai/AssistantAvatar'
import { ModelPicker } from '../components/ai/ModelPicker'
import type { AIModelItem } from '../components/ai/types'
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
  /** 错误分类（no_model 时展示"去配置模型"入口） */
  code?: string
  skills?: ActivatedSkill[]
  assistantName?: string
  /** 本条回答实际使用的模型（meta 事件下发） */
  modelName?: string
  provider?: string
  /** 工具调用日志（tool_call / tool_result） */
  toolLog?: ToolLogEntry[]
  /** 待确认的写操作（tool_confirmation_required） */
  confirmation?: ConfirmationRequest | null
}

interface ToolLogEntry {
  name: string
  params?: Record<string, unknown>
  result?: unknown
}

interface ConfirmationRequest {
  tool: string
  params: Record<string, unknown>
  preview?: string
  /** 确认执行后的结果/错误 */
  result?: unknown
  error?: string
  executing?: boolean
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

const PREFS_KEY = 'aidrive.workbench.prefs'

const FOLLOW_UPS = ['继续深入分析主要风险', '给出整改与验证清单', '解释关键网络的设计意图']

interface WorkbenchPrefs {
  source?: SourceKind
  projectId?: string | null
  connectionId?: string | null
  assistantId?: string | null
  modelId?: string | null
}

function loadPrefs(): WorkbenchPrefs {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as WorkbenchPrefs
  } catch {
    return {}
  }
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

function resultText(r: unknown): string {
  if (typeof r === 'string') return r
  if (r === undefined || r === null) return ''
  try {
    return JSON.stringify(r)
  } catch {
    return String(r)
  }
}

function isToolOk(r: unknown): boolean {
  if (r && typeof r === 'object') {
    const rec = r as { ok?: unknown; success?: unknown; error?: unknown }
    if (rec.error) return false
    if (rec.ok === true || rec.success === true) return true
  }
  return true
}

export function WorkbenchPage() {
  const navigate = useNavigate()
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
  const [historyQuery, setHistoryQuery] = useState('')
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [searchParams] = useSearchParams()
  const viewportRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  const abortRef = useRef<AbortController | null>(null)
  const pendingAsk = useRef(searchParams.get('ask'))

  // 实时 Altium 连接：有在线网关时，右侧优先显示 Altium 当前打开的 PCB。
  const [liveConnId, setLiveConnId] = useState<string | null>(null)

  const assistant = useMemo(
    () => assistants.find((a) => a.id === assistantId) ?? assistants.find((a) => a.isDefault) ?? null,
    [assistants, assistantId],
  )

  const loadConversations = useCallback(() => {
    api.get<ConversationItem[]>('/ai/conversations').then(setConversations).catch(() => {})
  }, [])

  useEffect(() => {
    const prefs = loadPrefs()
    const explicitProject = searchParams.get('projectId')
    const explicitConnection = searchParams.get('connectionId')
    const projectParam =
      explicitProject ?? (!explicitConnection && prefs.source === 'project' ? prefs.projectId ?? null : null)
    const connectionParam =
      explicitConnection ?? (!explicitProject && prefs.source === 'live' ? prefs.connectionId ?? null : null)
    api.get<ProjectSummary[]>('/files/projects').then((ps) => {
      const ready = ps.filter((p) => p.status === 'ready')
      setProjects(ready)
      if (projectParam && ready.some((p) => p.id === projectParam)) {
        setSource('project')
        setProjectId(projectParam)
      } else if (explicitProject && pendingAsk.current) {
        setInput(pendingAsk.current)
        pendingAsk.current = null
      }
    })
    api
      .get<ConnectionItem[]>('/altium/connections')
      .then((list) => {
        setConnections(list)
        if (connectionParam && list.some((c) => c.id === connectionParam)) {
          setSource('live')
          setConnectionId(connectionParam)
        } else if (explicitConnection && pendingAsk.current) {
          setInput(pendingAsk.current)
          pendingAsk.current = null
        }
      })
      .catch(() => setConnections([]))
    api.get<AssistantItem[]>('/ai/assistants').then((list) => {
      setAssistants(list.filter((a) => a.enabled))
      setAssistantId((prev) => {
        if (prev) return prev
        const saved = prefs.assistantId && list.some((a) => a.enabled && a.id === prefs.assistantId) ? prefs.assistantId : null
        return saved ?? list.find((a) => a.isDefault)?.id ?? list[0]?.id ?? null
      })
    })
    api.get<SkillItem[]>('/ai/skills').then((list) => setSkills(list.filter((s) => s.enabled)))
    api.get<AIModelItem[]>('/ai/models').then((list) => {
      const enabled = list.filter((m) => m.enabled)
      setModels(enabled)
      setModelId(enabled.find((m) => m.id === prefs.modelId)?.id ?? enabled[0]?.id ?? null)
    })
    loadConversations()
  }, [loadConversations, searchParams])

  // 轮询检测实时网关连接：在线则右侧显示 Altium 当前打开的 PCB。
  useEffect(() => {
    const check = () =>
      api
        .get<{ connected: boolean; id?: string }>('/altium/connections/first-connected')
        .then((c) => setLiveConnId(c?.connected ? (c.id ?? null) : null))
        .catch(() => setLiveConnId(null))
    check()
    const t = window.setInterval(check, 5000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    localStorage.setItem(
      PREFS_KEY,
      JSON.stringify({ source, projectId, connectionId, assistantId: assistant?.id ?? null, modelId }),
    )
  }, [source, projectId, connectionId, assistant?.id, modelId])

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

  const sourceName = useCallback(
    (c: ConversationItem) => {
      if (c.projectId) return projects.find((p) => p.id === c.projectId)?.name ?? '工程已删除'
      if (c.connectionId) return connections.find((x) => x.id === c.connectionId)?.name ?? '连接已失效'
      return '无设计'
    },
    [projects, connections],
  )

  const visibleConversations = useMemo(() => {
    const q = historyQuery.trim().toLowerCase()
    return q ? conversations.filter((c) => c.title.toLowerCase().includes(q)) : conversations
  }, [conversations, historyQuery])

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
  const requestedProject = searchParams.get('projectId')
  const requestedConnection = searchParams.get('connectionId')

  const send = useCallback(async (override?: string) => {
    const content = (override ?? input).trim()
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
            setMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (!last) return prev
              next[next.length - 1] = { ...last, modelName: event.modelName, provider: event.provider }
              return next
            })
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
          if (event.type === 'tool_call' && event.tool) {
            setMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (!last) return prev
              next[next.length - 1] = {
                ...last,
                toolLog: [...(last.toolLog ?? []), { name: event.tool!, params: event.params }],
              }
              return next
            })
          }
          if (event.type === 'tool_result' && event.tool) {
            setMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (!last) return prev
              const log = last.toolLog ?? []
              const idx = log.map((l) => l.name).lastIndexOf(event.tool!)
              if (idx < 0) {
                next[next.length - 1] = { ...last, toolLog: [...log, { name: event.tool!, result: event.result }] }
              } else {
                const updated = [...log]
                updated[idx] = { ...updated[idx], result: event.result }
                next[next.length - 1] = { ...last, toolLog: updated }
              }
              return next
            })
          }
          if (event.type === 'tool_confirmation_required' && event.tool) {
            setMessages((prev) => {
              const next = [...prev]
              const last = next[next.length - 1]
              if (!last) return prev
              next[next.length - 1] = {
                ...last,
                confirmation: { tool: event.tool!, params: event.params ?? {}, preview: event.preview },
              }
              return next
            })
          }
          if (event.type === 'error')
            setMessages((prev) => {
              const next = [...prev]
              next[next.length - 1] = {
                ...next[next.length - 1],
                content: event.message ?? '出错了',
                error: true,
                code: event.code,
              }
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

  useEffect(() => {
    const question = pendingAsk.current
    if (!question || streaming || !sourceReady) return
    if (requestedProject && projectId !== requestedProject) return
    if (requestedConnection && connectionId !== requestedConnection) return
    pendingAsk.current = null
    void send(question)
  }, [streaming, sourceReady, send, requestedProject, requestedConnection, projectId, connectionId])

  // 写操作确认：直连后端命令代理执行（confirmed=true）
  const confirmTool = useCallback(
    async (i: number, conf: ConfirmationRequest) => {
      if (streaming) return
      setStreaming(true)
      const finish = (patch: { result?: unknown; error?: string }) =>
        setMessages((prev) => {
          const next = [...prev]
          const m = next[i]
          if (m?.confirmation)
            next[i] = { ...m, confirmation: { ...m.confirmation, executing: false, ...patch } }
          return next
        })
      try {
        const conn = await api.get<{ connected: boolean; id?: string }>('/altium/connections/first-connected')
        if (!conn.connected || !conn.id) {
          finish({ error: '没有已连接的 Altium 网关（请先在「实时连接」页配置并测试连接）' })
          return
        }
        const payload = await api.post<Record<string, unknown>>(`/altium/connections/${conn.id}/command`, {
          name: conf.tool,
          params: { ...conf.params, confirmed: true },
        })
        finish({ result: payload })
      } catch (e) {
        finish({ error: e instanceof Error ? e.message : String(e) })
      } finally {
        setStreaming(false)
      }
    },
    [streaming],
  )

  const cancelTool = useCallback((i: number) => {
    setMessages((prev) => {
      const next = [...prev]
      const m = next[i]
      if (m?.confirmation) next[i] = { ...m, confirmation: null }
      return next
    })
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
            <ModelPicker
              models={models}
              value={modelId}
              onChange={setModelId}
              disabled={streaming}
              width={150}
              placeholder="默认模型"
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
            <ScrollArea.Autosize mah={240} mt={6}>
              <TextInput
                size="xs"
                mb={4}
                placeholder="搜索历史对话"
                leftSection={<IconSearch size={12} />}
                value={historyQuery}
                onChange={(e) => setHistoryQuery(e.target.value)}
              />
              {conversations.length === 0 && (
                <Text size="xs" c="dimmed" ta="center" py="sm">
                  暂无历史对话
                </Text>
              )}
              {conversations.length > 0 && visibleConversations.length === 0 && (
                <Text size="xs" c="dimmed" ta="center" py="sm">
                  没有匹配的对话
                </Text>
              )}
              {visibleConversations.map((c) => (
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
                      {sourceName(c)} · {assistants.find((a) => a.id === c.assistantId)?.name ?? '通用助手'} ·{' '}
                      {c.messageCount} 条 · {timeAgo(c.updatedAt)}
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
                      <button
                        key={s}
                        type="button"
                        className="ai-quick-chip"
                        onClick={() => (sourceReady ? send(s) : setInput(s))}
                      >
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
                    {m.modelName && (
                      <Text size="9px" c="dimmed" mb={2} ml={4}>
                        {m.provider} · {m.modelName}
                      </Text>
                    )}
                    <Box
                      className="ai-bubble ai-bubble-assistant"
                      style={m.error ? { border: '1px solid #fca5a5', background: '#fef2f2', color: '#b91c1c' } : undefined}
                    >
                      {m.content || (streaming && i === messages.length - 1 && !m.confirmation ? '思考中…' : '')}
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
                    {m.code === 'no_model' && (
                      <Button
                        mt={6}
                        size="compact-xs"
                        variant="light"
                        color="orange"
                        onClick={() => navigate('/ai-config?tab=models')}
                      >
                        去配置模型
                      </Button>
                    )}
                    {(m.toolLog?.length ?? 0) > 0 && (
                      <Box mt={4} style={{ fontSize: 11 }}>
                        {m.toolLog!.map((t, ti) => (
                          <Box
                            key={ti}
                            mb={2}
                            style={{
                              border: '1px solid #e5e7eb',
                              borderRadius: 8,
                              padding: '4px 8px',
                              background: '#f9fafb',
                            }}
                          >
                            <Text size="11px" fw={600}>
                              {t.name}
                            </Text>
                            {t.params && Object.keys(t.params).length > 0 && (
                              <Text size="10px" c="dimmed" style={{ wordBreak: 'break-all' }}>
                                参数：{JSON.stringify(t.params)}
                              </Text>
                            )}
                            {t.result !== undefined && (
                              <Text
                                size="10px"
                                c="dimmed"
                                style={{ wordBreak: 'break-all', color: isToolOk(t.result) ? '#047857' : undefined }}
                              >
                                结果：{resultText(t.result)}
                              </Text>
                            )}
                          </Box>
                        ))}
                      </Box>
                    )}
                    {m.confirmation && (
                      <Box
                        mt={6}
                        p="sm"
                        style={{
                          border: '1px solid #fbbf24',
                          background: '#fffbeb',
                          borderRadius: 10,
                          fontSize: 12,
                        }}
                      >
                        <Text size="11px" fw={700}>
                          写操作需要确认：{m.confirmation.tool}
                        </Text>
                        {Object.keys(m.confirmation.params).length > 0 && (
                          <Text size="10px" c="dimmed" style={{ wordBreak: 'break-all', marginTop: 2 }}>
                            参数：{JSON.stringify(m.confirmation.params)}
                          </Text>
                        )}
                        {m.confirmation.preview && (
                          <Text size="11px" style={{ marginTop: 4 }}>
                            预览：{m.confirmation.preview}
                          </Text>
                        )}
                        {m.confirmation.result !== undefined && (
                          <Text size="11px" style={{ marginTop: 4, color: isToolOk(m.confirmation.result) ? '#047857' : '#b91c1c' }}>
                            执行结果：{resultText(m.confirmation.result)}
                          </Text>
                        )}
                        {m.confirmation.error && (
                          <Text size="11px" style={{ marginTop: 4, color: '#b91c1c' }}>
                            {m.confirmation.error}
                          </Text>
                        )}
                        {m.confirmation.result === undefined && !m.confirmation.error && (
                          <Group gap={6} mt={6}>
                            <Button
                              size="compact-xs"
                              color="green"
                              loading={m.confirmation.executing}
                              onClick={() => confirmTool(i, m.confirmation!)}
                            >
                              确认执行
                            </Button>
                            <Button size="compact-xs" variant="subtle" color="gray" onClick={() => cancelTool(i)}>
                              取消
                            </Button>
                          </Group>
                        )}
                      </Box>
                    )}
                  </Box>
                ),
              )}
              {!streaming &&
                messages[messages.length - 1]?.role === 'assistant' &&
                !messages[messages.length - 1]?.error && (
                  <Group gap={4} mt="xs" wrap="wrap">
                    {FOLLOW_UPS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        className="ai-quick-chip"
                        disabled={!sourceReady}
                        onClick={() => send(q)}
                      >
                        {q}
                      </button>
                    ))}
                  </Group>
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
                if (e.key === 'Escape' && streaming) {
                  e.preventDefault()
                  stop()
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
                onClick={() => send()}
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
          <DesignDataTabs projectId={projectId} onAskAI={(question) => send(question)} />
        ) : source === 'live' && (connectionId ?? liveConnId) ? (
          <LiveAltiumPanel connectionId={(connectionId ?? liveConnId)!} />
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

interface LiveSummary {
  ok: boolean
  project?: string
  document?: { kind?: string; name?: string }
  pcbStats?: Record<string, number>
  board?: { widthMils?: number; heightMils?: number; layers?: number }
  schematic?: { componentCount?: number; netCount?: number }
  errors?: string[]
}

function LiveAltiumPanel({ connectionId }: { connectionId: string }) {
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
    const t = window.setInterval(load, 6000)
    return () => {
      window.clearInterval(t)
      setScreenshot((p) => {
        if (p) URL.revokeObjectURL(p)
        return null
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionId])

  if (error) {
    return (
      <Paper withBorder p="md" radius="lg">
        <Text c="red" size="sm">实时连接不可用：{error}</Text>
      </Paper>
    )
  }
  if (loading && !summary) {
    return (
      <Group justify="center" h="100%">
        <Loader />
      </Group>
    )
  }
  return (
    <Box h="100%" style={{ overflow: 'auto' }}>
      <Group justify="space-between" mb="xs">
        <Text fw={600} truncate style={{ maxWidth: '78%' }}>
          {summary?.project ? `Altium 实时：${summary.project}` : 'Altium 实时（未打开工程）'}
        </Text>
        <Button size="compact-xs" variant="light" onClick={load}>
          刷新
        </Button>
      </Group>
      {summary?.document?.kind && (
        <Text size="sm" c="dimmed" mb="xs">
          活动文档：[{summary.document.kind}] {summary.document.name}
        </Text>
      )}
      {summary?.pcbStats && (
        <Group grow mb="sm">
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
      {summary?.board?.widthMils && (
        <Text size="xs" c="dimmed" mb="xs">
          板框：{summary.board.widthMils} × {summary.board.heightMils ?? '?'} mil，{summary.board.layers ?? '?'} 层
        </Text>
      )}
      {screenshot && (
        <div className="svg-viewer" style={{ border: '1px solid var(--mantine-color-gray-3)' }}>
          <img src={screenshot} alt="Altium 当前打开的设计" style={{ width: '100%' }} />
        </div>
      )}
    </Box>
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
