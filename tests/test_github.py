import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.bootstrap.cloud import CommandError, Runner
from scripts.bootstrap.github import open_deployment_pr


class LocalGitRunner:
    """Real local Git; only GitHub network commands are faked."""
    def __init__(self):
        self.github = []
        self.open_prs = []
        self.fail_create = False

    def run(self, args, stdin=None, env=None):
        if args[0] == 'git' and args[3:] == ['remote', 'get-url', 'origin']:
            return 'git@github.com:example/app.git'
        if args[0] == 'gh':
            self.github.append(args)
            if args[1:3] == ['pr', 'list']:
                return json.dumps(self.open_prs)
            if args[1:3] == ['pr', 'create']:
                if self.fail_create:
                    raise CommandError('GitHub unavailable')
                body = Path(args[args.index('--body-file') + 1]).read_text()
                if 'Merging into `main` triggers' not in body:
                    raise AssertionError('Missing merge guidance')
                return 'https://github.com/example/app/pull/7'
            raise AssertionError(args)
        return Runner().run(args, stdin=stdin, env=env)


class DeploymentPRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'checkout'
        self.remote = Path(self.temp.name) / 'remote.git'
        self.root.mkdir()
        self.command('git', 'init', '--bare', str(self.remote))
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Setup Test')
        self.git('config', 'user.email', 'setup@example.com')
        (self.root / 'readme.md').write_text('Base repository\n')
        self.git('add', 'readme.md')
        self.git('commit', '-m', 'Base')
        self.git('remote', 'add', 'origin', str(self.remote))
        self.git('push', 'origin', 'main')
        self.base = self.git('rev-parse', 'HEAD')
        self.git('switch', '-c', 'work')
        (self.root / 'app.py').write_text('print("hello")\n')
        self.git('add', 'app.py')
        self.git('commit', '-m', 'Application')
        for name, content in [('deploy/config.json', '{"project":"my-project"}\n'),
                              ('.github/workflows/deploy.yml', 'name: Deploy\n')]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.config = SimpleNamespace(repository='example/app', branch='main', resource_id='app-12345678',
                                      service='app', project='my-project', region='us-central1')
        self.runner = LocalGitRunner()
        self.messages = []

    def command(self, *args):
        return subprocess.run(args, text=True, capture_output=True, check=True).stdout.strip()

    def git(self, *args):
        return self.command('git', '-C', str(self.root), *args)

    def publish(self, approve=True):
        return open_deployment_pr(self.config, self.runner, self.root,
                                  lambda *args: approve, self.messages.append)

    def test_pr_has_app_and_generated_files_without_changing_checkout(self):
        before = self.git('status', '--porcelain')
        head = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.publish(), 'https://github.com/example/app/pull/7')
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('branch', '--show-current'), 'work')
        create = self.runner.github[-1]
        branch = create[create.index('--head') + 1]
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'rev-parse', branch + '^'), self.base)
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'show', branch + ':app.py'), 'print("hello")')
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'show', branch + ':.github/workflows/deploy.yml'), 'name: Deploy')
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'rev-parse', 'main'), self.base)

    def test_dirty_unrelated_files_stop_before_publish(self):
        (self.root / 'app.py').write_text('uncommitted changes\n')
        with self.assertRaisesRegex(CommandError, 'Commit or stash'):
            self.publish()
        self.assertEqual(self.runner.github, [])

    def test_declining_does_not_push(self):
        self.assertEqual(self.publish(approve=False), '')
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'branch', '--format=%(refname:short)'), 'main')
        self.assertFalse(any(args[1:3] == ['pr', 'create'] for args in self.runner.github))

    def test_existing_pr_reused(self):
        self.publish()
        self.runner.github.clear()
        self.runner.open_prs = [{'url': 'https://github.com/example/app/pull/7'}]
        self.assertEqual(self.publish(), 'https://github.com/example/app/pull/7')
        self.assertFalse(any(args[1:3] == ['pr', 'create'] for args in self.runner.github))

    def test_existing_pr_edits_are_not_silently_reused(self):
        self.publish()
        branch = self.runner.github[-1][self.runner.github[-1].index('--head') + 1]
        self.command('git', '--git-dir', str(self.remote), 'update-ref', 'refs/heads/' + branch, self.base)
        self.runner.open_prs = [{'url': 'https://github.com/example/app/pull/7'}]
        with self.assertRaisesRegex(CommandError, 'different files'):
            self.publish()
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'rev-parse', branch), self.base)

    def test_retry_after_pr_failure_reuses_pushed_branch(self):
        self.runner.fail_create = True
        with self.assertRaisesRegex(CommandError, 'GitHub unavailable'):
            self.publish()
        branches = self.command('git', '--git-dir', str(self.remote), 'show-ref')
        self.runner.fail_create = False
        self.assertEqual(self.publish(), 'https://github.com/example/app/pull/7')
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'show-ref'), branches)

    def test_unrelated_template_history_produces_comparable_pr(self):
        self.git('checkout', '--orphan', 'template-copy')
        self.git('commit', '-m', 'Unrelated initial snapshot')
        self.assertEqual(self.publish(), 'https://github.com/example/app/pull/7')
        branch = self.runner.github[-1][self.runner.github[-1].index('--head') + 1]
        self.assertEqual(self.command('git', '--git-dir', str(self.remote), 'rev-parse', branch + '^'), self.base)

    def test_remote_updates_must_be_merged_before_snapshotting(self):
        self.git('switch', 'main')
        (self.root / 'remote-feature.py').write_text('new remote code\n')
        self.git('add', 'remote-feature.py')
        self.git('commit', '-m', 'New remote change')
        self.git('push', 'origin', 'main')
        self.git('switch', 'work')
        with self.assertRaisesRegex(CommandError, 'Merge or rebase'):
            self.publish()
        self.assertEqual(self.runner.github, [])

    def test_no_diff_does_not_create_pr(self):
        self.git('add', 'deploy/config.json', '.github/workflows/deploy.yml')
        self.git('commit', '-m', 'Already configured')
        self.git('push', 'origin', 'HEAD:main')
        self.assertIsNone(self.publish())
        self.assertEqual(self.runner.github, [])

    def test_post_merge_instructions_allow_pull_and_keep_generated_backup(self):
        from scripts.bootstrap.github import post_merge_commands
        self.publish()
        args = self.runner.github[-1]
        branch = args[args.index('--head') + 1]
        commit = self.command('git', '--git-dir', str(self.remote), 'rev-parse', branch)
        self.command('git', '--git-dir', str(self.remote), 'update-ref', 'refs/heads/main', commit)
        subprocess.run(['bash', '-e', '-c', post_merge_commands(self.config)], cwd=self.root,
                       check=True, capture_output=True, text=True)
        self.assertEqual(self.git('branch', '--show-current'), 'main')
        self.assertEqual(self.git('rev-parse', 'HEAD'), commit)
        self.assertEqual(self.git('status', '--porcelain'), '')
        self.assertIn('deployment setup backup', self.git('stash', 'list'))
        self.assertEqual(self.git('show', 'stash@{0}^3:deploy/config.json'), '{"project":"my-project"}')
