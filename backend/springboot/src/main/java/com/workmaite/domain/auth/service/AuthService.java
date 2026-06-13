package com.workmaite.domain.auth.service;

import com.workmaite.domain.auth.dto.LoginRequest;
import com.workmaite.domain.auth.dto.LoginResponse;
import com.workmaite.domain.auth.dto.RefreshRequest;
import com.workmaite.domain.auth.dto.SignupRequest;
import com.workmaite.domain.auth.entity.RefreshToken;
import com.workmaite.domain.auth.repository.RefreshTokenRepository;
import com.workmaite.domain.company.service.CompanyService;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.audit.AuditLogService;
import com.workmaite.global.auth.JwtTokenProvider;
import com.workmaite.global.auth.LegacyPbkdf2Verifier;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.HexFormat;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 인증 비즈니스 로직 - 회원가입: 이메일 중복 확인 후 비밀번호 암호화하여 저장 - 로그인: 이메일/비밀번호 검증 후 Access Token 발급 - 토큰 갱신:
 * Refresh Token 검증 후 새 Access Token 발급 - 로그아웃: Redis 도입 전까지 클라이언트 토큰 삭제 방식으로 처리
 */
@Service
@RequiredArgsConstructor
@Transactional
public class AuthService {

  private final UserRepository userRepository;
  private final RefreshTokenRepository refreshTokenRepository;
  private final PasswordEncoder passwordEncoder;
  private final JwtTokenProvider jwtTokenProvider;
  private final AuditLogService auditLogService;
  private final CompanyService companyService;

  public void signup(SignupRequest request) {
    // 이메일 중복 확인
    if (userRepository.existsByEmail(request.getEmail())) {
      throw new BusinessException(ErrorCode.DUPLICATE_EMAIL);
    }

    User user =
        User.builder()
            .email(request.getEmail())
            .name(request.getName())
            .passwordHash(passwordEncoder.encode(request.getPassword()))
            .company(companyService.getOrCreate(request.getCompany()))
            .department(request.getDepartment())
            .position(request.getPosition())
            .build();

    User saved = userRepository.save(user);
    // 같은 트랜잭션에서 생성된 사용자라 FK 충족을 위해 커밋 후 기록
    auditLogService.recordAfterCommit(saved.getId(), "SIGNUP", "auth", saved.getId(), null, null);
  }

  public LoginResponse login(LoginRequest request) {
    // 이메일/비밀번호 둘 다 틀려도 동일한 에러 반환 (보안상 구분하지 않음)
    User user =
        userRepository
            .findByEmail(request.getEmail())
            .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_CREDENTIALS));

    if (LegacyPbkdf2Verifier.isLegacy(user.getPasswordHash())) {
      // 구 FastAPI 가입자: pbkdf2 검증 후 성공 시 BCrypt로 재해시 (점진 마이그레이션)
      if (!LegacyPbkdf2Verifier.matches(request.getPassword(), user.getPasswordHash())) {
        throw new BusinessException(ErrorCode.INVALID_CREDENTIALS);
      }
      user.updatePassword(passwordEncoder.encode(request.getPassword()));
    } else if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
      throw new BusinessException(ErrorCode.INVALID_CREDENTIALS);
    }

    String accessToken = jwtTokenProvider.createAccessToken(user.getId());
    String refreshToken = issueRefreshToken(user.getId());
    auditLogService.recordAs(user.getId(), "LOGIN", "auth", user.getId(), null, null);
    return LoginResponse.of(accessToken, refreshToken, UserResponse.from(user));
  }

  /**
   * Refresh Token 회전: 검증 → DB 대조 → 기존 토큰 폐기 후 새 쌍 발급. 서명은 유효한데 DB에 없는 토큰은 이미 회전된 토큰의 재사용(탈취 신호)이므로
   * 해당 사용자의 모든 refresh token을 폐기한다.
   */
  // noRollbackFor: 재사용 탐지 시 전체 폐기가 예외와 함께 롤백되지 않도록 보장
  @Transactional(noRollbackFor = BusinessException.class)
  public LoginResponse refresh(RefreshRequest request) {
    jwtTokenProvider.validateRefreshToken(request.getRefreshToken());
    Integer userId = jwtTokenProvider.getUserId(request.getRefreshToken());
    if (!userRepository.existsById(userId)) {
      throw new BusinessException(ErrorCode.USER_NOT_FOUND);
    }

    String hash = sha256Hex(request.getRefreshToken());
    RefreshToken stored = refreshTokenRepository.findByTokenHash(hash).orElse(null);
    if (stored == null) {
      // 서명은 유효한데 DB에 없음 = 이미 회전된 토큰의 재사용(탈취 신호) → 전체 폐기
      refreshTokenRepository.deleteByUserId(userId);
      throw new BusinessException(ErrorCode.INVALID_TOKEN);
    }
    if (stored.isExpired()) {
      refreshTokenRepository.delete(stored);
      throw new BusinessException(ErrorCode.EXPIRED_TOKEN);
    }

    refreshTokenRepository.delete(stored);
    String newAccessToken = jwtTokenProvider.createAccessToken(userId);
    String newRefreshToken = issueRefreshToken(userId);
    return LoginResponse.of(newAccessToken, newRefreshToken);
  }

  /** 로그아웃: 제출된 refresh token을 폐기한다. 토큰이 없으면(만료 등) 인증된 사용자의 전체 refresh token을 폐기한다. */
  public void logout(String refreshToken, Integer authenticatedUserId) {
    if (refreshToken != null && !refreshToken.isBlank()) {
      refreshTokenRepository.deleteByTokenHash(sha256Hex(refreshToken));
    } else if (authenticatedUserId != null) {
      refreshTokenRepository.deleteByUserId(authenticatedUserId);
    }
    auditLogService.recordAs(
        authenticatedUserId, "LOGOUT", "auth", authenticatedUserId, null, null);
  }

  private String issueRefreshToken(Integer userId) {
    // 만료된 잔여 토큰 정리 (기기별 다중 로그인은 유지)
    refreshTokenRepository.deleteByUserIdAndExpiresAtBefore(userId, LocalDateTime.now());
    String refreshToken = jwtTokenProvider.createRefreshToken(userId);
    refreshTokenRepository.save(
        RefreshToken.builder()
            .userId(userId)
            .tokenHash(sha256Hex(refreshToken))
            .expiresAt(
                LocalDateTime.ofInstant(
                    jwtTokenProvider.getExpiration(refreshToken).toInstant(),
                    ZoneId.systemDefault()))
            .build());
    return refreshToken;
  }

  private static String sha256Hex(String value) {
    try {
      byte[] digest =
          MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
      return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 미지원 JVM", e);
    }
  }
}
