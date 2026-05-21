package com.workmaite.domain.reports.service;

import com.workmaite.domain.reports.dto.*;
import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportStatus;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional
public class ReportService {

    private final ReportRepository reportRepository;

    // 자료 제출
    public ReportResponse submitReport(Long meetingId, ReportSubmitRequest request) {
        Report report = Report.builder()
                .meetingId(meetingId)
                .sessionId(request.getSessionId())
                .uploaderId(request.getUploaderId())
                .fileType(request.getFileType())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();

        return ReportResponse.of(reportRepository.save(report));
    }

    // 재제출 - 기존 자료를 parent로 삼아 version +1
    public ReportResponse resubmitReport(Long reportId, ReportResubmitRequest request) {
        Report original = findByIdOrThrow(reportId);

        if (original.getStatus() == ReportStatus.APPROVED) {
            throw new BusinessException(ErrorCode.REPORT_ALREADY_APPROVED);
        }

        Report resubmitted = Report.builder()
                .meetingId(original.getMeetingId())
                .sessionId(original.getSessionId())
                .uploaderId(request.getUploaderId())
                .parentId(original.getId())
                .version(original.getVersion() + 1)
                .fileType(original.getFileType())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();

        return ReportResponse.of(reportRepository.save(resubmitted));
    }

    @Transactional(readOnly = true)
    public List<ReportResponse> getReportsByMeeting(Long meetingId) {
        return reportRepository.findAllByMeetingId(meetingId).stream()
                .map(ReportResponse::of)
                .toList();
    }

    @Transactional(readOnly = true)
    public ReportResponse getReport(Long reportId) {
        return ReportResponse.of(findByIdOrThrow(reportId));
    }

    // 상태 변경 (운영자 또는 AI 분석 완료 후 호출)
    public ReportResponse updateStatus(Long reportId, ReportStatusUpdateRequest request) {
        Report report = findByIdOrThrow(reportId);
        report.updateStatus(request.getStatus());
        return ReportResponse.of(report);
    }

    private Report findByIdOrThrow(Long reportId) {
        return reportRepository.findById(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND));
    }
}
