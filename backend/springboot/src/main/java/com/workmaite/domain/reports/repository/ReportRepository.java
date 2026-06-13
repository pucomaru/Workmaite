package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.Report;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReportRepository extends JpaRepository<Report, Long> {

  List<Report> findAllByMeetingId(Long meetingId);
}
