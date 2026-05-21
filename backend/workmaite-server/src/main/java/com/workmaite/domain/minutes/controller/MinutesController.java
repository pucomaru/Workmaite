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
 * POST   /api/v1/sessions/{sessionId}/minutes         - 회의록 생성
 * GET    /api/v1/sessions/{sessionId}/minutes         - 회의록 조회
 * PATCH  /api/v1/sessions/{sessionId}/minutes         - 회의록 수동 수정
 * POST   /api/v1/sessions/{sessionId}/minutes/summary - 진행 중 요약
 * POST   /api/v1/sessions/{sessionId}/minutes/confirm - 회의록 확정
 */
@RestController
@RequestMapping("/api/v1/sessions/{sessionId}/minutes")
@RequiredArgsConstructor
public class MinutesController {

    private final MinutesService minutesService;

    @PostMapping
    public ResponseEntity<ApiResponse<MinutesResponse>> generateMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesGenerateRequest request) {
        MinutesResponse response = minutesService.generateMinutes(sessionId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok(response));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<MinutesResponse>> getMinutes(@PathVariable Long sessionId) {
        MinutesResponse response = minutesService.getMinutes(sessionId);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @PatchMapping
    public ResponseEntity<ApiResponse<MinutesResponse>> updateMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesUpdateRequest request) {
        MinutesResponse response = minutesService.updateMinutes(sessionId, request);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @PostMapping("/summary")
    public ResponseEntity<ApiResponse<MinutesSummaryResponse>> getSummary(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesSummaryRequest request) {
        MinutesSummaryResponse response = minutesService.getSummary(request);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<MinutesResponse>> confirmMinutes(
            @PathVariable Long sessionId,
            @Valid @RequestBody MinutesConfirmRequest request) {
        MinutesResponse response = minutesService.confirmMinutes(sessionId, request);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }
}
