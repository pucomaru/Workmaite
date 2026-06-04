package com.workmaite.domain.meetings.entity;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class MeetingStatusConverter implements AttributeConverter<MeetingStatus, String> {

    @Override
    public String convertToDatabaseColumn(MeetingStatus status) {
        if (status == null) return null;
        return status.name().toLowerCase();
    }

    @Override
    public MeetingStatus convertToEntityAttribute(String dbValue) {
        if (dbValue == null) return null;
        return switch (dbValue.toLowerCase()) {
            case "active" -> MeetingStatus.ACTIVE;
            case "ended" -> MeetingStatus.ENDED;
            default -> throw new IllegalArgumentException("Unknown MeetingStatus: " + dbValue);
        };
    }
}
