from alembic import op
import sqlalchemy as sa

revision = "0004_review_runs"
down_revision = "0003_parse_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fls_review_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("sys_users.id"), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("ruleset_version", sa.String(20), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fls_review_runs_project_id", "fls_review_runs", ["project_id"])


def downgrade():
    raise RuntimeError("Review history downgrade is not supported; restore a verified backup")
