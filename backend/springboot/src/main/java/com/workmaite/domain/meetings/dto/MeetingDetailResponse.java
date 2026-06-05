package com.workmaite.domain.meetings.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.entity.MeetingType;
import com.workmaite.domain.user.entity.User;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Getter
@Builder
public class MeetingDetailResponse {

    private Long id;
    private String title;
    private String description;
    private String guidelines;

    @JsonProperty("meeting_type")
    private MeetingType type;

    @JsonProperty("start_date")
    private LocalDateTime startDate;

    @JsonProperty("end_date")
    private LocalDateTime endDate;

    private MeetingStatus status;

    @JsonProperty("created_by")
    private Long createdBy;

    @JsonProperty("created_at")
    private LocalDateTime createdAt;

    private List<MeetingMemberResponse> members;

    public static MeetingDetailResponse from(Meeting meeting, List<MeetingMember> members, Map<Long, User> userMap) {
        return MeetingDetailResponse.builder()
                .id(meeting.getId())
                .title(meeting.getTitle())
                .description(meeting.getDescription())
                .guidelines(meeting.getGuidelines())
                .type(meeting.getType())
                .startDate(meeting.getStartDate())
                .endDate(meeting.getEndDate())
                .status(meeting.getStatus())
                .createdBy(meeting.getCreatedBy())
                .createdAt(meeting.getCreatedAt())
                .members(members.stream()
                        .map(mm -> MeetingMemberResponse.from(mm, userMap.get(mm.getUserId())))
                        .toList())
                .build();
    }
}
