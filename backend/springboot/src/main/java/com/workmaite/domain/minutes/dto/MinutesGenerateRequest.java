package com.workmaite.domain.minutes.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class MinutesGenerateRequest {

  private String contentOriginal;
  private String fileName;
  private String filePath;
}
