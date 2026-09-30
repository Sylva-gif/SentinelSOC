"""Create the initial Sentinel SOC schema."""

from alembic import op

revision = "20260930_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app import models as _models  # noqa: F401 - register metadata
    from app.database import Base

    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    from app import models as _models  # noqa: F401 - register metadata
    from app.database import Base

    Base.metadata.drop_all(bind=op.get_bind())