"""Track source indexing policy independently from release revision."""
from alembic import op
import sqlalchemy as sa

revision = "2d86c73a901f"
down_revision = "7a7ce58b6e3f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_snapshots", sa.Column("index_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("knowledge_snapshots") as batch:
        batch.drop_column("index_version")
