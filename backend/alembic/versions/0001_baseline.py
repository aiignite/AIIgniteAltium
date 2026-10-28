from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def baseline_metadata():
    metadata = sa.MetaData()

    def column(name, kind, nullable=False, **kw):
        return sa.Column(name, kind, nullable=nullable, **kw)

    def text(name):
        return column(name, sa.Text())

    def string(name, size):
        return column(name, sa.String(size))

    def integer(name):
        return column(name, sa.Integer())

    def boolean(name):
        return column(name, sa.Boolean())

    def json(name, nullable=False):
        return column(name, sa.JSON(), nullable)

    def fk(name, table, nullable=True, index=False):
        return sa.Column(name, sa.Uuid(), sa.ForeignKey(table + ".id"), nullable=nullable, index=index)

    def table(name, *columns, soft=True):
        shared = [column("id", sa.Uuid(), primary_key=True),
                  column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
                  column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now())]
        if soft:
            shared.append(column("is_deleted", sa.Boolean(), index=True))
        return sa.Table(name, metadata, *columns, *shared)

    table("sys_users", column("email", sa.String(255), unique=True, index=True),
          string("display_name", 100), string("password_hash", 255), boolean("is_admin"), boolean("is_active"))
    table("ai_model_configs", column("name", sa.String(100), unique=True), string("provider", 30),
          string("base_url", 500), text("api_key"), string("model_name", 200), boolean("is_default"),
          boolean("enabled"), string("remark", 500), integer("sort_order"))
    table("ai_skills", column("code", sa.String(64), unique=True), string("name", 100),
          string("description", 500), string("category", 50), string("icon", 30), text("prompt_template"),
          json("keywords"), boolean("is_system"), boolean("enabled"), integer("sort_order"))
    table("ai_assistants", string("name", 100), string("description", 500), string("avatar", 30),
          string("category", 50), text("system_prompt"), json("skill_codes"), column("model_config_id", sa.Uuid(), True),
          boolean("is_system"), boolean("is_default"), boolean("enabled"), integer("usage_count"), integer("sort_order"))
    table("fls_projects", column("user_id", sa.String(36), index=True), string("name", 200),
          string("storage_dir", 500), column("status", sa.String(20), index=True), text("error"), json("file_names"),
          json("snapshot", True), json("svg_manifest"), string("design_json_path", 500), integer("parse_duration_ms"), string("remark", 500))
    table("alt_connections", string("name", 100), string("base_url", 500), string("api_token", 500),
          string("status", 20), column("last_checked_at", sa.DateTime(timezone=True), True), text("last_error"),
          json("info"), string("remark", 500))
    table("ai_conversations", fk("user_id", "sys_users", False, True), string("title", 200),
          fk("project_id", "fls_projects"), fk("model_config_id", "ai_model_configs"),
          column("assistant_id", sa.Uuid(), True), string("skill", 50), integer("message_count"))
    messages = table("ai_messages", fk("conversation_id", "ai_conversations", False, True), integer("seq"),
                     string("role", 20), text("content"), string("skill", 50), fk("model_config_id", "ai_model_configs"),
                     string("provider", 30), integer("duration_ms"), json("meta"), text("error"),
                     column("finished_at", sa.DateTime(timezone=True), True), soft=False)
    sa.Index("ix_ai_messages_conversation", messages.c.conversation_id, messages.c.seq)
    return metadata


def upgrade():
    baseline_metadata().create_all(op.get_bind(), checkfirst=False)


def downgrade():
    raise RuntimeError("Destructive schema downgrade is not supported; restore a verified backup")
