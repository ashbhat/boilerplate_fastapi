"""Create a reviewable deployment PR without switching branches or staging user files."""
import json
import os
import re
import tempfile
from pathlib import Path

from scripts.bootstrap.cloud import CommandError

GENERATED = ('deploy/config.json', '.github/workflows/deploy.yml')


def open_deployment_pr(config, runner, root, confirm, report=print):
    def git(*args, env=None):
        return runner.run(['git', '-C', str(root), *args], env=env)

    remote = git('remote', 'get-url', 'origin')
    match = re.fullmatch(r'(?:git@github.com:|https://github.com/|ssh://git@github.com/)([^/]+/[^/]+?)(?:\.git)?', remote)
    if not match or match[1].lower() != config.repository.lower():
        raise CommandError('The origin remote must match the configured GitHub repository before opening a PR.')
    changed = git('diff', 'HEAD', '--name-only', '-z').split('\0')
    untracked = git('ls-files', '--others', '--exclude-standard', '-z').split('\0')
    other_changes = sorted(set(changed + untracked) - set(GENERATED) - {''})
    if other_changes:
        raise CommandError('Commit or stash these files before rerunning setup to open the PR: ' + ', '.join(other_changes))

    git('fetch', 'origin', f'refs/heads/{config.branch}')
    base = git('rev-parse', 'FETCH_HEAD')
    history = git('rev-list', '--boundary', '--left-right', f'HEAD...{base}').splitlines()
    if any(line.startswith('>') for line in history) and any(line.startswith('-') for line in history):
        raise CommandError('The deployment branch has newer commits missing from this checkout. Merge or rebase it into your branch, then rerun setup.')
    with tempfile.TemporaryDirectory(prefix='deployment-pr-') as directory:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(directory) / 'index')}
        # A temporary index snapshots HEAD plus the two generated files. Using the
        # remote base as parent also supports template copies with unrelated history.
        git('read-tree', 'HEAD', env=env)
        git('add', '--', *GENERATED, env=env)
        tree = git('write-tree', env=env)
        changes = git('diff', '--stat', base, tree)
        if not changes:
            report('Deployment files already match the deployment branch; no PR is needed.')
            return None
        report('The PR will contain committed files from this checkout plus the generated deployment files:')
        report(git('diff', '--name-status', base, tree))
        report(changes)
        report('Review any modified or deleted files before continuing. The current checkout and staging area will stay unchanged.')
        head = f'codex/deploy-{config.resource_id}-{base[:7]}-{tree[:10]}'
        existing = json.loads(runner.run(['gh', 'pr', 'list', '--repo', config.repository,
                                         '--head', head, '--base', config.branch, '--state', 'open', '--json', 'url']))
        if existing:
            git('fetch', 'origin', f'refs/heads/{head}')
            if git('rev-parse', 'FETCH_HEAD^{tree}') != tree:
                raise CommandError('The setup branch contains different files. Refusing to reuse it.')
            report('Reusing the existing deployment PR.')
            return existing[0]['url']
        if not confirm('Push these changes to a setup branch and open a pull request?', True):
            report('PR creation skipped. The generated files are saved locally; rerun setup when ready.')
            return ''
        remote_head = git('ls-remote', '--heads', 'origin', f'refs/heads/{head}')
        if remote_head:
            git('fetch', 'origin', f'refs/heads/{head}')
            if git('rev-parse', 'FETCH_HEAD^{tree}') != tree:
                raise CommandError('The setup branch contains different files. Refusing to overwrite it.')
        else:
            commit = git('commit-tree', tree, '-p', base, '-m', 'Configure Cloud Run deployment')
            git('push', 'origin', f'{commit}:refs/heads/{head}')
        report(f'Setup branch pushed: {head}')
        body = Path(directory) / 'pr.md'
        body.write_text(
            f'Configure deployment of `{config.service}` to Google Cloud Run in '
            f'`{config.project}` / `{config.region}`.\n\n'
            'Cloud setup has completed. This PR includes the committed application snapshot '
            'from the setup checkout and the generated deployment configuration; review the full diff. '
            'Credentials are stored in Secret Manager, not this PR.\n\n'
            f'Merging into `{config.branch}` triggers CI, image publishing, database migrations, '
            'and deployment of the public API. Wait for CI to pass before merging. '
            'The Deploy workflow summary will contain the API URL.\n'
        )
        return runner.run(['gh', 'pr', 'create', '--repo', config.repository, '--base', config.branch,
                           '--head', head, '--title', 'Configure Cloud Run deployment', '--body-file', str(body)])
