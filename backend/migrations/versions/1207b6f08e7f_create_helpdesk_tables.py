from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "1207b6f08e7f"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:

    op.create_table(
        "categories",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_table(
        "users",
        sa.Column("login", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('customer', 'support', 'admin')", name=op.f("ck_users_role")),
        sa.CheckConstraint("auth_version >= 0", name=op.f("ck_users_auth_version")),
        sa.PrimaryKeyConstraint("login", name=op.f("pk_users")),
    )
    op.create_table(
        "response_norms",
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("response_seconds", sa.Integer(), nullable=False),
        sa.CheckConstraint("response_seconds > 0", name=op.f("ck_response_norms_positive_seconds")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_response_norms_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("category_id", name=op.f("pk_response_norms")),
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("author_login", sa.String(length=64), nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="new", nullable=False),
        sa.Column("response_norm_seconds", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(status = 'closed') = (closed_at IS NOT NULL)", name=op.f("ck_tickets_closed_at_status")),
        sa.CheckConstraint("status IN ('new', 'in_progress', 'closed')", name=op.f("ck_tickets_ticket_status")),
        sa.CheckConstraint("closed_at IS NULL OR closed_at >= created_at", name=op.f("ck_tickets_closed_at_order")),
        sa.CheckConstraint("response_norm_seconds > 0", name=op.f("ck_tickets_positive_norm")),
        sa.ForeignKeyConstraint(
            ["author_login"], ["users.login"], name=op.f("fk_tickets_author_login_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_tickets_category_id_categories"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("author_login", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_staff_reply", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_login"], ["users.login"], name=op.f("fk_comments_author_login_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"], ["tickets.id"], name=op.f("fk_comments_ticket_id_tickets"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
    )


def downgrade() -> None:

    op.drop_table("comments")
    op.drop_table("tickets")
    op.drop_table("response_norms")
    op.drop_table("users")
    op.drop_table("categories")
