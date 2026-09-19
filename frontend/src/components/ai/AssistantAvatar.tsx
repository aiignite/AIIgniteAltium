import { AvatarIcon } from './avatarIcons'

interface AssistantAvatarProps {
  avatar?: string
  size?: number
  iconSize?: number
  radius?: number
}

/** AIIgnitePLM 风格渐变头像（blue-500 → indigo-600） */
export function AssistantAvatar({ avatar, size = 32, iconSize = 16, radius = 10 }: AssistantAvatarProps) {
  return (
    <div className="ai-avatar" style={{ width: size, height: size, borderRadius: radius }}>
      <AvatarIcon id={avatar} size={iconSize} />
    </div>
  )
}
