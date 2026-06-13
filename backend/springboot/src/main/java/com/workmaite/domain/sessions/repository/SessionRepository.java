package com.workmaite.domain.sessions.repository;

import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SessionRepository extends JpaRepository<MeetingSession, Integer> {

  List<MeetingSession> findByMeetingId(Integer meetingId);

  List<MeetingSession> findByMeetingIdAndStatus(Integer meetingId, SessionStatus status);

  @Query(
      "SELECT s FROM MeetingSession s WHERE s.meetingId IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId) AND s.status = :status ORDER BY s.scheduledAt ASC")
  List<MeetingSession> findUpcomingByUserId(
      @Param("userId") Integer userId, @Param("status") SessionStatus status);

  @Query(
      "SELECT s FROM MeetingSession s WHERE s.meetingId IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId) AND s.scheduledAt BETWEEN :start AND :end ORDER BY s.scheduledAt ASC")
  List<MeetingSession> findByUserIdAndScheduledAtBetween(
      @Param("userId") Integer userId,
      @Param("start") LocalDateTime start,
      @Param("end") LocalDateTime end);
}
