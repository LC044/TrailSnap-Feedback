"""Persist only the safe metadata of observed conversation tool calls."""
from alembic import op
import sqlalchemy as sa

revision = "8e4d0f7b621c"
down_revision = "572ad201c684"


def upgrade():
    op.add_column("model_request_usage", sa.Column("tool_calls", sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table("model_request_usage") as batch:
        batch.drop_column("tool_calls")
