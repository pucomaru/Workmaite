package com.workmaite.domain.reports.controller;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.service.ReportService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * 자료 관련 API POST /api/v1/meetings/{meetingId}/reports - 회의체 기준 자료 제출 GET
 * /api/v1/meetings/{meetingId}/reports - 회의체별 자료 목록 조회 POST /api/v1/sessions/{sessionId}/reports -
 * 세션 기준 자료 업로드 GET /api/v1/sessions/{sessionId}/reports - 세션별 자료 목록 조회 GET
 * /api/v1/reports/{reportId} - 자료 단건 조회 PATCH /api/v1/reports/{reportId}/status - 상태 변경 POST
 * /api/v1/reports/{reportId}/resubmit - 재제출 POST /api/v1/reports/{reportId}/review - 검토 요청 GET
 * /api/v1/reports/{reportId}/review-result - 검토 결과 조회 DELETE /api/v1/reports/{reportId} - 자료 삭제
 */
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ReportController {

  private final ReportService reportService;

  // 자료 제출 - SUBMITTED 상태로 저장
  @PostMapping("/meetings/{meetingId}/reports")
  public ResponseEntity<ApiResponse<ReportResponse>> submitReport(
      @PathVariable Integer meetingId, @Valid @RequestBody ReportSubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.submitReport(meetingId, request)));
  }

  // 회의체에 제출된 자료 목록 조회
  @GetMapping("/meetings/{meetingId}/reports")
  public ResponseEntity<ApiResponse<List<ReportResponse>>> getReportsByMeeting(
      @PathVariable Integer meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReportsByMeeting(meetingId)));
  }

  // 세션 기준 자료 업로드 - SUBMITTED 상태로 저장
  @PostMapping("/sessions/{sessionId}/reports")
  public ResponseEntity<ApiResponse<ReportResponse>> submitReportForSession(
      @PathVariable Integer sessionId, @Valid @RequestBody ReportSessionSubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.submitReportForSession(sessionId, request)));
  }

  // 세션에 제출된 자료 목록 조회
  @GetMapping("/sessions/{sessionId}/reports")
  public ResponseEntity<ApiResponse<List<ReportResponse>>> getReportsBySession(
      @PathVariable Integer sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReportsByMeeting(sessionId)));
  }

  // 자료 단건 조회
  @GetMapping("/reports/{reportId}")
  public ResponseEntity<ApiResponse<ReportResponse>> getReport(@PathVariable Integer reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReport(reportId)));
  }

  // 자료 상태 변경 (운영자 또는 AI 분석 완료 후 호출)
  @PatchMapping("/reports/{reportId}/status")
  public ResponseEntity<ApiResponse<ReportResponse>> updateStatus(
      @PathVariable Integer reportId, @Valid @RequestBody ReportStatusUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.updateHumanStatus(reportId, request)));
  }

  // 자료 재제출 - 기존 자료를 parent로 삼아 version +1
  @PostMapping("/reports/{reportId}/resubmit")
  public ResponseEntity<ApiResponse<ReportResponse>> resubmitReport(
      @PathVariable Integer reportId, @Valid @RequestBody ReportResubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.resubmitReport(reportId, request)));
  }

  // 자료 검토 요청 - REVIEWING 상태로 변경
  @PostMapping("/reports/{reportId}/review")
  public ResponseEntity<ApiResponse<ReportResponse>> requestReview(@PathVariable Integer reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReport(reportId)));
  }

  // 자료 검토 결과 조회
  @GetMapping("/reports/{reportId}/review-result")
  public ResponseEntity<ApiResponse<ReportReviewResultResponse>> getReviewResult(
      @PathVariable Integer reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReviewResult(reportId)));
  }

  // 자료 삭제
  @DeleteMapping("/reports/{reportId}")
  public ResponseEntity<ApiResponse<Void>> deleteReport(@PathVariable Integer reportId) {
    reportService.deleteReport(reportId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }
}
