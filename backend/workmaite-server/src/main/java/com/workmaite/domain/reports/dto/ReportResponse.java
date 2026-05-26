package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportFileType;
import com.workmaite.domain.reports.entity.ReportStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class ReportResponse {

    private Long id;
    private Long meetingId;
    private Long sessionId;
    private Long uploaderId;
    private Long parentId;
    private Integer version;
    private ReportFileType fileType;
    private String fileName;
    private String filePath;
    private ReportStatus status;
    private Float score;
    private String layer1Result;
    private String layer2Result;
    private String layer3Result;
    private String feedback;
    private String missingElements;
    private LocalDateTime createdAt;

    public static ReportResponse of(Report report) {
        return ReportResponse.builder()
                .id(report.getId())
                .meetingId(report.getMeetingId())
                .sessionId(report.getSessionId())
                .uploaderId(report.getUploaderId())
                .parentId(report.getParentId())
                .version(report.getVersion())
                .fileType(report.getFileType())
                .fileName(report.getFileName())
                .filePath(report.getFilePath())
                .status(report.getStatus())
                .score(report.getScore())
                .layer1Result(report.getLayer1Result())
                .layer2Result(report.getLayer2Result())
                .layer3Result(report.getLayer3Result())
                .feedback(report.getFeedback())
                .missingElements(report.getMissingElements())
                .createdAt(report.getCreatedAt())
                .build();
    }
}
