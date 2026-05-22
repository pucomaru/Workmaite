package com.workmaite.domain.meetings.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
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
    private String purpose;

    @Column(columnDefinition = "TEXT")
    private String guidelines;

    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private MeetingPriority priority;

    // weekly | monthly | quarterly
    @Enumerated(EnumType.STRING)
    @Column(length = 20)
    private MeetingType type;

    @Column(name = "start_date")
    private LocalDateTime startDate;

    @Column(name = "end_date")
    private LocalDateTime endDate;

    // active | ended
    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private MeetingStatus status;

    // 회의체 생성자 (users.id FK)
    @Column(name = "created_by", nullable = false)
    private Long createdBy;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public static Meeting create(String title, String purpose, String guidelines,
                                 MeetingPriority priority, MeetingType type,
                                 LocalDateTime startDate, LocalDateTime endDate,
                                 Long createdBy) {
        Meeting meeting = new Meeting();
        meeting.title = title;
        meeting.purpose = purpose;
        meeting.guidelines = guidelines;
        meeting.priority = (priority != null) ? priority : MeetingPriority.NORMAL;
        meeting.type = type;
        meeting.startDate = startDate;
        meeting.endDate = endDate;
        meeting.status = MeetingStatus.ACTIVE;
        meeting.createdBy = createdBy;
        return meeting;
    }

    // null 필드는 변경하지 않음 (PATCH 방식)
    public void update(String title, String purpose, String guidelines,
                       MeetingPriority priority, MeetingType type,
                       LocalDateTime startDate, LocalDateTime endDate,
                       MeetingStatus status) {
        if (title != null) this.title = title;
        if (purpose != null) this.purpose = purpose;
        if (guidelines != null) this.guidelines = guidelines;
        if (priority != null) this.priority = priority;
        if (type != null) this.type = type;
        if (startDate != null) this.startDate = startDate;
        if (endDate != null) this.endDate = endDate;
        if (status != null) this.status = status;
    }
}
