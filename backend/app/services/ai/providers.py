"""[已废弃] 单文件 provider 实现已拆分为同目录的 ``providers/`` 包。

历史说明：
- 本文件（``providers.py``）原含 mock / openai 兼容 / anthropic 三条流式分支；
- 现拆分到 ``providers/``（base / openai_compat / ollama / llamacpp / anthropic / mock / factory），
  并新增 provider 注册表、默认值、一键模板与 usage 统计；
- 同名包优先于本模块被导入，因此本文件不会被加载，保留仅为兼容旧分支的 git 历史。

新代码请使用：
    from app.services.ai.providers import stream_chat, create_provider, list_providers
    from app.services.ai.llm_router import resolve   # 模型解析（请求→会话→助手→默认→兜底）
"""
