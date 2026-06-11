package com.workmaite.global.sync;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.task.TaskExecutor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.client.RestTemplate;

/**
 * PostgreSQL CUD 이후 FastAPI를 통해 Neo4j를 동기화.
 *
 * 호출 시점에 트랜잭션이 진행 중이면 afterCommit에 등록해 "커밋된 데이터"만
 * FastAPI가 읽도록 보장한다 (커밋 전 발사 시 AI 서버가 옛 데이터를 읽는 race 방지).
 * 실제 HTTP 호출은 TaskExecutor에서 비동기 실행 — 실패해도 요청 흐름에 영향 없음.
 * (실패 재시도는 outbox 패턴 도입 시 처리 — Plan.md P2-4)
 */
@Slf4j
@Service
public class NeoSyncService {

    private final RestTemplate restTemplate;
    private final TaskExecutor taskExecutor;
    private final String aiUrl;
    private final String internalSecret;

    public NeoSyncService(RestTemplate restTemplate,
                          TaskExecutor taskExecutor,
                          @Value("${ai.url:http://localhost:8000}") String aiUrl,
                          @Value("${internal.secret:workmaite-internal-secret-2024}") String internalSecret) {
        this.restTemplate = restTemplate;
        this.taskExecutor = taskExecutor;
        this.aiUrl = aiUrl;
        this.internalSecret = internalSecret;
    }

    private HttpEntity<Void> internalEntity() {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Secret", internalSecret);
        return new HttpEntity<>(headers);
    }

    /** 트랜잭션 진행 중이면 커밋 후, 아니면 즉시 — 어느 쪽이든 비동기로 실행 */
    private void afterCommitAsync(Runnable task) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    taskExecutor.execute(task);
                }
            });
        } else {
            taskExecutor.execute(task);
        }
    }

    public void syncMeeting(Long meetingId) {
        afterCommitAsync(() -> call("/api/sync/meeting/" + meetingId, "meeting:" + meetingId));
    }

    public void syncSession(Long sessionId) {
        afterCommitAsync(() -> call("/api/sync/session/" + sessionId, "session:" + sessionId));
    }

    public void syncAgenda(Long agendaId) {
        afterCommitAsync(() -> call("/api/sync/agenda/" + agendaId, "agenda:" + agendaId));
    }

    public void syncUser(Long userId) {
        afterCommitAsync(() -> call("/api/sync/user/" + userId, "user:" + userId));
    }

    public void syncMember(Long meetingId, Long userId, String role) {
        afterCommitAsync(() -> call(
                "/api/sync/member?meetingId=" + meetingId + "&userId=" + userId + "&role=" + role,
                "member:" + meetingId + "/" + userId));
    }

    public void deleteMeeting(Long meetingId) {
        afterCommitAsync(() -> callDelete("/api/sync/meeting/" + meetingId + "/delete", "delete-meeting:" + meetingId));
    }

    public void deleteMember(Long meetingId, Long userId) {
        afterCommitAsync(() -> callDelete(
                "/api/sync/member/delete?meetingId=" + meetingId + "&userId=" + userId,
                "delete-member:" + meetingId + "/" + userId));
    }

    private void call(String path, String label) {
        try {
            restTemplate.exchange(aiUrl + path, HttpMethod.POST, internalEntity(), Void.class);
            log.debug("[NeoSync] synced {}", label);
        } catch (Exception e) {
            log.warn("[NeoSync] failed to sync {} — {}", label, e.getMessage());
        }
    }

    private void callDelete(String path, String label) {
        try {
            restTemplate.exchange(aiUrl + path, HttpMethod.DELETE, internalEntity(), Void.class);
            log.debug("[NeoSync] deleted {}", label);
        } catch (Exception e) {
            log.warn("[NeoSync] failed to delete {} — {}", label, e.getMessage());
        }
    }
}
