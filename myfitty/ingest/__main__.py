import sys

from myfitty import db
from myfitty.config import ConfigError, load_config
from myfitty.ingest.importer import scan
from myfitty.rescore import seed_thresholds


def main(argv: list[str] | None = None) -> int:
    retry_failed = "--retry-failed" in (sys.argv[1:] if argv is None else argv)
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    with db.connect(cfg.db_path) as con:
        seed_thresholds(con, cfg.thresholds)
        result = scan(con, cfg, retry_failed=retry_failed)
    if result.folder_missing:
        print(f"FIT folder not found: {cfg.fit_dir}", file=sys.stderr)
        return 1
    print(result.summary())
    for name, reason in result.failures:
        print(f"  failed: {name}: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
