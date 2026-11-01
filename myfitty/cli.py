"""`myfitty app [streamlit options]` starts the UI; `myfitty ingest` imports the FIT folder."""
import sys
from pathlib import Path

USAGE = "usage: myfitty {app|ingest|rescore} [options]\n  app     start the web UI (extra options go to `streamlit run`)\n  ingest  import FIT files from MYFITTY_FIT_DIR\n  rescore recompute every activity's scores (after changing scoring rules)"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0 if argv else 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "app":
        from streamlit.web import cli as st_cli
        sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py")), *rest]
        return st_cli.main() or 0
    if cmd == "ingest":
        from myfitty.ingest.__main__ import main as ingest_main
        return ingest_main()
    if cmd == "rescore":
        from myfitty import db
        from myfitty.config import ConfigError, load_config
        from myfitty.rescore import rescore
        try:
            cfg = load_config()
        except ConfigError as e:
            print(f"config error: {e}", file=sys.stderr)
            return 2
        with db.connect(cfg.db_path) as con:
            print(f"rescored {rescore(con)} activities")
        return 0
    print(f"unknown command {cmd!r}\n{USAGE}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
