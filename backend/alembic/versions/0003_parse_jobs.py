from alembic import op
import sqlalchemy as sa

revision = "0003_parse_jobs"
down_revision = "0002_p0_security"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fls_projects", sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "fls_parse_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fls_parse_jobs_project_id", "fls_parse_jobs", ["project_id"])
    op.create_index("ix_fls_parse_jobs_status", "fls_parse_jobs", ["status"])
    op.create_index(
        "uq_parse_jobs_active_project",
        "fls_parse_jobs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "fls_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("fls_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("svg_manifest", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("design_json_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("parse_duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_fls_snapshots_project_version"),
    )
    op.create_index("ix_fls_snapshots_project_id", "fls_snapshots", ["project_id"])

    # 已有快照回填为版本 1，升级后历史可查
    op.execute(
        """
        INSERT INTO fls_snapshots
            (id, project_id, version, snapshot, svg_manifest, design_json_path, parse_duration_ms, created_at, updated_at)
        SELECT gen_random_uuid(), id, 1, snapshot, COALESCE(svg_manifest, '[]'::json), design_json_path,
               parse_duration_ms, now(), now()
        FROM fls_projects
        WHERE snapshot IS NOT NULL
        """
    )
    op.execute("UPDATE fls_projects SET current_version = 1 WHERE snapshot IS NOT NULL")


def downgrade():
    raise RuntimeError("Versioning downgrade is not supported; restore a verified backup")
