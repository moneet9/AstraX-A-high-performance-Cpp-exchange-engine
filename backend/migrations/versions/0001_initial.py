"""Create core paper trading tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=True),
        sa.Column("apple_subject", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("email"), sa.UniqueConstraint("apple_subject"))
    op.create_index("ix_users_email", "users", ["email"])
    op.create_table("accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False, server_default="Paper account"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("cash_ticks", sa.BigInteger(), nullable=False, server_default="100000000"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])
    op.create_table("orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False), sa.Column("side", sa.String(4), nullable=False),
        sa.Column("order_type", sa.String(16), nullable=False), sa.Column("tif", sa.String(8), nullable=False, server_default="GTC"),
        sa.Column("price_ticks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("stop_price_ticks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("peg_offset_ticks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("quantity", sa.BigInteger(), nullable=False), sa.Column("filled_quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("engine_order_id", sa.BigInteger(), nullable=True), sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="accepted"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("engine_order_id"), sa.UniqueConstraint("account_id", "idempotency_key", name="uq_order_idempotency"))
    op.create_index("ix_orders_account_id", "orders", ["account_id"])
    op.create_index("ix_orders_symbol", "orders", ["symbol"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table("fills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_ticks", sa.BigInteger(), nullable=False), sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_fills_order_id", "fills", ["order_id"])
    op.create_index("ix_fills_created_at", "fills", ["created_at"])
    op.create_table("positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(24), nullable=False), sa.Column("quantity", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("average_price_ticks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("realized_pnl_ticks", sa.BigInteger(), nullable=False, server_default="0"),
        sa.UniqueConstraint("account_id", "symbol", name="uq_position_account_symbol"))
    op.create_index("ix_positions_account_id", "positions", ["account_id"])
    op.create_table("push_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(256), nullable=False), sa.UniqueConstraint("token"))
    op.create_index("ix_push_tokens_user_id", "push_tokens", ["user_id"])


def downgrade():
    op.drop_table("push_tokens")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("orders")
    op.drop_table("accounts")
    op.drop_table("users")
