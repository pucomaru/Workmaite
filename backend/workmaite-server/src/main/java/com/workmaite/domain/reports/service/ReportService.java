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

/**
 * 자료 비즈니스 로직
 * - 제출: SUBMITTED 상태로 저장 (회의체 또는 세션 기준)
 * - 재제출: 기존 자료를 parent로 삼아 version +1
 * - 목록 조회: 회의체 또는 세션 단위로 조회
 * - 상태 변경: 운영자 또는 AI 분석 완료 후 호출
 * - 검토 요청: REVIEWING 상태로 변경
 * - 삭제: 자료 삭제
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class ReportService {

    private final ReportRepository reportRepository;

    // 회의체 기준 자료 제출
    @Transactional
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

    // 세션 기준 자료 업로드
    @Transactional
    public ReportResponse submitReportForSession(Long sessionId, ReportSessionSubmitRequest request) {
        Report report = Report.builder()
                .meetingId(request.getMeetingId())
                .sessionId(sessionId)
                .uploaderId(request.getUploaderId())
                .fileType(request.getFileType())
                .fileName(request.getFileName())
                .filePath(request.getFilePath())
                .build();
        return ReportResponse.of(reportRepository.save(report));
    }

    // 재제출 - 기존 자료를 parent로 삼아 version +1
    @Transactional
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

    public List<ReportResponse> getReportsByMeeting(Long meetingId) {
        return reportRepository.findAllByMeetingId(meetingId).stream()
                .map(ReportResponse::of)
                .toList();
    }

    public List<ReportResponse> getReportsBySession(Long sessionId) {
        return reportRepository.findAllBySessionId(sessionId).stream()
                .map(ReportResponse::of)
                .toList();
    }

    public ReportResponse getReport(Long reportId) {
        return ReportResponse.of(findByIdOrThrow(reportId));
    }

    // 상태 변경 (운영자 또는 AI 분석 완료 후 호출)
    @Transactional
    public ReportResponse updateStatus(Long reportId, ReportStatusUpdateRequest request) {
        Report report = findByIdOrThrow(reportId);
        report.updateStatus(request.getStatus());
        return ReportResponse.of(report);
    }

    // 검토 요청 - 상태를 REVIEWING으로 변경
    @Transactional
    public ReportResponse requestReview(Long reportId) {
        Report report = findByIdOrThrow(reportId);
        report.updateStatus(ReportStatus.REVIEWING);
        return ReportResponse.of(report);
    }

    // 검토 결과 조회
    public ReportReviewResultResponse getReviewResult(Long reportId) {
        return ReportReviewResultResponse.of(findByIdOrThrow(reportId));
    }

    // 자료 삭제
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
