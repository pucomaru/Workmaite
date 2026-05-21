package com.workmaite.domain.sessions.controller;

import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.service.SessionService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1")
public class SessionController {

    private final SessionService sessionService;

    @GetMapping("/meetings/{meetingId}/sessions")
    public ResponseEntity<ApiResponse<List<SessionResponse>>> getSessions(
            @PathVariable Long meetingId,
            @RequestParam(required = false) SessionStatus status) {
        return ResponseEntity.ok(ApiResponse.ok(sessionService.getSessions(meetingId, status)));
    }

    @PostMapping("/meetings/{meetingId}/sessions")
    public ResponseEntity<ApiResponse<SessionResponse>> createSession(
            @PathVariable Long meetingId,
            @RequestBody @Valid SessionCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(sessionService.createSession(meetingId, request)));
    }

    @GetMapping("/sessions/{sessionId}")
    public ResponseEntity<ApiResponse<SessionResponse>> getSession(
            @PathVariable Long sessionId) {
        return ResponseEntity.ok(ApiResponse.ok(sessionService.getSession(sessionId)));
    }

    @PatchMapping("/sessions/{sessionId}")
    public ResponseEntity<ApiResponse<SessionResponse>> updateSession(
            @PathVariable Long sessionId,
            @RequestBody SessionUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(sessionService.updateSession(sessionId, request)));
    }

    @DeleteMapping("/sessions/{sessionId}")
    public ResponseEntity<ApiResponse<Void>> deleteSession(
            @PathVariable Long sessionId) {
        sessionService.deleteSession(sessionId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }
}
