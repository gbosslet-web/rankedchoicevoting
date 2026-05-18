# Streamlit Ranked-Choice Voting App

A polished Streamlit ranked-choice voting system for board elections. It supports single-use voter links, multi-seat STV tabulation, admin election management, voter link generation, and live results publishing.

By default, the app runs locally with SQLite, so you do not need a Supabase account to test it.

## Local Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the app:

```bash
streamlit run app.py
```

Open `/?route=admin` to create and manage elections.

For local development, the admin password is:

```text
admin
```

Generated voter links use `/?token=UUID`.

Local elections and ballots are stored in `.data/rcv.sqlite`.

## Supabase Setup

Supabase is only needed when you want durable shared storage on Streamlit Cloud. Streamlit alone does not include a persistent multi-user database.

1. Open your Supabase project.
2. Run `supabase/migration.sql` in the Supabase SQL editor.
3. Open **Project Settings -> API**.
4. Copy **Project URL** into `SUPABASE_URL`.
5. Copy the **anon public** key into `SUPABASE_KEY`.
6. Refresh Streamlit.

## Streamlit Cloud

Add these same secrets in the Streamlit Cloud app settings:

```toml
SUPABASE_URL = "https://your-supabase-project.supabase.co"
SUPABASE_KEY = "your-anon-public-key"
ADMIN_PASSWORD = "change-this-before-launch"
APP_BASE_URL = "https://your-app.streamlit.app"
```

Keep production secret values out of Git. The included `.streamlit/secrets.toml` contains placeholders for local development.
