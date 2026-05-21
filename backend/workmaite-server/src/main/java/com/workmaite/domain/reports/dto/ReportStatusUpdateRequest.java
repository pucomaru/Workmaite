package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportStatus;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;

@Getter
public class ReportStatusUpdateRequest {

    @NotNull
    private ReportStatus status;
}
