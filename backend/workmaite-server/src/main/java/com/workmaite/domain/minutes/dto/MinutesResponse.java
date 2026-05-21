package com.workmaite.domain.minutes.dto;

import com.workmaite.domain.minutes.entity.Minutes;
import com.workmaite.domain.minutes.entity.MinutesStatus;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@Builder
public class MinutesResponse {

    private Long id;
    private Long sessionId;
    private Long recorderId;
    private String contentRaw;
    private String contentOriginal;
    private String contentSummary;
    private MinutesStatus status;
    private LocalDateTime generatedAt;
    private LocalDateTime updatedAt;

    public static MinutesResponse of(Minutes minutes) {
        return MinutesResponse.builder()
                .id(minutes.getId())
                .sessionId(minutes.getSessionId())
                .recorderId(minutes.getRecorderId())
                .contentRaw(minutes.getContentRaw())
                .contentOriginal(minutes.getContentOriginal())
                .contentSummary(minutes.getContentSummary())
                .status(minutes.getStatus())
                .generatedAt(minutes.getGeneratedAt())
                .updatedAt(minutes.getUpdatedAt())
                .build();
    }
}
