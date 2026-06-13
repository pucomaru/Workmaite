package com.workmaite.global.common;

import lombok.Getter;

/** API 공통 응답 형식 모든 응답은 이 형식으로 감싸서 반환 */
@Getter
public class ApiResponse<T> {

  private final boolean success; // 요청 성공 여부
  private final String message; // 응답 메시지
  private final T data; // 실제 응답 데이터

  private ApiResponse(boolean success, String message, T data) {
    this.success = success;
    this.message = message;
    this.data = data;
  }

  // 데이터 있는 성공 응답
  public static <T> ApiResponse<T> ok(T data) {
    return new ApiResponse<>(true, "success", data);
  }

  // 메시지 + 데이터 있는 성공 응답
  public static <T> ApiResponse<T> ok(String message, T data) {
    return new ApiResponse<>(true, message, data);
  }

  // 실패 응답 (data null)
  public static <T> ApiResponse<T> fail(String message) {
    return new ApiResponse<>(false, message, null);
  }
}
