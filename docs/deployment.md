# Deployment reference


Install Python 3.12 (the wizard also supports 3.9+), the
[Google Cloud CLI](https://cloud.google.com/sdk/docs/install),
[GitHub CLI](https://cli.github.com/) and Git. Then sign in:

```bash
gcloud auth login
gh auth login
python scripts/setup.py
```

The wizard offers a deployment-destination menu (Google Cloud Run initially),
text prompts with defaults, yes/no questions, and hidden database URL prompts.
It asks for:

- An **existing Google Cloud project** with billing enabled, region and service name.
- Your GitHub repository and deployment branch (detected where possible).
- Whether the API should be public. The default requires Google IAM authentication.
- A Neon PostgreSQL connection string. Paste the URL itself, without `psql` or quotes.
  Keep `sslmode=require` or `sslmode=verify-full` and other Neon connection options.
- A **direct connection URL for migrations** when the application URL uses pooling.
  In Neon's Connect dialog, turn connection pooling off to obtain this URL.

It shows a summary and asks before making changes. To preview without writing
files or creating resources (still requires authenticated CLI access):

```bash
python scripts/setup.py --dry-run
```

The script does **not** create a Neon database, a Google Cloud project, or a GitHub
repository. Create these first. It validates URL format; the deployment migration
job is the first live database connectivity/permission check. Neon IP restrictions
must allow Cloud Run egress; private network databases need additional configuration.

### What setup creates

Inside the selected Google Cloud project, setup enables the required APIs and creates:

- An Artifact Registry Docker repository.
- A deployment service account and a separate runtime service account.
- A Workload Identity pool/provider trusting only this GitHub repository's immutable
  owner/repository IDs, deployment branch, `deploy.yml` workflow, and push/manual events.
- Two Secret Manager secrets: application and direct migration database URLs.

Database URLs are sent to Secret Manager over stdin, never written to YAML/config,
command arguments or logs. No Google service-account keys or GitHub secrets are
needed. The runtime reads its secrets; GitHub authenticates through OIDC.

Your setup account needs permissions to enable services, inspect project billing,
create/manage Artifact Registry repositories, service accounts, workload identity
pools/providers and secrets, and set their/project IAM policies. A project owner
can bootstrap; organizations may instead delegate these permissions. Organization
policies can disallow public access or identity federation, in which case setup or
deployment reports the relevant error. The GitHub account needs repository push access.

The deployment account receives `roles/run.admin` and
`roles/serviceusage.serviceUsageConsumer` **at project scope** to create services/jobs
and configure public/private access. It receives Artifact Registry Writer on its
registry, Service Account User on its runtime account, and Token Creator on itself
for the private API smoke check. The runtime receives Secret Accessor on its two
secrets. Prefer a dedicated application project if other services need isolation.

### Deploy

After setup succeeds, review and commit the generated files:

```bash
git add deploy/config.json .github/workflows/deploy.yml
git commit -m "Configure Cloud Run deployment"
git push
```

Push to the deployment branch to run the workflow. You can also use **Actions →
Deploy → Run workflow** once the workflow exists on the default branch; select the
configured deployment branch. Other branches cannot authenticate to Google Cloud.

The workflow runs CI, builds and publishes an image, runs `alembic upgrade head` in
a single Cloud Run job, deploys the **same image digest**, and checks `/healthz`.
It creates the actual service and migration job on the first deploy; setup only
creates their supporting resources. Failed migrations stop deployment. Deployments
are serialized and never automatically cancel an active migration. GitHub may
replace older queued deployments with a newer one.

The service scales to zero with a maximum of three instances, one CPU and 512 MiB
memory. These are starter settings, not a spending cap. Cloud resources may incur
charges. The deploy workflow summary contains the API URL. For authenticated APIs,
callers need Cloud Run Invoker and a Google identity token with the service URL as
audience. `/healthz` is a process liveness check, not a database query.

Migrations must stay backward-compatible with the old app during deployment. No
automatic database downgrade or traffic rollback is attempted if deployment or the
smoke check fails. The sample endpoints are scaffolding; the migration checks are
not evidence that an application's business operations work end to end.

### Rerun or customize

`deploy/config.json` contains only non-secret setup answers. The generated
`.github/workflows/deploy.yml` is editable and self-contained. Changing the JSON
alone does not change deployments; rerun setup to regenerate the workflow.

Rerunning reuses resources owned by this setup. It asks before rotating database
credentials or overwriting edited files, and displays file diffs. It will refuse
unrelated resources or an identity provider whose trust no longer matches. Changing
the deployment branch or repository identity therefore requires manually reviewing
and updating the existing provider's trust as well as the workflow.

If setup fails partway through, already-created resources and the non-secret config
are retained. Fix the reported problem and rerun. Choose to paste URLs again if the
failure happened before secret versions were created. There is no automatic cleanup;
delete unneeded Cloud Run resources, registry, secrets, service accounts and identity
pool explicitly in Google Cloud. IAM changes can take a few minutes to propagate.

The secrets use `latest`; choosing new URLs creates new secret versions. Redeploy
to ensure all service instances use the new credentials. Previous versions are
retained. Setup never silently overwrites a customized workflow.

## Tests

```bash
python -m unittest discover -s tests -v
```

Set `TEST_DATABASE_URL` to a **disposable** PostgreSQL database to include the
upgrade/downgrade/upgrade integration test; it drops the sample table. Without it,
that one test is skipped. CI creates PostgreSQL 16 for this test and also builds
and smoke-tests the container. PR checks use no Google Cloud or Neon credentials.

The setup tests exercise prompts, validation, cancellation, partial failures and
secret transport with fake cloud command responses. They do not substitute for a
first deployment against your Google Cloud project's permissions and policies.

Reference: [Google GitHub federation](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines),
[Cloud Run secrets](https://cloud.google.com/run/docs/configuring/services/secrets),
[Neon connection pooling](https://neon.com/docs/connect/connection-pooling).
