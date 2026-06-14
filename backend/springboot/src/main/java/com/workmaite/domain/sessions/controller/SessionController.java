package com.workmaite.domain.sessions.controller;

import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.dto.UpcomingSessionResponse;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.service.SessionService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회의 관련 API GET /api/v1/me/sessions - 내 예정된 회의 목록 조회 GET /api/v1/meetings/{meetingId}/sessions -
 * 회의체별 회의 목록 조회 POST /api/v1/meetings/{meetingId}/sessions - 회의 생성 (secretary 권한) GET
 * /api/v1/sessions/{sessionId} - 회의 상세 조회 PATCH /api/v1/sessions/{sessionId} - 회의 수정 (secretary 권한)
 * PATCH /api/v1/sessions/{sessionId}/context - 회의 맥락 수정 DELETE /api/v1/sessions/{sessionId} - 회의 삭제
 * (secretary 권한) POST /api/v1/sessions/{sessionId}/start - 회의 시작 (secretary 권한) POST
 * /api/v1/sessions/{sessionId}/pause - 회의 정지 (secretary 권한) POST /api/v1/sessions/{sessionId}/end -
 * 회의 종료 (secretary 권한)
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class SessionController {

  private final SessionService sessionService;

  @GetMapping("/me/sessions")
  public ResponseEntity<ApiResponse<List<UpcomingSessionResponse>>> getMyUpcomingSessions(
      Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getMyUpcomingSessions(userId)));
  }

  @GetMapping("/meetings/{meetingId}/sessions")
  public ResponseEntity<ApiResponse<List<SessionResponse>>> getSessions(
      @PathVariable Long meetingId, @RequestParam(required = false) SessionStatus status) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSessions(meetingId, status)));
  }

  @PostMapping("/meetings/{meetingId}/sessions")
  public ResponseEntity<ApiResponse<SessionResponse>> createSession(
      @PathVariable Long meetingId, @RequestBody @Valid SessionCreateRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(sessionService.createSession(meetingId, request)));
  }

  @GetMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<SessionResponse>> getSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSession(sessionId)));
  }

  @GetMapping("/sessions/{sessionId}/agendas")
  public ResponseEntity<ApiResponse<List<Long>>> getSessionAgendas(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSessionAgendaIds(sessionId)));
  }

  @PatchMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<SessionResponse>> updateSession(
      @PathVariable Long sessionId, @RequestBody SessionUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.updateSession(sessionId, request)));
  }

  @DeleteMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<Void>> deleteSession(@PathVariable Long sessionId) {
    sessionService.deleteSession(sessionId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  // Meeting Progress — status, started_at, ended_at 업데이트

  @PostMapping("/sessions/{sessionId}/start")
  public ResponseEntity<ApiResponse<SessionResponse>> startSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.startSession(sessionId)));
  }

  @PostMapping("/sessions/{sessionId}/pause")
  public ResponseEntity<ApiResponse<SessionResponse>> pauseSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.pauseSession(sessionId)));
  }

  @PostMapping("/sessions/{sessionId}/resume")
  public ResponseEntity<ApiResponse<SessionResponse>> resumeSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.resumeSession(sessionId)));
  }

  @PostMapping("/sessions/{sessionId}/end")
  public ResponseEntity<ApiResponse<SessionResponse>> endSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.endSession(sessionId)));
  }

  @PostMapping("/sessions/{sessionId}/archive")
  public ResponseEntity<ApiResponse<SessionResponse>> archiveSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.archiveSession(sessionId)));
  }

  @PatchMapping("/sessions/{sessionId}/context")
  public ResponseEntity<ApiResponse<SessionResponse>> updateContext(
      @PathVariable Long sessionId, @RequestBody java.util.Map<String, String> body) {
    return ResponseEntity.ok(
        ApiResponse.ok(sessionService.updateContext(sessionId, body.get("context"))));
  }
}
