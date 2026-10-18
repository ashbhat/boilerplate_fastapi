"""Shared database URL configuration for application code and Alembic."""
import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL


def get_database_url():
    load_dotenv()
    url = os.getenv('DATABASE_URL')
    if url:
        if url.startswith('postgres://'):
            return 'postgresql://' + url[len('postgres://'):]
        return url
    return URL.create(
        'postgresql', username=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', ''), host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', '5432')), database=os.getenv('DB_NAME', 'postgres'),
    ).render_as_string(hide_password=False)
