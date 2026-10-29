/** [已迁移] 助手与技能管理已并入 AI 配置中心（/ai-config?tab=assistants|skills）。

保留此文件仅为兼容旧的导入路径（例如外部脚本或旧路由的懒加载引用）。
新代码请直接从 `./AIConfigPage` 或 `./ai/AssistantsPanel`、`./ai/SkillsPanel` 引用。
 */

export { AIConfigPage as AssistantsPage } from './AIConfigPage'
