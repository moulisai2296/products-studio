"""Create the PhotoDukaan tables in Supabase Postgres.

The Supabase service key (PostgREST) cannot run DDL, so table creation needs a
direct Postgres connection. Provide ONE of:

  SUPABASE_DB_URL       full connection string, e.g.
                        postgresql://postgres:PASS@db.<ref>.supabase.co:5432/postgres
  SUPABASE_DB_PASSWORD  just the DB password; the host is derived from SUPABASE_URL

Then run:  python setup_db.py

If neither is set, this prints schema.sql so you can paste it into the
Supabase dashboard SQL editor instead (10 seconds).
"""
import os
import sys
from urllib.parse import urlparse, quote

from dotenv import load_dotenv

load_dotenv()

HERE = os.path.dirname(__file__)
SCHEMA_PATH = os.path.join(HERE, "schema.sql")


def _project_ref() -> str | None:
    url = os.getenv("SUPABASE_URL", "")
    host = urlparse(url).hostname or ""
    # <ref>.supabase.co
    return host.split(".")[0] if host.endswith(".supabase.co") else None


def _connection_string() -> str | None:
    direct = os.getenv("SUPABASE_DB_URL")
    if direct:
        return direct
    password = os.getenv("SUPABASE_DB_PASSWORD")
    ref = _project_ref()
    if password and ref:
        pw = quote(password, safe="")
        return f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
    return None


def main() -> int:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()

    conn_str = _connection_string()
    if not conn_str:
        print("No SUPABASE_DB_URL or SUPABASE_DB_PASSWORD found.\n")
        print("Option A: add SUPABASE_DB_PASSWORD (or SUPABASE_DB_URL) to backend/.env "
              "and re-run:  python setup_db.py")
        print("           Find it in Supabase dashboard -> Project Settings -> Database "
              "-> Connection string.\n")
        print("Option B: paste the SQL below into the Supabase SQL Editor and run it:\n")
        print("-" * 70)
        print(schema)
        print("-" * 70)
        return 1

    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed. Run: pip install psycopg2-binary")
        return 1

    print(f"Connecting to Supabase Postgres ({_project_ref() or 'via SUPABASE_DB_URL'}) ...")
    try:
        conn = psycopg2.connect(conn_str, connect_timeout=15)
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Check the password/host. You can also paste schema.sql into the SQL editor.")
        return 1

    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(schema)
        print("Tables created (sessions, assets). Verifying ...")
        with conn.cursor() as cur:
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema='public' and table_name in ('sessions','assets') "
                "order by table_name;"
            )
            found = [r[0] for r in cur.fetchall()]
        print(f"Present tables: {found}")
        return 0 if set(found) == {"assets", "sessions"} else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
