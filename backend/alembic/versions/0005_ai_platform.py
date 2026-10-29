from alembic import op

from app.database_patches import AI_PLATFORM_STATEMENTS

revision = "0005_ai_platform"
down_revision = "0004_review_runs"
branch_labels = None
depends_on = None


def upgrade():
    for statement in AI_PLATFORM_STATEMENTS:
        op.execute(statement)


def downgrade():
    raise RuntimeError("AI platform columns downgrade is not supported; restore a verified backup")
