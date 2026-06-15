package com.workmaite.domain.minutes.dto;

import com.workmaite.domain.minutes.entity.Minutes;
import com.workmaite.domain.minutes.entity.MinutesStatus;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class MinutesResponse {

  private Long id;
  private Long sessionId;
  private Long recorderId;
  private String fileName;
  private String filePath;
  private String contentOriginal;
  private String contentSummary;
  private MinutesStatus status;
  private LocalDateTime generatedAt;

  public static MinutesResponse of(Minutes minutes) {
    return MinutesResponse.builder()
        .id(minutes.getId())
        .sessionId(minutes.getSessionId())
        .recorderId(minutes.getRecorderId())
        .fileName(minutes.getFileName())
        .filePath(minutes.getFilePath())
        .contentOriginal(minutes.getContentOriginal())
        .contentSummary(minutes.getContentSummary())
        .status(minutes.getStatus())
        .generatedAt(minutes.getGeneratedAt())
        .build();
  }
}
