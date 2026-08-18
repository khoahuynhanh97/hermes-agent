from sqlmodel import SQLModel, create_engine
from typing import Generator

from ..runtime_layout import get_knowledge_base_db_path

# The single engine instance for the entire application
_engine = None


def get_engine():
    """
    Returns the singleton SQL engine instance, creating it if necessary.
    """
    global _engine
    if _engine is None:
        db_path = get_knowledge_base_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn_str = f"sqlite:///{db_path}"
        _engine = create_engine(conn_str, echo=False)
    return _engine


def get_session() -> Generator[SQLModel, None, None]:
    """
    Provides a transactional scope around a series of operations.
    """
    with SQLModel.begin(get_engine()) as session:
        yield session


def create_db_and_tables():
    """
    Creates the database and all necessary tables if they don't exist.
    """
    engine = get_engine()
    from . import models  # noqa
    SQLModel.metadata.create_all(engine)
