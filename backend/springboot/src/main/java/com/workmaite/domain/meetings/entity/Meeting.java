package com.workmaite.domain.meetings.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

@Entity
@Table(name = "meetings")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class Meeting {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(length = 255, nullable = false)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String description;

    @Column(columnDefinition = "TEXT")
    private String guidelines;

    // weekly | monthly | quarterly
    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private MeetingType type;

    @Column(name = "start_date")
    private LocalDateTime startDate;

    @Column(name = "end_date")
    private LocalDateTime endDate;

    // active | ended
    @Convert(converter = MeetingStatusConverter.class)
    @Column(length = 20, nullable = false)
    private MeetingStatus status;

    @Column(name = "created_by", nullable = false)
    private Long createdBy;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public static Meeting create(String title, String description, String guidelines,
                                 MeetingType type,
                                 LocalDateTime startDate, LocalDateTime endDate,
                                 Long createdBy) {
        Meeting meeting = new Meeting();
        meeting.title = title;
        meeting.description = description;
        meeting.guidelines = guidelines;
        meeting.type = type;
        meeting.startDate = startDate;
        meeting.endDate = endDate;
        meeting.status = MeetingStatus.ACTIVE;
        meeting.createdBy = createdBy;
        return meeting;
    }

    public void update(String title, String description, String guidelines,
                       MeetingType type,
                       LocalDateTime startDate, LocalDateTime endDate,
                       MeetingStatus status) {
        if (title != null) this.title = title;
        if (description != null) this.description = description;
        if (guidelines != null) this.guidelines = guidelines;
        if (type != null) this.type = type;
        if (startDate != null) this.startDate = startDate;
        if (endDate != null) this.endDate = endDate;
        if (status != null) this.status = status;
    }
}
