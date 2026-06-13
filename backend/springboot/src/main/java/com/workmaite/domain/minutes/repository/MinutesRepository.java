package com.workmaite.domain.minutes.repository;

import com.workmaite.domain.minutes.entity.Minutes;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MinutesRepository extends JpaRepository<Minutes, Integer> {

  Optional<Minutes> findBySessionId(Integer sessionId);

  boolean existsBySessionId(Integer sessionId);

  void deleteBySessionId(Integer sessionId);
}
