package com.workmaite.domain.sessions.entity;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class SessionStatusConverter implements AttributeConverter<SessionStatus, String> {

  @Override
  public String convertToDatabaseColumn(SessionStatus status) {
    if (status == null) return null;
    return status.name().toLowerCase();
  }

  @Override
  public SessionStatus convertToEntityAttribute(String dbValue) {
    // 알 수 없거나 NULL인 status 한 건이 회의체 전체 세션 목록 조회를 500으로 깨뜨리지 않도록
    // 예외를 던지지 않고 안전 기본값(SCHEDULED)으로 폴백한다.
    if (dbValue == null) return SessionStatus.SCHEDULED;
    return switch (dbValue.trim().toLowerCase()) {
      case "scheduled" -> SessionStatus.SCHEDULED;
      case "ongoing" -> SessionStatus.ONGOING;
      case "ended" -> SessionStatus.ENDED;
      case "archived" -> SessionStatus.ARCHIVED;
      default -> SessionStatus.SCHEDULED;
    };
  }
}
