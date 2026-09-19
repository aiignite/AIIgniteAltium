import { useState } from 'react'
import { Button, Card, Center, PasswordInput, Tabs, TextInput, Title, Text } from '@mantine/core'
import { useAuth } from '../contexts/AuthContext'

export function LoginPage() {
  const { login, register } = useAuth()
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('admin@example.com')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async () => {
    setBusy(true)
    setError('')
    try {
      if (tab === 'login') await login(email, password)
      else await register(email, password, displayName)
    } catch (e) {
      setError(e instanceof Error ? e.message : '操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center h="100vh">
      <Card w={420} withBorder shadow="sm" radius="md" p="lg">
        <Title order={3} ta="center" mb={4}>
          AIDriveAltium
        </Title>
        <Text size="sm" c="dimmed" ta="center" mb="md">
          大模型辅助硬件设计平台
        </Text>
        <Tabs value={tab} onChange={(v) => setTab((v as 'login' | 'register') ?? 'login')} mb="sm">
          <Tabs.List grow>
            <Tabs.Tab value="login">登录</Tabs.Tab>
            <Tabs.Tab value="register">注册</Tabs.Tab>
          </Tabs.List>
        </Tabs>
        <TextInput label="邮箱" value={email} onChange={(e) => setEmail(e.target.value)} mb="sm" />
        <PasswordInput
          label="密码"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          mb="sm"
        />
        {tab === 'register' && (
          <TextInput label="姓名" value={displayName} onChange={(e) => setDisplayName(e.target.value)} mb="sm" />
        )}
        {error && (
          <Text c="red" size="sm" mb="sm">
            {error}
          </Text>
        )}
        <Button fullWidth loading={busy} onClick={submit}>
          {tab === 'login' ? '登录' : '注册并登录'}
        </Button>
        <Text size="xs" c="dimmed" ta="center" mt="md">
          开发环境默认管理员 admin@example.com / admin123456
        </Text>
      </Card>
    </Center>
  )
}
