package com.workmaite.domain.scripts.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ScriptSaveRequest {

  @NotEmpty(message = "저장할 스크립트 세그먼트가 없습니다.")
  @Valid
  private List<SegmentRequest> segments;

  @Getter
  @NoArgsConstructor
  public static class SegmentRequest {

    @NotBlank(message = "발화자 식별자는 필수입니다.")
    private String speakerLabel;

    // 매핑된 시스템 사용자 ID (nullable)
    private Long speakerUserId;

    @NotBlank(message = "발화 내용은 필수입니다.")
    private String content;

    @NotNull(message = "발화 시작 시간은 필수입니다.")
    private Double startSec;

    @NotNull(message = "발화 종료 시간은 필수입니다.")
    private Double endSec;

    // STT 신뢰도 (nullable)
    private Double confidence;
  }
}
