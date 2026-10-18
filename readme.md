## FastAPI Boilerplate <br/>
This boilerplate is designed to help get new FastAPI projects off the ground quickly. Just hit 'USE THIS TEMPLATE' to setup a new repository and go from there.


## Step 1: Conda Environment
Create a new miniconda environment. [Install Miniconda](https://conda.io/projects/conda/en/latest/user-guide/install/index.html) first if you haven't already. This will let you create a virtual environment to give you a clean environment to work in.

```bash
conda create -n boilerplate_backend python=3.9
conda activate boilerplate_backend
```

## Step 2: Installing Requirements
You can install requirements with the following command.
```bash
pip install -r requirements.txt
```

## Step 3: Setup Database
Create a local database with the following command. If you choose a different name, make sure to update it in your .env file.
[Install Postgres](https://postgresapp.com) first if you haven't already.
```bash
createdb boilerplate_backend_db;
```

Then, create your .env file. Make sure to set DB_USER and DB_PASS to the values on your machine. These are blank by default.
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=backend_db
DB_USER=
DB_PASSWORD=
```

Now, let's get our database up to speed. Run all migrations with this command:
```bash
alembic upgrade head
```

Your database is now created with a single table called SampleTable. You can check it out under _meta/_migrations/versions/50f2356dd61a_first_revision.py

## Step 4: Starting the Server
You can start the server with the following command
```bash
uvicorn main:app --reload --port 8001
```

## Step 5: Deploy to Services
When you're ready to deploy, you can run the setup script to configure your deployment. Google Cloud Run with a Neon database is currently supported.

For first-time setup, create a Neon database and a Google Cloud project with billing enabled. Install the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) and [GitHub CLI](https://cli.github.com/), then sign in and run:

```bash
gcloud auth login
gh auth login
python scripts/setup.py
```

The script asks you to choose a deployment destination, paste your Neon connection string, and provide your Google Cloud project and GitHub repository details. It asks before creating the supporting resources and generates `.github/workflows/deploy.yml` and `deploy/config.json`. Database credentials are stored in Secret Manager.

If you need to update your deployment configuration later, run the same script again. It reuses existing resources and shows changes before asking to overwrite your deploy YAML. You can preview setup without making changes with:

```bash
python scripts/setup.py --dry-run
```

After setup, review and commit the generated files, then push to your configured deployment branch. GitHub Actions will run checks, apply database migrations, and deploy your API.

**Already configured?** You don't need to run the script again unless your setup needs to change. Keep your existing deploy YAML and push to the configured branch to deploy as usual. Once the workflow is on your default branch, you can also use **Actions → Deploy → Run workflow** and select the configured deployment branch.

See [the deployment reference](docs/deployment.md) for permissions, connection options, and troubleshooting.
