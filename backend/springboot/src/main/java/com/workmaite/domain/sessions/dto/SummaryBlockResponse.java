package com.workmaite.domain.sessions.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.sessions.entity.SessionSummaryBlock;
import java.util.List;
import lombok.Builder;
import lombok.Getter;

@Getter
@Builder
public class SummaryBlockResponse {

  private Integer id;

  @JsonProperty("block_index")
  private Integer blockIndex;

  private String title;
  private List<String> bullets;

  @JsonProperty("recording_start_sec")
  private Double recordingStartSec;

  @JsonProperty("recording_end_sec")
  private Double recordingEndSec;

  public static SummaryBlockResponse from(SessionSummaryBlock block) {
    return SummaryBlockResponse.builder()
        .id(block.getId())
        .blockIndex(block.getBlockIndex())
        .title(block.getTitle())
        .bullets(block.getBullets())
        .recordingStartSec(block.getRecordingStartSec())
        .recordingEndSec(block.getRecordingEndSec())
        .build();
  }
}
