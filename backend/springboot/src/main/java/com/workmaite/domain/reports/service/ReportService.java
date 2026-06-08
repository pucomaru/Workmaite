package com.workmaite.domain.reports.service;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportScore;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.reports.repository.ReportScoreRepository;
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

    @Transactional
    public ReportResponse submitReport(Long meetingId, ReportSubmitRequest request) {
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
        ReportScore reportScore = reportScoreRepository.findByReportId(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
        return ReportReviewResultResponse.of(reportScore);
    }

    @Transactional
    public void deleteReport(Long reportId) {
        if (!reportRepository.existsById(reportId)) {
            throw new BusinessException(ErrorCode.REPORT_NOT_FOUND);
        }
        reportRepository.deleteById(reportId);
    }

    private Report findByIdOrThrow(Long reportId) {
        return reportRepository.findById(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
    }
}
