# Cloud Run and Neon setup

Goal: after copying this template, run `python scripts/setup.py` to interactively
configure an existing Google Cloud project and generate an editable deployment workflow.
The user approved bootstrap + generation and requested implementation in this chat.

## Design

- Python standard-library wizard: destination menu (Cloud Run initially), pasted
  project/repository/region/service/branch, hidden Neon URLs, yes/no prompts.
- Existing authenticated `gcloud` and `gh`; existing billing-enabled GCP project
  and GitHub repository. No Neon account or database creation.
- Non-secret config committed to deploy/config.json. URLs sent through stdin to
  Secret Manager; never placed in generated files, logs or process arguments.
- Per-service registry, runtime/deployer accounts, secrets and OIDC provider.
  Trust scoped to immutable GitHub owner/repository IDs, branch, workflow and event.
- Bootstrap is explicit, resumable and non-destructive. Existing provider trust
  must match; refuse unrelated resources. Overwrite diffs require confirmation.
- GitHub runs checks, builds an immutable image, runs a single migration job,
  deploys the same image and smoke-checks the authenticated or public service.
- Serialize deployments without cancelling active migration jobs. Private by default.
- Python 3.12 for CI/container. DATABASE_URL for application/migrations, with
  legacy DB_* fallback for local compatibility. Direct URL for Neon migrations.

## Implementation / validation

- [x] Add failing tests for URL handling, prompt validation, generated config,
  cloud errors/reruns, secret transport and workflow rendering.
- [x] Implement wizard/config/provisioning, with preview mode and explicit apply.
- [x] Add container, CI, deployment template and DATABASE_URL support.
- [x] Run unit tests, migration integration against local PostgreSQL if available,
  workflow validation and container smoke check if Docker is available.
- [x] Review the complete diff and document setup, roles, reruns and limitations.

## Review focus

Malformed/encoded URLs; OIDC trust broader than intended; permission errors mistaken
for absent resources; cancelled/failed setup leaving unsafe generated files; retries
accidentally rotating credentials or overwriting user edits. No live cloud provisioning
is part of development validation; first cloud deployment remains an explicit limitation.

## Verification results

29 tests passed including real PostgreSQL 16 migration roundtrip. Docker image built
and returned healthz successfully as a non-root user. CI and rendered deployment
YAML passed actionlint 1.7.7. Independent review found no actionable issues.
Live GCP provisioning, GitHub OIDC exchange and Neon deployment remain unverified.
