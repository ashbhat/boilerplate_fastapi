#!/usr/bin/env python3
"""Interactive Neon / Cloud Run bootstrap. Requires Python 3.9+, gcloud and gh."""
import argparse
import getpass
import warnings
import difflib
import json
import re
import shutil
import sys
from pathlib import Path

# Works from any directory without installing this repository as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bootstrap.cloud import Cloud, CommandError, Runner
from scripts.bootstrap.config import Config, ROOT, neon_url, direct_neon_url, render_workflow


def ask(label, default=None, validate=None, secret=False):
    while True:
        suffix = f' [{default}]' if default is not None else ''
        if secret:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                try:
                    value = getpass.getpass(f'{label}: ').strip()
                except getpass.GetPassWarning as exc:
                    raise RuntimeError('A terminal is required for hidden database input.') from exc
        else:
            value = input(f'{label}{suffix}: ').strip()
        value = value or default
        if not value:
            print('Please enter a value.')
            continue
        try:
            return validate(value) if validate else value
        except ValueError as exc:
            print(str(exc))


def confirm(label, default=False):
    while True:
        value = input(f'{label} [{"Y/n" if default else "y/N"}]: ').strip().lower()
        if not value:
            return default
        if value in ('yes', 'y'):
            return True
        if value in ('no', 'n'):
            return False
        print('Please answer yes or no.')


def choose(label, options):
    print(label)
    for i, option in enumerate(options, 1):
        print(f'  {i}. {option}')
    while True:
        value = input('Choose a number [1]: ').strip() or '1'
        if value.isdigit() and 1 <= int(value) <= len(options):
            return int(value) - 1
        print(f'Choose a number from 1 to {len(options)}.')


def validated(field):
    def validate(value):
        dummy = dict(project='sample-project', project_number='1', region='us-central1',
                     service='api', repository='owner/repo', repository_id='1', owner_id='1',
                     branch='main', public=False)
        dummy[field] = value
        Config.from_dict(dummy)
        return value
    return validate


def preview_file(path, content):
    if path.exists() and path.read_text() != content:
        print(''.join(difflib.unified_diff(path.read_text().splitlines(True), content.splitlines(True),
                                         fromfile=str(path), tofile=f'{path} (proposed)')))
        return confirm(f'Replace {path.relative_to(ROOT)} with the proposed contents?')
    return True


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(content)
    temporary.replace(path)


def setup(dry_run=False):
    runner = Runner()
    for executable in ('gcloud', 'gh', 'git'):
        if not shutil.which(executable):
            raise RuntimeError(f'Install {executable} first, then rerun setup. Sign in with gcloud auth login and gh auth login.')
    runner.run(['gh', 'auth', 'status'])
    account = runner.run(['gcloud', 'auth', 'list', '--filter=status:ACTIVE', '--format=value(account)'])
    if not account:
        raise RuntimeError('Run gcloud auth login first.')
    config_path = ROOT / 'deploy/config.json'
    previous = Config.from_dict(json.loads(config_path.read_text())) if config_path.exists() else None
    print('Set up deployment for this FastAPI project. No database is created in Neon.')
    print(f'Google Cloud account: {account}')
    choose('Deployment destination', ['Google Cloud — Cloud Run'])
    current_project = runner.run(['gcloud', 'config', 'get-value', 'project']).strip()
    project_default = current_project if current_project not in ('', '(unset)') else (previous.project if previous else None)
    project = ask('Existing Google Cloud project ID', project_default, validated('project'))
    project_info = json.loads(runner.run(['gcloud', 'projects', 'describe', project, '--format=json']))
    billing = json.loads(runner.run(['gcloud', 'billing', 'projects', 'describe', project, '--format=json']))
    if not billing.get('billingEnabled'):
        raise RuntimeError('Enable billing for this project, then rerun setup.')
    region = ask('Google Cloud region', previous.region if previous else 'us-central1', validated('region'))
    repository_default = previous.repository if previous else None
    if not repository_default:
        try:
            remote = runner.run(['git', '-C', str(ROOT), 'remote', 'get-url', 'origin'])
            match = re.fullmatch(r'(?:git@github.com:|https://github.com/)([^/]+/[^/]+?)(?:\.git)?', remote)
            if match:
                repository_default = match[1]
        except CommandError:
            pass
    repository = ask('GitHub repository (owner/name)', repository_default, validated('repository'))
    repo = json.loads(runner.run(['gh', 'api', f'repos/{repository}']))
    if not repo.get('permissions', {}).get('push', False):
        raise RuntimeError('Your GitHub account needs push access to this repository.')
    service_default = previous.service if previous else re.sub(r'[^a-z0-9-]', '-', repository.split('/')[1].lower())[:40].strip('-')
    if not service_default or not service_default[0].isalpha():
        service_default = 'my-api'
    service = ask('Cloud Run service name', service_default, validated('service'))
    branch = ask('Deploy when this branch is pushed', previous.branch if previous else repo['default_branch'], validated('branch'))
    public = True
    c = Config(project=project, project_number=str(project_info['projectNumber']), region=region,
               service=service, repository=repo['full_name'], repository_id=str(repo['id']),
               owner_id=str(repo['owner']['id']), branch=branch, public=public)
    workflow = render_workflow(c)
    serialized = json.dumps(c.to_dict(), indent=2) + '\n'
    print(f'\nProject: {project} | Region: {region} | Service: {service}')
    print(f'GitHub: {c.repository} | Branch: {branch} | Access: {"public" if public else "authenticated"}')
    print(f'Configure registry {c.resource_id}, two service accounts, GitHub OIDC trust, and two database secrets.')
    print('The deployer receives Cloud Run Admin and Service Usage Consumer in this project;')
    print('registry, runtime impersonation and secret access are scoped to the created resources.')
    print('Setup creates billable supporting resources; it does not deploy or run migrations.')
    print('Write deploy/config.json and .github/workflows/deploy.yml. Commit these after setup succeeds.')
    if dry_run:
        print('\nPreview only: no files, credentials or cloud resources were changed.\n')
        print(workflow)
        return
    for path, content in ((config_path, serialized), (ROOT / '.github/workflows/deploy.yml', workflow)):
        if not preview_file(path, content):
            print('Cancelled. No resources or files changed.')
            return
    same_resources = previous and (previous.project, previous.resource_id) == (c.project, c.resource_id)
    cloud = Cloud(c, runner)
    secrets_ready = same_resources and cloud.database_secrets_ready()
    if same_resources and not secrets_ready:
        print('Database credentials are not saved or unavailable. Please paste your Neon URL to finish setup.')
    replace = not secrets_ready or confirm('Paste a new Neon URL (rotate stored credentials)?', False)
    database_url = migration_url = None
    if replace:
        print('\nCopy the PostgreSQL connection string from Neon. Input is hidden; do not paste a psql command.')
        database_url = ask('Neon database URL', validate=neon_url, secret=True)
        migration_url = direct_neon_url(database_url)
        print('URL format validated. Connectivity and permissions will be checked by the migration job on deployment.')
    if not confirm('Create/configure these resources and write deployment files now?', False):
        print('Cancelled. No resources or files changed.')
        return
    # Persist non-secret answers first so interrupted provisioning can be resumed.
    write_file(config_path, serialized)
    cloud.provision(database_url, migration_url)
    write_file(ROOT / '.github/workflows/deploy.yml', workflow)
    print('\nSetup complete. Review and commit deploy/config.json and .github/workflows/deploy.yml,')
    print(f'then push to {branch}. The workflow builds, migrates and deploys your API.')
    print('You can also run Deploy from GitHub Actions once the workflow is on the default branch.')
    print('If initial deployment hits IAM propagation delays, wait a few minutes and rerun it.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Read account/project metadata and preview; no writes or secret prompts.')
    args = parser.parse_args()
    try:
        setup(args.dry_run)
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled. If provisioning started, rerun to resume; existing resources are retained.')
        return 1
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
        print(f'\nSetup failed: {exc}', file=sys.stderr)
        print('Fix the issue and rerun. Existing resources are retained; paste the URL again if secrets were not populated.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
