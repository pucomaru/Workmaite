package com.workmaite.domain.minutes.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MinutesConfirmRequest {

  private String contentSummary; // null이면 AI 생성본(contentOriginal) 그대로 확정
}
