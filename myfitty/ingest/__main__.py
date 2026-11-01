import sys

from myfitty import db
from myfitty.config import load_config
from myfitty.ingest.importer import scan


def main() -> int:
    cfg = load_config()
    with db.connect(cfg.db_path) as con:
        result = scan(con, cfg)
    if result.folder_missing:
        print(f"FIT folder not found: {cfg.fit_dir}", file=sys.stderr)
        return 1
    print(result.summary())
    for name, reason in result.failures:
        print(f"  failed: {name}: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
