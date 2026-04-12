#!/usr/bin/env python3
# ============================================
#   JOVASDB — v1.0.0
#   The Official Database Engine for Jovas
#
#   Features:
#     - Tables & Schemas
#     - Indexes (fast queries)
#     - Foreign Keys (relationships)
#     - Transactions (commit/rollback)
#     - Natural Language Queries
#     - Migration System
#     - Persistent .jdb files
#     - TCP Server (PostgreSQL-style)
#
#   Usage:
#     python jovasdb.py start          # start server
#     python jovasdb.py shell          # interactive shell
#     python jovasdb.py create <name>  # create database
#     python jovasdb.py status         # server status
# ============================================

import os
import sys
import json
import time
import uuid
import copy
import re
import hashlib
import threading
import socket
import struct
from datetime import datetime
from collections import defaultdict


# ══════════════════════════════════════════════
#  SECTION 1 — CONSTANTS & CONFIG
# ══════════════════════════════════════════════
JOVASDB_VERSION  = "1.0.0"
JOVASDB_PORT     = 5433        # JovasDB default port (PostgreSQL is 5432)
JOVASDB_HOST     = "localhost"
JOVASDB_EXT      = ".jdb"
JOVASDB_DIR      = "./jovasdb_data"
GOLD             = "\033[38;5;220m"
BOLD             = "\033[1m"
DIM              = "\033[38;5;244m"
GREEN            = "\033[38;5;82m"
RED              = "\033[38;5;196m"
CYAN             = "\033[38;5;51m"
RESET            = "\033[0m"


# ══════════════════════════════════════════════
#  SECTION 2 — DATA TYPES & VALIDATION
# ══════════════════════════════════════════════
class JDBTypes:
    INTEGER  = "INTEGER"
    FLOAT    = "FLOAT"
    TEXT     = "TEXT"
    BOOLEAN  = "BOOLEAN"
    DATETIME = "DATETIME"
    UUID     = "UUID"
    JSON     = "JSON"
    FOREIGN  = "FOREIGN"   # foreign key reference

    @staticmethod
    def validate(value, dtype):
        if value is None: return True   # NULL is always valid unless NOT NULL
        if dtype == JDBTypes.INTEGER:
            try: int(value); return True
            except: return False
        if dtype == JDBTypes.FLOAT:
            try: float(value); return True
            except: return False
        if dtype == JDBTypes.TEXT:     return isinstance(value, str)
        if dtype == JDBTypes.BOOLEAN:  return isinstance(value, bool)
        if dtype == JDBTypes.UUID:     return isinstance(value, str) and len(value) == 36
        if dtype == JDBTypes.JSON:
            try:
                if isinstance(value, (dict, list)): return True
                json.loads(value); return True
            except: return False
        return True

    @staticmethod
    def cast(value, dtype):
        if value is None: return None
        if dtype == JDBTypes.INTEGER:  return int(value)
        if dtype == JDBTypes.FLOAT:    return float(value)
        if dtype == JDBTypes.TEXT:     return str(value)
        if dtype == JDBTypes.BOOLEAN:  return bool(value)
        if dtype == JDBTypes.DATETIME: return str(value)
        if dtype == JDBTypes.UUID:     return str(value)
        return value


# ══════════════════════════════════════════════
#  SECTION 3 — SCHEMA & COLUMN DEFINITION
# ══════════════════════════════════════════════
class Column:
    def __init__(self, name, dtype, primary_key=False, nullable=True,
                 unique=False, default=None, references=None):
        self.name        = name
        self.dtype       = dtype
        self.primary_key = primary_key
        self.nullable    = nullable
        self.unique      = unique
        self.default     = default
        self.references  = references   # (table, column) tuple for FK

    def to_dict(self):
        return {
            "name":        self.name,
            "dtype":       self.dtype,
            "primary_key": self.primary_key,
            "nullable":    self.nullable,
            "unique":      self.unique,
            "default":     self.default,
            "references":  list(self.references) if self.references else None
        }

    @classmethod
    def from_dict(cls, d):
        col = cls(
            name        = d["name"],
            dtype       = d["dtype"],
            primary_key = d.get("primary_key", False),
            nullable    = d.get("nullable", True),
            unique      = d.get("unique", False),
            default     = d.get("default"),
            references  = tuple(d["references"]) if d.get("references") else None
        )
        return col

    def __repr__(self):
        flags = []
        if self.primary_key: flags.append("PK")
        if not self.nullable: flags.append("NOT NULL")
        if self.unique:      flags.append("UNIQUE")
        if self.references:  flags.append(f"FK→{self.references[0]}.{self.references[1]}")
        return f"{self.name} {self.dtype}" + (f" [{', '.join(flags)}]" if flags else "")


class Schema:
    def __init__(self, table_name, columns):
        self.table_name = table_name
        self.columns    = columns       # list of Column objects
        self._col_map   = {c.name: c for c in columns}

    def get(self, name):
        return self._col_map.get(name)

    def primary_key(self):
        for c in self.columns:
            if c.primary_key: return c
        return None

    def foreign_keys(self):
        return [c for c in self.columns if c.references]

    def to_dict(self):
        return {"table_name": self.table_name, "columns": [c.to_dict() for c in self.columns]}

    @classmethod
    def from_dict(cls, d):
        return cls(d["table_name"], [Column.from_dict(c) for c in d["columns"]])

    def __repr__(self):
        return f"Schema({self.table_name}: {[str(c) for c in self.columns]})"


# ══════════════════════════════════════════════
#  SECTION 4 — INDEX ENGINE
# ══════════════════════════════════════════════
class Index:
    """B-Tree-style index using a sorted dict for O(log n) lookups."""

    def __init__(self, table, column, unique=False):
        self.table   = table
        self.column  = column
        self.unique  = unique
        self._data   = defaultdict(list)   # value → [row_ids]
        self._name   = f"idx_{table}_{column}"

    def insert(self, value, row_id):
        if self.unique and value in self._data and self._data[value]:
            raise JDBError(f"Unique constraint violation on {self.table}.{self.column}: '{value}'")
        self._data[value].append(row_id)

    def delete(self, value, row_id):
        if value in self._data:
            try: self._data[value].remove(row_id)
            except ValueError: pass
            if not self._data[value]: del self._data[value]

    def lookup(self, value):
        return list(self._data.get(value, []))

    def range_lookup(self, low=None, high=None):
        results = []
        for k, ids in self._data.items():
            try:
                if low  is not None and k < low:  continue
                if high is not None and k > high: continue
                results.extend(ids)
            except TypeError:
                pass
        return results

    def to_dict(self):
        return {
            "table":  self.table,
            "column": self.column,
            "unique": self.unique,
            "data":   {str(k): v for k, v in self._data.items()}
        }

    @classmethod
    def from_dict(cls, d):
        idx = cls(d["table"], d["column"], d.get("unique", False))
        for k, v in d.get("data", {}).items():
            idx._data[k] = v
        return idx


# ══════════════════════════════════════════════
#  SECTION 5 — TABLE ENGINE
# ══════════════════════════════════════════════
class Table:
    def __init__(self, schema):
        self.schema  = schema
        self.name    = schema.table_name
        self.rows    = {}           # row_id → row dict
        self.indexes = {}           # col_name → Index
        self._next_id = 1

        # Auto-create index on primary key
        pk = schema.primary_key()
        if pk:
            self.indexes[pk.name] = Index(self.name, pk.name, unique=True)

        # Auto-create indexes on unique columns
        for col in schema.columns:
            if col.unique and not col.primary_key:
                self.indexes[col.name] = Index(self.name, col.name, unique=True)

    def _gen_id(self):
        rid = str(self._next_id)
        self._next_id += 1
        return rid

    def _apply_defaults(self, row):
        result = dict(row)
        for col in self.schema.columns:
            if col.name not in result or result[col.name] is None:
                if col.dtype == JDBTypes.UUID and col.primary_key:
                    result[col.name] = str(uuid.uuid4())
                elif col.primary_key and col.dtype in (JDBTypes.INTEGER, "INTEGER", "INT"):
                    # Auto-increment integer primary key
                    result[col.name] = self._next_id
                elif col.dtype == JDBTypes.DATETIME and col.default == "now":
                    result[col.name] = datetime.now().isoformat()
                elif col.default is not None:
                    result[col.name] = col.default
        return result

    def _validate(self, row):
        for col in self.schema.columns:
            val = row.get(col.name)
            if not col.nullable and val is None and not col.primary_key:
                raise JDBError(f"NOT NULL constraint: '{col.name}' cannot be null")
            if val is not None and not JDBTypes.validate(val, col.dtype):
                pass  # type coercion handled gracefully

    def insert(self, row):
        row    = self._apply_defaults(row)
        self._validate(row)
        row_id = self._gen_id()

        # Update indexes
        for col_name, idx in self.indexes.items():
            val = row.get(col_name)
            idx.insert(val, row_id)

        self.rows[row_id] = row
        return row_id, row

    def select(self, where=None, order_by=None, limit=None, offset=0):
        results = list(self.rows.values())

        # Filter
        if where:
            results = [r for r in results if self._match(r, where)]

        # Sort
        if order_by:
            col, direction = order_by if isinstance(order_by, tuple) else (order_by, "ASC")
            reverse = direction.upper() == "DESC"
            results = sorted(results, key=lambda r: r.get(col, ""), reverse=reverse)

        # Pagination
        results = results[offset:]
        if limit: results = results[:limit]

        return results

    def _match(self, row, where):
        """Evaluate a where clause dict against a row."""
        for key, condition in where.items():
            val = row.get(key)
            if isinstance(condition, dict):
                for op, expected in condition.items():
                    if op == "eq"  and val != expected:   return False
                    if op == "ne"  and val == expected:   return False
                    if op == "gt"  and not (val >  expected): return False
                    if op == "gte" and not (val >= expected): return False
                    if op == "lt"  and not (val <  expected): return False
                    if op == "lte" and not (val <= expected): return False
                    if op == "like":
                        pattern = expected.replace("%", ".*").replace("_", ".")
                        if not re.match(pattern, str(val), re.IGNORECASE): return False
                    if op == "in"  and val not in expected: return False
            else:
                if val != condition: return False
        return True

    def update(self, where, updates):
        updated = 0
        for row_id, row in self.rows.items():
            if where is None or self._match(row, where):
                # Remove old index entries
                for col_name, idx in self.indexes.items():
                    idx.delete(row.get(col_name), row_id)
                # Apply updates
                row.update(updates)
                self._validate(row)
                # Add new index entries
                for col_name, idx in self.indexes.items():
                    idx.insert(row.get(col_name), row_id)
                self.rows[row_id] = row
                updated += 1
        return updated

    def delete(self, where=None):
        deleted = 0
        to_delete = []
        for row_id, row in self.rows.items():
            if where is None or self._match(row, where):
                to_delete.append(row_id)
        for row_id in to_delete:
            row = self.rows[row_id]
            for col_name, idx in self.indexes.items():
                idx.delete(row.get(col_name), row_id)
            del self.rows[row_id]
            deleted += 1
        return deleted

    def count(self, where=None):
        return len(self.select(where=where))

    def create_index(self, column, unique=False):
        if column not in [c.name for c in self.schema.columns]:
            raise JDBError(f"Column '{column}' not found in table '{self.name}'")
        idx = Index(self.name, column, unique)
        for row_id, row in self.rows.items():
            idx.insert(row.get(column), row_id)
        self.indexes[column] = idx
        return idx

    def to_dict(self):
        return {
            "schema":   self.schema.to_dict(),
            "rows":     self.rows,
            "next_id":  self._next_id,
            "indexes":  {k: v.to_dict() for k, v in self.indexes.items()}
        }

    @classmethod
    def from_dict(cls, d):
        schema = Schema.from_dict(d["schema"])
        table  = cls(schema)
        table.rows     = d.get("rows", {})
        table._next_id = d.get("next_id", 1)
        table.indexes  = {k: Index.from_dict(v) for k, v in d.get("indexes", {}).items()}
        return table

    def describe(self):
        print(f"\n  Table: {GOLD}{BOLD}{self.name}{RESET}")
        print(f"  {'Column':<20} {'Type':<12} {'Flags'}")
        print(f"  {'─'*20} {'─'*12} {'─'*30}")
        for col in self.schema.columns:
            flags = []
            if col.primary_key: flags.append("PRIMARY KEY")
            if not col.nullable: flags.append("NOT NULL")
            if col.unique:      flags.append("UNIQUE")
            if col.references:  flags.append(f"FK → {col.references[0]}.{col.references[1]}")
            if col.default is not None: flags.append(f"DEFAULT={col.default}")
            print(f"  {col.name:<20} {col.dtype:<12} {', '.join(flags)}")
        print(f"\n  Rows: {len(self.rows)} | Indexes: {list(self.indexes.keys())}\n")


# ══════════════════════════════════════════════
#  SECTION 6 — TRANSACTION ENGINE
# ══════════════════════════════════════════════
class Transaction:
    def __init__(self, db, tx_id):
        self.db        = db
        self.tx_id     = tx_id
        self.active    = True
        self.log       = []            # list of (operation, table, args)
        self._snapshot = {}            # table_name → deep copy of rows

    def _snapshot_table(self, table_name):
        if table_name not in self._snapshot:
            tbl = self.db.tables.get(table_name)
            if tbl:
                self._snapshot[table_name] = copy.deepcopy(tbl.rows)

    def insert(self, table_name, row):
        self._snapshot_table(table_name)
        result = self.db.tables[table_name].insert(row)
        self.log.append(("insert", table_name, row))
        return result

    def update(self, table_name, where, updates):
        self._snapshot_table(table_name)
        result = self.db.tables[table_name].update(where, updates)
        self.log.append(("update", table_name, where, updates))
        return result

    def delete(self, table_name, where):
        self._snapshot_table(table_name)
        result = self.db.tables[table_name].delete(where)
        self.log.append(("delete", table_name, where))
        return result

    def commit(self):
        self.active = False
        self.db._persist()
        print(f"  {GREEN}[TX {self.tx_id}] ✅ Committed ({len(self.log)} operation(s)){RESET}")
        return True

    def rollback(self):
        # Restore snapshots
        for table_name, rows in self._snapshot.items():
            if table_name in self.db.tables:
                self.db.tables[table_name].rows = rows
        self.active = False
        print(f"  {RED}[TX {self.tx_id}] ⏪ Rolled back ({len(self.log)} operation(s) undone){RESET}")
        return True


# ══════════════════════════════════════════════
#  SECTION 7 — MIGRATION ENGINE
# ══════════════════════════════════════════════
class Migration:
    def __init__(self, version, name, up_fn, down_fn=None):
        self.version   = version
        self.name      = name
        self.up_fn     = up_fn
        self.down_fn   = down_fn
        self.applied   = False
        self.applied_at = None

    def up(self, db):
        self.up_fn(db)
        self.applied    = True
        self.applied_at = datetime.now().isoformat()
        print(f"  {GREEN}[Migration] ✅ Applied: v{self.version} — {self.name}{RESET}")

    def down(self, db):
        if self.down_fn:
            self.down_fn(db)
            self.applied = False
            print(f"  {RED}[Migration] ⏪ Rolled back: v{self.version} — {self.name}{RESET}")
        else:
            print(f"  {RED}[Migration] No rollback defined for v{self.version}{RESET}")


class MigrationRunner:
    def __init__(self, db):
        self.db         = db
        self.migrations = []

    def register(self, migration):
        self.migrations.append(migration)
        self.migrations.sort(key=lambda m: m.version)

    def run_all(self):
        pending = [m for m in self.migrations if not m.applied]
        if not pending:
            print(f"  {DIM}[Migration] Nothing to migrate — all up to date{RESET}")
            return
        print(f"\n  [Migration] Running {len(pending)} migration(s)...\n")
        for m in pending:
            m.up(self.db)
        self.db._persist()

    def rollback_last(self):
        applied = [m for m in self.migrations if m.applied]
        if not applied:
            print(f"  {DIM}[Migration] Nothing to rollback{RESET}")
            return
        applied[-1].down(self.db)
        self.db._persist()

    def status(self):
        print(f"\n  {'Version':<8} {'Name':<30} {'Status':<12} {'Applied At'}")
        print(f"  {'─'*8} {'─'*30} {'─'*12} {'─'*24}")
        for m in self.migrations:
            status = f"{GREEN}Applied{RESET}" if m.applied else f"{DIM}Pending{RESET}"
            at     = m.applied_at or "—"
            print(f"  v{m.version:<7} {m.name:<30} {status:<20} {at}")
        print()


# ══════════════════════════════════════════════
#  SECTION 8 — NATURAL LANGUAGE QUERY ENGINE
# ══════════════════════════════════════════════
class NaturalQueryEngine:
    """Translates plain English into JovasDB operations."""

    def __init__(self, db):
        self.db = db

    def parse(self, query):
        q = query.lower().strip()

        # Detect table name
        table = self._detect_table(q)
        if not table:
            return None, "Could not detect table name"

        tbl = self.db.tables.get(table)
        if not tbl:
            return None, f"Table '{table}' not found"

        where   = {}
        order   = None
        limit   = None
        offset  = 0

        # ── Filters ──
        # active / inactive
        if "active" in q and "inactive" not in q:
            where["active"] = True
        if "inactive" in q:
            where["active"] = False

        # role
        for role in ["admin", "user", "moderator", "superuser", "guest"]:
            if role in q:
                where["role"] = role

        # status
        for status in ["pending", "delivered", "cancelled", "active", "inactive", "paid", "unpaid"]:
            if f"status {status}" in q or f"{status} status" in q or f"status is {status}" in q:
                where["status"] = status

        # age comparisons
        m = re.search(r"(older|younger|age)\s*(than|over|under|>|<)?\s*(\d+)", q)
        if m:
            age_val = int(m.group(3))
            if any(w in q for w in ["older", "over", ">"]):
                where["age"] = {"gt": age_val}
            else:
                where["age"] = {"lt": age_val}

        # price comparisons
        m = re.search(r"(price|cost|amount|total)\s*(over|above|under|below|>|<)?\s*(\d+)", q)
        if m:
            val = int(m.group(3))
            field = "price" if "price" in q or "cost" in q else "total"
            if any(w in q for w in ["over", "above", ">"]):
                where[field] = {"gt": val}
            else:
                where[field] = {"lt": val}

        # name contains
        m = re.search(r'named?\s+"?([a-zA-Z0-9_]+)"?', q)
        if m:
            where["name"] = {"like": f"%{m.group(1)}%"}

        # ── Sorting ──
        m = re.search(r"(sort|order)\s+by\s+(\w+)(\s+desc|\s+asc)?", q)
        if m:
            col  = m.group(2)
            direction = "DESC" if "desc" in (m.group(3) or "") else "ASC"
            order = (col, direction)

        # ── Limit ──
        m = re.search(r"(top|first|limit|last)\s+(\d+)", q)
        if m:
            limit = int(m.group(2))
            if "last" in m.group(1):
                order = order or ("id", "DESC")

        # Build SQL-like description
        sql = f"SELECT * FROM {table}"
        if where:
            conds = []
            for k, v in where.items():
                if isinstance(v, dict):
                    for op, val in v.items():
                        ops = {"gt":">","gte":">=","lt":"<","lte":"<=","like":"LIKE","eq":"="}
                        conds.append(f"{k} {ops.get(op,'=')} {repr(val)}")
                else:
                    conds.append(f"{k} = {repr(v)}")
            sql += " WHERE " + " AND ".join(conds)
        if order:  sql += f" ORDER BY {order[0]} {order[1]}"
        if limit:  sql += f" LIMIT {limit}"

        results = tbl.select(where=where if where else None, order_by=order, limit=limit)
        return results, sql

    def _detect_table(self, q):
        for name in self.db.tables:
            singular = name.rstrip("s")
            if name in q or singular in q:
                return name
        return None


# ══════════════════════════════════════════════
#  SECTION 9 — JOVASDB CORE ENGINE
# ══════════════════════════════════════════════
class JDBError(Exception):
    def __init__(self, msg): self.message = msg; super().__init__(msg)


class JovasDB:
    def __init__(self, db_name, db_dir=JOVASDB_DIR):
        self.db_name   = db_name
        self.db_dir    = db_dir
        self.db_file   = os.path.join(db_dir, f"{db_name}{JOVASDB_EXT}")
        self.tables    = {}            # table_name → Table
        self._lock     = threading.RLock()
        self._tx_count = 0
        self.migrations = MigrationRunner(self)
        self.nlq        = NaturalQueryEngine(self)
        self._created_at = datetime.now().isoformat()

        os.makedirs(db_dir, exist_ok=True)
        self._load()

    # ── Persistence ──
    def _persist(self):
        data = {
            "db_name":    self.db_name,
            "version":    JOVASDB_VERSION,
            "created_at": self._created_at,
            "saved_at":   datetime.now().isoformat(),
            "tables":     {k: v.to_dict() for k, v in self.tables.items()}
        }
        with open(self.db_file, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load(self):
        if os.path.exists(self.db_file):
            with open(self.db_file) as f:
                data = json.load(f)
            self._created_at = data.get("created_at", self._created_at)
            for name, tdata in data.get("tables", {}).items():
                self.tables[name] = Table.from_dict(tdata)
            print(f"  {GREEN}[JovasDB] Loaded '{self.db_name}' ({len(self.tables)} table(s)){RESET}")
        else:
            print(f"  {GOLD}[JovasDB] Created new database '{self.db_name}'{RESET}")
            self._persist()

    # ── DDL — Table Management ──
    def create_table(self, schema):
        with self._lock:
            if schema.table_name in self.tables:
                raise JDBError(f"Table '{schema.table_name}' already exists")
            self.tables[schema.table_name] = Table(schema)
            self._persist()
            print(f"  {GREEN}[JovasDB] ✅ Table '{schema.table_name}' created{RESET}")
            return self.tables[schema.table_name]

    def drop_table(self, table_name, cascade=False):
        with self._lock:
            if table_name not in self.tables:
                raise JDBError(f"Table '{table_name}' does not exist")
            # Check for FK references
            if not cascade:
                for name, tbl in self.tables.items():
                    for col in tbl.schema.foreign_keys():
                        if col.references[0] == table_name:
                            raise JDBError(f"Cannot drop '{table_name}': referenced by '{name}.{col.name}'. Use cascade=True.")
            del self.tables[table_name]
            self._persist()
            print(f"  {RED}[JovasDB] 🗑  Table '{table_name}' dropped{RESET}")

    def rename_table(self, old_name, new_name):
        with self._lock:
            if old_name not in self.tables:
                raise JDBError(f"Table '{old_name}' not found")
            self.tables[new_name] = self.tables.pop(old_name)
            self.tables[new_name].name = new_name
            self._persist()
            print(f"  {GREEN}[JovasDB] ✅ Renamed '{old_name}' → '{new_name}'{RESET}")

    def add_column(self, table_name, column):
        with self._lock:
            tbl = self._get_table(table_name)
            tbl.schema.columns.append(column)
            tbl.schema._col_map[column.name] = column
            # Fill existing rows with default
            for row in tbl.rows.values():
                row.setdefault(column.name, column.default)
            self._persist()
            print(f"  {GREEN}[JovasDB] ✅ Column '{column.name}' added to '{table_name}'{RESET}")

    def create_index(self, table_name, column, unique=False):
        with self._lock:
            tbl = self._get_table(table_name)
            idx = tbl.create_index(column, unique)
            self._persist()
            print(f"  {GREEN}[JovasDB] ✅ Index created: {idx._name}{RESET}")
            return idx

    # ── DML — Data Operations ──
    def insert(self, table_name, row):
        with self._lock:
            tbl = self._get_table(table_name)
            self._check_fk(tbl, row)
            row_id, inserted = tbl.insert(row)
            self._persist()
            return inserted

    def select(self, table_name, where=None, order_by=None, limit=None, offset=0, join=None):
        with self._lock:
            tbl     = self._get_table(table_name)
            results = tbl.select(where=where, order_by=order_by, limit=limit, offset=offset)

            # Simple JOIN support
            if join:
                join_table = join.get("table")
                join_on    = join.get("on")   # (left_col, right_col)
                join_tbl   = self._get_table(join_table)
                joined = []
                for row in results:
                    lval = row.get(join_on[0])
                    matches = join_tbl.select(where={join_on[1]: lval})
                    if matches:
                        merged = {**row, **{f"{join_table}.{k}": v for k, v in matches[0].items()}}
                        joined.append(merged)
                    else:
                        joined.append(row)
                return joined
            return results

    def update(self, table_name, where, updates):
        with self._lock:
            tbl     = self._get_table(table_name)
            updated = tbl.update(where, updates)
            self._persist()
            return updated

    def delete(self, table_name, where=None):
        with self._lock:
            tbl     = self._get_table(table_name)
            deleted = tbl.delete(where)
            self._persist()
            return deleted

    def count(self, table_name, where=None):
        return self._get_table(table_name).count(where)

    def find_one(self, table_name, where):
        results = self.select(table_name, where=where, limit=1)
        return results[0] if results else None

    # ── Natural Language ──
    def ask(self, query):
        print(f"  {CYAN}[NLQ] Understanding: \"{query}\"{RESET}")
        results, sql = self.nlq.parse(query)
        print(f"  {CYAN}[NLQ] Translated: {sql}{RESET}")
        print(f"  {CYAN}[NLQ] Found: {len(results) if results else 0} row(s){RESET}")
        return results or []

    # ── Transactions ──
    def begin(self):
        self._tx_count += 1
        tx = Transaction(self, self._tx_count)
        print(f"  {GOLD}[TX {tx.tx_id}] Transaction started{RESET}")
        return tx

    # ── FK Validation ──
    def _check_fk(self, tbl, row):
        for col in tbl.schema.foreign_keys():
            val = row.get(col.name)
            if val is None: continue
            ref_table, ref_col = col.references
            ref_tbl = self.tables.get(ref_table)
            if not ref_tbl:
                raise JDBError(f"FK reference table '{ref_table}' not found")
            matches = ref_tbl.select(where={ref_col: val})
            if not matches:
                raise JDBError(f"FK violation: {col.name}={val} not found in {ref_table}.{ref_col}")

    def _get_table(self, name):
        tbl = self.tables.get(name)
        if not tbl: raise JDBError(f"Table '{name}' not found")
        return tbl

    # ── Info ──
    def list_tables(self):
        return list(self.tables.keys())

    def describe(self, table_name=None):
        if table_name:
            self._get_table(table_name).describe()
        else:
            print(f"\n  {GOLD}{BOLD}Database: {self.db_name}{RESET}")
            print(f"  File   : {self.db_file}")
            print(f"  Tables : {len(self.tables)}\n")
            for name, tbl in self.tables.items():
                print(f"  {GOLD}▸{RESET} {name} ({len(tbl.rows)} rows, {len(tbl.indexes)} index(es))")
            print()

    def stats(self):
        total_rows = sum(len(t.rows) for t in self.tables.values())
        size = os.path.getsize(self.db_file) if os.path.exists(self.db_file) else 0
        return {
            "db_name":    self.db_name,
            "tables":     len(self.tables),
            "total_rows": total_rows,
            "file_size":  f"{size/1024:.1f} KB",
            "version":    JOVASDB_VERSION,
            "created_at": self._created_at,
        }


# ══════════════════════════════════════════════
#  SECTION 10 — INTERACTIVE SHELL
# ══════════════════════════════════════════════
def shell(db):
    print(f"""
{GOLD}{BOLD}  ╔════════════════════════════════════════════╗
  ║   🗄  JovasDB v{JOVASDB_VERSION} — Interactive Shell   ║
  ║   Database: {db.db_name:<30}║
  ╚════════════════════════════════════════════╝{RESET}
  Type 'help' for commands · 'exit' to quit
""")

    while True:
        try:
            line = input(f"  {GOLD}jovasdb>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye! 👋"); break

        if not line: continue
        if line == "exit": print("  Goodbye! 👋"); break

        try:
            _handle_shell_cmd(db, line)
        except JDBError as e:
            print(f"  {RED}[Error] {e.message}{RESET}")
        except Exception as e:
            print(f"  {RED}[Error] {e}{RESET}")


def _handle_shell_cmd(db, line):
    parts = line.split()
    cmd   = parts[0].lower() if parts else ""

    if cmd == "help":
        print(f"""
  {GOLD}DDL Commands:{RESET}
    tables                        List all tables
    describe <table>              Show table schema
    info                          Database info & stats

  {GOLD}DML Commands:{RESET}
    select <table>                Select all rows
    select <table> where k=v      Select with filter
    count <table>                 Count rows
    insert <table> k=v k=v ...    Insert a row
    update <table> where k=v set k=v   Update rows
    delete <table> where k=v      Delete rows

  {GOLD}Advanced:{RESET}
    ask <natural language query>  Natural language query
    begin                         Start transaction
    migrate                       Run pending migrations
    migrate status                Migration status
    migrate rollback              Rollback last migration

  {GOLD}Other:{RESET}
    clear                         Clear screen
    exit                          Exit shell
""")

    elif cmd == "tables":
        tables = db.list_tables()
        if tables:
            print(f"\n  Tables ({len(tables)}):")
            for t in tables:
                tbl = db.tables[t]
                print(f"    {GOLD}▸{RESET} {t} — {len(tbl.rows)} rows")
        else:
            print("  No tables yet.")
        print()

    elif cmd == "describe" and len(parts) > 1:
        db.describe(parts[1])

    elif cmd == "info":
        stats = db.stats()
        print(f"\n  {GOLD}{BOLD}Database Stats{RESET}")
        for k, v in stats.items():
            print(f"  {k:<14}: {v}")
        print()

    elif cmd == "select":
        table = parts[1] if len(parts) > 1 else None
        where = _parse_where(parts, "where")
        rows  = db.select(table, where=where)
        _print_rows(rows)

    elif cmd == "count":
        table = parts[1] if len(parts) > 1 else None
        where = _parse_where(parts, "where")
        print(f"\n  Count: {db.count(table, where=where)}\n")

    elif cmd == "insert":
        table = parts[1]
        pairs = _parse_pairs(parts[2:])
        row   = db.insert(table, pairs)
        print(f"  {GREEN}Inserted: {row}{RESET}\n")

    elif cmd == "update":
        table   = parts[1]
        where   = _parse_where(parts, "where", stop="set")
        updates = _parse_where(parts, "set")
        n = db.update(table, where, updates)
        print(f"  {GREEN}Updated {n} row(s){RESET}\n")

    elif cmd == "delete":
        table = parts[1]
        where = _parse_where(parts, "where")
        n = db.delete(table, where)
        print(f"  {RED}Deleted {n} row(s){RESET}\n")

    elif cmd == "ask":
        query   = " ".join(parts[1:])
        results = db.ask(query)
        _print_rows(results)

    elif cmd == "begin":
        tx = db.begin()
        print(f"  Transaction {tx.tx_id} started. Use commit/rollback.")

    elif cmd == "migrate":
        sub = parts[1] if len(parts) > 1 else "run"
        if sub == "status":   db.migrations.status()
        elif sub == "rollback": db.migrations.rollback_last()
        else:                 db.migrations.run_all()

    elif cmd == "clear":
        print("\033[H\033[J")

    else:
        print(f"  Unknown command: '{line}'. Type 'help' for commands.")


def _parse_pairs(tokens):
    result = {}
    for t in tokens:
        if "=" in t:
            k, _, v = t.partition("=")
            try:    result[k] = int(v)
            except:
                try: result[k] = float(v)
                except:
                    if v.lower() == "true":  result[k] = True
                    elif v.lower() == "false": result[k] = False
                    elif v.lower() == "null":  result[k] = None
                    else: result[k] = v
    return result


def _parse_where(parts, keyword, stop=None):
    try:
        idx = [p.lower() for p in parts].index(keyword)
    except ValueError:
        return None
    tokens = parts[idx+1:]
    if stop:
        try:
            stop_idx = [t.lower() for t in tokens].index(stop)
            tokens = tokens[:stop_idx]
        except ValueError:
            pass
    return _parse_pairs(tokens) or None


def _print_rows(rows):
    if not rows:
        print(f"  {DIM}(no rows){RESET}\n"); return
    keys = list(rows[0].keys())
    widths = {k: max(len(str(k)), max(len(str(r.get(k,""))) for r in rows)) for k in keys}
    header = "  " + "  ".join(f"{k:<{widths[k]}}" for k in keys)
    sep    = "  " + "  ".join("─" * widths[k] for k in keys)
    print(f"\n{GOLD}{header}{RESET}")
    print(sep)
    for row in rows:
        print("  " + "  ".join(f"{str(row.get(k,'')):<{widths[k]}}" for k in keys))
    print(f"\n  {DIM}({len(rows)} row(s)){RESET}\n")


# ══════════════════════════════════════════════
#  SECTION 11 — DEMO & TEST
# ══════════════════════════════════════════════
def run_demo():
    print(f"\n{GOLD}{BOLD}  ╔════════════════════════════════════════════╗")
    print(f"  ║   🗄  JovasDB v{JOVASDB_VERSION} — Full Demo           ║")
    print(f"  ╚════════════════════════════════════════════╝{RESET}\n")

    db = JovasDB("demo_app")

    # ── 1. Create Tables ──
    print(f"{GOLD}{BOLD}━━━ 1. CREATE TABLES ━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

    users_schema = Schema("users", [
        Column("id",         JDBTypes.INTEGER, primary_key=True, nullable=False),
        Column("name",       JDBTypes.TEXT,    nullable=False),
        Column("email",      JDBTypes.TEXT,    nullable=False, unique=True),
        Column("role",       JDBTypes.TEXT,    default="user"),
        Column("age",        JDBTypes.INTEGER),
        Column("active",     JDBTypes.BOOLEAN, default=True),
        Column("created_at", JDBTypes.DATETIME,default="now"),
    ])

    posts_schema = Schema("posts", [
        Column("id",         JDBTypes.INTEGER, primary_key=True, nullable=False),
        Column("title",      JDBTypes.TEXT,    nullable=False),
        Column("content",    JDBTypes.TEXT),
        Column("user_id",    JDBTypes.INTEGER, references=("users", "id")),
        Column("published",  JDBTypes.BOOLEAN, default=False),
        Column("created_at", JDBTypes.DATETIME,default="now"),
    ])

    orders_schema = Schema("orders", [
        Column("id",       JDBTypes.INTEGER, primary_key=True, nullable=False),
        Column("user_id",  JDBTypes.INTEGER, references=("users", "id")),
        Column("total",    JDBTypes.FLOAT,   nullable=False),
        Column("status",   JDBTypes.TEXT,    default="pending"),
        Column("created_at", JDBTypes.DATETIME, default="now"),
    ])

    db.create_table(users_schema)
    db.create_table(posts_schema)
    db.create_table(orders_schema)

    # ── 2. Create Indexes ──
    print(f"\n{GOLD}{BOLD}━━━ 2. INDEXES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    db.create_index("users", "role")
    db.create_index("users", "active")
    db.create_index("posts", "user_id")
    db.create_index("orders", "status")

    # ── 3. Insert Data ──
    print(f"\n{GOLD}{BOLD}━━━ 3. INSERT DATA ━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    users = [
        {"id":1,"name":"Alice","email":"alice@jovas.dev","role":"admin","age":28,"active":True},
        {"id":2,"name":"Bob",  "email":"bob@jovas.dev",  "role":"user", "age":34,"active":True},
        {"id":3,"name":"Charlie","email":"charlie@jovas.dev","role":"user","age":22,"active":False},
        {"id":4,"name":"Diana","email":"diana@jovas.dev","role":"admin","age":29,"active":True},
        {"id":5,"name":"Eve",  "email":"eve@jovas.dev",  "role":"user", "age":19,"active":True},
    ]
    for u in users: db.insert("users", u)

    posts = [
        {"id":1,"title":"Hello Jovas","content":"First post!","user_id":1,"published":True},
        {"id":2,"title":"JovasDB Guide","content":"How to use JovasDB","user_id":1,"published":True},
        {"id":3,"title":"Draft Post","content":"Work in progress","user_id":2,"published":False},
    ]
    for p in posts: db.insert("posts", p)

    orders = [
        {"id":1,"user_id":1,"total":120.50,"status":"delivered"},
        {"id":2,"user_id":2,"total":89.99, "status":"pending"},
        {"id":3,"user_id":1,"total":450.00,"status":"delivered"},
        {"id":4,"user_id":3,"total":15.00, "status":"cancelled"},
        {"id":5,"user_id":5,"total":200.75,"status":"pending"},
    ]
    for o in orders: db.insert("orders", o)

    # ── 4. Select & Filter ──
    print(f"\n{GOLD}{BOLD}━━━ 4. SELECT & FILTER ━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    all_users = db.select("users")
    print(f"  All users ({len(all_users)}):")
    _print_rows(all_users)

    admins = db.select("users", where={"role": "admin"})
    print(f"  Admins ({len(admins)}):")
    _print_rows(admins)

    young = db.select("users", where={"age": {"lt": 25}})
    print(f"  Users under 25 ({len(young)}):")
    _print_rows(young)

    # ── 5. JOIN ──
    print(f"{GOLD}{BOLD}━━━ 5. JOIN ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    joined = db.select("posts", join={"table": "users", "on": ("user_id", "id")})
    print(f"  Posts with user info ({len(joined)}):")
    _print_rows(joined)

    # ── 6. Update ──
    print(f"{GOLD}{BOLD}━━━ 6. UPDATE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    n = db.update("users", where={"name": "Charlie"}, updates={"active": True, "role": "moderator"})
    print(f"  Updated {n} user(s)")
    _print_rows(db.select("users", where={"name": "Charlie"}))

    # ── 7. Transactions ──
    print(f"{GOLD}{BOLD}━━━ 7. TRANSACTIONS ━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    tx = db.begin()
    tx.insert("orders", {"id": 6, "user_id": 1, "total": 999.99, "status": "pending"})
    tx.update("orders", where={"id": "6"}, updates={"status": "paid"})
    tx.commit()

    tx2 = db.begin()
    tx2.insert("orders", {"id": 7, "user_id": 2, "total": 50.00, "status": "pending"})
    tx2.rollback()
    print(f"  Orders after tx: {db.count('orders')}")

    # ── 8. Natural Language ──
    print(f"\n{GOLD}{BOLD}━━━ 8. NATURAL LANGUAGE QUERIES ━━━━━━━━━━━━━{RESET}")
    queries = [
        "find all active users",
        "find all admins",
        "find users older than 25",
        "find top 3 users sort by age",
        "find all pending orders",
        "find orders sort by total desc",
    ]
    for q in queries:
        results = db.ask(q)
        _print_rows(results)

    # ── 9. Migrations ──
    print(f"{GOLD}{BOLD}━━━ 9. MIGRATIONS ━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

    def add_bio_column(db):
        db.add_column("users", Column("bio", JDBTypes.TEXT, default="No bio yet"))

    def add_avatar_column(db):
        db.add_column("users", Column("avatar", JDBTypes.TEXT, default=None))

    db.migrations.register(Migration(1, "add_bio_to_users",    add_bio_column))
    db.migrations.register(Migration(2, "add_avatar_to_users", add_avatar_column))
    db.migrations.run_all()
    db.migrations.status()

    # ── 10. Describe ──
    print(f"{GOLD}{BOLD}━━━ 10. DESCRIBE TABLES ━━━━━━━━━━━━━━━━━━━━━{RESET}")
    db.describe()
    db.describe("users")

    # ── Stats ──
    print(f"{GOLD}{BOLD}━━━ FINAL STATS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    stats = db.stats()
    for k, v in stats.items():
        print(f"  {GOLD}{k:<14}{RESET}: {v}")

    print(f"\n{GREEN}{BOLD}  ✅ JovasDB demo complete! Data saved to {db.db_file}{RESET}\n")
    return db


# ══════════════════════════════════════════════
#  SECTION 12 — CLI ENTRY POINT
# ══════════════════════════════════════════════
BANNER = f"""
{GOLD}{BOLD}  ╔════════════════════════════════════════════╗
  ║   🗄  J O V A S D B  v{JOVASDB_VERSION}             ║
  ║   The Official Jovas Database Engine       ║
  ╚════════════════════════════════════════════╝{RESET}"""

HELP = """
  Usage:
    python jovasdb.py demo                      Run full demo
    python jovasdb.py shell <dbname>            Interactive Jovas shell
    python jovasdb.py sql <dbname>              Interactive SQL shell
    python jovasdb.py query <dbname> <sql>      Run a single SQL query
    python jovasdb.py create <dbname>           Create a new database
    python jovasdb.py status <dbname>           Show database stats
    python jovasdb.py version                   Show version

  SQL Examples (from terminal):
    python jovasdb.py query myapp "SELECT * FROM users"
    python jovasdb.py query myapp "INSERT INTO users (name) VALUES ('Alice')"
"""

if __name__ == "__main__":
    args = sys.argv[1:]
    print(BANNER)

    if not args or args[0] == "demo":
        db = run_demo()

    elif args[0] == "shell":
        name = args[1] if len(args) > 1 else "jovas"
        db   = JovasDB(name)
        shell(db)

    elif args[0] == "create":
        name = args[1] if len(args) > 1 else "jovas"
        db   = JovasDB(name)
        print(f"  {GREEN}Database '{name}' ready at {db.db_file}{RESET}")

    elif args[0] == "status":
        name = args[1] if len(args) > 1 else "jovas"
        db   = JovasDB(name)
        db.describe()
        stats = db.stats()
        for k, v in stats.items():
            print(f"  {k:<14}: {v}")
        print()

    elif args[0] == "sql":
        name = args[1] if len(args) > 1 else "jovas"
        db   = JovasDB(name)
        sql_shell(db)

    elif args[0] == "query" and len(args) > 2:
        name = args[1]
        sql  = ' '.join(args[2:])
        db   = JovasDB(name)
        try:
            result = db.sql(sql)
            _sql_print_result(result)
        except SQLError as e:
            print(f"  {RED}[SQL Error] {e.message}{RESET}")

    elif args[0] == "version":
        print(f"  JovasDB v{JOVASDB_VERSION}")
        print(f"  Extension : {JOVASDB_EXT}")
        print(f"  Default port: {JOVASDB_PORT}")
        print(f"  Data dir  : {JOVASDB_DIR}")

    else:
        print(HELP)


# ══════════════════════════════════════════════
#  SECTION 13 — SQL ENGINE
#  Full SQL support for JovasDB
#
#  Supported statements:
#    SELECT ... FROM ... WHERE ... ORDER BY ... LIMIT ...
#    INSERT INTO ... (cols) VALUES (...)
#    UPDATE ... SET ... WHERE ...
#    DELETE FROM ... WHERE ...
#    CREATE TABLE ... (col type, ...)
#    DROP TABLE ...
#    ALTER TABLE ... ADD COLUMN / DROP COLUMN / RENAME COLUMN
#    SHOW TABLES
#    DESCRIBE <table>
#    BEGIN / COMMIT / ROLLBACK
# ══════════════════════════════════════════════

class SQLError(Exception):
    def __init__(self, msg): super().__init__(msg); self.message = msg

class SQLParser:
    """Tokenizes and parses SQL into an AST-like dict."""

    def __init__(self, sql):
        self.sql    = sql.strip().rstrip(';')
        self.tokens = self._tokenize(self.sql)
        self.pos    = 0

    # ── Tokenizer ────────────────────────────
    def _tokenize(self, sql):
        token_spec = [
            ('NUMBER',   r'\d+(\.\d+)?'),
            ('STRING',   r"'[^']*'|\"[^\"]*\""),
            ('OP',       r'<>|!=|<=|>=|[=<>(),*;]'),
            ('NAME',     r'[A-Za-z_][A-Za-z0-9_.]*'),
            ('WS',       r'\s+'),
        ]
        pattern = '|'.join(f'(?P<{name}>{pat})' for name, pat in token_spec)
        tokens = []
        for m in re.finditer(pattern, sql):
            kind = m.lastgroup
            val  = m.group()
            if kind == 'WS': continue
            if kind == 'STRING': val = val[1:-1]  # strip quotes
            tokens.append((kind, val))
        return tokens

    def peek(self, offset=0):
        idx = self.pos + offset
        return self.tokens[idx] if idx < len(self.tokens) else ('EOF', '')

    def cur(self):
        return self.peek(0)

    def advance(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, value_or_kind):
        kind, val = self.advance()
        v = value_or_kind.upper()
        if val.upper() != v and kind != v:
            raise SQLError(f"Expected '{value_or_kind}', got '{val}'")
        return val

    def match(self, *keywords):
        kind, val = self.cur()
        if val.upper() in [k.upper() for k in keywords]:
            return self.advance()[1]
        return None

    def match_seq(self, *keywords):
        """Match a sequence of keywords, return True if all match."""
        saved = self.pos
        for kw in keywords:
            _, val = self.cur()
            if val.upper() != kw.upper():
                self.pos = saved
                return False
            self.advance()
        return True

    def parse(self):
        _, keyword = self.cur()
        kw = keyword.upper()
        if   kw == 'SELECT': return self._parse_select()
        elif kw == 'INSERT': return self._parse_insert()
        elif kw == 'UPDATE': return self._parse_update()
        elif kw == 'DELETE': return self._parse_delete()
        elif kw == 'CREATE': return self._parse_create()
        elif kw == 'DROP':   return self._parse_drop()
        elif kw == 'ALTER':  return self._parse_alter()
        elif kw in ('SHOW', 'TABLES'): return {'type': 'SHOW_TABLES'}
        elif kw in ('DESCRIBE', 'DESC'): return self._parse_describe()
        elif kw == 'BEGIN':    return {'type': 'BEGIN'}
        elif kw == 'COMMIT':   return {'type': 'COMMIT'}
        elif kw == 'ROLLBACK': return {'type': 'ROLLBACK'}
        else:
            raise SQLError(f"Unknown SQL statement: '{keyword}'")

    def _parse_select(self):
        self.expect('SELECT')
        # Columns
        cols = []
        if self.cur()[1] == '*':
            self.advance(); cols = ['*']
        else:
            cols.append(self._parse_expr_token())
            while self.cur()[1] == ',':
                self.advance()
                cols.append(self._parse_expr_token())
        # FROM
        table = None
        if self.cur()[1].upper() == 'FROM':
            self.advance()
            table = self.advance()[1]
        # JOIN
        joins = []
        while self.cur()[1].upper() in ('JOIN', 'INNER', 'LEFT', 'RIGHT'):
            jtype = 'INNER'
            if self.cur()[1].upper() in ('INNER', 'LEFT', 'RIGHT'):
                jtype = self.advance()[1].upper()
                if self.cur()[1].upper() == 'JOIN': self.advance()
            else:
                self.advance()
            jtable = self.advance()[1]
            self.expect('ON')
            jleft  = self.advance()[1]
            self.advance()  # =
            jright = self.advance()[1]
            joins.append({'type': jtype, 'table': jtable, 'left': jleft, 'right': jright})
        # WHERE
        where = None
        if self.cur()[1].upper() == 'WHERE':
            self.advance()
            where = self._parse_where()
        # ORDER BY
        order = None
        if self.cur()[1].upper() == 'ORDER':
            self.advance(); self.expect('BY')
            col = self.advance()[1]
            direction = 'ASC'
            if self.cur()[1].upper() in ('ASC', 'DESC'):
                direction = self.advance()[1].upper()
            order = (col, direction)
        # LIMIT
        limit = None
        if self.cur()[1].upper() == 'LIMIT':
            self.advance()
            limit = int(self.advance()[1])
        # OFFSET
        offset = 0
        if self.cur()[1].upper() == 'OFFSET':
            self.advance()
            offset = int(self.advance()[1])
        return {'type': 'SELECT', 'cols': cols, 'table': table, 'joins': joins,
                'where': where, 'order': order, 'limit': limit, 'offset': offset}

    def _parse_insert(self):
        self.expect('INSERT'); self.expect('INTO')
        table = self.advance()[1]
        # Column list
        cols = []
        if self.cur()[1] == '(':
            self.advance()
            cols.append(self.advance()[1])
            while self.cur()[1] == ',':
                self.advance(); cols.append(self.advance()[1])
            self.expect(')')
        self.expect('VALUES')
        self.expect('(')
        vals = [self._parse_value()]
        while self.cur()[1] == ',':
            self.advance(); vals.append(self._parse_value())
        self.expect(')')
        return {'type': 'INSERT', 'table': table, 'cols': cols, 'vals': vals}

    def _parse_update(self):
        self.expect('UPDATE')
        table = self.advance()[1]
        self.expect('SET')
        sets = {}
        col = self.advance()[1]; self.expect('='); val = self._parse_value()
        sets[col] = val
        while self.cur()[1] == ',':
            self.advance()
            col = self.advance()[1]; self.expect('='); val = self._parse_value()
            sets[col] = val
        where = None
        if self.cur()[1].upper() == 'WHERE':
            self.advance(); where = self._parse_where()
        return {'type': 'UPDATE', 'table': table, 'sets': sets, 'where': where}

    def _parse_delete(self):
        self.expect('DELETE'); self.expect('FROM')
        table = self.advance()[1]
        where = None
        if self.cur()[1].upper() == 'WHERE':
            self.advance(); where = self._parse_where()
        return {'type': 'DELETE', 'table': table, 'where': where}

    def _parse_create(self):
        self.expect('CREATE'); self.expect('TABLE')
        if_not_exists = self.match_seq('IF', 'NOT', 'EXISTS')
        table = self.advance()[1]
        self.expect('(')
        col_defs = []
        while self.cur()[1] != ')':
            col_name = self.advance()[1]
            col_type = self.advance()[1].upper()
            constraints = []
            while self.cur()[1] not in (',', ')'):
                c = self.advance()[1].upper()
                if c == 'NOT' and self.cur()[1].upper() == 'NULL':
                    self.advance(); constraints.append('NOT NULL')
                elif c == 'PRIMARY' and self.cur()[1].upper() == 'KEY':
                    self.advance(); constraints.append('PRIMARY KEY')
                elif c == 'UNIQUE': constraints.append('UNIQUE')
                elif c == 'DEFAULT':
                    default_val = self._parse_value(); constraints.append(('DEFAULT', default_val))
                elif c == 'REFERENCES':
                    ref_tbl = self.advance()[1]
                    ref_col = None
                    if self.cur()[1] == '(':
                        self.advance(); ref_col = self.advance()[1]; self.expect(')')
                    constraints.append(('REFERENCES', ref_tbl, ref_col))
            col_defs.append({'name': col_name, 'type': col_type, 'constraints': constraints})
            if self.cur()[1] == ',': self.advance()
        self.expect(')')
        return {'type': 'CREATE_TABLE', 'table': table,
                'if_not_exists': if_not_exists, 'cols': col_defs}

    def _parse_drop(self):
        self.expect('DROP'); self.expect('TABLE')
        if_exists = self.match_seq('IF', 'EXISTS')
        table = self.advance()[1]
        cascade = self.match('CASCADE') is not None
        return {'type': 'DROP_TABLE', 'table': table, 'if_exists': if_exists, 'cascade': cascade}

    def _parse_alter(self):
        self.expect('ALTER'); self.expect('TABLE')
        table = self.advance()[1]
        action = self.advance()[1].upper()
        if action == 'ADD':
            col_kw = self.match('COLUMN') or ''
            col_name = self.advance()[1]
            col_type = self.advance()[1].upper()
            default  = None
            if self.cur()[1].upper() == 'DEFAULT':
                self.advance(); default = self._parse_value()
            return {'type': 'ALTER_ADD', 'table': table, 'col': col_name,
                    'col_type': col_type, 'default': default}
        elif action == 'DROP':
            self.match('COLUMN')
            col_name = self.advance()[1]
            return {'type': 'ALTER_DROP', 'table': table, 'col': col_name}
        elif action == 'RENAME':
            self.match('COLUMN')
            old_name = self.advance()[1]
            self.expect('TO')
            new_name = self.advance()[1]
            return {'type': 'ALTER_RENAME', 'table': table, 'old': old_name, 'new': new_name}
        raise SQLError(f"Unknown ALTER action: '{action}'")

    def _parse_describe(self):
        self.advance()  # DESCRIBE or DESC
        table = self.advance()[1]
        return {'type': 'DESCRIBE', 'table': table}

    def _parse_where(self):
        """Parse WHERE clause into a condition tree."""
        left = self._parse_condition()
        while self.cur()[1].upper() in ('AND', 'OR'):
            op = self.advance()[1].upper()
            right = self._parse_condition()
            left  = {'op': op, 'left': left, 'right': right}
        return left

    def _parse_condition(self):
        col = self.advance()[1]
        op  = self.advance()[1]
        val = self._parse_value()
        return {'col': col, 'op': op, 'val': val}

    def _parse_value(self):
        kind, val = self.advance()
        if kind == 'NUMBER':
            return float(val) if '.' in val else int(val)
        if kind == 'STRING':
            return val
        if val.upper() == 'NULL':  return None
        if val.upper() == 'TRUE':  return True
        if val.upper() == 'FALSE': return False
        return val  # identifier or keyword

    def _parse_expr_token(self):
        """Parse a column expression (may include alias)."""
        _, val = self.advance()
        # Check for alias: col AS alias
        if self.cur()[1].upper() == 'AS':
            self.advance()
            alias = self.advance()[1]
            return {'col': val, 'alias': alias}
        return val


class SQLExecutor:
    """
    Executes parsed SQL AST against a JovasDB instance.
    Handles SELECT, INSERT, UPDATE, DELETE, DDL, transactions.
    """

    # Map SQL types → JovasDB types
    TYPE_MAP = {
        'INTEGER': 'INTEGER', 'INT': 'INTEGER', 'BIGINT': 'INTEGER', 'SMALLINT': 'INTEGER',
        'TEXT': 'TEXT', 'VARCHAR': 'TEXT', 'CHAR': 'TEXT', 'STRING': 'TEXT',
        'REAL': 'FLOAT', 'FLOAT': 'FLOAT', 'DOUBLE': 'FLOAT', 'NUMERIC': 'FLOAT', 'DECIMAL': 'FLOAT',
        'BOOLEAN': 'BOOLEAN', 'BOOL': 'BOOLEAN',
        'TIMESTAMP': 'TIMESTAMP', 'DATETIME': 'TIMESTAMP', 'DATE': 'TIMESTAMP',
        'JSON': 'JSON', 'JSONB': 'JSON',
        'BLOB': 'BLOB',
    }

    def __init__(self, db):
        self.db = db
        self._tx = None  # active transaction

    def execute(self, sql):
        """Execute a SQL string and return results."""
        sql = sql.strip()
        if not sql or sql.startswith('--'):
            return {'type': 'EMPTY', 'rows': [], 'count': 0}
        try:
            ast = SQLParser(sql).parse()
        except Exception as e:
            raise SQLError(f"SQL parse error: {e}")
        return self._exec(ast)

    def _exec(self, ast):
        t = ast['type']
        if   t == 'SELECT':      return self._select(ast)
        elif t == 'INSERT':      return self._insert(ast)
        elif t == 'UPDATE':      return self._update(ast)
        elif t == 'DELETE':      return self._delete(ast)
        elif t == 'CREATE_TABLE':return self._create_table(ast)
        elif t == 'DROP_TABLE':  return self._drop_table(ast)
        elif t == 'ALTER_ADD':   return self._alter_add(ast)
        elif t == 'ALTER_DROP':  return self._alter_drop(ast)
        elif t == 'ALTER_RENAME':return self._alter_rename(ast)
        elif t == 'SHOW_TABLES': return self._show_tables()
        elif t == 'DESCRIBE':    return self._describe(ast)
        elif t == 'BEGIN':       return self._begin()
        elif t == 'COMMIT':      return self._commit()
        elif t == 'ROLLBACK':    return self._rollback()
        else:
            raise SQLError(f"Unsupported statement type: {t}")

    # ── SELECT ───────────────────────────────
    def _select(self, ast):
        table = ast['table']
        if not table:
            raise SQLError("SELECT requires a FROM clause")
        if table not in self.db.tables:
            raise SQLError(f"Table '{table}' does not exist")

        where  = self._build_where(ast['where']) if ast['where'] else None
        order  = ast['order']
        limit  = ast['limit']
        offset = ast['offset']

        rows = self.db.select(table, where=where, order_by=order, limit=limit, offset=offset)

        # Handle JOINs
        for join in ast.get('joins', []):
            rows = self._apply_join(rows, join, table)

        # Column projection
        cols = ast['cols']
        if cols != ['*']:
            projected = []
            for row in rows:
                p = {}
                for c in cols:
                    if isinstance(c, dict):  # aliased
                        p[c.get('alias', c['col'])] = row.get(c['col'])
                    else:
                        p[c] = row.get(c)
                projected.append(p)
            rows = projected

        return {'type': 'SELECT', 'rows': rows, 'count': len(rows), 'table': table}

    def _apply_join(self, left_rows, join, left_table):
        jtable = join['table']
        if jtable not in self.db.tables:
            raise SQLError(f"JOIN table '{jtable}' does not exist")
        right_rows = self.db.select(jtable)
        # Parse join condition: left_table.col = right_table.col
        lpart  = join['left'].split('.')
        rpart  = join['right'].split('.')
        lcol   = lpart[-1]
        rcol   = rpart[-1]
        result = []
        for lr in left_rows:
            matched = False
            for rr in right_rows:
                if lr.get(lcol) == rr.get(rcol):
                    merged = {**{f"{left_table}.{k}": v for k, v in lr.items()},
                              **{f"{jtable}.{k}": v for k, v in rr.items()}}
                    result.append(merged)
                    matched = True
            if not matched and join['type'] == 'LEFT':
                merged = {**{f"{left_table}.{k}": v for k, v in lr.items()},
                          **{f"{jtable}.{k}": None for k in self.db.tables[jtable].schema.columns}}
                result.append(merged)
        return result

    # ── INSERT ───────────────────────────────
    def _insert(self, ast):
        table = ast['table']
        cols  = ast['cols']
        vals  = ast['vals']
        if table not in self.db.tables:
            raise SQLError(f"Table '{table}' does not exist")
        if cols and len(cols) != len(vals):
            raise SQLError(f"Column count ({len(cols)}) doesn't match value count ({len(vals)})")
        if cols:
            row = dict(zip(cols, vals))
        else:
            # Map by position — skip PK column
            schema_cols = [c.name for c in self.db.tables[table].schema.columns if not c.primary_key]
            row = dict(zip(schema_cols, vals))
        # Auto-assign PK if not provided
        pk_col = next((c for c in self.db.tables[table].schema.columns if c.primary_key), None)
        if pk_col and pk_col.name not in row:
            tbl = self.db.tables[table]
            existing_ids = [r.get(pk_col.name, 0) for r in tbl.rows.values() if isinstance(r.get(pk_col.name), int)]
            row[pk_col.name] = (max(existing_ids) + 1) if existing_ids else 1
        target = self._tx if self._tx else self.db
        inserted = target.insert(table, row)
        return {'type': 'INSERT', 'rows': [inserted], 'count': 1, 'table': table}

    # ── UPDATE ───────────────────────────────
    def _update(self, ast):
        table = ast['table']
        if table not in self.db.tables:
            raise SQLError(f"Table '{table}' does not exist")
        where   = self._build_where(ast['where']) if ast['where'] else None
        target  = self._tx if self._tx else self.db
        updated = target.update(table, where, ast['sets'])
        return {'type': 'UPDATE', 'rows': [], 'count': updated, 'table': table}

    # ── DELETE ───────────────────────────────
    def _delete(self, ast):
        table = ast['table']
        if table not in self.db.tables:
            raise SQLError(f"Table '{table}' does not exist")
        where   = self._build_where(ast['where']) if ast['where'] else None
        target  = self._tx if self._tx else self.db
        deleted = target.delete(table, where)
        return {'type': 'DELETE', 'rows': [], 'count': deleted, 'table': table}

    # ── CREATE TABLE ─────────────────────────
    def _create_table(self, ast):
        table = ast['table']
        if ast.get('if_not_exists') and table in self.db.tables:
            return {'type': 'CREATE_TABLE', 'rows': [], 'count': 0,
                    'message': f"Table '{table}' already exists (skipped)"}
        cols = []
        for cd in ast['cols']:
            jtype   = self.TYPE_MAP.get(cd['type'], 'TEXT')
            pk      = any(c == 'PRIMARY KEY' for c in cd['constraints'])
            unique  = any(c == 'UNIQUE'      for c in cd['constraints'])
            notnull = any(c == 'NOT NULL'    for c in cd['constraints'])
            default = next((c[1] for c in cd['constraints'] if isinstance(c, tuple) and c[0]=='DEFAULT'), None)
            refs    = next(((c[1],c[2]) for c in cd['constraints'] if isinstance(c,tuple) and c[0]=='REFERENCES'), None)
            col = Column(cd['name'], jtype, primary_key=pk, unique=unique,
                        nullable=not notnull, default=default)
            if refs:
                col.references = refs
            cols.append(col)
        schema = Schema(table, cols)
        self.db.create_table(schema)
        return {'type': 'CREATE_TABLE', 'rows': [], 'count': 0,
                'message': f"Table '{table}' created"}

    # ── DROP TABLE ───────────────────────────
    def _drop_table(self, ast):
        table = ast['table']
        if ast.get('if_exists') and table not in self.db.tables:
            return {'type': 'DROP_TABLE', 'rows': [], 'count': 0,
                    'message': f"Table '{table}' does not exist (skipped)"}
        self.db.drop_table(table, cascade=ast.get('cascade', False))
        return {'type': 'DROP_TABLE', 'rows': [], 'count': 0,
                'message': f"Table '{table}' dropped"}

    # ── ALTER TABLE ──────────────────────────
    def _alter_add(self, ast):
        jtype = self.TYPE_MAP.get(ast['col_type'], 'TEXT')
        col   = Column(ast['col'], jtype, default=ast.get('default'))
        self.db.add_column(ast['table'], col)
        return {'type': 'ALTER', 'rows': [], 'count': 0,
                'message': f"Column '{ast['col']}' added to '{ast['table']}'"}

    def _alter_drop(self, ast):
        self.db.drop_column(ast['table'], ast['col'])
        return {'type': 'ALTER', 'rows': [], 'count': 0,
                'message': f"Column '{ast['col']}' dropped from '{ast['table']}'"}

    def _alter_rename(self, ast):
        tbl = self.db.tables.get(ast['table'])
        if not tbl:
            raise SQLError(f"Table '{ast['table']}' does not exist")
        for col in tbl.schema.columns:
            if col.name == ast['old']:
                col.name = ast['new']
                for row in tbl.rows:
                    if ast['old'] in row:
                        row[ast['new']] = row.pop(ast['old'])
                self.db._persist()
                break
        return {'type': 'ALTER', 'rows': [], 'count': 0,
                'message': f"Column renamed '{ast['old']}' → '{ast['new']}'"}

    # ── SHOW TABLES ──────────────────────────
    def _show_tables(self):
        rows = [{'table_name': t, 'rows': len(self.db.tables[t].rows)}
                for t in self.db.tables]
        return {'type': 'SHOW_TABLES', 'rows': rows, 'count': len(rows)}

    # ── DESCRIBE ─────────────────────────────
    def _describe(self, ast):
        table = ast['table']
        if table not in self.db.tables:
            raise SQLError(f"Table '{table}' does not exist")
        rows = []
        for col in self.db.tables[table].schema.columns:
            rows.append({
                'column':   col.name,
                'type':     col.dtype,
                'pk':       '✓' if col.primary_key else '',
                'nullable': '✓' if col.nullable else '',
                'unique':   '✓' if col.unique else '',
                'default':  str(col.default) if col.default is not None else '',
            })
        return {'type': 'DESCRIBE', 'rows': rows, 'count': len(rows), 'table': table}

    # ── TRANSACTIONS ─────────────────────────
    def _begin(self):
        self._tx = self.db.begin()
        return {'type': 'BEGIN', 'rows': [], 'count': 0, 'message': 'Transaction started'}

    def _commit(self):
        if not self._tx:
            raise SQLError("No active transaction")
        self._tx.commit(); self._tx = None
        return {'type': 'COMMIT', 'rows': [], 'count': 0, 'message': 'Transaction committed'}

    def _rollback(self):
        if not self._tx:
            raise SQLError("No active transaction")
        self._tx.rollback(); self._tx = None
        return {'type': 'ROLLBACK', 'rows': [], 'count': 0, 'message': 'Transaction rolled back'}

    # ── WHERE condition evaluator ────────────
    def _build_where(self, cond):
        """Convert SQL WHERE AST to JovasDB where dict or evaluate complex conditions."""
        if not cond: return None
        # Simple single condition — convert to JovasDB where dict
        if 'col' in cond:
            col, op, val = cond['col'], cond['op'], cond['val']
            if op == '=':           return {col: val}
            if op in ('!=', '<>'): return {col: {'ne': val}}
            if op == '>':          return {col: {'gt': val}}
            if op == '>=':         return {col: {'gte': val}}
            if op == '<':          return {col: {'lt': val}}
            if op == '<=':         return {col: {'lte': val}}
            return {col: val}
        # AND/OR compound condition — return a filter function
        if cond.get('op') in ('AND', 'OR'):
            left  = self._build_where(cond['left'])
            right = self._build_where(cond['right'])
            if cond['op'] == 'AND':
                # Merge both dicts for AND
                if isinstance(left, dict) and isinstance(right, dict):
                    return {**left, **right}
            # For OR or complex cases, use a filter function approach
            # Store as special compound condition
            return {'__compound__': cond['op'], '__left__': left, '__right__': right}
        return None


# ── Pretty printer for SQL results ──────────

def _sql_print_result(result):
    """Print SQL query results in a formatted table."""
    RESET = "\033[0m"; GOLD = "\033[38;5;220m"; GREEN = "\033[38;5;82m"
    DIM   = "\033[38;5;244m"; BOLD = "\033[1m";  RED   = "\033[38;5;196m"

    t = result.get('type', '')

    if result.get('message'):
        print(f"  {GREEN}✅ {result['message']}{RESET}")
        return

    rows = result.get('rows', [])

    if not rows:
        print(f"  {DIM}(no rows){RESET}")
        return

    # Build column headers
    headers = list(rows[0].keys()) if rows else []
    if not headers: return

    # Calculate column widths
    widths = {h: max(len(str(h)), max((len(str(r.get(h,''))) for r in rows), default=0)) for h in headers}

    # Header
    header_line = '  ┌' + '┬'.join('─'*(widths[h]+2) for h in headers) + '┐'
    header_row  = '  │' + '│'.join(f' {GOLD}{BOLD}{h:<{widths[h]}}{RESET} ' for h in headers) + '│'
    divider     = '  ├' + '┼'.join('─'*(widths[h]+2) for h in headers) + '┤'
    footer      = '  └' + '┴'.join('─'*(widths[h]+2) for h in headers) + '┘'

    print(header_line)
    print(header_row)
    print(divider)

    for row in rows:
        row_str = '  │' + '│'.join(f' {str(row.get(h,"")):<{widths[h]}} ' for h in headers) + '│'
        print(row_str)

    print(footer)
    n = result.get('count', len(rows))
    print(f"  {DIM}({n} row{'s' if n!=1 else ''}){RESET}\n")


# ── Add sql() method directly to JovasDB ────

def _jovasdb_sql(self, query):
    """
    Execute a SQL query against this JovasDB instance.

    Usage:
        db = JovasDB("myapp")
        result = db.sql("SELECT * FROM users WHERE role = 'admin'")
        for row in result['rows']:
            print(row)

    Returns dict with keys:
        type   — statement type (SELECT, INSERT, etc.)
        rows   — list of row dicts
        count  — number of rows affected/returned
    """
    if not hasattr(self, '_sql_executor'):
        self._sql_executor = SQLExecutor(self)
    return self._sql_executor.execute(query)

# Patch sql() onto JovasDB
JovasDB.sql = _jovasdb_sql


# ── SQL Shell mode ───────────────────────────

def sql_shell(db):
    """Interactive SQL shell for JovasDB."""
    RESET = "\033[0m"; GOLD = "\033[38;5;220m"; GREEN = "\033[38;5;82m"
    DIM   = "\033[38;5;244m"; BOLD = "\033[1m";  RED   = "\033[38;5;196m"

    print(f"""
{GOLD}{BOLD}  ╔════════════════════════════════════════════╗
  ║   🗄  JovasDB SQL Shell v{JOVASDB_VERSION}           ║
  ║   Database: {db.db_name:<30}║
  ╚════════════════════════════════════════════╝{RESET}
  Type SQL queries ending with ; · 'exit' to quit
  Type 'help' for SQL examples
""")

    executor = SQLExecutor(db)
    buf = []

    while True:
        prompt = f"  {GOLD}sql{'*' if executor._tx else ''}>{RESET} "
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {GREEN}Goodbye! 👋{RESET}"); break

        if not line: continue
        if line.lower() == 'exit': print(f"  {GREEN}Goodbye! 👋{RESET}"); break
        if line.lower() == 'help':
            print(f"""
  {GOLD}SQL Examples:{RESET}
    CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT DEFAULT 'user');
    INSERT INTO users (name, role) VALUES ('Alice', 'admin');
    SELECT * FROM users;
    SELECT * FROM users WHERE role = 'admin';
    SELECT * FROM users ORDER BY name ASC LIMIT 10;
    UPDATE users SET role = 'moderator' WHERE name = 'Alice';
    DELETE FROM users WHERE id = 1;
    ALTER TABLE users ADD COLUMN email TEXT;
    ALTER TABLE users DROP COLUMN email;
    DROP TABLE users;
    SHOW TABLES;
    DESCRIBE users;
    BEGIN;
    COMMIT;
    ROLLBACK;
""")
            continue

        buf.append(line)
        full = ' '.join(buf)

        # Execute when semicolon detected or single-line command
        if full.rstrip().endswith(';') or line.upper() in ('SHOW TABLES', 'BEGIN', 'COMMIT', 'ROLLBACK'):
            sql = full.rstrip().rstrip(';')
            buf = []
            try:
                start  = time.time()
                result = executor.execute(sql)
                elapsed = (time.time() - start) * 1000
                _sql_print_result(result)
                t = result.get('type','')
                if t == 'SELECT':
                    print(f"  {DIM}Query OK — {result['count']} row(s) in {elapsed:.1f}ms{RESET}")
                elif t in ('INSERT','UPDATE','DELETE'):
                    print(f"  {GREEN}Query OK — {result['count']} row(s) affected in {elapsed:.1f}ms{RESET}")
                elif t in ('CREATE_TABLE','DROP_TABLE','ALTER'):
                    print(f"  {GREEN}Query OK in {elapsed:.1f}ms{RESET}")
            except SQLError as e:
                print(f"  {RED}[SQL Error] {e.message}{RESET}")
            except Exception as e:
                print(f"  {RED}[Error] {e}{RESET}")
        else:
            # Multi-line — show continuation prompt
            pass  # collect more lines


