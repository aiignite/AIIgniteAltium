from alembic import op
import sqlalchemy as sa

revision = "0002_p0_security"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("alt_connections", "api_token", type_=sa.Text(), existing_type=sa.String(500), existing_nullable=False)
    op.create_table("alt_connection_grants",
                    sa.Column("connection_id", sa.Uuid(), sa.ForeignKey("alt_connections.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("user_id", sa.Uuid(), sa.ForeignKey("sys_users.id", ondelete="CASCADE"), primary_key=True))
    op.create_index("ix_alt_connection_grants_user_id", "alt_connection_grants", ["user_id"])
    op.add_column("ai_conversations", sa.Column("connection_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_ai_conversations_connection_id", "ai_conversations", "alt_connections", ["connection_id"], ["id"])
    op.create_check_constraint("ck_conversation_source", "ai_conversations", "project_id IS NULL OR connection_id IS NULL")


def downgrade():
    raise RuntimeError("Security downgrade is not supported; restore a verified backup")
