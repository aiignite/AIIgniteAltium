import { Box, Group, Tabs } from '@mantine/core'
import { IconBrain, IconCpu, IconSparkles } from '@tabler/icons-react'
import { useSearchParams } from 'react-router-dom'
import { AssistantsPanel } from './ai/AssistantsPanel'
import { ModelsPanel } from './ai/ModelsPanel'
import { SkillsPanel } from './ai/SkillsPanel'

const TABS = ['models', 'assistants', 'skills'] as const

/** AI 配置中心：模型 / 助手 / 技能（三者强关联，同页减少跳转）。 */
export function AIConfigPage() {
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab') ?? 'models'
  const tab = (TABS as readonly string[]).includes(raw) ? raw : 'models'

  return (
    <Box>
      <Group justify="space-between" mb="md">
        <Tabs
          value={tab}
          onChange={(value) => {
            const next = new URLSearchParams(params)
            next.set('tab', value ?? 'models')
            setParams(next, { replace: true })
          }}
          variant="pills"
          radius="lg"
        >
          <Tabs.List>
            <Tabs.Tab value="models" leftSection={<IconCpu size={16} />}>
              大模型
            </Tabs.Tab>
            <Tabs.Tab value="assistants" leftSection={<IconBrain size={16} />}>
              助手
            </Tabs.Tab>
            <Tabs.Tab value="skills" leftSection={<IconSparkles size={16} />}>
              技能
            </Tabs.Tab>
          </Tabs.List>
        </Tabs>
      </Group>

      {tab === 'models' && <ModelsPanel />}
      {tab === 'assistants' && <AssistantsPanel />}
      {tab === 'skills' && <SkillsPanel />}
    </Box>
  )
}
