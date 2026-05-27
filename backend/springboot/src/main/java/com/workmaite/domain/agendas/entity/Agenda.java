package com.workmaite.domain.agendas.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.LocalDateTime;

/**
 * 안건 엔티티 - agendas 테이블 매핑
 */
@Entity
@Table(name = "agendas")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class Agenda {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "meeting_id", nullable = false)
    private Long meetingId;

    @Column(name = "assignee_id")
    private Long assigneeId;

    @Column(length = 255, nullable = false)
    private String title;

    @Column(columnDefinition = "TEXT")
    private String content;

    @Column(name = "order_index", nullable = false)
    private Integer orderIndex;

    @Enumerated(EnumType.STRING)
    @Column(length = 20, nullable = false)
    private AgendaStatus status;

    @CreatedDate
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    public static Agenda create(Long meetingId, String title, String content, Integer orderIndex) {
        Agenda agenda = new Agenda();
        agenda.meetingId = meetingId;
        agenda.title = title;
        agenda.content = content;
        agenda.orderIndex = orderIndex;
        agenda.status = AgendaStatus.ON_HOLD;
        return agenda;
    }

    public void update(String title, String content, Integer orderIndex, AgendaStatus status) {
        if (title != null) this.title = title;
        if (content != null) this.content = content;
        if (orderIndex != null) this.orderIndex = orderIndex;
        if (status != null) this.status = status;
    }

    public void assign(Long assigneeId) {
        this.assigneeId = assigneeId;
    }
}
