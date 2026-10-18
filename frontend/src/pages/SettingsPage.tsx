import { useEffect, useState } from 'react'
import { Badge, Box, Button, Group, Paper, SimpleGrid, Text, ThemeIcon } from '@mantine/core'
import {
  IconArrowRight,
  IconBrain,
  IconDatabase,
  IconLock,
  IconPlugConnected,
} from '@tabler/icons-react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { AIModelItem } from '../components/ai/types'

export function SettingsPage() {
  const navigate = useNavigate()
  const [models, setModels] = useState<AIModelItem[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .get<AIModelItem[]>('/ai/models')
      .then(setModels)
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
  }, [])

  const enabled = models.filter((m) => m.enabled)
  const withKey = models.filter((m) => m.hasKey || m.provider === 'mock')
  const defaultModel = models.find((m) => m.isDefault)

  return (
    <Box>
      <Paper radius="xl" p="lg" mb="md" withBorder>
        <Group justify="space-between" wrap="nowrap">
          <Box>
            <Group gap="xs">
              <ThemeIcon size={36} radius={10} variant="light" color="orange">
                <IconBrain size={20} />
              </ThemeIcon>
              <Text fw={800} size="lg">
                AI 平台
              </Text>
            </Group>
            <Text size="sm" c="dimmed" mt={6} maw={620}>
              模型配置、助手人设与技能库统一在「AI 配置」中维护。密钥加密存储，界面与导出均只显示掩码。
            </Text>
            <Group gap="xs" mt="sm">
              <Badge variant="light" color="orange">
                模型 {models.length}
              </Badge>
              <Badge variant="light" color="green">
                启用 {enabled.length}
              </Badge>
              <Badge variant="light" color="blue">
                可用 {withKey.length}
              </Badge>
              <Badge variant="light" color="yellow">
                默认 {defaultModel?.name ?? '未设置'}
              </Badge>
            </Group>
          </Box>
          <Button
            rightSection={<IconArrowRight size={16} />}
            onClick={() => navigate('/ai-config?tab=models')}
            style={{ background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)', border: 0 }}
          >
            打开 AI 配置
          </Button>
        </Group>
      </Paper>

      {error && (
        <Text size="xs" c="red.7" mb="sm">
          {error}
        </Text>
      )}

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        <SettingCard
          icon={<IconPlugConnected size={18} />}
          title="模型与路由"
          desc="Provider、Base URL、采样参数、工具/图像能力；请求按「请求 → 会话 → 助手 → 默认」解析。"
          action="管理模型"
          onClick={() => navigate('/ai-config?tab=models')}
        />
        <SettingCard
          icon={<IconLock size={18} />}
          title="密钥安全"
          desc="API Key 写入即加密（enc:v1），列表仅回传尾号掩码；历史明文在启动时自动升级。"
          action="查看模型"
          onClick={() => navigate('/ai-config?tab=models')}
        />
        <SettingCard
          icon={<IconDatabase size={18} />}
          title="数据与迁移"
          desc="新增列由幂等 ALTER 保证；可执行 backend/scripts/migrate_ai_platform.py 单独重放。"
          action="查看助手"
          onClick={() => navigate('/ai-config?tab=assistants')}
        />
      </SimpleGrid>
    </Box>
  )
}

interface SettingCardProps {
  icon: React.ReactNode
  title: string
  desc: string
  action: string
  onClick: () => void
}

function SettingCard({ icon, title, desc, action, onClick }: SettingCardProps) {
  return (
    <Paper withBorder radius="lg" p="md">
      <Group gap="xs" mb={6}>
        <ThemeIcon size={30} radius={8} variant="light" color="gray">
          {icon}
        </ThemeIcon>
        <Text size="sm" fw={700}>
          {title}
        </Text>
      </Group>
      <Text size="xs" c="dimmed" mih={54}>
        {desc}
      </Text>
      <Button size="compact-xs" variant="light" mt="sm" onClick={onClick}>
        {action}
      </Button>
    </Paper>
  )
}
