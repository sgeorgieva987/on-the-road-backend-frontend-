"""Add grouped destination information for visitor-facing detail boxes."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "8e0f7f4a2c11"
down_revision: Union[str, None] = "4bb46c29ca1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("destinations", sa.Column("information", sa.JSON(), nullable=True))
    # Existing records get an empty object and are enriched by the API fallback.
    op.execute(sa.text("UPDATE destinations SET information = '{}' WHERE information IS NULL"))
    with op.batch_alter_table("destinations") as batch_op:
        batch_op.alter_column("information", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.drop_column("destinations", "information")
