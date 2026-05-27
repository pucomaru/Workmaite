package com.workmaite.domain.minutes.dto;

import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class MinutesSummaryResponse {

    private String summary;

    public static MinutesSummaryResponse of(String summary) {
        return MinutesSummaryResponse.builder()
                .summary(summary)
                .build();
    }
}
