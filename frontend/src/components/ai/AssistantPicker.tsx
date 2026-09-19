import { useRef, useState } from 'react'
import { IconCheck, IconChevronDown, IconSearch } from '@tabler/icons-react'
import { AssistantAvatar } from './AssistantAvatar'

export interface AssistantItem {
  id: string
  name: string
  description: string
  avatar: string
  isDefault: boolean
  isSystem?: boolean
  enabled?: boolean
  skillCodes?: string[]
}

interface AssistantPickerProps {
  assistants: AssistantItem[]
  selectedId: string | null
  onSelect: (assistant: AssistantItem) => void
}

/** 复刻 AIIgnitePLM AiAssistantPickerMenu：搜索 + 助手列表 + 默认徽标 */
export function AssistantPicker({ assistants, selectedId, onSelect }: AssistantPickerProps) {
  const [opened, setOpened] = useState(false)
  const [query, setQuery] = useState('')
  const blurTimer = useRef<number | undefined>(undefined)

  const filtered = assistants.filter(
    (a) =>
      a.name.toLowerCase().includes(query.toLowerCase()) ||
      (a.description ?? '').toLowerCase().includes(query.toLowerCase()),
  )

  const selected = assistants.find((a) => a.id === selectedId) ?? assistants.find((a) => a.isDefault) ?? assistants[0]

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        onClick={() => setOpened((o) => !o)}
        onBlur={() => {
          blurTimer.current = window.setTimeout(() => setOpened(false), 150)
        }}
        onFocus={() => window.clearTimeout(blurTimer.current)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '5px 10px 5px 6px',
          borderRadius: 12,
          border: '1px solid #e5e7eb',
          background: '#fff',
          cursor: 'pointer',
          maxWidth: 320,
        }}
      >
        <AssistantAvatar avatar={selected?.avatar} size={30} iconSize={15} />
        <div style={{ textAlign: 'left', minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#111827', whiteSpace: 'nowrap' }}>
              {selected?.name ?? '通用助手'}
            </span>
            <IconChevronDown size={13} color="#9ca3af" style={{ flexShrink: 0 }} />
          </div>
          <div
            style={{
              fontSize: 10,
              color: '#6b7280',
              maxWidth: 220,
              overflow: 'hidden',
              whiteSpace: 'nowrap',
              textOverflow: 'ellipsis',
            }}
          >
            {selected?.description || '硬件设计 AI 助手'}
          </div>
        </div>
      </button>

      {opened && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            zIndex: 60,
            width: 288,
            overflow: 'hidden',
            borderRadius: 12,
            border: '1px solid #e5e7eb',
            background: '#fff',
            boxShadow: '0 20px 25px -5px rgba(0,0,0,.1), 0 8px 10px -6px rgba(0,0,0,.1)',
          }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <div style={{ padding: 8 }}>
            <div
              style={{
                fontSize: 10,
                fontWeight: 500,
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                color: '#9ca3af',
                padding: '4px 8px 4px',
              }}
            >
              选择助手
            </div>
            <div style={{ position: 'relative', padding: '0 8px 6px' }}>
              <IconSearch
                size={12}
                color="#9ca3af"
                style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)' }}
              />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="搜索助手名称..."
                autoFocus
                style={{
                  width: '100%',
                  boxSizing: 'border-box',
                  borderRadius: 8,
                  border: '1px solid #e5e7eb',
                  background: '#f9fafb',
                  padding: '6px 12px 6px 28px',
                  fontSize: 12,
                  color: '#111827',
                  outline: 'none',
                }}
              />
            </div>
            {filtered.length === 0 && (
              <div style={{ padding: '24px 0', textAlign: 'center', fontSize: 12, color: '#64748b' }}>暂无助手</div>
            )}
            <div style={{ maxHeight: 280, overflowY: 'auto' }}>
              {filtered.map((a) => {
                const isSelected = a.id === selectedId
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => {
                      onSelect(a)
                      setOpened(false)
                      setQuery('')
                    }}
                    style={{
                      display: 'flex',
                      width: '100%',
                      alignItems: 'center',
                      gap: 12,
                      borderRadius: 8,
                      padding: '10px 12px',
                      textAlign: 'left',
                      cursor: 'pointer',
                      border: 'none',
                      background: isSelected ? '#eff6ff' : 'transparent',
                      color: isSelected ? '#2563eb' : 'inherit',
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.background = '#f9fafb'
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    <AssistantAvatar avatar={a.avatar} size={32} iconSize={14} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <p
                        style={{
                          margin: 0,
                          fontSize: 14,
                          fontWeight: 500,
                          overflow: 'hidden',
                          whiteSpace: 'nowrap',
                          textOverflow: 'ellipsis',
                          color: isSelected ? '#2563eb' : '#111827',
                        }}
                      >
                        {a.name || '未命名助手'}
                      </p>
                      <p
                        style={{
                          margin: 0,
                          fontSize: 10,
                          color: '#6b7280',
                          overflow: 'hidden',
                          whiteSpace: 'nowrap',
                          textOverflow: 'ellipsis',
                        }}
                      >
                        {a.description || ' '}
                      </p>
                    </div>
                    {isSelected && <IconCheck size={14} color="#2563eb" style={{ flexShrink: 0 }} />}
                    {a.isDefault && (
                      <span
                        className="ai-badge ai-badge-default"
                        style={{ flexShrink: 0 }}
                      >
                        默认
                      </span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
