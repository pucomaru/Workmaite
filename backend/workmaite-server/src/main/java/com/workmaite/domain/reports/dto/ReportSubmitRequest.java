package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportFileType;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportSubmitRequest {

    @NotNull
    private Long uploaderId;

    private Long sessionId;

    @NotNull
    private ReportFileType fileType;

    private String fileName;

    private String filePath;
}
