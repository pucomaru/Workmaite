package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.ReportScore;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ReportScoreRepository extends JpaRepository<ReportScore, Long> {
  Optional<ReportScore> findByReportId(Long reportId);
}
