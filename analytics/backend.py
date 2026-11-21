"""Backend boundary: no network during configuration; remote execution is opt-in."""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
from sqlmesh.core.config.connection import DuckDBConnectionConfig, MotherDuckConnectionConfig, PostgresConnectionConfig


class UTCMotherDuckConnectionConfig(MotherDuckConnectionConfig):
    @property
    def _static_connection_kwargs(self):
        # The pinned upstream MotherDuck config ignores connector_config.
        kwargs = super()._static_connection_kwargs
        kwargs['config'] = {**kwargs['config'], 'TimeZone': 'UTC'}
        return kwargs


def required(name):
    value = os.environ.get(name, '')
    if not value:
        raise ValueError(f'{name} is required')
    return value


@dataclass(frozen=True)
class Backend:
    kind: str
    database: str
    state_mode: str = 'local'

    @classmethod
    def from_env(cls, home):
        kind = os.environ.get('TEMPO_BACKEND', 'duckdb')
        if kind == 'duckdb':
            return cls(kind, str(Path(home).resolve()/'warehouse.duckdb'))
        if kind != 'motherduck':
            raise ValueError('TEMPO_BACKEND must be duckdb or motherduck')
        database = required('TEMPO_MOTHERDUCK_DATABASE')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', database):
            raise ValueError('Use a simple lowercase MotherDuck database identifier')
        mode = required('TEMPO_STATE_MODE')
        if mode not in ('local', 'postgres'):
            raise ValueError('TEMPO_STATE_MODE must be local or postgres')
        return cls(kind, database, mode)

    def require_execution(self):
        if self.kind == 'motherduck':
            if os.environ.get('TEMPO_ENABLE_REMOTE') != '1':
                raise ValueError('Remote execution disabled; TEMPO_ENABLE_REMOTE=1 requires separately authorized usage')
            required('motherduck_token')
            if self.state_mode == 'postgres':
                for name in ('TEMPO_STATE_HOST','TEMPO_STATE_DATABASE','TEMPO_STATE_USER','TEMPO_STATE_PASSWORD'):
                    required(name)
            if os.environ.get('TEMPO_REMOTE_SINGLE_WRITER') != '1':
                raise ValueError('Remote pilot requires externally serialized execution and TEMPO_REMOTE_SINGLE_WRITER=1')

    def identity(self):
        identity = dict(version=1, backend=self.kind, database=self.database, state_mode=self.state_mode)
        if self.kind == 'motherduck' and self.state_mode == 'postgres':
            identity['state_target'] = {k: required(k) for k in ('TEMPO_STATE_HOST','TEMPO_STATE_DATABASE','TEMPO_STATE_USER')}
            identity['state_target']['port'] = os.environ.get('TEMPO_STATE_PORT', '5432')
        return identity

    def bind(self, home):
        """Never reuse a publication/checkpoint home against a different target."""
        home = Path(home).resolve()
        home.mkdir(parents=True, exist_ok=True)
        identity = self.identity()
        path = home/'backend.json'
        if not path.exists() and self.kind != 'duckdb' and (home/'warehouse.duckdb').exists():
            raise ValueError('Local warehouse exists; use a fresh home for MotherDuck')
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if json.loads(path.read_text()) != identity:
                raise ValueError('Backend/state target differs from the home binding; use a separate home')
        else:
            with os.fdopen(fd, 'w') as handle:
                json.dump(identity, handle, sort_keys=True)
                handle.flush(); os.fsync(handle.fileno())

    def connect(self, home):
        self.require_execution()
        self.bind(home)
        target = self.database if self.kind == 'duckdb' else f'md:{self.database}?attach_mode=single'
        db = None
        try:
            db = duckdb.connect(target)
            db.execute("SET TimeZone='UTC'")
            return db
        except Exception:
            if db is not None:
                db.close()
            if self.kind == 'motherduck':
                raise RuntimeError('MotherDuck connection failed; verify credentials, database and version compatibility') from None
            raise

    def sqlmesh_connections(self, home):
        if self.kind == 'duckdb':
            return DuckDBConnectionConfig(database=self.database, concurrent_tasks=1,
                connector_config={'TimeZone':'UTC'}), None
        # Leave token unset: the extension reads motherduck_token at runtime.
        connection = UTCMotherDuckConnectionConfig(database=self.database, concurrent_tasks=1)
        if self.state_mode == 'local':
            state = DuckDBConnectionConfig(database=str(Path(home)/'sqlmesh-state.duckdb'), concurrent_tasks=1)
        else:
            try:
                port = int(os.environ.get('TEMPO_STATE_PORT','5432'))
            except ValueError:
                raise ValueError('Invalid TEMPO_STATE_PORT') from None
            if not 1 <= port <= 65535:
                raise ValueError('Invalid TEMPO_STATE_PORT')
            state = PostgresConnectionConfig(host=required('TEMPO_STATE_HOST'), port=port,
                database=required('TEMPO_STATE_DATABASE'), user=required('TEMPO_STATE_USER'),
                password=required('TEMPO_STATE_PASSWORD'), sslmode='verify-full', concurrent_tasks=1)
        return connection, state


def connect(home):
    return Backend.from_env(home).connect(home)


def table_count(db, schema='raw', table=None):
    sql = 'SELECT count(*) FROM information_schema.tables WHERE table_catalog=current_database()'
    params = []
    if schema is not None:
        sql += ' AND table_schema=?'
        params.append(schema)
    if table is not None:
        sql += ' AND table_name=?'
        params.append(table)
    return db.execute(sql, params).fetchone()[0]


def assert_fresh(home):
    backend = Backend.from_env(home)
    backend.require_execution()
    if backend.kind == 'duckdb' and Path(backend.database).exists():
        raise ValueError('Database exists; choose a fresh directory (no destructive reset)')
    with backend.connect(home) as db:
        if table_count(db, schema=None):
            raise ValueError('Raw schema is already initialized; use a fresh database')
