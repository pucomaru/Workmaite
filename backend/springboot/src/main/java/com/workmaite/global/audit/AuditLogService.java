package com.workmaite.global.audit;

import com.workmaite.domain.audit.entity.AuditLog;
import com.workmaite.domain.audit.repository.AuditLogRepository;
import com.workmaite.global.auth.CurrentUser;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 감사 로그 기록 (P1-6). 항상 REQUIRES_NEW(TransactionTemplate)로 기록해 호출자 트랜잭션과 분리하고, 기록 실패는 본 처리에 영향을 주지
 * 않는다. (프록시 self-call 문제를 피하려고 @Transactional 대신 TransactionTemplate 사용 — afterCommit 콜백처럼 프록시를 거치지
 * 않는 경로에서도 동일하게 동작)
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AuditLogService {

  private final AuditLogRepository auditLogRepository;
  private final PlatformTransactionManager transactionManager;

  /** SecurityContext의 현재 사용자를 actor로 기록 */
  public void record(
      String action, String entityType, Long entityId, Long meetingId, String detailJson) {
    recordAs(CurrentUser.idOrNull(), action, entityType, entityId, meetingId, detailJson);
  }

  /** 인증 컨텍스트가 없는 시점(로그인 등)에 actor를 명시해 기록 */
  public void recordAs(
      Long actorId,
      String action,
      String entityType,
      Long entityId,
      Long meetingId,
      String detailJson) {
    write(actorId, action, entityType, entityId, meetingId, detailJson, clientIp());
  }

  /** 호출자 트랜잭션 커밋 후 기록. actor 자신이 같은 트랜잭션에서 생성되는 경우(signup) FK 충족을 위해 사용한다. */
  public void recordAfterCommit(
      Long actorId,
      String action,
      String entityType,
      Long entityId,
      Long meetingId,
      String detailJson) {
    String ip = clientIp(); // afterCommit 시점엔 요청 컨텍스트가 없을 수 있어 미리 캡처
    if (TransactionSynchronizationManager.isSynchronizationActive()) {
      TransactionSynchronizationManager.registerSynchronization(
          new TransactionSynchronization() {
            @Override
            public void afterCommit() {
              write(actorId, action, entityType, entityId, meetingId, detailJson, ip);
            }
          });
    } else {
      write(actorId, action, entityType, entityId, meetingId, detailJson, ip);
    }
  }

  private void write(
      Long actorId,
      String action,
      String entityType,
      Long entityId,
      Long meetingId,
      String detailJson,
      String ip) {
    try {
      TransactionTemplate tt = new TransactionTemplate(transactionManager);
      tt.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
      tt.executeWithoutResult(
          status ->
              auditLogRepository.save(
                  AuditLog.builder()
                      .actorId(actorId)
                      .action(action)
                      .entityType(entityType)
                      .entityId(entityId)
                      .meetingId(meetingId)
                      .detail(detailJson)
                      .ipAddr(ip)
                      .build()));
    } catch (Exception e) {
      log.warn("감사 로그 기록 실패 (본 처리에는 영향 없음): {}", e.getMessage());
    }
  }

  private String clientIp() {
    try {
      ServletRequestAttributes attrs =
          (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
      if (attrs == null) {
        return null;
      }
      String forwarded = attrs.getRequest().getHeader("X-Forwarded-For");
      if (forwarded != null && !forwarded.isBlank()) {
        return forwarded.split(",")[0].trim();
      }
      return attrs.getRequest().getRemoteAddr();
    } catch (Exception e) {
      return null;
    }
  }
}
