import { useState } from 'react'
import type { ReactNode } from 'react'
import { Alert, Badge, Button, Card, Group, SimpleGrid, Text, Tooltip } from '@mantine/core'
import {
  IconFileCode,
  IconFileSpreadsheet,
  IconFileText,
  IconNetwork,
  IconPackage,
  IconCrosshair,
} from '@tabler/icons-react'
import { api } from '../api/client'
import { safeFilename, triggerDownload } from '../utils/download'

interface ExportItem {
  key: string
  label: string
  hint: string
  path: string
  suffix: string
  icon: ReactNode
  requiresPcb?: boolean
}

export function ExportPanel({
  projectId,
  projectName,
  version,
  hasPcb,
}: {
  projectId: string
  projectName: string
  version: number
  hasPcb: boolean
}) {
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  const items: ExportItem[] = [
    {
      key: 'bom-merged',
      label: '合并 BOM',
      hint: '按 值/封装/DNP 合并，含数量与位号',
      path: `/files/projects/${projectId}/exports/bom?merged=true`,
      suffix: '.csv',
      icon: <IconFileSpreadsheet size={14} />,
    },
    {
      key: 'bom-detail',
      label: 'BOM 明细',
      hint: '每个位号一行，含图纸与 DNP 标记',
      path: `/files/projects/${projectId}/exports/bom?merged=false`,
      suffix: '.csv',
      icon: <IconFileText size={14} />,
    },
    {
      key: 'nets',
      label: '网络表',
      hint: '网络名、连接数与端接明细',
      path: `/files/projects/${projectId}/exports/nets`,
      suffix: '.csv',
      icon: <IconNetwork size={14} />,
    },
    {
      key: 'package',
      label: '输出包',
      hint: 'BOM、网络表、清单、design.json 与渲染图 ZIP',
      path: `/files/projects/${projectId}/exports/package`,
      suffix: '.zip',
      icon: <IconPackage size={14} />,
    },
    {
      key: 'pnp',
      label: '贴片坐标',
      hint: '从 .PcbDoc 生成贴片坐标 CSV（mm）',
      path: `/files/projects/${projectId}/exports/pnp`,
      suffix: '.csv',
      icon: <IconCrosshair size={14} />,
      requiresPcb: true,
    },
    {
      key: 'outjob',
      label: 'Gerber 配置',
      hint: 'Altium OutJob：Gerber、NC Drill 与贴片输出',
      path: `/files/projects/${projectId}/exports/outjob`,
      suffix: '.OutJob',
      icon: <IconFileCode size={14} />,
      requiresPcb: true,
    },
  ]

  const run = async (item: ExportItem) => {
    if (busy) return
    setBusy(item.key)
    setError('')
    setDone('')
    try {
      const url = await api.blob(item.path)
      triggerDownload(url, `${safeFilename(projectName)}-${item.label}-v${version}${item.suffix}`)
      setDone(item.label)
      window.setTimeout(() => URL.revokeObjectURL(url), 1500)
    } catch (e) {
      setError(e instanceof Error ? e.message : '导出失败')
    } finally {
      setBusy('')
    }
  }

  return (
    <Card withBorder mt="md" p="md">
      <Group justify="space-between" mb="sm">
        <Group gap="xs">
          <Text fw={600}>输出文件</Text>
          <Text size="xs" c="dimmed">
            BOM、网络表、图件与制造输出
          </Text>
        </Group>
        <Badge color="gray" variant="light">
          快照 v{version}
        </Badge>
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }} spacing="xs">
        {items.map((item) => {
          const disabled = Boolean(item.requiresPcb && !hasPcb)
          const button = (
            <Button
              key={item.key}
              size="compact-sm"
              variant="light"
              leftSection={item.icon}
              loading={busy === item.key}
              disabled={disabled || (Boolean(busy) && busy !== item.key)}
              onClick={() => run(item)}
            >
              {item.label}
            </Button>
          )
          return (
            <Tooltip
              key={item.key}
              label={disabled ? '工程未包含 PCB 文档（.PcbDoc）' : item.hint}
              multiline
              maw={260}
            >
              <div>{button}</div>
            </Tooltip>
          )
        })}
      </SimpleGrid>
      <Text size="xs" c="dimmed" mt="xs">
        Gerber/钻孔由 Altium 运行该 OutJob 生成（放入工程目录后执行）；平台提供 OutJob 配置、BOM、贴片坐标与渲染图。
      </Text>
      {done && (
        <Text size="xs" c="green" mt={4}>
          已导出：{done}
        </Text>
      )}
      {error && (
        <Alert color="red" mt="xs" p="xs">
          <Text size="sm">{error}</Text>
        </Alert>
      )}
    </Card>
  )
}
