package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.ReportScore;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReportScoreRepository extends JpaRepository<ReportScore, Long> {
  Optional<ReportScore> findByReportId(Long reportId);

  // 회의체 삭제 시: 해당 회의체 보고서들의 점수 정리.
  @Modifying
  @Query(
      "DELETE FROM ReportScore s WHERE s.reportId IN (SELECT r.id FROM Report r WHERE r.meetingId = :meetingId)")
  void deleteByMeetingId(@Param("meetingId") Long meetingId);
}
