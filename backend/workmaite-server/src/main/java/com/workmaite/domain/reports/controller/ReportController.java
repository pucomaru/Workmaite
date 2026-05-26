package com.workmaite.domain.reports.controller;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.service.ReportService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * POST   /api/v1/meetings/{meetingId}/reports              - 자료 제출
 * GET    /api/v1/meetings/{meetingId}/reports              - 자료 목록 조회
 * GET    /api/v1/reports/{reportId}                        - 자료 단건 조회
 * PATCH  /api/v1/reports/{reportId}/status                 - 상태 변경
 * POST   /api/v1/reports/{reportId}/resubmit               - 재제출
 */
@RestController
@RequiredArgsConstructor
public class ReportController {

    private final ReportService reportService;

    @PostMapping("/api/v1/meetings/{meetingId}/reports")
    public ResponseEntity<ApiResponse<ReportResponse>> submitReport(
            @PathVariable Long meetingId,
            @Valid @RequestBody ReportSubmitRequest request) {
        ReportResponse response = reportService.submitReport(meetingId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok(response));
    }

    @GetMapping("/api/v1/meetings/{meetingId}/reports")
    public ResponseEntity<ApiResponse<List<ReportResponse>>> getReportsByMeeting(
            @PathVariable Long meetingId) {
        List<ReportResponse> response = reportService.getReportsByMeeting(meetingId);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @GetMapping("/api/v1/reports/{reportId}")
    public ResponseEntity<ApiResponse<ReportResponse>> getReport(@PathVariable Long reportId) {
        ReportResponse response = reportService.getReport(reportId);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @PatchMapping("/api/v1/reports/{reportId}/status")
    public ResponseEntity<ApiResponse<ReportResponse>> updateStatus(
            @PathVariable Long reportId,
            @Valid @RequestBody ReportStatusUpdateRequest request) {
        ReportResponse response = reportService.updateStatus(reportId, request);
        return ResponseEntity.ok(ApiResponse.ok(response));
    }

    @PostMapping("/api/v1/reports/{reportId}/resubmit")
    public ResponseEntity<ApiResponse<ReportResponse>> resubmitReport(
            @PathVariable Long reportId,
            @Valid @RequestBody ReportResubmitRequest request) {
        ReportResponse response = reportService.resubmitReport(reportId, request);
        return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok(response));
    }
}
