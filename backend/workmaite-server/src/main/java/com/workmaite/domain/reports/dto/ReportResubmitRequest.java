package com.workmaite.domain.reports.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportResubmitRequest {

    @NotNull(message = "업로더 ID를 입력해주세요.")
    private Long uploaderId;

    private String fileName;

    private String filePath;
}
