"""Validated, non-secret setup configuration and workflow rendering."""
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]


def neon_url(value):
    value = value.strip()
    try:
        url = urlsplit(value)
        valid = (url.scheme in ('postgres', 'postgresql') and url.hostname
                 and url.hostname.endswith('.neon.tech') and url.username and url.password
                 and url.path not in ('', '/') and not url.fragment
                 and not any(c.isspace() for c in value)
                 and url.port in (None, 5432)
                 and parse_qs(url.query).get('sslmode') in (['require'], ['verify-full']))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Paste a Neon PostgreSQL URL with user, password, database and sslmode=require (or verify-full).')
    return 'postgresql://' + value.split('://', 1)[1]


def direct_neon_url(value):
    """Derive Neon's direct endpoint without changing credentials or URL options."""
    url = urlsplit(neon_url(value))
    credentials, host = url.netloc.rsplit('@', 1)
    endpoint, separator, domain = host.partition('.')
    if endpoint.endswith('-pooler'):
        endpoint = endpoint[:-len('-pooler')]
    return url._replace(netloc=f'{credentials}@{endpoint}{separator}{domain}').geturl()


@dataclass(frozen=True)
class Config:
    project: str
    project_number: str
    region: str
    service: str
    repository: str
    repository_id: str
    owner_id: str
    branch: str
    public: bool = False

    def __post_init__(self):
        patterns = {
            'project': r'[a-z][a-z0-9-]{4,28}[a-z0-9]',
            'project_number': r'[0-9]+',
            'region': r'[a-z]+-[a-z]+[0-9]+',
            'service': r'[a-z](?:[a-z0-9-]{0,38}[a-z0-9])?',
            'repository': r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',
            'repository_id': r'[0-9]+', 'owner_id': r'[0-9]+',
            'branch': r'[A-Za-z0-9][A-Za-z0-9_./-]*',
        }
        for key, pattern in patterns.items():
            value = getattr(self, key)
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise ValueError(f'Invalid {key}; use a simple name without whitespace or shell characters.')
        if any(x in self.branch for x in ('..', '//', '/.', '.lock')) or self.branch.endswith(('/', '.')):
            raise ValueError('Invalid deployment branch.')
        if type(self.public) is not bool:
            raise ValueError('public must be true or false.')

    @property
    def resource_id(self):
        digest = hashlib.sha256(f'{self.repository_id}:{self.service}'.encode()).hexdigest()[:8]
        return f'{self.service[:12]}-{digest}'

    @property
    def deployer(self):
        return f'{self.resource_id}-deploy@{self.project}.iam.gserviceaccount.com'

    @property
    def runtime(self):
        return f'{self.resource_id}-run@{self.project}.iam.gserviceaccount.com'

    @property
    def pool(self):
        return f'gh-{self.resource_id}'

    @property
    def provider(self):
        return f'projects/{self.project_number}/locations/global/workloadIdentityPools/{self.pool}/providers/github'

    @property
    def trust_condition(self):
        # Immutable IDs prevent repository/owner-name reuse from inheriting trust.
        return (f"assertion.repository_id == '{self.repository_id}' && "
                f"assertion.repository_owner_id == '{self.owner_id}' && "
                f"assertion.ref == 'refs/heads/{self.branch}' && "
                f"assertion.workflow_ref == '{self.repository}/.github/workflows/deploy.yml@refs/heads/{self.branch}' && "
                "assertion.event_name in ['push', 'workflow_dispatch']")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


def render_workflow(config):
    template = (ROOT / 'deploy/templates/google-cloud-run.yml').read_text()
    values = {
        'BRANCH': config.branch, 'REF': f'refs/heads/{config.branch}',
        'PROJECT': config.project, 'REGION': config.region, 'SERVICE': config.service,
        'RESOURCE': config.resource_id, 'PROVIDER': config.provider,
        'DEPLOYER': config.deployer, 'RUNTIME': config.runtime,
        'PUBLIC': str(config.public).lower(),
    }
    for key, value in values.items():
        literal = f"'{value}'" if key == 'REF' else json.dumps(value)
        template = template.replace(f'@@{key}@@', literal)
    if '@@' in template:
        raise ValueError('Unresolved deployment template placeholder.')
    return template
