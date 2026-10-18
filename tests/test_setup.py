import io
import json
import contextlib
import tempfile
from pathlib import Path
import scripts.setup as wizard
import unittest
from unittest.mock import patch

from scripts.bootstrap.config import Config, neon_url, direct_neon_url, render_workflow
from scripts.setup import ask, confirm, choose
from scripts.bootstrap.cloud import Cloud, CommandError, Runner


class ConfigTests(unittest.TestCase):
    def test_encoded_neon_url_preserved(self):
        url = 'postgresql://me:p%25%40ss@ep-test.neon.tech/app?sslmode=require&channel_binding=require'
        self.assertEqual(neon_url(url), url)

    def test_rejects_bad_or_insecure_urls_without_echoing_secret(self):
        for url in ['https://me:SECRET@ep-test.neon.tech/app',
                    'postgresql://me:SECRET@localhost/app?sslmode=require',
                    'postgresql://me:SECRET@ep-test.neon.tech/app?sslmode=disable',
                    'postgresql://me:SECRET@ep-test.neon.tech/app?sslmode=require&sslmode=disable']:
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                neon_url(url)
            self.assertNotIn('SECRET', str(caught.exception))

    def test_direct_url_changes_only_pooled_hostname(self):
        url = 'postgresql://me:p%40ss-pooler.@ep-test-pooler.us-east-2.aws.neon.tech:5432/app?sslmode=require&channel_binding=require'
        expected = 'postgresql://me:p%40ss-pooler.@ep-test.us-east-2.aws.neon.tech:5432/app?sslmode=require&channel_binding=require'
        self.assertEqual(direct_neon_url(url), expected)
        self.assertEqual(direct_neon_url(expected), expected)

    def test_render_and_roundtrip_no_unresolved_placeholders(self):
        c = sample()
        rendered = render_workflow(c)
        self.assertNotIn('@@', rendered)
        self.assertIn('branches: ["main"]', rendered)
        self.assertEqual(Config.from_dict(json.loads(json.dumps(c.to_dict()))), c)

    def test_invalid_names_cannot_be_injected_into_workflow(self):
        for field, value in [('project', 'x\nEVIL=y'), ('service', '$(whoami)'),
                             ('branch', "main' || true"), ('repository', 'foo/bar/baz')]:
            data = sample().to_dict()
            data[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                Config.from_dict(data)


class PromptTests(unittest.TestCase):
    def test_yes_no_reprompts(self):
        with patch('builtins.input', side_effect=['maybe', 'YES']), patch('sys.stdout', new=io.StringIO()):
            self.assertTrue(confirm('Continue?', default=False))

    def test_menu_reprompts_invalid_selection(self):
        with patch('builtins.input', side_effect=['0', 'nope', '1']), patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(choose('Destination', ['Google Cloud Run']), 0)

    def test_required_value_reprompts(self):
        with patch('builtins.input', side_effect=['', 'hello']), patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(ask('Name'), 'hello')


class CloudTests(unittest.TestCase):
    def test_permission_error_does_not_create_resource(self):
        runner = FakeRunner(fail='PERMISSION_DENIED')
        with self.assertRaises(CommandError):
            Cloud(sample(), runner).ensure(['secrets', 'describe', 'db'], ['secrets', 'create', 'db'])
        self.assertEqual(len(runner.calls), 1)

    def test_not_found_creates_but_existing_does_not(self):
        runner = FakeRunner(fail='NOT_FOUND')
        Cloud(sample(), runner).ensure(['secrets', 'describe', 'db'], ['secrets', 'create', 'db'])
        self.assertEqual(len(runner.calls), 3)
        runner = FakeRunner()
        Cloud(sample(), runner).ensure(['secrets', 'describe', 'db'], ['secrets', 'create', 'db'])
        self.assertEqual(len(runner.calls), 1)

    def test_secret_uses_stdin_not_arguments(self):
        runner = FakeRunner()
        Cloud(sample(), runner).add_secret_version('db', 'TOP_SECRET')
        args, stdin = runner.calls[-1]
        self.assertNotIn('TOP_SECRET', ' '.join(args))
        self.assertEqual(stdin, 'TOP_SECRET')

    def test_subprocess_failure_redacts_secret(self):
        import subprocess
        result = subprocess.CompletedProcess([], 1, '', 'backend echoed TOP_SECRET')
        with patch('subprocess.run', return_value=result), self.assertRaises(CommandError) as caught:
            Runner().run(['gcloud', 'secrets', 'versions', 'add'], stdin='TOP_SECRET')
        self.assertNotIn('TOP_SECRET', str(caught.exception))


def sample():
    return Config(project='my-project', project_number='123456', region='us-central1',
                  service='my-api', repository='ash/my-api', repository_id='42',
                  owner_id='17', branch='main', public=False)


class FakeRunner:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def run(self, args, stdin=None):
        self.calls.append((args, stdin))
        if self.fail:
            reason, self.fail = self.fail, None
            raise CommandError(reason)
        return '{}'

class ProvisioningTests(unittest.TestCase):
    def test_created_resources_are_read_back(self):
        runner = FakeRunner(fail='NOT_FOUND')
        Cloud(sample(), runner).ensure(['secrets', 'describe', 'db'], ['secrets', 'create', 'db'])
        self.assertEqual(runner.calls[-1][0][1:4], ['secrets', 'describe', 'db'])

    def test_refuses_unowned_service(self):
        cloud = Cloud(sample(), FakeRunner())
        with self.assertRaisesRegex(CommandError, 'ownership'):
            cloud.check_run_resources()

class WorkflowTests(unittest.TestCase):
    def test_rendered_workflow_has_branch_gate_and_serial_migrations(self):
        import yaml
        data = yaml.load(render_workflow(sample()), Loader=yaml.BaseLoader)
        self.assertEqual(data['on']['push']['branches'], ['main'])
        self.assertEqual(data['jobs']['deploy']['if'], "github.ref == 'refs/heads/main'")
        self.assertEqual(data['jobs']['deploy']['needs'], 'checks')
        self.assertEqual(data['concurrency']['cancel-in-progress'], 'false')
        self.assertEqual(data['jobs']['deploy']['permissions']['id-token'], 'write')


class ProvisionRunner:
    """Boundary fixture for already-created cloud resources; records mutations."""
    def __init__(self, invalid_trust=False):
        self.calls = []
        self.invalid_trust = invalid_trust

    def run(self, args, stdin=None):
        self.calls.append((args, stdin))
        c = sample()
        if args[1:3] == ['run', 'services'] or args[1:3] == ['run', 'jobs']:
            raise CommandError('NOT_FOUND')
        if 'describe' not in args:
            return '{}'
        if args[1:3] == ['iam', 'service-accounts']:
            return json.dumps({'description': f'boilerplate:{c.resource_id}'})
        if args[1:4] == ['iam', 'workload-identity-pools', 'providers']:
            return json.dumps({'attributeCondition': 'true' if self.invalid_trust else c.trust_condition,
                               'attributeMapping': {'google.subject': 'assertion.sub', 'attribute.repository_id': 'assertion.repository_id'},
                               'oidc': {'issuerUri': 'https://token.actions.githubusercontent.com'}, 'state': 'ACTIVE'})
        if args[1:3] == ['iam', 'workload-identity-pools']:
            return json.dumps({'description': f'boilerplate:{c.resource_id}', 'state': 'ACTIVE'})
        if args[1:3] == ['secrets', 'versions']:
            return '{"state": "ENABLED"}'
        return json.dumps({'labels': {'bootstrap_id': c.resource_id}})


class FullProvisionTests(unittest.TestCase):
    def test_rerun_does_not_rotate_secrets(self):
        runner = ProvisionRunner()
        with patch('sys.stdout', new=io.StringIO()):
            Cloud(sample(), runner).provision()
        self.assertFalse(any(args[1:4] == ['secrets', 'versions', 'add'] for args, _ in runner.calls))
        self.assertEqual(sum(args[1:4] == ['secrets', 'versions', 'describe'] for args, _ in runner.calls), 2)
        trust = [args for args, _ in runner.calls if '--role=roles/iam.workloadIdentityUser' in args]
        self.assertEqual(len(trust), 1)
        self.assertIn('/attribute.repository_id/42', ' '.join(trust[0]))

    def test_broad_existing_trust_fails_before_secrets(self):
        runner = ProvisionRunner(invalid_trust=True)
        with patch('sys.stdout', new=io.StringIO()), self.assertRaisesRegex(CommandError, 'trust'):
            Cloud(sample(), runner).provision('SECRET', 'DIRECT_SECRET')
        self.assertFalse(any(args[1] == 'secrets' for args, _ in runner.calls))

    def test_new_urls_only_passed_to_secret_version_stdin(self):
        runner = ProvisionRunner()
        with patch('sys.stdout', new=io.StringIO()):
            Cloud(sample(), runner).provision('SECRET', 'DIRECT_SECRET')
        supplied = [(args, stdin) for args, stdin in runner.calls if stdin is not None]
        self.assertEqual([stdin for _, stdin in supplied], ['SECRET', 'DIRECT_SECRET'])
        self.assertTrue(all(args[1:4] == ['secrets', 'versions', 'add'] for args, _ in supplied))
        self.assertNotIn('SECRET', ' '.join(' '.join(args) for args, _ in runner.calls))


class StartupProbeTests(unittest.TestCase):
    def test_ci_probe_retries_connection_reset_during_startup(self):
        import http.server
        import socket
        import struct
        import subprocess
        import shlex
        import threading
        import yaml
        from scripts.bootstrap.config import ROOT

        class StartingServer(http.server.BaseHTTPRequestHandler):
            requests = 0

            def do_GET(self):
                StartingServer.requests += 1
                if StartingServer.requests == 1:
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                    self.connection.close()
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'healthy')

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), StartingServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            workflow = yaml.load((ROOT / '.github/workflows/ci.yml').read_text(), Loader=yaml.BaseLoader)
            command = workflow['jobs']['test']['steps'][-1]['run'].strip().splitlines()[-1]
            command = command.replace('http://localhost:8080', f'http://127.0.0.1:{server.server_port}')
            result = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('healthy', result.stdout)
            self.assertGreaterEqual(StartingServer.requests, 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class ReadOnlyRunner:
    current_project = 'active-project'

    def run(self, args, stdin=None):
        if args[:3] == ['gh', 'auth', 'status']:
            return ''
        if args[:3] == ['gcloud', 'auth', 'list']:
            return 'developer@example.com'
        if args[:4] == ['gcloud', 'config', 'get-value', 'project']:
            return self.current_project
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

    def test_enter_accepts_active_gcloud_project(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.run_wizard(Path(directory), [''] * 6, dry_run=True)
            self.assertIn('Project: active-project |', output)
            self.assertIn('Access: public', output)

    def test_typed_project_overrides_gcloud_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.run_wizard(Path(directory), ['', 'other-project', '', '', '', ''], dry_run=True)
            self.assertIn('Project: other-project |', output)

    def test_unset_gcloud_project_requires_input(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ReadOnlyRunner, 'current_project', '(unset)'):
            output = self.run_wizard(Path(directory), ['', '', 'typed-project', '', '', '', ''], dry_run=True)
            self.assertIn('Please enter a value.', output)
            self.assertIn('Project: typed-project |', output)

    def test_active_project_is_default_even_with_saved_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'deploy').mkdir()
            (root / 'deploy/config.json').write_text(json.dumps(sample().to_dict()))
            output = self.run_wizard(root, [''] * 6, dry_run=True)
            self.assertIn('Project: active-project |', output)
            self.assertIn('Access: public', output)

    def test_dry_run_never_prompts_for_secrets_or_writes_files(self):
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', side_effect=AssertionError('Secret prompt')):
            root = Path(directory)
            output = self.run_wizard(root, ['', 'my-project', '', '', '', ''], dry_run=True)
            self.assertEqual(list(root.iterdir()), [])
            self.assertIn('Preview only', output)
            self.assertIn('name: Deploy', output)

    def test_cancel_does_not_write_or_provision(self):
        secret = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', return_value=secret), \
                patch.object(Cloud, 'provision', side_effect=AssertionError('Unexpected provisioning')):
            root = Path(directory)
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', 'no'])
            self.assertEqual(list(root.iterdir()), [])
            self.assertNotIn('SECRET', output)
            self.assertIn('Cancelled', output)

    def test_failed_provision_saves_only_non_secret_resume_config(self):
        secret = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', return_value=secret), \
                patch.object(Cloud, 'provision', side_effect=CommandError('PERMISSION_DENIED')):
            root = Path(directory)
            with self.assertRaises(CommandError):
                self.run_wizard(root, ['', 'my-project', '', '', '', '', 'yes'])
            self.assertNotIn('SECRET', (root / 'deploy/config.json').read_text())
            self.assertFalse((root / '.github/workflows/deploy.yml').exists())

    def test_decline_overwrite_preserves_workflow_and_cloud(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Cloud, 'provision', side_effect=AssertionError('Unexpected provisioning')):
            root = Path(directory)
            target = root / '.github/workflows/deploy.yml'
            target.parent.mkdir(parents=True)
            target.write_text('user changes\n')
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', 'no'])
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
            output = self.run_wizard(root, ['', 'my-project', '', '', '', '', 'yes'])
            self.assertEqual(provisioned, [(secret, secret)])
            self.assertTrue(json.loads((root / 'deploy/config.json').read_text())['public'])
            from dataclasses import replace
            self.assertEqual((root / '.github/workflows/deploy.yml').read_text(), render_workflow(replace(sample(), public=True)))
            for path in root.rglob('*'):
                if path.is_file():
                    self.assertNotIn('SECRET', path.read_text())
            self.assertNotIn('SECRET', output)

    def test_pooled_url_needs_only_one_secret_prompt(self):
        secret = 'postgresql://user:SECRET@ep-test-pooler.neon.tech/app?sslmode=require'
        direct = 'postgresql://user:SECRET@ep-test.neon.tech/app?sslmode=require'
        provisioned = []
        def provision(cloud, database_url, migration_url):
            provisioned.append((database_url, migration_url))
        with tempfile.TemporaryDirectory() as directory, patch('getpass.getpass', side_effect=[secret]), \
                patch.object(Cloud, 'provision', provision):
            output = self.run_wizard(Path(directory), ['', 'my-project', '', '', '', '', 'yes'])
        self.assertEqual(provisioned, [(secret, direct)])
        self.assertNotIn('SECRET', output)


if __name__ == '__main__':
    unittest.main()
