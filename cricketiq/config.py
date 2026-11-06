"""Project paths shared by the command-line importer and the UI."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "processed" / "cricketiq.duckdb"
