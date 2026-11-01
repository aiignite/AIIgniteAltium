import sqlalchemy as sa
from alembic import op

revision = "0006_command_audit"
down_revision = "0005_ai_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alt_command_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("sys_users.id"), nullable=False),
        sa.Column(
            "connection_id",
            sa.Uuid(),
            sa.ForeignKey("alt_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("command", sa.String(100), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="executed"),
        sa.Column("request_id", sa.String(80), nullable=True),
        sa.Column("undo_of_id", sa.Uuid(), sa.ForeignKey("alt_command_audits.id"), nullable=True),
        sa.Column("undone_by_id", sa.Uuid(), sa.ForeignKey("sys_users.id"), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("connection_id", "request_id", name="uq_alt_command_audits_request"),
    )
    op.create_index("ix_alt_command_audits_user_id", "alt_command_audits", ["user_id"])
    op.create_index("ix_alt_command_audits_connection_id", "alt_command_audits", ["connection_id"])


def downgrade():
    raise RuntimeError("Command audit downgrade is not supported; restore a verified backup")
