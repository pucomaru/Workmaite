package com.workmaite.domain.meetings.entity;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class MeetingMemberRoleConverter implements AttributeConverter<MeetingMemberRole, String> {

    @Override
    public String convertToDatabaseColumn(MeetingMemberRole role) {
        if (role == null) return null;
        return switch (role) {
            case SECRETARY -> "admin";
            case MEMBER -> "presenter";
        };
    }

    @Override
    public MeetingMemberRole convertToEntityAttribute(String dbValue) {
        if (dbValue == null) return null;
        return switch (dbValue.toLowerCase()) {
            case "admin" -> MeetingMemberRole.SECRETARY;
            case "presenter" -> MeetingMemberRole.MEMBER;
            default -> throw new IllegalArgumentException("Unknown MeetingMemberRole: " + dbValue);
        };
    }
}
