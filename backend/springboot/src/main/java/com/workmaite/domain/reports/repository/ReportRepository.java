package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.Report;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ReportRepository extends JpaRepository<Report, Long> {

    List<Report> findAllByMeetingId(Long meetingId);

    List<Report> findAllBySessionId(Long sessionId);
}
