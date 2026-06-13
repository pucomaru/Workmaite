package com.workmaite.global.sync;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

/**
 * 아웃박스 디스패처 (P2-4). - kick(): 커밋 직후 즉시 비동기 디스패치 (낮은 지연) - poll(): 30초 주기로 잔여 pending 행 재처리 (실패 재시도
 * — DATA-1 유실 방지) 단일 replica 전제(현 구성). 멀티 replica 확장 시 SKIP LOCKED 클레임으로 전환할 것.
 */
@Slf4j
@Component
public class SyncOutboxDispatcher {

  private final SyncOutboxRepository outboxRepository;
  private final RestTemplate restTemplate;
  private final TaskExecutor taskExecutor;
  private final ObjectMapper objectMapper = new ObjectMapper();
  private final String aiUrl;
  private final String internalSecret;
  private final AtomicBoolean running = new AtomicBoolean(false);

  public SyncOutboxDispatcher(
      SyncOutboxRepository outboxRepository,
      RestTemplate restTemplate,
      @Qualifier("applicationTaskExecutor") TaskExecutor taskExecutor,
      @Value("${ai.url:http://localhost:8000}") String aiUrl,
      @Value("${internal.secret:workmaite-internal-secret-2024}") String internalSecret) {
    this.outboxRepository = outboxRepository;
    this.restTemplate = restTemplate;
    this.taskExecutor = taskExecutor;
    this.aiUrl = aiUrl;
    this.internalSecret = internalSecret;
  }

  /** 커밋 직후 호출 — 비동기로 한 사이클 디스패치 */
  public void kick() {
    taskExecutor.execute(this::dispatchPending);
  }

  /** 잔여/실패 행 주기 재처리 */
  @Scheduled(fixedDelayString = "${sync.outbox.poll-ms:30000}")
  public void poll() {
    dispatchPending();
  }

  private void dispatchPending() {
    if (!running.compareAndSet(false, true)) {
      return; // 동시 실행 방지
    }
    try {
      List<SyncOutbox> batch =
          outboxRepository.findTop50ByStatusOrderByIdAsc(SyncOutbox.STATUS_PENDING);
      for (SyncOutbox row : batch) {
        try {
          send(row);
          row.markDone();
        } catch (org.springframework.web.client.HttpClientErrorException.NotFound e) {
          // 동기화 전에 원본 엔티티가 삭제됨 — 재시도 무의미, 종료 처리
          row.markDone();
          log.info(
              "[SyncOutbox] {} {}:{} 원본 없음(404) — skip",
              row.getOp(),
              row.getEntityType(),
              row.getEntityId());
        } catch (Exception e) {
          row.markAttemptFailed(e.getMessage());
          log.warn(
              "[SyncOutbox] {} {}:{} 실패 (retry={}) — {}",
              row.getOp(),
              row.getEntityType(),
              row.getEntityId(),
              row.getRetryCount(),
              e.getMessage());
        }
        outboxRepository.save(row);
      }
    } finally {
      running.set(false);
    }
  }

  private void send(SyncOutbox row) throws Exception {
    boolean delete = "delete".equals(row.getOp());
    String url =
        switch (row.getEntityType()) {
          case "meeting" ->
              delete
                  ? "/api/sync/meeting/" + row.getEntityId() + "/delete"
                  : "/api/sync/meeting/" + row.getEntityId();
          case "session" -> "/api/sync/session/" + row.getEntityId();
          case "agenda" -> "/api/sync/agenda/" + row.getEntityId();
          case "user" -> "/api/sync/user/" + row.getEntityId();
          case "member" -> {
            JsonNode p = objectMapper.readTree(row.getPayload() == null ? "{}" : row.getPayload());
            long userId = p.path("user_id").asLong();
            if (delete) {
              yield "/api/sync/member/delete?meetingId=" + row.getEntityId() + "&userId=" + userId;
            }
            yield "/api/sync/member?meetingId="
                + row.getEntityId()
                + "&userId="
                + userId
                + "&role="
                + p.path("role").asText("member");
          }
          default ->
              throw new IllegalArgumentException("unknown entity_type: " + row.getEntityType());
        };

    HttpHeaders headers = new HttpHeaders();
    headers.set("X-Internal-Secret", internalSecret);
    restTemplate.exchange(
        aiUrl + url,
        delete ? HttpMethod.DELETE : HttpMethod.POST,
        new HttpEntity<>(headers),
        Void.class);
  }
}
