#!/bin/sh
set -eu

python - <<'PY'
import os
import sys
import time

import psycopg

dsn = (
    f"host={os.environ.get('POSTGRES_HOST', 'db')} "
    f"port={os.environ.get('POSTGRES_PORT', '5432')} "
    f"dbname={os.environ.get('POSTGRES_DB', 'parking')} "
    f"user={os.environ.get('POSTGRES_USER', 'parking')} "
    f"password={os.environ.get('POSTGRES_PASSWORD', 'parking')}"
)
for _attempt in range(30):
    try:
        psycopg.connect(dsn).close()
        break
    except Exception:
        time.sleep(1)
else:
    sys.exit("database is not ready")
PY

python - <<'PY'
import os
import subprocess
import sys

import psycopg

dsn = (
    f"host={os.environ.get('POSTGRES_HOST', 'db')} "
    f"port={os.environ.get('POSTGRES_PORT', '5432')} "
    f"dbname={os.environ.get('POSTGRES_DB', 'parking')} "
    f"user={os.environ.get('POSTGRES_USER', 'parking')} "
    f"password={os.environ.get('POSTGRES_PASSWORD', 'parking')}"
)
# API and worker share this entrypoint. One session holds the lock until
# migrate and seed finish, so a fresh database is not created twice at once.
connection = psycopg.connect(dsn)
connection.autocommit = True
with connection.cursor() as cursor:
    cursor.execute("SELECT pg_advisory_lock(8675309)")
try:
    subprocess.check_call([sys.executable, "manage.py", "migrate", "--noinput"])
    subprocess.check_call([sys.executable, "manage.py", "seed_demo"])
finally:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(8675309)")
    connection.close()
PY
exec "$@"
