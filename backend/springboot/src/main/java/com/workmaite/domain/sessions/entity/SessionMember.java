package com.workmaite.domain.sessions.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "session_members")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class SessionMember {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "session_id", nullable = false)
  private Long sessionId;

  @Column(name = "user_id", nullable = false)
  private Long userId;

  @Column(name = "role")
  private String role;

  public static SessionMember of(Long sessionId, Long userId, String role) {
    SessionMember m = new SessionMember();
    m.sessionId = sessionId;
    m.userId = userId;
    m.role = role != null ? role : "member";
    return m;
  }
}
