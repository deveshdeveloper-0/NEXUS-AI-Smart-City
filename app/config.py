from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_environment(path: Path = ENV_FILE) -> None:
    load_dotenv(dotenv_path=path, override=False)


load_environment()
