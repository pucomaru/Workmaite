package com.workmaite.global.audit;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 감사 로그 대상 메서드 표시 (P1-6). 메서드가 정상 완료되면 AuditLogAspect가 audit_logs에 기록한다. entityId/meetingId는 파라미터
 * 이름(xxxId/meetingId)에서 자동 추출한다.
 */
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface AuditLogged {

  /** CREATE / UPDATE / DELETE / APPROVE / LOGIN ... */
  String action();

  /** meeting / report / agenda / minutes / member / session ... */
  String entityType();
}
