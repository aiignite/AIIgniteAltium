"""模块化单体入口注册表（沿 AIIgnitePLM 约定）。"""

ALL_MODULES = ["system", "ai", "files", "altium"]


def register_all_modules(app) -> None:
    import importlib

    for group in ALL_MODULES:
        module = importlib.import_module(f"app.modules.{group}")
        module.register_routers(app)
