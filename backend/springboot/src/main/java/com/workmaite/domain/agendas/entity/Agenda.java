package com.workmaite.domain.agendas.entity;

import jakarta.persistence.*;
import java.time.LocalDateTime;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@Table(name = "agenda")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
@EntityListeners(AuditingEntityListener.class)
public class Agenda {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "meeting_id", nullable = false)
  private Long meetingId;

  @Column(name = "session_id")
  private Long sessionId;

  @Column(length = 255, nullable = false)
  private String title;

  @Enumerated(EnumType.STRING)
  @Column(length = 20, nullable = false)
  private AgendaStatus status;

  @Column(name = "assignee_id")
  private Long assigneeId;

  @JdbcTypeCode(SqlTypes.JSON)
  @Column(columnDefinition = "jsonb")
  private String department;

  @Column(name = "due_date")
  private LocalDateTime dueDate;

  @Column(length = 20)
  private String priority = "medium";

  @Column(name = "ai_evidence", columnDefinition = "TEXT")
  private String aiEvidence;

  @CreatedDate
  @Column(name = "created_at", nullable = false, updatable = false)
  private LocalDateTime createdAt;

  public static Agenda create(Long meetingId, Long sessionId, String title, String priority) {
    Agenda agenda = new Agenda();
    agenda.meetingId = meetingId;
    agenda.sessionId = sessionId;
    agenda.title = title;
    agenda.status = AgendaStatus.ON_HOLD;
    agenda.priority = priority != null ? priority : "medium";
    return agenda;
  }

  public void update(
      String title,
      AgendaStatus status,
      String department,
      LocalDateTime dueDate,
      String priority) {
    if (title != null) this.title = title;
    if (status != null) this.status = status;
    if (department != null) this.department = department;
    if (dueDate != null) this.dueDate = dueDate;
    if (priority != null) this.priority = priority;
  }

  public void assign(Long assigneeId) {
    this.assigneeId = assigneeId;
  }

  public void setAiEvidence(String aiEvidence) {
    this.aiEvidence = aiEvidence;
  }
}
