import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Box,
  Button,
  Grid,
  Group,
  Paper,
  ScrollArea,
  Select,
  Text,
  Textarea,
} from '@mantine/core'
import { api, streamChat, type ChatStreamEvent } from '../api/client'
import { DesignDataTabs } from '../components/DesignDataTabs'

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
}

export function WorkbenchPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [projectId, setProjectId] = useState<string | null>(null)
  const [skills, setSkills] = useState<{ id: string; name: string }[]>([])
  const [skill, setSkill] = useState<string>('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const viewportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.get<ProjectSummary[]>('/files/projects').then((ps) => {
      const ready = ps.filter((p) => p.status === 'ready')
      setProjects(ready)
      if (ready.length > 0) setProjectId((prev) => prev ?? ready[0].id)
    })
    api.get<{ id: string; name: string }[]>('/ai/skills').then(setSkills)
  }, [])

  useEffect(() => {
    viewportRef.current?.scrollTo({ top: viewportRef.current.scrollHeight })
  }, [messages])

  const send = useCallback(async () => {
    const content = input.trim()
    if (!content || streaming) return
    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content }, { role: 'assistant', content: '' }])
    setStreaming(true)
    await streamChat(
      {
        content,
        conversationId,
        projectId: projectId || null,
        skill: skill || null,
      },
      (event: ChatStreamEvent) => {
        if (event.type === 'meta' && event.conversationId) setConversationId(event.conversationId)
        if (event.type === 'delta' && event.text)
          setMessages((prev) => {
            const next = [...prev]
            next[next.length - 1] = {
              role: 'assistant',
              content: next[next.length - 1].content + event.text,
            }
            return next
          })
        if (event.type === 'error')
          setMessages((prev) => {
            const next = [...prev]
            next[next.length - 1] = { role: 'assistant', content: event.message ?? '出错了', error: true }
            return next
          })
        if (event.type === 'done') setStreaming(false)
      },
    )
    setStreaming(false)
  }, [input, streaming, conversationId, projectId, skill])

  return (
    <Grid gap="md" style={{ height: 'calc(100vh - 90px)' }}>
      <Grid.Col span={{ base: 12, md: 5 }} style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <Group mb="xs" grow>
          <Select
            placeholder="关联设计工程"
            data={projects.map((p) => ({ value: p.id, label: `${p.name}（${p.stats.componentCount ?? 0} 元件）` }))}
            value={projectId}
            onChange={setProjectId}
            allowDeselect
            clearable
          />
          <Select
            placeholder="技能"
            data={[{ value: '', label: '通用助手' }, ...skills.filter((s) => s.id).map((s) => ({ value: s.id, label: s.name }))]}
            value={skill}
            onChange={(v) => setSkill(v ?? '')}
          />
        </Group>
        <Paper withBorder p="sm" style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
          <ScrollArea style={{ flex: 1 }} viewportRef={viewportRef} offsetScrollbars>
            {messages.length === 0 && (
              <Text c="dimmed" size="sm" ta="center" mt="xl">
                选择工程与技能，开始对话。例如：「帮我审查这个工程的原理图」
              </Text>
            )}
            {messages.map((m, i) => (
              <Box
                key={i}
                p="xs"
                mb="xs"
                className={m.role === 'user' ? 'chat-message-user' : 'chat-message-assistant'}
                style={{ borderRadius: 10, whiteSpace: 'pre-wrap', fontSize: 13.5, border: m.error ? '1px solid var(--mantine-color-red-3)' : undefined }}
              >
                {m.content}
              </Box>
            ))}
            {streaming && messages[messages.length - 1]?.content === '' && <Text size="sm" c="dimmed">思考中…</Text>}
          </ScrollArea>
          <Group mt="xs" align="flex-end" gap="xs">
            <Textarea
              flex={1}
              autosize
              minRows={2}
              maxRows={5}
              placeholder="输入消息，Enter 发送"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <Button onClick={send} loading={streaming}>
              发送
            </Button>
            <Button
              variant="light"
              onClick={() => {
                setMessages([])
                setConversationId(null)
              }}
            >
              新对话
            </Button>
          </Group>
        </Paper>
      </Grid.Col>

      <Grid.Col span={{ base: 12, md: 7 }} style={{ minHeight: 0 }}>
        {projectId ? (
          <DesignDataTabs projectId={projectId} />
        ) : (
          <Paper withBorder p="xl" h="100%">
            <Text c="dimmed" ta="center">
              在左侧选择已解析的工程后，这里显示原理图/PCB 预览与元件、网络、BOM 数据。
              <br />
              前往「工程文件」页上传 Altium 工程。
            </Text>
          </Paper>
        )}
      </Grid.Col>
    </Grid>
  )
}
