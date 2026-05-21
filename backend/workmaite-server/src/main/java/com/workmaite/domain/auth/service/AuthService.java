package com.workmaite.domain.auth.service;

import com.workmaite.domain.auth.dto.LoginRequest;
import com.workmaite.domain.auth.dto.LoginResponse;
import com.workmaite.domain.auth.dto.SignupRequest;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.auth.JwtTokenProvider;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional
public class AuthService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider jwtTokenProvider;

    public void signup(SignupRequest request) {
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
        User user = userRepository.findByEmail(request.getEmail())
                .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_CREDENTIALS));

        if (!passwordEncoder.matches(request.getPassword(), user.getPasswordHash())) {
            throw new BusinessException(ErrorCode.INVALID_CREDENTIALS);
        }

        String accessToken = jwtTokenProvider.createAccessToken(user.getId());
        return LoginResponse.of(accessToken);
    }

    // Redis 도입 전: 클라이언트에서 토큰 삭제로 처리
    public void logout() {
    }
}
