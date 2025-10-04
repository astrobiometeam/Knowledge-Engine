
import os
import sqlite3
from contextlib import closing
from typing import Optional, List, Tuple

DB_FILENAME = "space_biology.db"

def get_db_path() -> str:
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), DB_FILENAME)

SCHEMA = {
    "papers": {
        "columns": [
            ("id", "INTEGER PRIMARY KEY"),
            ("title", "TEXT NOT NULL"),
            ("abstract", "TEXT"),
            ("authors", "TEXT"),
            ("source", "TEXT"),
            ("url", "TEXT"),
            ("keywords", "TEXT"),
            ("publication_date", "TEXT"),
            ("doi", "TEXT"),
            ("pubmed_id", "TEXT"),
            ("nasa_id", "TEXT"),
            ("created_at", "TEXT"),
            ("sentiment", "TEXT"),
            ("objective", "TEXT")
        ],
        "indexes": [
            ("idx_papers_pubmed_id", "pubmed_id"),
            ("idx_papers_nasa_id", "nasa_id"),
            ("idx_papers_doi", "doi")
        ]
    },
    "knowledge_nodes": {
        "columns": [
            ("id", "INTEGER PRIMARY KEY"),
            ("name", "TEXT NOT NULL"),
            ("node_type", "TEXT"),
            ("description", "TEXT"),
            ("confidence", "REAL"),
            ("category", "TEXT"),
            ("node_metadata", "TEXT"),
            ("paper_id", "INTEGER"),
            ("created_at", "TEXT")
        ],
        "indexes": [
            ("idx_knodes_paper_id", "paper_id")
        ]
    },
    "search_history": {
        "columns": [
            ("id", "INTEGER PRIMARY KEY"),
            ("query", "TEXT NOT NULL"),
            ("results_count", "INTEGER DEFAULT 0"),
            ("search_time", "TEXT"),
            ("user_ip", "TEXT"),
            ("filters_used", "TEXT"),
            ("sources_searched", "TEXT")
        ],
        "indexes": [
            ("idx_search_history_time", "search_time")
        ]
    }
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
    return cur.fetchone() is not None

def _existing_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table});")
    rows = cur.fetchall()
    return [r[1] for r in rows]


def _create_table(conn: sqlite3.Connection, table: str, cols: List[Tuple[str,str]]):
    cols_sql = ",\n  ".join(f"{name} {ctype}" for name, ctype in cols)
    sql = f"CREATE TABLE IF NOT EXISTS {table} (\n  {cols_sql}\n);"
    conn.execute(sql)
    conn.commit()

def _add_column(conn: sqlite3.Connection, table: str, col: str, ctype: str):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ctype};")
        conn.commit()

    except sqlite3.OperationalError as e:
        print(f" Error adding column {col} to {table} : {e} ")


def _ensure_indexes(conn: sqlite3.Connection, table: str, indexes: List[Tuple[str,str]]):
    for idx_name, col in indexes:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({col});")
            conn.commit()
        except Exception as e:
            print(f"Error creating index {idx_name}: {e}")


def ensure_papers_columns(db_path: Optional[str] = None):

    db_path = db_path or get_db_path()

    
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            print(f"Error creating database path: {e}")


    try:
        with sqlite3.connect(db_path) as conn:

            conn.execute("PRAGMA foreign_keys = ON;")

            for table, meta in SCHEMA.items():
                cols = meta["columns"]
                idxs = meta.get("indexes", [])

                if not _table_exists(conn, table):

                    _create_table(conn, table, cols)
                else:
                    print(f"Table '{table}' already exists — checking columns...")


                existing = _existing_columns(conn, table)
                for col_name, col_type in cols:
                    if col_name not in existing:

                        _add_column(conn, table, col_name, col_type)
                    else:
                        print(f"Column '{col_name}' exists in '{table}'")

                if idxs:
                    _ensure_indexes(conn, table, idxs)

    except sqlite3.DatabaseError as e:
        print(f"Database error : {e}")


if __name__ == "__main__":
    print("Starting database check...")
    ensure_papers_columns()
    print("End of database health check")
