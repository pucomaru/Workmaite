package com.workmaite.domain.sessions.controller;

import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.dto.UpcomingSessionResponse;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.service.SessionService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
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
@Tag(name = "회의 세션", description = "회의 세션 생성·조회·수정·삭제 및 진행 상태(시작/정지/재개/종료/보관) 관리 API")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class SessionController {

  private final SessionService sessionService;

  @Operation(summary = "내 예정된 회의 목록 조회", description = "인증된 사용자가 참여 예정인 회의 세션 목록을 조회한다.")
  @GetMapping("/me/sessions")
  public ResponseEntity<ApiResponse<List<UpcomingSessionResponse>>> getMyUpcomingSessions(
      Authentication authentication) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getMyUpcomingSessions(userId)));
  }

  @Operation(
      summary = "회의체별 회의 목록 조회",
      description = "특정 회의체에 속한 회의 세션 목록을 조회한다. status로 상태별 필터링이 가능하다.")
  @GetMapping("/meetings/{meetingId}/sessions")
  public ResponseEntity<ApiResponse<List<SessionResponse>>> getSessions(
      @PathVariable Long meetingId, @RequestParam(required = false) SessionStatus status) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSessions(meetingId, status)));
  }

  @Operation(
      summary = "회의 생성",
      description = "회의체에 새 회의 세션을 생성한다. 간사(secretary) 권한이 필요하며 성공 시 201 Created를 반환한다.")
  @PostMapping("/meetings/{meetingId}/sessions")
  public ResponseEntity<ApiResponse<SessionResponse>> createSession(
      @PathVariable Long meetingId, @RequestBody @Valid SessionCreateRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(sessionService.createSession(meetingId, request)));
  }

  @Operation(summary = "회의 상세 조회", description = "특정 회의 세션의 상세 정보를 조회한다.")
  @GetMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<SessionResponse>> getSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSession(sessionId)));
  }

  @Operation(summary = "회의 안건 ID 목록 조회", description = "특정 회의 세션에 연결된 안건 ID 목록을 조회한다.")
  @GetMapping("/sessions/{sessionId}/agendas")
  public ResponseEntity<ApiResponse<List<Long>>> getSessionAgendas(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.getSessionAgendaIds(sessionId)));
  }

  @Operation(summary = "회의 수정", description = "회의 세션 정보를 수정한다. 간사(secretary) 권한이 필요하다.")
  @PatchMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<SessionResponse>> updateSession(
      @PathVariable Long sessionId, @RequestBody SessionUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.updateSession(sessionId, request)));
  }

  @Operation(summary = "회의 삭제", description = "회의 세션을 삭제한다. 간사(secretary) 권한이 필요한 파괴적 작업이다.")
  @DeleteMapping("/sessions/{sessionId}")
  public ResponseEntity<ApiResponse<Void>> deleteSession(@PathVariable Long sessionId) {
    sessionService.deleteSession(sessionId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }

  // Meeting Progress — status, started_at, ended_at 업데이트

  @Operation(
      summary = "회의 시작",
      description = "회의를 시작 상태로 전환하고 시작 시각(started_at)을 기록한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/sessions/{sessionId}/start")
  public ResponseEntity<ApiResponse<SessionResponse>> startSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.startSession(sessionId)));
  }

  @Operation(summary = "회의 정지", description = "진행중인 회의를 일시 정지 상태로 전환한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/sessions/{sessionId}/pause")
  public ResponseEntity<ApiResponse<SessionResponse>> pauseSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.pauseSession(sessionId)));
  }

  @Operation(summary = "회의 재개", description = "정지된 회의를 다시 진행 상태로 전환한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/sessions/{sessionId}/resume")
  public ResponseEntity<ApiResponse<SessionResponse>> resumeSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.resumeSession(sessionId)));
  }

  @Operation(
      summary = "회의 종료",
      description = "회의를 종료 상태로 전환하고 종료 시각(ended_at)을 기록한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/sessions/{sessionId}/end")
  public ResponseEntity<ApiResponse<SessionResponse>> endSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.endSession(sessionId)));
  }

  @Operation(summary = "회의 보관", description = "종료된 회의를 보관(아카이브) 상태로 전환한다. 간사(secretary) 권한이 필요하다.")
  @PostMapping("/sessions/{sessionId}/archive")
  public ResponseEntity<ApiResponse<SessionResponse>> archiveSession(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(sessionService.archiveSession(sessionId)));
  }

  @Operation(summary = "회의 맥락 수정", description = "회의 세션의 맥락(context) 텍스트를 수정한다.")
  @PatchMapping("/sessions/{sessionId}/context")
  public ResponseEntity<ApiResponse<SessionResponse>> updateContext(
      @PathVariable Long sessionId, @RequestBody java.util.Map<String, String> body) {
    return ResponseEntity.ok(
        ApiResponse.ok(sessionService.updateContext(sessionId, body.get("context"))));
  }
}
