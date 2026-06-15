package com.workmaite.domain.scripts.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ScriptUpdateRequest {

  @NotEmpty(message = "수정할 세그먼트가 없습니다.")
  @Valid
  private List<SegmentUpdate> segments;

  @Getter
  @NoArgsConstructor
  public static class SegmentUpdate {

    // 수정할 세그먼트 ID (필수)
    @NotNull(message = "세그먼트 ID는 필수입니다.")
    private Long id;

    // 부분 수정: 모든 필드 nullable
    private String speakerLabel;
    private Long speakerUserId;
    private String content;
    private Double startSec;
    private Double endSec;
  }
}
