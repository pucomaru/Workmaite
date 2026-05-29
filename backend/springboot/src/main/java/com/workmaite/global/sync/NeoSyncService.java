package com.workmaite.global.sync;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

/**
 * PostgreSQL CUD 이후 FastAPI를 통해 Neo4j를 비동기 동기화.
 * 실패해도 메인 트랜잭션에 영향 없음.
 */
@Slf4j
@Service
public class NeoSyncService {

    private final RestTemplate restTemplate;
    private final String aiUrl;

    public NeoSyncService(RestTemplate restTemplate,
                          @Value("${ai.url:http://localhost:8000}") String aiUrl) {
        this.restTemplate = restTemplate;
        this.aiUrl = aiUrl;
    }

    @Async
    public void syncMeeting(Long meetingId) {
        call("/api/sync/meeting/" + meetingId, "meeting:" + meetingId);
    }

    @Async
    public void syncSession(Long sessionId) {
        call("/api/sync/session/" + sessionId, "session:" + sessionId);
    }

    @Async
    public void syncAgenda(Long agendaId) {
        call("/api/sync/agenda/" + agendaId, "agenda:" + agendaId);
    }

    @Async
    public void syncUser(Long userId) {
        call("/api/sync/user/" + userId, "user:" + userId);
    }

    @Async
    public void syncMember(Long meetingId, Long userId) {
        call("/api/sync/member?meetingId=" + meetingId + "&userId=" + userId, "member:" + meetingId + "/" + userId);
    }

    @Async
    public void deleteMeeting(Long meetingId) {
        callDelete("/api/sync/meeting/" + meetingId + "/delete", "delete-meeting:" + meetingId);
    }

    @Async
    public void deleteMember(Long meetingId, Long userId) {
        callDelete("/api/sync/member/delete?meetingId=" + meetingId + "&userId=" + userId, "delete-member:" + meetingId + "/" + userId);
    }

    private void call(String path, String label) {
        try {
            restTemplate.postForEntity(aiUrl + path, null, Void.class);
            log.debug("[NeoSync] synced {}", label);
        } catch (Exception e) {
            log.warn("[NeoSync] failed to sync {} — {}", label, e.getMessage());
        }
    }

    private void callDelete(String path, String label) {
        try {
            org.springframework.web.client.RequestCallback callback = restTemplate.acceptHeaderRequestCallback(Void.class);
            restTemplate.execute(aiUrl + path, org.springframework.http.HttpMethod.DELETE, callback, null);
            log.debug("[NeoSync] deleted {}", label);
        } catch (Exception e) {
            log.warn("[NeoSync] failed to delete {} — {}", label, e.getMessage());
        }
    }
}
