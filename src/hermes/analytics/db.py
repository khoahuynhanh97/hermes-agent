from sqlmodel import SQLModel, create_engine
from typing import Generator

from ..runtime_layout import get_analytics_db_path

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        db_path = get_analytics_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn_str = f"sqlite:///{db_path}"
        _engine = create_engine(conn_str, echo=False)
    return _engine


def get_session() -> Generator[SQLModel, None, None]:
    with SQLModel.begin(get_engine()) as session:
        yield session


def create_db_and_tables():
    engine = get_engine()
    from . import models  # noqa
    SQLModel.metadata.create_all(engine)
