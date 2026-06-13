package com.workmaite.domain.reports.service;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportScore;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.reports.repository.ReportScoreRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ReportService {

  private final ReportRepository reportRepository;
  private final ReportScoreRepository reportScoreRepository;
  private final MeetingAccessGuard meetingAccessGuard;

  @Transactional
  @AuditLogged(action = "CREATE", entityType = "report")
  public ReportResponse submitReport(Long meetingId, ReportSubmitRequest request) {
    meetingAccessGuard.requireView(meetingId);
    Report report =
        Report.builder()
            .meetingId(meetingId)
            .uploadId(request.getUploadId())
            .submitterDepartment(request.getSubmitterDepartment())
            .fileName(request.getFileName())
            .filePath(request.getFilePath())
            .build();
    return ReportResponse.of(reportRepository.save(report));
  }

  @Transactional
  @AuditLogged(action = "CREATE", entityType = "report")
  public ReportResponse submitReportForSession(Long sessionId, ReportSessionSubmitRequest request) {
    meetingAccessGuard.requireView(request.getMeetingId());
    Report report =
        Report.builder()
            .meetingId(request.getMeetingId())
            .uploadId(request.getUploadId())
            .submitterDepartment(request.getSubmitterDepartment())
            .fileName(request.getFileName())
            .filePath(request.getFilePath())
            .build();
    return ReportResponse.of(reportRepository.save(report));
  }

  @Transactional
  @AuditLogged(action = "RESUBMIT", entityType = "report")
  public ReportResponse resubmitReport(Long reportId, ReportResubmitRequest request) {
    Report original = fetchOrThrow(reportId);
    // 재제출은 편집 — 소유자(업로더) 또는 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireOwnedEdit(original.getMeetingId(), original.getUploadId());

    Report resubmitted =
        Report.builder()
            .meetingId(original.getMeetingId())
            .uploadId(request.getUploadId())
            .submitterDepartment(request.getSubmitterDepartment())
            .parentId(original.getId())
            .version(original.getVersion() + 1)
            .fileName(request.getFileName())
            .filePath(request.getFilePath())
            .build();

    return ReportResponse.of(reportRepository.save(resubmitted));
  }

  public List<ReportResponse> getReportsByMeeting(Long meetingId) {
    meetingAccessGuard.requireView(meetingId);
    return reportRepository.findAllByMeetingId(meetingId).stream().map(ReportResponse::of).toList();
  }

  /** 세션 소속 회의체의 자료 목록 (이전엔 sessionId를 meetingId로 오용 — IDOR/버그 수정). */
  public List<ReportResponse> getReportsBySession(Long sessionId) {
    return getReportsByMeeting(meetingAccessGuard.meetingIdOfSession(sessionId));
  }

  public ReportResponse getReport(Long reportId) {
    return ReportResponse.of(findByIdOrThrow(reportId));
  }

  @Transactional
  @AuditLogged(action = "REVIEW", entityType = "report")
  public ReportResponse updateHumanStatus(Long reportId, ReportStatusUpdateRequest request) {
    Report report = fetchOrThrow(reportId);
    // 보고서 승인/반려는 회의체 운영 행위 — 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireMeetingEdit(report.getMeetingId());
    report.updateHumanStatus(request.getStatus());
    return ReportResponse.of(report);
  }

  public ReportReviewResultResponse getReviewResult(Long reportId) {
    meetingAccessGuard.requireViewByReport(reportId);
    ReportScore reportScore =
        reportScoreRepository
            .findByReportId(reportId)
            .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
    return ReportReviewResultResponse.of(reportScore);
  }

  @Transactional
  @AuditLogged(action = "DELETE", entityType = "report")
  public void deleteReport(Long reportId) {
    Report report = fetchOrThrow(reportId);
    // 삭제는 편집 — 소유자(업로더) 또는 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireOwnedEdit(report.getMeetingId(), report.getUploadId());
    reportRepository.deleteById(reportId);
  }

  // 조회 단일 진입점 — 조회 권한 검증 포함 (IDOR 차단)
  private Report findByIdOrThrow(Long reportId) {
    Report report = fetchOrThrow(reportId);
    meetingAccessGuard.requireView(report.getMeetingId());
    return report;
  }

  // 가드 없는 원본 조회 — 호출부에서 view/edit 권한을 명시적으로 검증한다
  private Report fetchOrThrow(Long reportId) {
    return reportRepository
        .findById(reportId)
        .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
  }
}
