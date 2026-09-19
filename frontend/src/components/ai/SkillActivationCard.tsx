import { useState } from 'react'
import { IconChevronDown, IconSparkles } from '@tabler/icons-react'

export interface ActivatedSkillInfo {
  code: string
  name: string
  description?: string
  score?: number
  reasons?: string[]
}

interface SkillActivationCardProps {
  skills: ActivatedSkillInfo[]
}

/** 复刻 AIIgnitePLM SkillActivationCard：消息内“已激活 N 个技能”绿色卡片 */
export function SkillActivationCard({ skills }: SkillActivationCardProps) {
  const [expanded, setExpanded] = useState(false)
  if (skills.length === 0) return null

  return (
    <div className="ai-skill-card" style={{ marginBottom: 8, fontSize: 11, padding: '6px 10px' }}>
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          width: '100%',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          color: '#047857',
          fontWeight: 600,
          fontSize: 11,
        }}
      >
        <IconSparkles size={12} />
        已激活 {skills.length} 个技能
        <IconChevronDown
          size={12}
          style={{ marginLeft: 'auto', transition: 'transform .15s', transform: expanded ? 'rotate(180deg)' : 'none' }}
        />
      </button>
      {expanded && (
        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
          {skills.map((s) => (
            <div key={s.code} style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <span
                style={{
                  background: '#d1fae5',
                  borderRadius: 6,
                  padding: '1px 6px',
                  fontWeight: 700,
                  fontSize: 10,
                }}
              >
                {s.name}
              </span>
              {typeof s.score === 'number' && (
                <span style={{ fontSize: 10, color: '#059669' }}>匹配度 {s.score}</span>
              )}
              {s.description && (
                <span style={{ fontSize: 10, color: '#047857', opacity: 0.85 }}>{s.description}</span>
              )}
              {s.reasons && s.reasons.length > 0 && (
                <span style={{ fontSize: 9, color: '#059669', opacity: 0.7 }}>{s.reasons.join(' · ')}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
