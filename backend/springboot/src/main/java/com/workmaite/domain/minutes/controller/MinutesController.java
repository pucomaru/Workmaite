package com.workmaite.domain.minutes.controller;

import com.workmaite.domain.minutes.dto.MinutesConfirmRequest;
import com.workmaite.domain.minutes.dto.MinutesGenerateRequest;
import com.workmaite.domain.minutes.dto.MinutesResponse;
import com.workmaite.domain.minutes.dto.MinutesSummaryRequest;
import com.workmaite.domain.minutes.dto.MinutesSummaryResponse;
import com.workmaite.domain.minutes.dto.MinutesUpdateRequest;
import com.workmaite.domain.minutes.service.MinutesService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 회의록 관련 API POST /api/v1/sessions/{sessionId}/minutes/generate - 회의록 생성 GET
 * /api/v1/sessions/{sessionId}/minutes - 회의록 조회 PATCH /api/v1/sessions/{sessionId}/minutes - 회의록 수동
 * 수정 POST /api/v1/sessions/{sessionId}/minutes/summary - 진행 중 요약 POST
 * /api/v1/sessions/{sessionId}/minutes/confirm - 회의록 확정
 */
@Tag(name = "회의록", description = "세션 회의록 생성·조회·수정·요약·확정 API")
@RestController
@RequestMapping("/api/v1/sessions/{sessionId}/minutes")
@RequiredArgsConstructor
public class MinutesController {

  private final MinutesService minutesService;

  @Operation(
      summary = "회의록 생성",
      description =
          "세션(sessionId)의 회의록을 생성합니다. sessionId당 하나만 허용되며, AI가 contentRaw를 가공해 contentOriginal을"
              + " 생성합니다. 201 Created를 반환합니다.")
  @PostMapping("/generate")
  public ResponseEntity<ApiResponse<MinutesResponse>> generateMinutes(
      @PathVariable Long sessionId, @Valid @RequestBody MinutesGenerateRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(minutesService.generateMinutes(sessionId, request)));
  }

  @Operation(summary = "회의록 조회", description = "세션(sessionId)의 회의록을 조회합니다.")
  @GetMapping
  public ResponseEntity<ApiResponse<MinutesResponse>> getMinutes(@PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(minutesService.getMinutes(sessionId)));
  }

  @Operation(
      summary = "회의록 수동 수정",
      description = "세션(sessionId)의 회의록을 수동으로 수정합니다. 확정(completed) 상태에서는 수정할 수 없습니다.")
  @PatchMapping
  public ResponseEntity<ApiResponse<MinutesResponse>> updateMinutes(
      @PathVariable Long sessionId, @Valid @RequestBody MinutesUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(minutesService.updateMinutes(sessionId, request)));
  }

  @Operation(summary = "진행 중 요약", description = "회의 진행 중 요약을 생성합니다. DB에 저장하지 않고 AI 요약 결과만 반환합니다.")
  @PostMapping("/summary")
  public ResponseEntity<ApiResponse<MinutesSummaryResponse>> getSummary(
      @PathVariable Long sessionId, @Valid @RequestBody MinutesSummaryRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(minutesService.getSummary(request)));
  }

  @Operation(
      summary = "회의록 확정",
      description = "세션(sessionId)의 회의록을 확정합니다. contentSummary가 없으면 contentOriginal을 그대로 확정합니다.")
  @PostMapping("/confirm")
  public ResponseEntity<ApiResponse<MinutesResponse>> confirmMinutes(
      @PathVariable Long sessionId, @Valid @RequestBody MinutesConfirmRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(minutesService.confirmMinutes(sessionId, request)));
  }
}
