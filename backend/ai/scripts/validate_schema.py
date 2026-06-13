"""FastAPI(SQLAlchemy) 모델이 실제 DB 스키마와 일치하는지 검증한다.

스키마의 단일 소스는 Spring Flyway(V1 baseline). CI에서 빈 postgres에 Flyway V1을 적용한 뒤
이 스크립트로 모델 ↔ 스키마를 대조한다. **read-only reflect** 로 스키마/데이터를 변경하지 않는다.

검출: 모델에 있으나 DB에 없는 테이블/컬럼, 타입(int/bigint/smallint, str, float, ts, bool, json) 불일치.
불일치가 있으면 비정상 종료(exit 1)하여 CI를 실패시킨다.

실행: DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD 환경변수 설정 후
      python scripts/validate_schema.py
"""
import sys

from sqlalchemy import inspect

import models  # noqa: F401  — Base.metadata 에 전 테이블을 등록하기 위한 import
from database import Base, engine


def category(sa_type) -> str:
    """SQLAlchemy 타입(모델 정의 / DB reflect)을 비교용 카테고리로 정규화."""
    n = type(sa_type).__name__.upper()
    if n in ("BIGINTEGER", "BIGINT"):
        return "int8"
    if n in ("SMALLINTEGER", "SMALLINT"):
        return "int2"
    if n in ("INTEGER", "INT"):
        return "int4"
    if n in ("STRING", "VARCHAR", "TEXT", "CHAR", "NVARCHAR", "NAME", "CITEXT"):
        return "str"
    if n in ("FLOAT", "DOUBLE_PRECISION", "DOUBLEPRECISION", "REAL", "NUMERIC", "DECIMAL"):
        return "float"
    if n in ("DATETIME", "TIMESTAMP"):
        return "ts"
    if n in ("DATE",):
        return "date"
    if n in ("BOOLEAN", "BOOL"):
        return "bool"
    if n in ("JSON", "JSONB"):
        return "json"
    return n.lower()


def main() -> None:
    insp = inspect(engine)
    db_tables = set(insp.get_table_names())
    errors: list[str] = []

    for tname, table in sorted(Base.metadata.tables.items()):
        if tname not in db_tables:
            errors.append(f"[{tname}] 테이블이 DB에 없음")
            continue
        db_cols = {c["name"]: c["type"] for c in insp.get_columns(tname)}
        for col in table.columns:
            if col.name not in db_cols:
                errors.append(f"[{tname}.{col.name}] 모델에 있으나 DB에 없음")
                continue
            m_cat, d_cat = category(col.type), category(db_cols[col.name])
            if m_cat != d_cat:
                errors.append(
                    f"[{tname}.{col.name}] 타입 불일치: "
                    f"모델={col.type}({m_cat}) vs DB={db_cols[col.name]}({d_cat})"
                )

    if errors:
        print("❌ 스키마 불일치:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
    print(f"✅ OK — {len(Base.metadata.tables)}개 테이블, 모델 ↔ DB 스키마 일치")


if __name__ == "__main__":
    main()
