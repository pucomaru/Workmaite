package com.workmaite.domain.reports.controller;

import com.workmaite.domain.reports.dto.ReportResponse;
import com.workmaite.domain.reports.dto.ReportResubmitRequest;
import com.workmaite.domain.reports.dto.ReportReviewResultResponse;
import com.workmaite.domain.reports.dto.ReportSessionSubmitRequest;
import com.workmaite.domain.reports.dto.ReportStatusUpdateRequest;
import com.workmaite.domain.reports.dto.ReportSubmitRequest;
import com.workmaite.domain.reports.service.ReportService;
import com.workmaite.global.common.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 자료 관련 API POST /api/v1/meetings/{meetingId}/reports - 회의체 기준 자료 제출 GET
 * /api/v1/meetings/{meetingId}/reports - 회의체별 자료 목록 조회 POST /api/v1/sessions/{sessionId}/reports -
 * 세션 기준 자료 업로드 GET /api/v1/sessions/{sessionId}/reports - 세션별 자료 목록 조회 GET
 * /api/v1/reports/{reportId} - 자료 단건 조회 PATCH /api/v1/reports/{reportId}/status - 상태 변경 POST
 * /api/v1/reports/{reportId}/resubmit - 재제출 POST /api/v1/reports/{reportId}/review - 검토 요청 GET
 * /api/v1/reports/{reportId}/review-result - 검토 결과 조회 DELETE /api/v1/reports/{reportId} - 자료 삭제
 */
@Tag(name = "보고자료", description = "회의체·세션 보고자료 제출, 조회, 상태 변경, 검토, 재제출, 삭제 API")
@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ReportController {

  private final ReportService reportService;

  @Operation(
      summary = "회의체 기준 자료 제출",
      description = "회의체(meetingId)에 보고자료를 제출합니다. SUBMITTED 상태로 저장되며 201 Created를 반환합니다.")
  @PostMapping("/meetings/{meetingId}/reports")
  public ResponseEntity<ApiResponse<ReportResponse>> submitReport(
      @PathVariable Long meetingId, @Valid @RequestBody ReportSubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.submitReport(meetingId, request)));
  }

  @Operation(summary = "회의체별 자료 목록 조회", description = "특정 회의체(meetingId)에 제출된 보고자료 목록을 조회합니다.")
  @GetMapping("/meetings/{meetingId}/reports")
  public ResponseEntity<ApiResponse<List<ReportResponse>>> getReportsByMeeting(
      @PathVariable Long meetingId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReportsByMeeting(meetingId)));
  }

  @Operation(
      summary = "세션 기준 자료 업로드",
      description = "세션(sessionId)에 보고자료를 업로드합니다. SUBMITTED 상태로 저장되며 201 Created를 반환합니다.")
  @PostMapping("/sessions/{sessionId}/reports")
  public ResponseEntity<ApiResponse<ReportResponse>> submitReportForSession(
      @PathVariable Long sessionId, @Valid @RequestBody ReportSessionSubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.submitReportForSession(sessionId, request)));
  }

  @Operation(summary = "세션별 자료 목록 조회", description = "특정 세션(sessionId)에 제출된 보고자료 목록을 조회합니다.")
  @GetMapping("/sessions/{sessionId}/reports")
  public ResponseEntity<ApiResponse<List<ReportResponse>>> getReportsBySession(
      @PathVariable Long sessionId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReportsBySession(sessionId)));
  }

  @Operation(summary = "자료 단건 조회", description = "reportId로 보고자료 단건을 조회합니다.")
  @GetMapping("/reports/{reportId}")
  public ResponseEntity<ApiResponse<ReportResponse>> getReport(@PathVariable Long reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReport(reportId)));
  }

  @Operation(summary = "자료 상태 변경", description = "보고자료의 상태를 변경합니다. 운영자(간사) 또는 AI 분석 완료 후 호출됩니다.")
  @PatchMapping("/reports/{reportId}/status")
  public ResponseEntity<ApiResponse<ReportResponse>> updateStatus(
      @PathVariable Long reportId, @Valid @RequestBody ReportStatusUpdateRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.updateHumanStatus(reportId, request)));
  }

  @Operation(
      summary = "자료 재제출",
      description = "기존 자료(reportId)를 parent로 삼아 version을 +1 하여 새 버전을 제출합니다. 201 Created를 반환합니다.")
  @PostMapping("/reports/{reportId}/resubmit")
  public ResponseEntity<ApiResponse<ReportResponse>> resubmitReport(
      @PathVariable Long reportId, @Valid @RequestBody ReportResubmitRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED)
        .body(ApiResponse.ok(reportService.resubmitReport(reportId, request)));
  }

  @Operation(summary = "자료 검토 요청", description = "보고자료의 검토를 요청합니다(REVIEWING 상태). 현재 자료 정보를 반환합니다.")
  @PostMapping("/reports/{reportId}/review")
  public ResponseEntity<ApiResponse<ReportResponse>> requestReview(@PathVariable Long reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReport(reportId)));
  }

  @Operation(summary = "자료 검토 결과 조회", description = "보고자료(reportId)의 AI 검토 결과를 조회합니다.")
  @GetMapping("/reports/{reportId}/review-result")
  public ResponseEntity<ApiResponse<ReportReviewResultResponse>> getReviewResult(
      @PathVariable Long reportId) {
    return ResponseEntity.ok(ApiResponse.ok(reportService.getReviewResult(reportId)));
  }

  @Operation(summary = "자료 삭제", description = "보고자료(reportId)를 삭제합니다.")
  @DeleteMapping("/reports/{reportId}")
  public ResponseEntity<ApiResponse<Void>> deleteReport(@PathVariable Long reportId) {
    reportService.deleteReport(reportId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }
}
