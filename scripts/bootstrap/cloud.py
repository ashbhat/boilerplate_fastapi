"""Google Cloud bootstrap. All commands use argv, never a shell."""
import json
import subprocess


class CommandError(RuntimeError):
    pass


class Runner:
    def run(self, args, stdin=None):
        try:
            result = subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)
        except OSError as exc:
            raise CommandError(f'Could not run {args[0]}; check installation.') from exc
        if result.returncode:
            # Secret operations suppress all subprocess output: services can echo inputs.
            detail = 'Secret operation failed; inspect IAM/API access and rerun setup.' if stdin is not None else result.stderr.strip()
            raise CommandError(f'{args[0]} command failed: {detail}')
        return result.stdout.strip()


class Cloud:
    def __init__(self, config, runner=None):
        self.c = config
        self.runner = runner or Runner()

    def run(self, args, stdin=None):
        return self.runner.run(['gcloud', *args, f'--project={self.c.project}', '--quiet', '--format=json'], stdin=stdin)

    def ensure(self, describe, create):
        try:
            return json.loads(self.run(describe) or '{}')
        except CommandError as exc:
            if 'NOT_FOUND' not in str(exc):
                raise
        self.run(create)
        return json.loads(self.run(describe) or '{}')

    def owned(self, describe, create, *, account=False):
        data = self.ensure(describe, create)
        if account:
            matches = data.get('description') == f'boilerplate:{self.c.resource_id}'
        else:
            matches = data.get('labels', {}).get('bootstrap_id') == self.c.resource_id
        if not matches:
            raise CommandError('Resource ownership does not match this setup; refusing to modify it.')
        return data

    def bind(self, resource, member, role):
        self.run([*resource, f'--member={member}', f'--role={role}', '--condition=None'])

    def add_secret_version(self, name, value):
        self.run(['secrets', 'versions', 'add', name, '--data-file=-'], stdin=value)

    def check_run_resources(self):
        for kind, name in (('services', self.c.service), ('jobs', f'{self.c.resource_id}-migrate')):
            try:
                data = json.loads(self.run(['run', kind, 'describe', name, f'--region={self.c.region}']))
            except CommandError as exc:
                if 'NOT_FOUND' in str(exc) or 'Cannot find' in str(exc):
                    continue
                raise
            if data.get('metadata', {}).get('labels', {}).get('bootstrap_id') != self.c.resource_id:
                raise CommandError('Cloud Run resource ownership does not match this setup; choose another service name.')

    def provision(self, database_url=None, migration_url=None):
        c = self.c
        print('Enabling Google Cloud APIs...')
        self.run(['services', 'enable', 'run.googleapis.com', 'artifactregistry.googleapis.com',
                  'secretmanager.googleapis.com', 'iam.googleapis.com', 'iamcredentials.googleapis.com',
                  'sts.googleapis.com', 'cloudresourcemanager.googleapis.com'])
        self.check_run_resources()
        print('Configuring image registry and service accounts...')
        self.owned(['artifacts', 'repositories', 'describe', c.resource_id, f'--location={c.region}'],
                   ['artifacts', 'repositories', 'create', c.resource_id, f'--location={c.region}',
                    '--repository-format=docker', f'--labels=bootstrap_id={c.resource_id}'])
        for email in (c.runtime, c.deployer):
            self.owned(['iam', 'service-accounts', 'describe', email],
                       ['iam', 'service-accounts', 'create', email.split('@')[0],
                        f'--description=boilerplate:{c.resource_id}'], account=True)
        member = f'serviceAccount:{c.deployer}'
        for role in ('roles/run.admin', 'roles/serviceusage.serviceUsageConsumer'):
            self.bind(['projects', 'add-iam-policy-binding', c.project], member, role)
        self.bind(['artifacts', 'repositories', 'add-iam-policy-binding', c.resource_id,
                   f'--location={c.region}'], member, 'roles/artifactregistry.writer')
        self.bind(['iam', 'service-accounts', 'add-iam-policy-binding', c.runtime], member,
                  'roles/iam.serviceAccountUser')
        # Needed to mint an audience-bound ID token for the private-service smoke check.
        self.bind(['iam', 'service-accounts', 'add-iam-policy-binding', c.deployer], member,
                  'roles/iam.serviceAccountTokenCreator')

        print('Configuring GitHub OIDC trust...')
        pool_args = [f'--location=global', f'--workload-identity-pool={c.pool}']
        pool = self.ensure(['iam', 'workload-identity-pools', 'describe', c.pool, '--location=global'],
                          ['iam', 'workload-identity-pools', 'create', c.pool, '--location=global',
                           f'--description=boilerplate:{c.resource_id}'])
        if pool.get('description') != f'boilerplate:{c.resource_id}' or pool.get('state') != 'ACTIVE':
            raise CommandError('Existing workload identity pool is not owned/active for this setup.')
        mapping = {'google.subject': 'assertion.sub', 'attribute.repository_id': 'assertion.repository_id'}
        provider = self.ensure(['iam', 'workload-identity-pools', 'providers', 'describe', 'github', *pool_args],
                              ['iam', 'workload-identity-pools', 'providers', 'create-oidc', 'github', *pool_args,
                               '--issuer-uri=https://token.actions.githubusercontent.com',
                               '--attribute-mapping=' + ','.join(f'{k}={v}' for k, v in mapping.items()),
                               f'--attribute-condition={c.trust_condition}'])
        if (provider.get('attributeCondition') != c.trust_condition or
                provider.get('attributeMapping') != mapping or
                provider.get('oidc', {}).get('issuerUri') != 'https://token.actions.githubusercontent.com' or
                provider.get('state') != 'ACTIVE' or provider.get('disabled', False)):
            raise CommandError('Existing GitHub identity provider differs from the requested trust. Review it manually before rerunning.')
        principal = (f'principalSet://iam.googleapis.com/projects/{c.project_number}/locations/global/'
                     f'workloadIdentityPools/{c.pool}/attribute.repository_id/{c.repository_id}')
        self.bind(['iam', 'service-accounts', 'add-iam-policy-binding', c.deployer], principal,
                  'roles/iam.workloadIdentityUser')

        print('Configuring database secrets...')
        for suffix, value in (('database', database_url), ('migrations', migration_url)):
            name = f'{c.resource_id}-{suffix}'
            self.owned(['secrets', 'describe', name],
                       ['secrets', 'create', name, '--replication-policy=automatic',
                        f'--labels=bootstrap_id={c.resource_id}'])
            self.bind(['secrets', 'add-iam-policy-binding', name], f'serviceAccount:{c.runtime}',
                      'roles/secretmanager.secretAccessor')
            if value is not None:
                self.add_secret_version(name, value)
            else:
                version = json.loads(self.run(['secrets', 'versions', 'describe', 'latest', f'--secret={name}']))
                if version.get('state') != 'ENABLED':
                    raise CommandError('The existing database secret has no enabled latest version. Rerun and replace the URLs.')
