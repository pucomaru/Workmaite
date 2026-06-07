package com.workmaite.domain.reports.dto;

import jakarta.validation.constraints.NotBlank;
import lombok.Getter;

@Getter
public class ReportStatusUpdateRequest {

    @NotBlank(message = "상태를 입력해주세요.")
    private String status;
}
