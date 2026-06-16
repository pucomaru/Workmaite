"""에이전트 데이터 변경(쓰기) '제안' 도구 — 구조화-구성형, CRUD only, 스키마(DDL) 변경 절대 불가.

설계(보안 철저):
- AI는 operation/entity/fields를 **추론해 구성**하고, 서버는 그 구조화된 의도를 **화이트리스트·권한**으로
  검증한다(원시 SQL/Cypher 생성·실행 없음 → 인젝션·대량삭제·DDL 불가능).
- 에이전트는 직접 실행하지 않는다. 권한 통과 시 '제안(spec)'만 반환한다. spec엔 실제로 호출할
  **기존 CRUD 엔드포인트(exec)** 가 담겨, 사용자 확인 후 프런트가 그 엔드포인트를 호출한다
  → 기존 권한 재검증·감사(AuditLogMiddleware)·PG/Neo4j 동기화를 그대로 재사용(중복·새 executor 없음).
- 권한·허용범위 밖이면 사람이 이해할 **거부 사유**를 반환해 왜 불가능한지 사용자에게 알린다.
"""

import json
import logging
from typing import cast

from fastapi import HTTPException
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from core import access_guard as guard
from db import models
from db.database import SessionLocal

logger = logging.getLogger(__name__)

# 스트림 루프가 감지해 프런트 확인 카드 이벤트로 변환하는 표식
ACTION_CONFIRM_SENTINEL = "__ACTION_CONFIRM__"

# ── 화이트리스트: 변경 가능한 엔티티·필드·권한·허용 operation만 정의 (AI는 이 범위 안에서만 구성) ──
# guard: owned=require_owned_edit(소유자 본인 또는 회의체 편집권), owned_session=세션경유 소유물,
#        meeting_self=회의체 자체 편집권
_ENTITIES: dict[str, dict] = {
    "agenda": {
        "model": models.Agenda,
        "guard": "owned",
        "owner_attr": "assignee_id",
        "label_attr": "title",
        "updatable": {"title", "status", "priority", "due_date", "department"},
        "ops": {"update", "delete"},
    },
    "minutes": {
        "model": models.Minutes,
        "guard": "owned_session",
        "owner_attr": "recorder_id",
        "label_attr": "file_name",
        "updatable": {"file_name", "status"},
        "ops": {"update", "delete"},
    },
    "report": {
        "model": models.Report,
        "guard": "owned",
        "owner_attr": "upload_id",
        "label_attr": "file_name",
        "updatable": {"file_name", "human_status"},
        "ops": {"update", "delete"},
    },
    "meeting": {
        "model": models.Meeting,
        "guard": "meeting_self",
        "owner_attr": None,
        "label_attr": "title",
        "updatable": set(),  # 회의체 수정은 설정 화면에서 — 에이전트는 삭제만
        "ops": {"delete"},
    },
}


def _load_user(db, config: RunnableConfig):
    uid = (config or {}).get("configurable", {}).get("user_id")
    return db.query(models.User).filter(models.User.id == uid).first() if uid else None


def _enforce_permission(db, user, entity_key: str, row) -> None:
    """엔티티별 권한 가드를 적용한다(실패 시 HTTPException). 서버가 강제 — LLM이 못 우회."""
    meta = _ENTITIES[entity_key]
    g = meta["guard"]
    if g == "owned":
        guard.require_owned_edit(
            db, user, row.meeting_id, getattr(row, meta["owner_attr"], None)
        )
    elif g == "owned_session":
        mid = guard.meeting_id_of_session(db, row.session_id)
        guard.require_owned_edit(db, user, mid, getattr(row, meta["owner_attr"], None))
    elif g == "meeting_self":
        guard.require_meeting_edit(db, user, row.id)


def _resolve_exec(operation: str, entity: str, row, fields: dict | None) -> dict:
    """확인 후 프런트가 호출할 기존 CRUD 엔드포인트를 해석한다(method/url/body)."""
    if entity == "agenda":
        if operation == "delete":
            return {"method": "delete", "url": f"/api/agent/archive/agendas/{row.id}"}
        return {
            "method": "patch",
            "url": f"/api/agent/archive/agendas/{row.id}",
            "body": fields,
        }
    if entity == "minutes":
        if operation == "delete":
            # 회의록 삭제는 세션 단위 엔드포인트
            return {
                "method": "delete",
                "url": f"/api/ai/sessions/{row.session_id}/minutes",
            }
        return {
            "method": "patch",
            "url": f"/api/agent/archive/minutes/{row.id}",
            "body": fields,
        }
    if entity == "report":
        if operation == "delete":
            return {"method": "delete", "url": f"/api/upload/reports/{row.id}"}
        return {
            "method": "patch",
            "url": f"/api/agent/archive/reports/{row.id}",
            "body": fields,
        }
    if entity == "meeting":
        return {"method": "delete", "url": f"/api/ai/meetings/{row.id}"}
    raise ValueError(entity)


def _propose_create(db, user, entity: str, fields: dict) -> str:
    """생성(create) 제안. 현재 agenda 생성만 지원(기존 commit 엔드포인트 재사용)."""
    if entity != "agenda":
        return f"[작업 불가] '{entity}' 생성은 채팅에서 지원하지 않습니다. (생성 가능: agenda)"
    title = (fields.get("title") or "").strip()
    mid = fields.get("meeting_id")
    if not title or not mid:
        return "[작업 불가] 아젠다 생성에는 meeting_id와 title이 필요합니다. list_my_meetings로 회의체를 먼저 확인하세요."
    try:
        guard.require_meeting_edit(db, user, int(mid))
    except HTTPException as e:
        return f"[작업 불가] {e.detail} 사용자에게 이 사유를 그대로 알려주세요."
    mg = db.query(models.Meeting).filter(models.Meeting.id == int(mid)).first()
    summary = f"'{mg.title if mg else mid}' 회의체에 아젠다 '{title}' 추가"
    approved: dict = {"title": title}
    if fields.get("dept"):
        approved["dept"] = fields["dept"]
    if fields.get("due_date"):
        approved["due_date"] = fields["due_date"]
    spec = {
        "operation": "create",
        "entity": "agenda",
        "summary": summary,
        "danger": False,
        "exec": {
            "method": "post",
            "url": "/api/agent/archive/agendas/commit",
            "body": {"meeting_id": int(mid), "approved": [approved]},
        },
    }
    return (
        ACTION_CONFIRM_SENTINEL
        + json.dumps(spec, ensure_ascii=False)
        + f"\n('{summary}'을(를) 진행할지 사용자에게 한 문장으로 확인을 요청하세요. 위 표식·JSON 원문은 출력하지 마세요.)"
    )


@tool
def propose_data_change(
    operation: str,
    entity: str,
    target_id: int = 0,
    fields: dict | None = None,
    config: RunnableConfig = None,
) -> str:
    """데이터 변경을 '제안'한다(실제 실행 아님 — 사용자가 확인하면 그때 실행). 권한·허용범위는 서버가 강제.

    수정/삭제는 먼저 read 도구(list_agendas 등)로 정확한 대상 id를 확인한 뒤 호출하세요.
    권한이 없으면 거부 사유가 반환되며, 그 사유를 사용자에게 그대로 안내하세요. 아래 허용 범위만 가능합니다.

    Args:
        operation: "create"(생성) | "update"(수정) | "delete"(삭제)
        entity: 대상 종류. 허용·가능 작업:
            - agenda  : create, update, delete
            - minutes : update, delete
            - report  : update, delete
            - meeting : delete (회의체 전체 삭제 — 수정은 설정 화면에서)
        target_id: update/delete 시 대상 ID (create엔 불필요)
        fields:
            - operation="create", entity="agenda": {"meeting_id": 회의체ID, "title": 제목, "dept"?: 부서, "due_date"?: "YYYY-MM-DD"}
            - operation="update"의 변경 값(dict). 엔티티별 허용 필드:
                · agenda  : title, status, priority, due_date(YYYY-MM-DD), department
                · minutes : file_name, status
                · report  : file_name, human_status
            (예: 아젠다 완료 처리 = operation="update", entity="agenda", target_id=42, fields={"status":"done"})
    """
    db = SessionLocal()
    try:
        user = _load_user(db, cast(RunnableConfig, config))
        if user is None:
            return "[작업 불가] 로그인 정보를 확인할 수 없습니다."

        if operation == "create":
            return _propose_create(db, user, entity, fields or {})

        meta = _ENTITIES.get(entity)
        if not meta:
            return (
                f"[작업 불가] '{entity}'는 변경 대상이 아닙니다. "
                f"가능한 대상: {', '.join(_ENTITIES.keys())}."
            )
        if operation not in meta["ops"]:
            return (
                f"[작업 불가] {entity}에는 '{operation}'를 할 수 없습니다. "
                f"가능: {', '.join(sorted(meta['ops']))}."
            )

        row = db.query(meta["model"]).filter(meta["model"].id == int(target_id)).first()
        if not row:
            return f"[작업 불가] 해당 {entity}(id={target_id})를 찾을 수 없습니다."

        # ── 권한 강제 (서버) ──
        try:
            _enforce_permission(db, user, entity, row)
        except HTTPException as e:
            return f"[작업 불가] {e.detail} 사용자에게 이 사유를 그대로 알려주세요."

        label = getattr(row, meta["label_attr"], None) if meta["label_attr"] else entity
        label = label or entity

        if operation == "update":
            fields = fields or {}
            if not isinstance(fields, dict) or not fields:
                return "[작업 불가] update에는 변경할 fields가 필요합니다."
            bad = [k for k in fields if k not in meta["updatable"]]
            if bad:
                return (
                    f"[작업 불가] {entity}에서 바꿀 수 없는 필드: {', '.join(bad)}. "
                    f"허용 필드: {', '.join(sorted(meta['updatable']))}."
                )
            summary = f"{entity} '{label}'의 {', '.join(fields.keys())} 변경"
            danger = False
        else:  # delete
            summary = f"{entity} '{label}' 삭제"
            danger = True

        spec = {
            "operation": operation,
            "entity": entity,
            "target_id": int(target_id),
            "summary": summary,
            "danger": danger,
            "exec": _resolve_exec(operation, entity, row, fields),
        }
        return (
            ACTION_CONFIRM_SENTINEL
            + json.dumps(spec, ensure_ascii=False)
            + f"\n('{summary}'을(를) 진행할지 사용자에게 한 문장으로 확인을 요청하세요. 위 표식·JSON 원문은 출력하지 마세요.)"
        )
    finally:
        db.close()


ACTION_TOOLS: list = [propose_data_change]
