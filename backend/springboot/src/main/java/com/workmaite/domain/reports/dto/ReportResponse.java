package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.Report;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ReportResponse {

  private Long id;
  private Long meetingId;
  private Long parentId;
  private Long uploadId;
  private Integer version;
  private String submitterDepartment;
  private String fileName;
  private String filePath;
  private String humanStatus;
  private LocalDateTime createdAt;

  public static ReportResponse of(Report report) {
    return ReportResponse.builder()
        .id(report.getId())
        .meetingId(report.getMeetingId())
        .parentId(report.getParentId())
        .uploadId(report.getUploadId())
        .version(report.getVersion())
        .submitterDepartment(report.getSubmitterDepartment())
        .fileName(report.getFileName())
        .filePath(report.getFilePath())
        .humanStatus(report.getHumanStatus())
        .createdAt(report.getCreatedAt())
        .build();
  }
}
