import { useEffect, useState } from 'react'
import { Alert, ActionIcon, Badge, Button, Group, Modal, Paper, Table, Text, TextInput } from '@mantine/core'
import { IconTrash } from '@tabler/icons-react'
import { api } from '../api/client'

interface Connection {
  id: string
  name: string
  baseUrl: string
  status: string
  remark: string
}

export function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[]>([])
  const [opened, setOpened] = useState(false)
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('http://192.168.x.x:3296')

  const load = () => api.get<Connection[]>('/altium/connections').then(setConnections)
  useEffect(() => {
    load()
  }, [])

  return (
    <Paper withBorder p="md">
      <Alert title="功能路线" color="indigo" mb="md">
        与运行中 Altium 的实时连接（DelphiScript 桥 + gateway MCP server：截图、查询网络/元件、执行命令）
        按计划在<b>第二步</b>启用。当前阶段请使用「工程文件」的离线解析通道。
      </Alert>
      <Group justify="space-between" mb="md">
        <Text fw={600}>Altium 网关连接</Text>
        <Button onClick={() => setOpened(true)}>新增连接</Button>
      </Group>
      <Table.ScrollContainer minWidth={600}>
        <Table verticalSpacing="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>名称</Table.Th>
              <Table.Th>Base URL</Table.Th>
              <Table.Th>状态</Table.Th>
              <Table.Th style={{ textAlign: 'right' }}>操作</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {connections.map((c) => (
              <Table.Tr key={c.id}>
                <Table.Td>{c.name}</Table.Td>
                <Table.Td>{c.baseUrl}</Table.Td>
                <Table.Td>
                  <Badge color="gray" variant="light">
                    第二步启用
                  </Badge>
                </Table.Td>
                <Table.Td style={{ textAlign: 'right' }}>
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    onClick={async () => {
                      await api.delete(`/altium/connections/${c.id}`)
                      load()
                    }}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
            {connections.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={4}>
                  <Text c="dimmed" ta="center" size="sm">
                    暂无连接配置
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      <Modal opened={opened} onClose={() => setOpened(false)} title="新增 Altium 网关连接">
        <TextInput label="名称" value={name} onChange={(e) => setName(e.target.value)} mb="sm" />
        <TextInput
          label="Base URL（运行 gateway 的 Windows 机器地址）"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          mb="sm"
        />
        <Button
          fullWidth
          onClick={async () => {
            await api.post('/altium/connections', { name, baseUrl })
            setOpened(false)
            setName('')
            load()
          }}
        >
          保存
        </Button>
      </Modal>
    </Paper>
  )
}
