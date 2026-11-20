from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings

class Base(DeclarativeBase):
    pass

def make_engine():
    url = settings().database_url
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def init_db():
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Idempotent migration for pre-existing deployments without Alembic.
    # Keep the column nullable because older synthetic/Zoom recordings have no name.
    if "participant_name" not in {c["name"] for c in inspect(engine).get_columns("recordings")}:
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE recordings ADD COLUMN participant_name VARCHAR(80)'))

def db_session():
    with SessionLocal() as session:
        yield session
