package com.workmaite.global.exception;

import com.workmaite.global.common.ApiResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

  @ExceptionHandler(MethodArgumentNotValidException.class)
  public ResponseEntity<ApiResponse<Void>> handleValidationException(
      MethodArgumentNotValidException e) {
    String message =
        e.getBindingResult().getFieldErrors().stream()
            .map(FieldError::getDefaultMessage)
            .findFirst()
            .orElse(ErrorCode.INVALID_INPUT_VALUE.getMessage());
    // 필드 검증 메시지만 기록 (거부된 값은 PII일 수 있어 제외)
    log.warn("입력 검증 실패: {}", message);
    return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(ApiResponse.fail(message));
  }

  @ExceptionHandler(BusinessException.class)
  public ResponseEntity<ApiResponse<Void>> handleBusinessException(BusinessException e) {
    // 비즈니스 예외는 정상적인 4xx 흐름 — ERROR가 아닌 WARN으로 기록 (코드명으로 추적)
    ErrorCode errorCode = e.getErrorCode();
    log.warn("BusinessException [{}] {}", errorCode.name(), errorCode.getMessage());
    return ResponseEntity.status(errorCode.getStatus())
        .body(ApiResponse.fail(errorCode.getMessage()));
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ApiResponse<Void>> handleException(Exception e) {
    log.error("Unhandled exception: {}", e.getMessage(), e);
    return ResponseEntity.status(ErrorCode.INTERNAL_SERVER_ERROR.getStatus())
        .body(ApiResponse.fail(ErrorCode.INTERNAL_SERVER_ERROR.getMessage()));
  }
}
