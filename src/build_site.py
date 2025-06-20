"""Render static HTML pages from lots using Jinja2."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from log_utils import get_logger, install_excepthook

log = get_logger().bind(script=__file__)
install_excepthook(log)

LOTS_DIR = Path("data/lots")
VIEWS_DIR = Path("data/views")
TEMPLATES = Path("templates")


def build_page(env: Environment, lot_path: Path) -> None:
    lot = lot_path.read_text()
    template = env.get_template("lot.html")
    out = VIEWS_DIR / (lot_path.stem + ".html")
    out.write_text(template.render(lot=lot))
    log.debug("Wrote", path=str(out))


def main() -> None:
    log.info("Building site")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    VIEWS_DIR.mkdir(parents=True, exist_ok=True)
    for p in LOTS_DIR.glob("*.json"):
        build_page(env, p)
    log.info("Site build complete")


if __name__ == "__main__":
    main()
