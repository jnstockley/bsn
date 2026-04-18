import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool
from sqlalchemy.pool import StaticPool

from alembic import context

from models import Base
from util.logging import logger

load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Route Alembic's own loggers through our existing logger's handlers/formatter
for name in ("alembic", "alembic.runtime.migration", "sqlalchemy.engine"):
    alembic_logger = logging.getLogger(name)
    alembic_logger.handlers = []
    for handler in logger.handlers:
        alembic_logger.addHandler(handler)
    alembic_logger.setLevel(logger.level)
    alembic_logger.propagate = False

# Build the database URL using the same logic as db.py
data_url = os.getenv("DATA_DIR", "./data")

if data_url == ":memory:":
    db_url = "sqlite:///:memory:"
else:
    data_dir = Path(data_url)
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{data_url}/bsn.db"

config.set_main_option("sqlalchemy.url", db_url)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool if data_url != ":memory:" else StaticPool,
        connect_args={"check_same_thread": False} if data_url == ":memory:" else {},
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
