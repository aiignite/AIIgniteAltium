"""模型注册中心：新模型组加入 ALL_MODEL_GROUPS 并在此导入，保证 create_all 可见。"""

ALL_MODEL_GROUPS = ["system", "ai", "files", "altium"]

from app.models.system import User  # noqa: F401,E402
from app.models.ai import (  # noqa: F401,E402
    AIAssistant,
    AIModelConfig,
    AISkill,
    Conversation,
    Message,
)
from app.models.files import UploadedProject  # noqa: F401,E402
from app.models.altium import GatewayConnection  # noqa: F401,E402
