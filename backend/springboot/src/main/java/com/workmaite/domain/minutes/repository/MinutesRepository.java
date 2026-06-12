package com.workmaite.domain.minutes.repository;

import com.workmaite.domain.minutes.entity.Minutes;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

public interface MinutesRepository extends JpaRepository<Minutes, Long> {

    Optional<Minutes> findBySessionId(Long sessionId);
    boolean existsBySessionId(Long sessionId);
    void deleteBySessionId(Long sessionId);
}
