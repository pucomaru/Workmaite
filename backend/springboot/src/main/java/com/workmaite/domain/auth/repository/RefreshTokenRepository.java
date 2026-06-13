package com.workmaite.domain.auth.repository;

import com.workmaite.domain.auth.entity.RefreshToken;
import java.time.LocalDateTime;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, Integer> {

  Optional<RefreshToken> findByTokenHash(String tokenHash);

  void deleteByTokenHash(String tokenHash);

  void deleteByUserId(Integer userId);

  void deleteByUserIdAndExpiresAtBefore(Integer userId, LocalDateTime now);
}
