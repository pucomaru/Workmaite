package com.workmaite.domain.user.controller;

import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.service.UserService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 사용자 정보 관련 API
 * GET  /api/v1/users/me      - 내 정보 조회
 * PATCH /api/v1/users/me     - 회원정보 수정
 * GET  /api/v1/users/search  - 사용자 검색 (?q=)
 * GET  /api/v1/users         - 전체 사용자 목록
 * PATCH /api/v1/users/{id}   - 특정 사용자 정보 수정 (관리자)
 */
@RestController
@RequestMapping("/api/v1/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    // 내 정보 조회 - JWT에서 추출한 userId로 조회
    @GetMapping("/me")
    public ResponseEntity<ApiResponse<UserResponse>> getMe(Authentication authentication) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(userService.getMe(userId)));
    }

    // 회원정보 수정 - 조직, 부서, 직위, 비밀번호 변경 가능
    @PatchMapping("/me")
    public ResponseEntity<ApiResponse<UserResponse>> updateMe(
            Authentication authentication,
            @Valid @RequestBody UpdateUserRequest request) {
        Long userId = Long.parseLong(authentication.getName());
        return ResponseEntity.ok(ApiResponse.ok(userService.updateMe(userId, request)));
    }

    // 사용자 검색 - 이름 또는 이메일로 검색
    @GetMapping("/search")
    public ResponseEntity<ApiResponse<List<UserResponse>>> searchUsers(@RequestParam String q) {
        return ResponseEntity.ok(ApiResponse.ok(userService.searchUsers(q)));
    }

    // 전체 사용자 목록
    @GetMapping
    public ResponseEntity<ApiResponse<List<UserResponse>>> getAllUsers() {
        return ResponseEntity.ok(ApiResponse.ok(userService.getAllUsers()));
    }

    // 특정 사용자 정보 수정 (관리자 기능)
    @PatchMapping("/{userId}")
    public ResponseEntity<ApiResponse<UserResponse>> updateUser(
            @PathVariable Long userId,
            @RequestBody UpdateUserRequest request) {
        return ResponseEntity.ok(ApiResponse.ok(userService.updateUser(userId, request)));
    }
}
