package com.workmaite.domain.minutes.controller;

import com.workmaite.domain.minutes.dto.*;
import com.workmaite.domain.minutes.service.MinutesService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 회의록 관련 API
 * POST   /api/v1/sessions/{sessionId}/minutes/generate - 회의록 생성
 * GET    /api/v1/sessions/{sessionId}/minutes          - 회의록 조회
 * PATCH  /api/v1/sessions/{sessionId}/minutes          - 회의록 수동 수정
 * POST   /api/v1/sessions/{sessionId}/minutes/summary  - 진행 중 요약
 * POST   /api/v1/sessions/{sessionId}/minutes/confirm  - 회의록 확정
 */
@RestController
@RequestMapping("/api/v1/sessions/{sessionId}/minutes")
@RequiredArgsConstructor
public class MinutesController {

    private final MinutesService minutesService;

    // 회의록 생성 - sessionId당 하나만 허용, AI가 contentRaw를 가공해 contentOriginal 생성
    @PostMapping("/generate")
    public ResponseEntity<ApiResponse<MinutesResponse>> generateMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesGenerateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.ok(minutesService.generateMinutes(sessionId, request)));
    }

    // 회의록 조회
    @GetMapping
    public ResponseEntity<ApiResponse<MinutesResponse>> getMinutes(@PathVariable Long sessionId) {
        return ResponseEntity.ok(ApiResponse.ok(minutesService.getMinutes(sessionId)));
    }

    // 회의록 수동 수정 - CONFIRMED 상태에서는 불가
    @PatchMapping
    public ResponseEntity<ApiResponse<MinutesResponse>> updateMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesUpdateRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(minutesService.updateMinutes(sessionId, request)));
    }

    // 진행 중 요약 - DB 저장 없이 AI 요약 결과만 반환
    @PostMapping("/summary")
    public ResponseEntity<ApiResponse<MinutesSummaryResponse>> getSummary(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesSummaryRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(minutesService.getSummary(request)));
    }

    // 회의록 확정 - contentSummary 없으면 contentOriginal 그대로 확정
    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<MinutesResponse>> confirmMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesConfirmRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(minutesService.confirmMinutes(sessionId, request)));
    }
}
