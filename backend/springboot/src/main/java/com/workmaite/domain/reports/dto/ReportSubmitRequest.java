package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportFileType;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportSubmitRequest {

    @NotNull(message = "업로더 ID를 입력해주세요.")
    private Long uploaderId;

    private Long sessionId;

    @NotNull(message = "파일 타입을 선택해주세요.")
    private ReportFileType fileType;

    private String fileName;

    private String filePath;
}
