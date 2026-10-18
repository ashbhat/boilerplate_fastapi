import contextlib
import io
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from api.database import get_database_url


class DatabaseTests(unittest.TestCase):
    def test_encoded_url_and_ssl_options_preserved_without_logging(self):
        url = 'postgresql://user:p%25%40ss@db.example.com/app?sslmode=require'
        output = io.StringIO()
        with patch.dict(os.environ, {'DATABASE_URL': url}), contextlib.redirect_stdout(output):
            self.assertEqual(get_database_url(), url)
        self.assertEqual(output.getvalue(), '')

    def test_postgres_alias_normalized(self):
        with patch.dict(os.environ, {'DATABASE_URL': 'postgres://user:pass@host/db'}):
            self.assertEqual(get_database_url(), 'postgresql://user:pass@host/db')

    def test_legacy_credentials_encoded(self):
        from sqlalchemy.engine import make_url
        with patch('api.database.load_dotenv'), patch.dict(os.environ, {'DB_USER': 'user', 'DB_PASSWORD': 'p@ss%word',
                                     'DB_NAME': 'local_db'}, clear=True):
            parsed = make_url(get_database_url())
        self.assertEqual(parsed.password, 'p@ss%word')
        self.assertEqual(parsed.database, 'local_db')

    def test_alembic_offline_accepts_percent_encoded_password(self):
        env = {**os.environ, 'DATABASE_URL': 'postgresql://user:p%25ss@localhost/app?sslmode=require'}
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head', '--sql'],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CREATE TABLE', result.stdout)
        self.assertNotIn('p%25ss', result.stdout + result.stderr)

    @unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Set TEST_DATABASE_URL for a disposable PostgreSQL database')
    def test_upgrade_downgrade_upgrade(self):
        from sqlalchemy import create_engine, inspect
        env = {**os.environ, 'DATABASE_URL': os.environ['TEST_DATABASE_URL']}
        for revision in ('head', 'base', 'head'):
            command = 'downgrade' if revision == 'base' else 'upgrade'
            result = subprocess.run([sys.executable, '-m', 'alembic', command, revision],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        engine = create_engine(env['DATABASE_URL'])
        try:
            self.assertIn('SampleTable', inspect(engine).get_table_names())
        finally:
            engine.dispose()


class ApiTests(unittest.TestCase):
    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from main import app
        response = TestClient(app).get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
