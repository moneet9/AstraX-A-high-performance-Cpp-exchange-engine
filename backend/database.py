import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg:///astrax")
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope():
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
