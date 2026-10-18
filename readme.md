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
Run the setup script and follow the prompts to configure your deployment. Google Cloud Run with Neon is currently supported.

```bash
python scripts/setup.py
```

The script sets up the supporting resources and creates or updates `.github/workflows/deploy.yml`, asking before overwriting changes. It then previews the changes and opens a pull request. Review the PR, wait for checks to pass, and merge it to start deployment. The Deploy workflow summary contains your API URL.

Already configured? Keep using your existing workflow. Run the script again only when you need to update your setup.
