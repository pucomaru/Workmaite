package com.workmaite.domain.reports.repository;

import com.workmaite.domain.reports.entity.ReportScore;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface ReportScoreRepository extends JpaRepository<ReportScore, Long> {
    Optional<ReportScore> findByReportId(Long reportId);
}
