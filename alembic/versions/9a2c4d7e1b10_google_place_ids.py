"""Add optional Google Place IDs for precise Maps links."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9a2c4d7e1b10"
down_revision: Union[str, None] = "8e0f7f4a2c11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("destinations", sa.Column("google_place_id", sa.String(length=256), nullable=True))
    op.create_index("ix_destinations_google_place_id", "destinations", ["google_place_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_destinations_google_place_id", table_name="destinations")
    op.drop_column("destinations", "google_place_id")
