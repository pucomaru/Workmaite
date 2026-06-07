package com.workmaite.domain.reports.dto;

import com.workmaite.domain.reports.entity.ReportScore;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ReportReviewResultResponse {

    private Long reportId;
    private String aiStatus;
    private Float totalScore;
    private String detailScores;
    private String feedback;

    public static ReportReviewResultResponse of(ReportScore reportScore) {
        return ReportReviewResultResponse.builder()
                .reportId(reportScore.getReportId())
                .aiStatus(reportScore.getAiStatus())
                .totalScore(reportScore.getTotalScore())
                .detailScores(reportScore.getDetailScores())
                .feedback(reportScore.getFeedback())
                .build();
    }
}
