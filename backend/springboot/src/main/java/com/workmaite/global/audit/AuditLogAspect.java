package com.workmaite.global.audit;

import lombok.RequiredArgsConstructor;
import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.springframework.stereotype.Component;

/**
 * {@link AuditLogged} 메서드가 정상 완료되면 audit_logs에 기록한다 (P1-6).
 * - entityId: "meetingId" 외의 첫 번째 `*Id` Long 파라미터
 * - meetingId: "meetingId" 이름의 Long 파라미터
 */
@Aspect
@Component
@RequiredArgsConstructor
public class AuditLogAspect {

    private final AuditLogService auditLogService;

    @AfterReturning("@annotation(auditLogged)")
    public void afterReturning(JoinPoint joinPoint, AuditLogged auditLogged) {
        Long entityId = null;
        Long meetingId = null;

        MethodSignature signature = (MethodSignature) joinPoint.getSignature();
        String[] names = signature.getParameterNames();
        Object[] args = joinPoint.getArgs();
        if (names != null) {
            for (int i = 0; i < names.length; i++) {
                if (!(args[i] instanceof Long value)) {
                    continue;
                }
                if ("meetingId".equals(names[i])) {
                    meetingId = value;
                } else if (entityId == null && names[i].endsWith("Id") && !"requesterId".equals(names[i])
                        && !"userId".equals(names[i])) {
                    entityId = value;
                }
            }
        }

        auditLogService.record(auditLogged.action(), auditLogged.entityType(), entityId, meetingId, null);
    }
}
