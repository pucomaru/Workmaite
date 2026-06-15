package com.workmaite.global.exception;

import lombok.Getter;

/** 비즈니스 로직 예외 의도적으로 던지는 예외 (유저 없음, 중복 이메일 등) ErrorCode 를 담아서 GlobalExceptionHandler 로 전달 */
@Getter
public class BusinessException extends RuntimeException {

  private final ErrorCode errorCode;

  public BusinessException(ErrorCode errorCode) {
    super(errorCode.getMessage());
    this.errorCode = errorCode;
  }
}
