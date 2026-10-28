from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

BACKEND_DIR = Path(__file__).resolve().parents[3]


def migration_config() -> Config:
    return Config(str(BACKEND_DIR / "alembic.ini"))


def check_schema_current(connection) -> None:
    expected = set(ScriptDirectory.from_config(migration_config()).get_heads())
    current = set(MigrationContext.configure(connection).get_current_heads())
    if current != expected:
        raise RuntimeError("Database schema is not current; run python -m alembic upgrade head (legacy databases require verified adopt-baseline first)")


def validate_baseline(connection) -> None:
    baseline = ScriptDirectory.from_config(migration_config()).get_revision("0001_baseline").module.baseline_metadata()
    inspector = inspect(connection)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    if actual_tables != set(baseline.tables):
        raise RuntimeError("Baseline mismatch: table set; no stamp performed")
    for name, table in baseline.tables.items():
        actual = {c["name"]: c for c in inspector.get_columns(name)}
        if set(actual) != set(table.c.keys()):
            raise RuntimeError(f"Baseline mismatch: {name} columns; no stamp performed")
        for col in table.c:
            got = actual[col.name]
            expected_type = str(col.type.compile(dialect=connection.dialect)).upper()
            got_type = str(got["type"].compile(dialect=connection.dialect)).upper()
            if expected_type != got_type or col.nullable != got["nullable"]:
                raise RuntimeError(f"Baseline mismatch: {name}.{col.name} type/nullability; no stamp performed")
            if col.server_default is not None and got["default"] != str(col.server_default.arg.compile(dialect=connection.dialect)):
                raise RuntimeError(f"Baseline mismatch: {name}.{col.name} default; no stamp performed")
        if set(inspector.get_pk_constraint(name)["constrained_columns"]) != {c.name for c in table.primary_key}:
            raise RuntimeError(f"Baseline mismatch: {name} primary key; no stamp performed")
        expected_fks = {(tuple(c.parent.name for c in f.elements), tuple(c.column.table.name for c in f.elements),
                         tuple(c.column.name for c in f.elements)) for f in table.foreign_key_constraints}
        actual_fks = {(tuple(f["constrained_columns"]), tuple([f["referred_table"]] * len(f["referred_columns"])),
                       tuple(f["referred_columns"])) for f in inspector.get_foreign_keys(name)}
        if expected_fks != actual_fks or any(
            any(value not in (None, False, "NO ACTION") for value in f.get("options", {}).values())
            for f in inspector.get_foreign_keys(name)
        ):
            raise RuntimeError(f"Baseline mismatch: {name} foreign keys; no stamp performed")
        expected_unique = {tuple(c.name for c in constraint.columns) for constraint in table.constraints if constraint.__class__.__name__ == "UniqueConstraint"}
        actual_unique = {tuple(c["column_names"]) for c in inspector.get_unique_constraints(name)}
        if expected_unique != actual_unique:
            raise RuntimeError(f"Baseline mismatch: {name} uniqueness; no stamp performed")
        expected_indexes = {(idx.name, tuple(c.name for c in idx.columns), bool(idx.unique)) for idx in table.indexes}
        actual_indexes = {(idx["name"], tuple(idx["column_names"]), bool(idx["unique"])) for idx in inspector.get_indexes(name) if not idx.get("duplicates_constraint")}
        if (expected_indexes != actual_indexes or inspector.get_check_constraints(name)
                or any(any(idx.get("dialect_options", {}).values()) for idx in inspector.get_indexes(name))):
            raise RuntimeError(f"Baseline mismatch: {name} indexes/checks; no stamp performed")


def adopt_baseline(connection) -> None:
    if MigrationContext.configure(connection).get_current_heads():
        raise RuntimeError("Database is already versioned; use alembic upgrade head")
    validate_baseline(connection)
    config = migration_config()
    config.attributes["connection"] = connection
    command.stamp(config, "0001_baseline")
    command.upgrade(config, "head")
