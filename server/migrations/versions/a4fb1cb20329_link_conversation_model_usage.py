"""Associate model usage with conversations without backfilling guesses."""
from alembic import op
import sqlalchemy as sa

revision = "a4fb1cb20329"
down_revision = "2d86c73a901f"


def upgrade():
    for name, length in (("conversation_kind", 16), ("conversation_id", 36), ("message_id", 36)):
        op.add_column("model_request_usage", sa.Column(name, sa.String(length), nullable=True))
    op.create_index("ix_model_usage_conversation", "model_request_usage", ["conversation_kind", "conversation_id", "message_id"])


def downgrade():
    op.drop_index("ix_model_usage_conversation", table_name="model_request_usage")
    with op.batch_alter_table("model_request_usage") as batch:
        for name in ("message_id", "conversation_id", "conversation_kind"):
            batch.drop_column(name)
