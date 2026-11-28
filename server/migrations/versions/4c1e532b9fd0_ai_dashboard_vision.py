"""Track admitted chat activity and explicitly enabled image input."""
from alembic import op
import sqlalchemy as sa

revision = "4c1e532b9fd0"
down_revision = "a4fb1cb20329"


def upgrade():
    op.add_column("ai_models", sa.Column("supports_vision", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "ai_chat_activity",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("actor_key", sa.String(64), nullable=False),
        sa.Column("anonymous", sa.Boolean(), nullable=False),
        sa.Column("retry", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_chat_activity_created_at", "ai_chat_activity", ["created_at"])


def downgrade():
    op.drop_table("ai_chat_activity")
    with op.batch_alter_table("ai_models") as batch:
        batch.drop_column("supports_vision")
