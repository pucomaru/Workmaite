package com.workmaite.domain.meetings.entity;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class MeetingTypeConverter implements AttributeConverter<MeetingType, String> {

    @Override
    public String convertToDatabaseColumn(MeetingType type) {
        if (type == null) return null;
        return type.name();
    }

    @Override
    public MeetingType convertToEntityAttribute(String dbValue) {
        if (dbValue == null || dbValue.isBlank()) return null;
        return switch (dbValue.trim().toLowerCase()) {
            case "weekly" -> MeetingType.Weekly;
            case "monthly" -> MeetingType.Monthly;
            case "quarterly" -> MeetingType.Quarterly;
            default -> throw new IllegalArgumentException("Unknown MeetingType: " + dbValue);
        };
    }
}
