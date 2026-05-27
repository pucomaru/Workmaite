package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportFileType;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ReportSessionSubmitRequest {

    @NotNull(message = "회의체 ID를 입력해주세요.")
    private Long meetingId;

    @NotNull(message = "업로더 ID를 입력해주세요.")
    private Long uploaderId;

    @NotNull(message = "파일 타입을 선택해주세요.")
    private ReportFileType fileType;

    private String fileName;

    private String filePath;
}
