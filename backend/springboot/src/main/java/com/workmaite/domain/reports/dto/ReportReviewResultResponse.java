package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.Report;
import com.workmaite.domain.reports.entity.ReportStatus;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ReportReviewResultResponse {

    private Long reportId;
    private ReportStatus status;
    private Float score;
    private String layer1Result;
    private String layer2Result;
    private String layer3Result;
    private String feedback;
    private String missingElements;

    public static ReportReviewResultResponse of(Report report) {
        return ReportReviewResultResponse.builder()
                .reportId(report.getId())
                .status(report.getStatus())
                .score(report.getScore())
                .layer1Result(report.getLayer1Result())
                .layer2Result(report.getLayer2Result())
                .layer3Result(report.getLayer3Result())
                .feedback(report.getFeedback())
                .missingElements(report.getMissingElements())
                .build();
    }
}
