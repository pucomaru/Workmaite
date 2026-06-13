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
    if (dbValue == null) return null;
    return switch (dbValue.toLowerCase()) {
      case "scheduled" -> SessionStatus.SCHEDULED;
      case "ongoing" -> SessionStatus.ONGOING;
      case "ended" -> SessionStatus.ENDED;
      case "archived" -> SessionStatus.ARCHIVED;
      default -> throw new IllegalArgumentException("Unknown SessionStatus: " + dbValue);
    };
  }
}
