package com.workmaite.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

/**
 * 에러 코드 관리 enum
 * 에러 종류, HTTP 상태코드, 메시지를 한 곳에서 관리
 */
@Getter
@RequiredArgsConstructor
public enum ErrorCode {

    // 공통
    INVALID_INPUT_VALUE(HttpStatus.BAD_REQUEST, "잘못된 입력값입니다."),
    INTERNAL_SERVER_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "서버 오류가 발생했습니다."),

    // 유저
    USER_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 유저입니다."),
    DUPLICATE_EMAIL(HttpStatus.CONFLICT, "이미 사용 중인 이메일입니다."),

    // 인증
    INVALID_TOKEN(HttpStatus.UNAUTHORIZED, "유효하지 않은 토큰입니다."),
    EXPIRED_TOKEN(HttpStatus.UNAUTHORIZED, "만료된 토큰입니다."),
    UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "인증이 필요합니다."),

    // 회의록
    MINUTES_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회의록입니다."),
    MINUTES_ALREADY_EXISTS(HttpStatus.CONFLICT, "이미 생성된 회의록입니다."),
    MINUTES_ALREADY_CONFIRMED(HttpStatus.BAD_REQUEST, "이미 확정된 회의록입니다."),

    // 자료
    REPORT_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 자료입니다."),
    REPORT_ALREADY_APPROVED(HttpStatus.BAD_REQUEST, "이미 승인된 자료는 재제출할 수 없습니다.");

    private final HttpStatus status;  // HTTP 상태코드
    private final String message;     // 에러 메시지
}