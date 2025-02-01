from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
import os
from dotenv import load_dotenv
import sys
from importlib import import_module
from _meta._migrations.base import Base

# Load environment variables
load_dotenv()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Construct database URL
def get_database_url():
    host = os.getenv('DB_HOST', 'localhost')
    port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'postgres')
    user = os.getenv('DB_USER', 'postgres')
    password = os.getenv('DB_PASSWORD', '')
    
    url = f"postgresql://{user}:{password}@{host}:{port}/{db_name}"
    print(f"Database URL: {url}")  # Add this line to print the URL
    return url

# Override sqlalchemy.url with dynamic configuration
config.set_main_option('sqlalchemy.url', get_database_url())

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# Set the target metadata for 'autogenerate' support
target_metadata = Base.metadata

# Add your app's directory to the path for dynamic imports
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, root_path)

def load_models():
    """
    Dynamically load all modules containing SQLAlchemy models in the application.
    """
    # Adjust path to go up two levels (one for _migrations, one for _meta)
    import_errors = False

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Ignore unwanted directories like your virtual environment or third-party packages
        if '.pythonlibs' in dirpath or 'site-packages' in dirpath or '_meta' in dirpath:
            continue

        for filename in filenames:
            if filename == 'models.py':
                module_path = os.path.relpath(os.path.join(dirpath, filename), root_path)
                module_name = module_path.replace(os.path.sep, '.')[:-3]  # Remove the '.py' extension

                try:
                    print(f"Importing module: {module_name}")  # Print module name for debugging
                    import_module(module_name)
                except ModuleNotFoundError as e:
                    print(f"Failed to import {module_name}: {e}")
                    import_errors = True
                except Exception as e:
                    print(f"Error importing {module_name}: {e}")
                    import_errors = True

    # Raise an exception if any import errors occurred
    if import_errors:
        raise RuntimeError("Model import errors detected. Aborting Alembic autogenerate.")



# Load all model modules
load_models()


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
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
