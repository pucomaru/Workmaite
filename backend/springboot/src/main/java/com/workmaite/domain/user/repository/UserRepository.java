package com.workmaite.domain.user.repository;

import com.workmaite.domain.user.entity.User;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

  Optional<User> findByEmail(String email);

  // 활성 계정만 — 로그인 시 탈퇴(소프트 삭제) 계정 차단 (MT-6).
  // 명시적 JPQL 사용: boolean 필드 isActive 의 파생 쿼리 파싱 모호성 회피
  @Query("SELECT u FROM User u WHERE u.email = :email AND u.isActive = true")
  Optional<User> findActiveByEmail(@Param("email") String email);

  boolean existsByEmail(String email);

  List<User> findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(String name, String email);
}
