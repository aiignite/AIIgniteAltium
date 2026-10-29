/** AI 配置相关共享类型（模型 / provider / 测试结果）。 */

export interface AIModelItem {
  id: string
  name: string
  provider: string
  providerName: string
  baseUrl: string
  modelName: string
  hasKey: boolean
  keyHint: string
  temperature: number
  maxTokens: number
  topP: number
  contextWindow: string
  supportsTools: boolean
  supportsImage: boolean
  speed: string
  cost: string
  isSystem: boolean
  isDefault: boolean
  enabled: boolean
  remark: string
  sortOrder: number
  testStatus: string
  testLatencyMs: number
  testedAt: string | null
  lastError: string
  createdAt: string
}

export interface ProviderMeta {
  id: string
  name: string
  requiresApiKey: boolean
  defaultBaseUrl: string
  defaultModel: string
  supportsTools: boolean
  group: string
}

export interface ModelPreset {
  id: string
  name: string
  provider: string
  baseUrl: string
  modelName: string
  contextWindow: string
  supportsTools: boolean
  speed: string
  cost: string
}

export interface ProvidersResponse {
  providers: ProviderMeta[]
  presets: ModelPreset[]
  speeds: string[]
  costs: string[]
  defaultTemperature: number
  defaultMaxTokens: number
}

export interface ModelTestResult {
  ok: boolean
  latencyMs: number
  category: string
  statusCode?: number | null
  error: string
  hint: string
  provider: string
  model: string
}

/** provider 是否需要密钥（mock / 本地引擎无需） */
export function modelNeedsKey(model: AIModelItem): boolean {
  return model.provider !== 'mock' && !model.hasKey
}
