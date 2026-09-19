import { Outlet, useNavigate, Link } from 'react-router-dom'
import { AppShell, Burger, Group, Title, Text, Button, NavLink as MantineNavLink } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { IconCpu, IconFolder, IconMessageChatbot, IconPlugConnected, IconSettings } from '@tabler/icons-react'
import { useAuth } from '../contexts/AuthContext'

const NAV = [
  { to: '/', label: '对话工作台', icon: IconMessageChatbot },
  { to: '/projects', label: '工程文件', icon: IconFolder },
  { to: '/connections', label: 'Altium 连接', icon: IconPlugConnected },
  { to: '/settings', label: '设置', icon: IconSettings },
]

export function AppLayout() {
  const [opened, { toggle }] = useDisclosure()
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <IconCpu size={22} />
            <Title order={4}>AIDriveAltium</Title>
            <Text size="xs" c="dimmed">
              大模型辅助硬件设计
            </Text>
          </Group>
          <Group>
            <Text size="sm">{user?.displayName}</Text>
            <Button
              variant="subtle"
              size="compact-sm"
              onClick={() => {
                logout()
                navigate('/login', { replace: true })
              }}
            >
              退出
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        {NAV.map((item) => (
          <MantineNavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            leftSection={<item.icon size={18} />}
            style={{ borderRadius: 8, marginBottom: 2 }}
          />
        ))}
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
