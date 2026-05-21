package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SessionRepository extends JpaRepository<MeetingSession, Long> {

    List<MeetingSession> findByMeetingId(Long meetingId);

    List<MeetingSession> findByMeetingIdAndStatus(Long meetingId, SessionStatus status);
}
