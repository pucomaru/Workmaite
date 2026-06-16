package com.workmaite.domain.logs.repository;

import com.workmaite.domain.logs.entity.HitlReview;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface HitlReviewRepository extends JpaRepository<HitlReview, Long> {

  // 회의체 삭제 시: 삭제되는 보고서/아젠다를 참조하는 검토 이력 정리 (no-cascade FK).
  @Modifying
  @Query(
      "DELETE FROM HitlReview h WHERE h.reportId IN (SELECT r.id FROM Report r WHERE r.meetingId = :meetingId)")
  void deleteByMeetingReports(@Param("meetingId") Long meetingId);

  @Modifying
  @Query(
      "DELETE FROM HitlReview h WHERE h.agendaId IN (SELECT a.id FROM Agenda a WHERE a.meetingId = :meetingId)")
  void deleteByMeetingAgendas(@Param("meetingId") Long meetingId);
}
