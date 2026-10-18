# Coding guidance

## Application structure

- Put all application feature code in submodules under `api/`. Follow
  `api/sample/` as the directory-layout example.
- Every feature submodule must contain these four files:
  - `controllers.py`: FastAPI routes and HTTP concerns. Delegate business logic
    to services.
  - `models.py`: SQLAlchemy database models using the shared `Base` from
    `_meta._migrations.base`.
  - `schemas.py`: Pydantic request and response schemas.
  - `services.py`: Business logic and database operations.
- Keep all four files even when a module does not yet need models or schemas;
  do not invent unnecessary tables or schemas just to populate them.
- A feature may contain additional submodules when needed. Each nested feature
  submodule follows the same four-file structure.
- Expose a FastAPI `router` from each module's `controllers.py`. Import and
  register feature routers in `api/router.py` with `api_router.include_router()`.
  Nested routers may be composed through their parent module's router, but every
  route must ultimately be registered through `api/router.py`.
- Keep `main.py` focused on application initialization and mounting `api_router`;
  add new feature endpoints in controllers, not directly in `main.py`.
- Tests remain in `tests/`, migrations in `_meta/_migrations/versions/`, and
  setup/deployment tooling in their existing directories.

## Model changes and migrations

- When changing SQLAlchemy models, generate a migration from the repository root:

  ```bash
  alembic revision --autogenerate -m 'Description of changes'
  ```

- Use a descriptive message explaining the schema change. Run autogeneration
  against a development database with the existing migrations applied.
- Review the generated migration: verify `upgrade()`, `downgrade()`, and the
  revision chain. Autogeneration can require manual corrections, particularly
  for renames and data migrations.
- Commit the generated migration alongside the model changes in the same PR.
  Do not submit a model/schema change with an empty migration or no migration.
- Do not rewrite migrations already applied to a shared or deployed database;
  create a new revision instead.
- If the development database is unavailable, report the blocker rather than
  claiming the migration was generated or verified.
- Deployment runs committed migrations before deploying the API. Do not run
  migrations against a deployed database just to generate or test a revision.

## Development and validation

- Use the environment and local database setup in `readme.md`.
- Install development dependencies with `pip install -r requirements-dev.txt`.
- Start the API with `uvicorn main:app --reload --port 8001`.
- Run tests with `python -m unittest discover -s tests -v`. Database integration
  tests require `TEST_DATABASE_URL` pointing to a disposable database: they run
  downgrades that remove tables. Report skipped checks accurately.
- Add or update tests for changed behavior. Keep changes focused and follow the
  existing module structure rather than introducing unnecessary abstractions.

## Configuration and deployment

- Read credentials from environment variables. Never commit or log secrets,
  `.env` contents, or database connection strings.
- When changing generated deployment behavior, update
  `deploy/templates/google-cloud-run.yml`, not only a generated workflow.
- Keep supporting documentation concise and relevant to the requested change.
