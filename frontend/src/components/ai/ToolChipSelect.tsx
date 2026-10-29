import { Chip, ChipGroup, Group, Text } from '@mantine/core'

export interface ToolInfo {
  name: string
  description: string
  category: string
  requiresConfirmation: boolean
}

interface ToolChipSelectProps {
  tools: ToolInfo[]
  value: string[]
  onChange: (value: string[]) => void
  hint?: string
}

/**
 * 工具子集选择器：来自 `GET /ai/tools/registry` 的真实工具清单。
 * 空选 = 不限制；已保存但注册表里暂不存在的工具仍会保留为可取消的胶囊。
 */
export function ToolChipSelect({ tools, value, onChange, hint }: ToolChipSelectProps) {
  const known = new Set(tools.map((t) => t.name))
  const unknown = value.filter((v) => !known.has(v))

  return (
    <Group gap={6} wrap="wrap">
      <ChipGroup multiple value={value} onChange={onChange}>
        {tools.map((t) => (
          <Chip key={t.name} value={t.name} size="xs" radius="md" title={t.description}>
            {t.name}
          </Chip>
        ))}
        {unknown.map((name) => (
          <Chip key={name} value={name} size="xs" radius="md" color="gray" title="该工具当前未注册">
            {name}
          </Chip>
        ))}
      </ChipGroup>
      <Text size="10px" c="dimmed">
        {hint ?? `留空=全部（当前 ${tools.length} 个可用）`}
      </Text>
    </Group>
  )
}
