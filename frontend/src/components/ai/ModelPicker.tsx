import { Select } from '@mantine/core'
import { modelNeedsKey, type AIModelItem } from './types'

interface ModelPickerProps {
  models: AIModelItem[]
  value: string | null
  onChange: (value: string | null) => void
  placeholder?: string
  size?: 'xs' | 'sm'
  width?: number | string
  flex?: number
  allowClear?: boolean
  label?: string
  disabled?: boolean
}

/**
 * 模型选择器（工作台 / 助手表单共用）：
 * - 展示 provider、模型名与"默认"标记
 * - 未配置密钥的云端模型禁选并提示
 */
export function ModelPicker({
  models,
  value,
  onChange,
  placeholder = '使用默认模型',
  size = 'xs',
  width,
  flex,
  allowClear = true,
  label,
  disabled = false,
}: ModelPickerProps) {
  const data = models
    .filter((m) => m.enabled)
    .map((m) => {
      const blocked = modelNeedsKey(m)
      const marks = [
        m.isDefault ? '默认' : '',
        blocked ? '未配 Key' : '',
        m.supportsTools ? '' : '无工具',
      ].filter(Boolean)
      return {
        value: m.id,
        label: `${m.name}${m.providerName ? ` · ${m.providerName}` : ''}${marks.length ? `（${marks.join(' / ')}）` : ''}`,
        disabled: blocked,
      }
    })

  return (
    <Select
      label={label}
      size={size}
      w={width}
      flex={flex}
      placeholder={placeholder}
      data={data}
      value={value}
      onChange={onChange}
      clearable={allowClear}
      searchable
      disabled={disabled}
      nothingFoundMessage="还没有可用模型"
      comboboxProps={{ withinPortal: true }}
    />
  )
}
