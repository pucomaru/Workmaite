package com.workmaite.global.sync;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * PostgreSQL CUD 이후 Neo4j 동기화 — 아웃박스 패턴 (P2-4).
 *
 * <p>호출자의 트랜잭션 안에서 neo4j_sync_outbox 행을 기록한다(원자성 — 비즈니스 변경과 동기화 의도가 함께 커밋/롤백). 실제 FastAPI 호출은 커밋 후
 * SyncOutboxDispatcher가 수행하고, 실패 시 행이 남아 폴러가 재시도한다 (DATA-1 fire-and-forget 유실 해결).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class NeoSyncService {

  private final SyncOutboxRepository outboxRepository;
  private final SyncOutboxDispatcher dispatcher;

  public void syncMeeting(Integer meetingId) {
    enqueue("meeting", meetingId, "upsert", null);
  }

  public void syncSession(Integer sessionId) {
    enqueue("session", sessionId, "upsert", null);
  }

  public void syncAgenda(Integer agendaId) {
    enqueue("agenda", agendaId, "upsert", null);
  }

  public void syncUser(Integer userId) {
    enqueue("user", userId, "upsert", null);
  }

  public void syncMember(Integer meetingId, Integer userId, String role) {
    enqueue(
        "member", meetingId, "upsert", "{\"user_id\": " + userId + ", \"role\": \"" + role + "\"}");
  }

  public void deleteMeeting(Integer meetingId) {
    enqueue("meeting", meetingId, "delete", null);
  }

  /** 세션 삭제 전파 (DATA-4) */
  public void deleteSession(Integer sessionId) {
    enqueue("session", sessionId, "delete", null);
  }

  /** 아젠다 삭제 전파 (DATA-4) */
  public void deleteAgenda(Integer agendaId) {
    enqueue("agenda", agendaId, "delete", null);
  }

  public void deleteMember(Integer meetingId, Integer userId) {
    enqueue("member", meetingId, "delete", "{\"user_id\": " + userId + "}");
  }

  private void enqueue(String entityType, Integer entityId, String op, String payloadJson) {
    // 호출자 트랜잭션에 참여해 비즈니스 변경과 함께 커밋된다 (롤백 시 동기화도 취소)
    outboxRepository.save(
        SyncOutbox.builder()
            .entityType(entityType)
            .entityId(entityId)
            .op(op)
            .payload(payloadJson)
            .build());

    // 커밋 후 즉시 디스패치 (지연 최소화) — 실패해도 폴러가 재시도
    if (TransactionSynchronizationManager.isSynchronizationActive()) {
      TransactionSynchronizationManager.registerSynchronization(
          new TransactionSynchronization() {
            @Override
            public void afterCommit() {
              dispatcher.kick();
            }
          });
    } else {
      dispatcher.kick();
    }
  }
}
