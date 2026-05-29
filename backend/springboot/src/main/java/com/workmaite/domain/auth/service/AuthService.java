package com.workmaite.domain.auth.service;

import com.workmaite.domain.auth.dto.LoginRequest;
import com.workmaite.domain.auth.dto.LoginResponse;
import com.workmaite.domain.auth.dto.RefreshRequest;
import com.workmaite.domain.auth.dto.SignupRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.auth.JwtTokenProvider;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 인증 비즈니스 로직
 * - 회원가입: 이메일 중복 확인 후 비밀번호 암호화하여 저장
 * - 로그인: 이메일/비밀번호 검증 후 Access Token 발급
 * - 토큰 갱신: Refresh Token 검증 후 새 Access Token 발급
 * - 로그아웃: Redis 도입 전까지 클라이언트 토큰 삭제 방식으로 처리
 */
@Service
@RequiredArgsConstructor
@Transactional
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;

    public void signup(SignupRequest request) {
        // 이메일 중복 확인
        if (userRepository.existsByEmail(request.getEmail())) {
            throw new BusinessException(ErrorCode.DUPLICATE_EMAIL);
        }

        User user = User.builder()
                .email(request.getEmail())
                .name(request.getName())
                .passwordHash(passwordEncoder.encode(request.getPassword()))
                .company(request.getCompany())
                .department(request.getDepartment())
                .position(request.getPosition())
                .build();

        userRepository.save(user);
    }

    public LoginResponse login(LoginRequest request) {
        // 이메일/비밀번호 둘 다 틀려도 동일한 에러 반환 (보안상 구분하지 않음)
        User user = userRepository.findByEmail(request.getEmail())
                .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_CREDENTIALS));

        if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            throw new BusinessException(ErrorCode.INVALID_CREDENTIALS);
        }

        String accessToken = jwtTokenProvider.createAccessToken(user.getId());
        String refreshToken = jwtTokenProvider.createRefreshToken(user.getId());
        return LoginResponse.of(accessToken, refreshToken, UserResponse.from(user));
    }

    // Refresh Token 검증 후 새 Access Token 발급
    @Transactional(readOnly = true)
    public LoginResponse refresh(RefreshRequest request) {
        jwtTokenProvider.validateToken(request.getRefreshToken());
        Long userId = jwtTokenProvider.getUserId(request.getRefreshToken());
        if (!userRepository.existsById(userId)) {
            throw new BusinessException(ErrorCode.USER_NOT_FOUND);
        }
        String newAccessToken = jwtTokenProvider.createAccessToken(userId);
        String newRefreshToken = jwtTokenProvider.createRefreshToken(userId);
        return LoginResponse.of(newAccessToken, newRefreshToken);
    }

    // Redis 도입 후 Access Token 블랙리스트 처리 예정
    public void logout() {
    }
}
