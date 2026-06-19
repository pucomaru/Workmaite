package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.Report;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReportRepository extends JpaRepository<Report, Long> {

  List<Report> findAllByMeetingId(Long meetingId);

  // 회의체 삭제 시: 해당 회의체 보고서 일괄 삭제 (report_agendas는 ON DELETE CASCADE).
  @Modifying
  @Query("DELETE FROM Report r WHERE r.meetingId = :meetingId")
  void deleteByMeetingId(@Param("meetingId") Long meetingId);
}
