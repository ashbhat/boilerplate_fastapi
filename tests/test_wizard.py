import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.setup as wizard
from test_setup import sample
from scripts.bootstrap.cloud import Cloud, CommandError
from scripts.bootstrap.config import render_workflow


class ReadOnlyRunner:
    def run(self, args, stdin=None):
        if args[:3] == ['gh', 'auth', 'status']:
            return ''
        if args[:3] == ['gcloud', 'auth', 'list']:
            return 'developer@example.com'
        if args[:3] == ['gcloud', 'projects', 'describe']:
            return '{"projectNumber": "123456"}'
        if args[:4] == ['gcloud', 'billing', 'projects', 'describe']:
            return '{"billingEnabled": true}'
        if args[0] == 'git':
            return 'git@github.com:ash/my-api.git'
        if args[:2] == ['gh', 'api']:
            return json.dumps({'full_name': 'ash/my-api', 'id': 42, 'owner': {'id': 17},
                               'default_branch': 'main', 'permissions': {'push': True}})
        raise AssertionError(f'Unexpected command: {args}')


class WizardTests(unittest.TestCase):
    def run_wizard(self, root, inputs, dry_run=False):
        output = io.StringIO()
        with patch.object(wizard, 'ROOT', root), patch.object(wizard, 'Runner', ReadOnlyRunner), \
                patch('shutil.which', return_value='/fake/bin'), \
                patch('builtins.input', side_effect=inputs), \
                contextlib.redirect_stdout(output):
            wizard.setup(dry_run=dry_run)
        return output.getvalue()

    def test_dry_run_never_prompts_for_secrets_or_writes_files(self):
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', side_effect=AssertionError('Secret prompt')):
            root = Path(directory)
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', ''], dry_run=True)
            self.assertEqual(list(root.iterdir()), [])
            self.assertIn('Preview only', output)
            self.assertIn('name: Deploy', output)

    def test_cancel_does_not_write_or_provision(self):
        secret = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', return_value=secret), \
                patch.object(Cloud, 'provision', side_effect=AssertionError('Unexpected provisioning')):
            root = Path(directory)
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', '', '', 'no'])
            self.assertEqual(list(root.iterdir()), [])
            self.assertNotIn('SECRET', output)
            self.assertIn('Cancelled', output)

    def test_failed_provision_saves_only_non_secret_resume_config(self):
        secret = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', return_value=secret), \
                patch.object(Cloud, 'provision', side_effect=CommandError('PERMISSION_DENIED')):
            root = Path(directory)
            with self.assertRaises(CommandError):
                self.run_wizard(root, ['', 'my-project', '', '', '', '', '', '', 'yes'])
            self.assertNotIn('SECRET', (root / 'deploy/config.json').read_text())
            self.assertFalse((root / '.github/workflows/deploy.yml').exists())

    def test_decline_overwrite_preserves_workflow_and_cloud(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Cloud, 'provision', side_effect=AssertionError('Unexpected provisioning')):
            root = Path(directory)
            target = root / '.github/workflows/deploy.yml'
            target.parent.mkdir(parents=True)
            target.write_text('user changes\n')
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', '', 'no'])
            self.assertEqual(target.read_text(), 'user changes\n')
            self.assertIn('Cancelled', output)

    def test_success_generates_workflow_without_secrets(self):
        secret = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        provisioned = []
        def provision(cloud, database_url, migration_url):
            provisioned.append((database_url, migration_url))
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', return_value=secret), \
                patch.object(Cloud, 'provision', provision):
            root = Path(directory)
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', '', '', 'yes'])
            self.assertEqual(provisioned, [(secret, secret)])
            self.assertEqual((root / '.github/workflows/deploy.yml').read_text(), render_workflow(sample()))
            for path in root.rglob('*'):
                if path.is_file():
                    self.assertNotIn('SECRET', path.read_text())
            self.assertNotIn('SECRET', output)
