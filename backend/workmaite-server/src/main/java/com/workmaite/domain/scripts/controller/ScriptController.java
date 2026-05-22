package com.workmaite.domain.scripts.controller;

import com.workmaite.domain.scripts.dto.*;
import com.workmaite.domain.scripts.service.ScriptService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * POST   /api/v1/sessions/{sessionId}/scripts  - STT 세그먼트 일괄 저장
 * GET    /api/v1/sessions/{sessionId}/scripts  - 세그먼트 목록 조회 (시작 시간 오름차순)
 * PATCH  /api/v1/sessions/{sessionId}/scripts  - 세그먼트 수정 (ID 목록 기반 부분 수정)
 * DELETE /api/v1/sessions/{sessionId}/scripts  - 세션의 모든 세그먼트 삭제
 */
@RestController
@RequestMapping("/api/v1/sessions/{sessionId}/scripts")
@RequiredArgsConstructor
public class ScriptController {

    private final ScriptService scriptService;

    @PostMapping
    public ResponseEntity<ApiResponse<List<ScriptResponse>>> saveScripts(
            @PathVariable Long sessionId,
            @Valid @RequestBody ScriptSaveRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(scriptService.saveScripts(sessionId, request)));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<ScriptResponse>>> getScripts(
            @PathVariable Long sessionId) {
        return ResponseEntity.ok(ApiResponse.ok(scriptService.getScripts(sessionId)));
    }

    @PatchMapping
    public ResponseEntity<ApiResponse<List<ScriptResponse>>> updateScripts(
            @PathVariable Long sessionId,
            @Valid @RequestBody ScriptUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(scriptService.updateScripts(sessionId, request)));
    }

    @DeleteMapping
    public ResponseEntity<ApiResponse<Void>> deleteScripts(
            @PathVariable Long sessionId) {
        scriptService.deleteScripts(sessionId);
        return ResponseEntity.ok(ApiResponse.ok(null));
    }
}
