from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from companion.settings import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    if url.startswith("sqlite:///"):
        sqlite_path = Path(url.removeprefix("sqlite:///"))
        if sqlite_path.parent != Path("."):
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url == "sqlite:///:memory:":
        return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(url, connect_args=connect_args)


def make_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(database_url), expire_on_commit=False)


SessionLocal = make_session_factory()


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
