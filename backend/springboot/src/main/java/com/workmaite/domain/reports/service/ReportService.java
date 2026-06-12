package com.workmaite.domain.reports.service;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportScore;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.reports.repository.ReportScoreRepository;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ReportService {

    private final ReportRepository reportRepository;
    private final ReportScoreRepository reportScoreRepository;
    private final MeetingAccessGuard meetingAccessGuard;

    @Transactional
    public ReportResponse submitReport(Long meetingId, ReportSubmitRequest request) {
        meetingAccessGuard.requireMember(meetingId);
        Report report = Report.builder()
                .meetingId(meetingId)
                .uploadId(request.getUploadId())
                .submitterDepartment(request.getSubmitterDepartment())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();
        return ReportResponse.of(reportRepository.save(report));
    }

    @Transactional
    public ReportResponse submitReportForSession(Long sessionId, ReportSessionSubmitRequest request) {
        meetingAccessGuard.requireMember(request.getMeetingId());
        Report report = Report.builder()
                .meetingId(request.getMeetingId())
                .uploadId(request.getUploadId())
                .submitterDepartment(request.getSubmitterDepartment())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();
        return ReportResponse.of(reportRepository.save(report));
    }

    @Transactional
    public ReportResponse resubmitReport(Long reportId, ReportResubmitRequest request) {
        Report original = findByIdOrThrow(reportId);

        Report resubmitted = Report.builder()
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
        meetingAccessGuard.requireMember(meetingId);
        return reportRepository.findAllByMeetingId(meetingId).stream()
                .map(ReportResponse::of)
                .toList();
    }

    public ReportResponse getReport(Long reportId) {
        return ReportResponse.of(findByIdOrThrow(reportId));
    }

    @Transactional
    public ReportResponse updateHumanStatus(Long reportId, ReportStatusUpdateRequest request) {
        Report report = findByIdOrThrow(reportId);
        report.updateHumanStatus(request.getStatus());
        return ReportResponse.of(report);
    }

    public ReportReviewResultResponse getReviewResult(Long reportId) {
        meetingAccessGuard.requireMemberByReport(reportId);
        ReportScore reportScore = reportScoreRepository.findByReportId(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
        return ReportReviewResultResponse.of(reportScore);
    }

    @Transactional
    public void deleteReport(Long reportId) {
        meetingAccessGuard.requireMemberByReport(reportId);
        reportRepository.deleteById(reportId);
    }

    // 모든 reportId 경로의 단일 진입점 — 멤버십 검증 포함 (IDOR 차단, P1-4)
    private Report findByIdOrThrow(Long reportId) {
        Report report = reportRepository.findById(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
        meetingAccessGuard.requireMember(report.getMeetingId());
        return report;
    }
}
