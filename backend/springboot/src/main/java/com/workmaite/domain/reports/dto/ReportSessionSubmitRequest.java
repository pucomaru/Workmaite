package com.workmaite.domain.reports.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ReportSessionSubmitRequest {

  @NotNull(message = "회의체 ID를 입력해주세요.")
  private Integer meetingId;

  @NotNull(message = "업로더 ID를 입력해주세요.")
  private Integer uploadId;

  @NotBlank(message = "제출 부서를 입력해주세요.")
  private String submitterDepartment;

  private String fileName;
  private String filePath;
}
