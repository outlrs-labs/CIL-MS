"""Import the local pilot catalog into an empty production PostgreSQL catalog."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values

TABLES = {
    'analyses': ('id', 'owner', 'payload'),
    'reports': ('id', 'owner', 'path', 'title', 'created'),
    'audit_reviews': ('report_id', 'submitter', 'entity', 'category', 'status', 'assistant_reviewer', 'manager_reviewer', 'comment', 'updated'),
    'submissions': ('id', 'entity', 'family', 'cadence', 'period', 'version', 'owner', 'created', 'payload'),
    'report_revisions': ('id', 'series', 'version', 'previous_id'),
    'extractions': ('id', 'entity', 'payload'),
}
ENTITIES = {'ECL', 'BCCL', 'CCL', 'NCL', 'WCL', 'SECL', 'MCL', 'CMPDI'}

DDL = (
    'create table if not exists analyses(id text primary key, owner text not null, payload text not null)',
    'create table if not exists reports(id text primary key, owner text not null, path text not null, title text not null, created double precision not null)',
    "create table if not exists audit_reviews(report_id text primary key, submitter text not null, entity text not null, category text not null default '', status text not null, assistant_reviewer text, manager_reviewer text, comment text not null default '', updated double precision not null)",
    'create table if not exists submissions(id text primary key, entity text, family text, cadence text, period text, version integer, owner text, created double precision, payload text, unique(entity,family,cadence,period,version))',
    'create table if not exists report_revisions(id text primary key, series text, version integer, previous_id text, unique(series,version))',
    'create table if not exists extractions(id text primary key, entity text, payload text)',
)


def migrate(source_path: Path, database_url: str) -> dict[str, int]:
    source = sqlite3.connect(f'file:{source_path}?mode=ro', uri=True)
    result: dict[str, int] = {}
    with psycopg.connect(database_url) as target:
        for statement in DDL:
            target.execute(statement)
        for table, columns in TABLES.items():
            exists = source.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone()
            if not exists:
                result[table] = 0
                continue
            rows = source.execute(f"select {','.join(columns)} from {table}").fetchall()
            if table == 'reports':
                path_index = columns.index('path')
                rebased = []
                for row in rows:
                    values = list(row)
                    parts = Path(values[path_index]).parts
                    entity_at = next((index for index, part in enumerate(parts) if part in ENTITIES), None)
                    if entity_at is None:
                        raise RuntimeError(f'Cannot map report path into the production data root: {values[path_index]}')
                    values[path_index] = str(Path('/srv/cil-data/cil').joinpath(*parts[entity_at:]))
                    rebased.append(tuple(values))
                rows = rebased
            if not rows:
                result[table] = 0
                continue
            placeholders = ','.join(['%s'] * len(columns))
            updates = ','.join(f'{column}=excluded.{column}' for column in columns[1:])
            statement = f"insert into {table} ({','.join(columns)}) values ({placeholders}) on conflict ({columns[0]}) do update set {updates}"
            with target.cursor() as cursor:
                cursor.executemany(statement, rows)
            result[table] = len(rows)
    source.close()
    return result


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3):
        raise SystemExit('Usage: migrate_sqlite_to_postgres.py CATALOG.sqlite3 [.env.production]')
    source_path = Path(sys.argv[1]).resolve()
    env_path = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else Path('.env.production').resolve()
    values = dotenv_values(env_path)
    database_url = values.get('DATABASE_URL') or __import__('os').environ.get('DATABASE_URL', '')
    if not source_path.is_file() or not database_url:
        raise SystemExit('Catalog file and DATABASE_URL are required.')
    counts = migrate(source_path, database_url)
    print('Migrated catalog rows:', ', '.join(f'{name}={count}' for name, count in counts.items()))
