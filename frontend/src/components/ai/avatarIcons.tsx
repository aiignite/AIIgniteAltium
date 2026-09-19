import { createElement } from 'react'
import {
  IconBolt,
  IconBook,
  IconBrain,
  IconBulb,
  IconChartBar,
  IconCircuitBattery,
  IconClipboardCheck,
  IconCpu,
  IconFlask,
  IconMessageChatbot,
  IconRobot,
  IconRocket,
  IconSearch,
  IconSettings,
  IconSparkles,
  IconTool,
} from '@tabler/icons-react'

export type AIIcon = React.FC<{ size?: number | string; stroke?: number | string; color?: string }>

/** 助手/技能可选图标（对齐 AIIgnitePLM AVATAR_OPTIONS 的 id 约定） */
export const AVATAR_OPTIONS: { id: string; icon: AIIcon; label: string }[] = [
  { id: 'bot', icon: IconRobot, label: '机器人' },
  { id: 'sparkles', icon: IconSparkles, label: '通用' },
  { id: 'cpu', icon: IconCpu, label: '技术' },
  { id: 'circuit', icon: IconCircuitBattery, label: '电路' },
  { id: 'clipboard', icon: IconClipboardCheck, label: '审查' },
  { id: 'bulb', icon: IconBulb, label: '创意' },
  { id: 'chart', icon: IconChartBar, label: '分析' },
  { id: 'brain', icon: IconBrain, label: '智能' },
  { id: 'tool', icon: IconTool, label: '工具' },
  { id: 'bolt', icon: IconBolt, label: '高效' },
  { id: 'flask', icon: IconFlask, label: '实验' },
  { id: 'rocket', icon: IconRocket, label: '项目' },
  { id: 'book', icon: IconBook, label: '知识' },
  { id: 'search', icon: IconSearch, label: '检索' },
  { id: 'chat', icon: IconMessageChatbot, label: '对话' },
  { id: 'settings', icon: IconSettings, label: '配置' },
]

export function getAvatarIcon(id?: string): AIIcon {
  return AVATAR_OPTIONS.find((o) => o.id === id)?.icon ?? IconRobot
}

interface AvatarIconProps {
  id?: string
  size?: number
  stroke?: number
  color?: string
}

/** 按 id 渲染图标（createElement 避免在渲染期动态创建组件） */
export function AvatarIcon({ id, size = 16, stroke = 1.8, color }: AvatarIconProps) {
  return createElement(getAvatarIcon(id), { size, stroke, color })
}
