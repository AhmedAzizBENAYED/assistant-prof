"""Base tables: settings, documents, versions.

Revision ID: 0001
Revises:
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the three base tables."""
    op.create_table(
        "settings",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
    )
    # SQLite accepts a foreign key to a table created later: documents and versions refer to
    # each other.
    op.create_table(
        "documents",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("head_version_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(
            ["head_version_id"],
            ["versions.id"],
            name="fk_documents_head_version_id_versions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
    )
    op.create_table(
        "versions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("document_id", sa.String(36), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("operations", sa.JSON(), nullable=True),
        sa.Column("model_used", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_versions_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["versions.id"],
            name="fk_versions_parent_id_versions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_versions"),
        sa.UniqueConstraint("document_id", "number", name="uq_versions_document_id_number"),
    )


def downgrade() -> None:
    """Drop the three base tables."""
    op.drop_table("versions")
    op.drop_table("documents")
    op.drop_table("settings")
