package com.workmaite.domain.reports.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportResubmitRequest {

    @NotNull
    private Long uploaderId;

    private String fileName;

    private String filePath;
}
