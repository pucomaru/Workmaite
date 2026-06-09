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

    public static SessionMember of(Long sessionId, Long userId) {
        SessionMember m = new SessionMember();
        m.sessionId = sessionId;
        m.userId = userId;
        return m;
    }
}
