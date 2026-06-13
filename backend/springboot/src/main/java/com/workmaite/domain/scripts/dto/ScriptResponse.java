package com.workmaite.domain.scripts.dto;

import com.workmaite.domain.scripts.entity.SttSegment;
import java.time.LocalDateTime;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class ScriptResponse {

  private Long id;
  private Long sessionId;
  private String speakerLabel;
  private Long speakerUserId;
  private String content;
  private Double startSec;
  private Double endSec;
  private Double confidence;
  private LocalDateTime createdAt;

  public static ScriptResponse from(SttSegment segment) {
    return ScriptResponse.builder()
        .id(segment.getId())
        .sessionId(segment.getSessionId())
        .speakerLabel(segment.getSpeakerLabel())
        .speakerUserId(segment.getSpeakerUserId())
        .content(segment.getContent())
        .startSec(segment.getStartSec())
        .endSec(segment.getEndSec())
        .confidence(segment.getConfidence())
        .createdAt(segment.getCreatedAt())
        .build();
  }
}
