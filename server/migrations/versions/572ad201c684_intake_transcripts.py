"""Store new AI assistant turns for audited administrator review."""
from alembic import op
import sqlalchemy as sa

revision = "572ad201c684"
down_revision = "4c1e532b9fd0"


def upgrade():
    op.create_table(
        "intake_conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("response", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("image_count", sa.Integer(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_intake_message_conversation_time", "intake_conversation_messages", ["conversation_id", "created_at"])


def downgrade():
    op.drop_table("intake_conversation_messages")
