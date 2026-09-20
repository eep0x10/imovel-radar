"""Online SQLite snapshots and restore verification. Never overwrite a target."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from . import storage


def snapshot(destination: Path | None = None):
    storage.initialize()
    destination = destination or storage.db_path().parent / "backups" / ("radar-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".sqlite3")
    destination = destination.resolve()
    manifest = destination.with_suffix(".manifest.json")
    if destination.exists() or manifest.exists():
        raise ValueError("O destino já existe; escolha um novo arquivo")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents races or replacing an existing database.
    with destination.open("xb"):
        pass
    with closing(storage.connect()) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
        integrity = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("Backup não passou na verificação de integridade")
        counts = {table: dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("users", "properties", "observations", "tracking", "sources")}
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    result = {"path": str(destination), "integrity_check": integrity, "sha256": sha, "counts": counts, "created_at": storage.now_iso()}
    with manifest.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2))
    return result


def restore_copy(source: Path, destination: Path):
    if destination.exists() or source.resolve() == destination.resolve():
        raise ValueError("Restaure em um arquivo novo; o banco ativo não é sobrescrito")
    if not source.is_file():
        raise ValueError("Snapshot não encontrado")
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Snapshot inválido")
        tables = {row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"users", "properties", "observations", "tracking", "sources", "schema_versions"}
        version = src.execute("PRAGMA user_version").fetchone()[0]
        if not required.issubset(tables) or version not in (1, 2):
            raise ValueError("Snapshot não corresponde ao esquema compatível do Imóvel Radar")
        if src.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Snapshot contém referências inválidas")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb"):
            pass
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            return {"integrity_check": dst.execute("PRAGMA integrity_check").fetchone()[0], "properties": dst.execute("SELECT COUNT(*) FROM properties").fetchone()[0]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--restore-copy", type=Path)
    args = parser.parse_args()
    if args.restore_copy:
        if not args.out:
            parser.error("--restore-copy requer --out com destino novo")
        result = restore_copy(args.restore_copy, args.out)
    else:
        result = snapshot(args.out)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
