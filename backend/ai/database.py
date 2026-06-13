import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# PostgreSQL (k8s: postgres-1-postgresql.postgres.svc.cluster.local:5432)
# 로컬 개발 시: kubectl port-forward svc/postgres-1-postgresql 5432:5432 -n postgres
_DB_HOST = os.environ["DB_HOST"]
_DB_PORT = os.environ["DB_PORT"]
_DB_NAME = os.environ["DB_NAME"]
_DB_USER = os.environ["DB_USER"]
_DB_PASS = os.environ["DB_PASSWORD"]

SQLALCHEMY_DATABASE_URL = (
    f"postgresql+psycopg2://{_DB_USER}:{_DB_PASS}@{_DB_HOST}:{_DB_PORT}/{_DB_NAME}"
)

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
