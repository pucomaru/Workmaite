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
    INVALID_CREDENTIALS(HttpStatus.UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다."),
    INVALID_TOKEN(HttpStatus.UNAUTHORIZED, "유효하지 않은 토큰입니다."),
    EXPIRED_TOKEN(HttpStatus.UNAUTHORIZED, "만료된 토큰입니다."),
    UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "인증이 필요합니다."),

    // 회의록
    MINUTES_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회의록입니다."),
    MINUTES_ALREADY_EXISTS(HttpStatus.CONFLICT, "이미 생성된 회의록입니다."),

    // 조직
    ORGANIZATION_MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 구성원입니다."),

    // 안건
    AGENDA_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 안건입니다."),

    // 자료
    REPORT_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 자료입니다."),
    REPORT_ALREADY_APPROVED(HttpStatus.BAD_REQUEST, "이미 승인된 자료는 재제출할 수 없습니다."),
    MINUTES_ALREADY_CONFIRMED(HttpStatus.BAD_REQUEST, "이미 확정된 회의록입니다."),
    // 회의체
    MEETING_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회의체입니다."),
    MEETING_MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "회의체에 존재하지 않는 참여자입니다."),
    MEETING_MEMBER_ALREADY_EXISTS(HttpStatus.CONFLICT, "이미 추가된 참여자입니다."),
    MEETING_ACCESS_DENIED(HttpStatus.FORBIDDEN, "간사 권한이 필요합니다."),

    // Session - 회의 도메인 에러
    // 회의 조회 시 존재하지 않는 경우
    SESSION_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회의입니다."),
    // SCHEDULED 상태가 아닌 회의를 일시정지하려는 경우 (pause는 ONGOING 상태에서만 가능)
    SESSION_NOT_STARTED(HttpStatus.BAD_REQUEST, "시작되지 않은 회의입니다."),
    // 이미 시작(ONGOING)된 회의를 수정하려는 경우
    SESSION_ALREADY_STARTED(HttpStatus.BAD_REQUEST, "이미 시작된 회의입니다."),
    // 이미 종료(ENDED)된 회의를 수정하려는 경우
    SESSION_ALREADY_ENDED(HttpStatus.BAD_REQUEST, "이미 종료된 회의입니다."),
    // 간사(secretary) 권한 없이 회의를 수정/삭제하려는 경우
    UNAUTHORIZED_SESSION_ACCESS(HttpStatus.FORBIDDEN, "회의에 대한 접근 권한이 없습니다.");

    private final HttpStatus status;  // HTTP 상태코드
    private final String message;     // 에러 메시지
}