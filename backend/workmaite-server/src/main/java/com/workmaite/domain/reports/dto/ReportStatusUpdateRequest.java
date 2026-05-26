package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportStatus;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportStatusUpdateRequest {

    @NotNull(message = "상태를 선택해주세요.")
    private ReportStatus status;
}
