"""llama.cpp server（llama-server --api）：OpenAI 兼容端点，无需 API Key。"""

from __future__ import annotations

from app.services.ai.providers.openai_compat import OpenAICompatibleProvider


class LlamaCppProvider(OpenAICompatibleProvider):
    id = "llamacpp"
    name = "llama.cpp（本地）"
    requires_api_key = False
    default_base_url = "http://localhost:8080/v1"
    default_model = "local-model"
    supports_tools = False  # llama-server 的 tool 支持取决于启动参数与模型模板
    group = "local"
