package com.workmaite.domain.auth.controller;

import com.workmaite.domain.auth.dto.LoginRequest;
import com.workmaite.domain.auth.dto.LoginResponse;
import com.workmaite.domain.auth.dto.RefreshRequest;
import com.workmaite.domain.auth.dto.SignupRequest;
import com.workmaite.domain.auth.service.AuthService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 인증 관련 API POST /api/v1/auth/signup - 회원가입 POST /api/v1/auth/login - 로그인 (Access Token 발급) POST
 * /api/v1/auth/refresh - Access Token 갱신 (Refresh Token 필요) POST /api/v1/auth/logout - 로그아웃
 */
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthController {

  private final AuthService authService;

  // 회원가입 - 성공 시 201 반환
  @PostMapping("/signup")
  public ResponseEntity<ApiResponse<Void>> signup(@Valid @RequestBody SignupRequest request) {
    authService.signup(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(ApiResponse.ok(null));
  }

  // 로그인 - 성공 시 Access Token 반환
  @PostMapping("/login")
  public ResponseEntity<ApiResponse<LoginResponse>> login(
      @Valid @RequestBody LoginRequest request) {
    LoginResponse response = authService.login(request);
    return ResponseEntity.ok(ApiResponse.ok(response));
  }

  // Refresh Token으로 새 Access Token 발급
  @PostMapping("/refresh")
  public ResponseEntity<ApiResponse<LoginResponse>> refresh(
      @Valid @RequestBody RefreshRequest request) {
    return ResponseEntity.ok(ApiResponse.ok(authService.refresh(request)));
  }

  // 로그아웃 - 제출된 refresh token 폐기 (없으면 인증 사용자의 전체 폐기)
  @PostMapping("/logout")
  public ResponseEntity<ApiResponse<Void>> logout(
      @RequestBody(required = false) RefreshRequest request, Authentication authentication) {
    Integer userId =
        authentication != null && authentication.getName() != null
            ? Integer.parseInt(authentication.getName())
            : null;
    authService.logout(request != null ? request.getRefreshToken() : null, userId);
    return ResponseEntity.ok(ApiResponse.ok(null));
  }
}
