package com.workmaite.domain.user.controller;

import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.service.UserService;
import com.workmaite.global.common.ApiResponse;
import jakarta.validation.Valid;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 사용자 정보 관련 API GET /api/v1/users/me - 내 정보 조회 PATCH /api/v1/users/me - 회원정보 수정 GET
 * /api/v1/users/search - 사용자 검색 (?q=) GET /api/v1/users - 전체 사용자 목록 PATCH /api/v1/users/{id} - 특정
 * 사용자 정보 수정 (관리자)
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
      Authentication authentication, @Valid @RequestBody UpdateUserRequest request) {
    Long userId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.updateMe(userId, request)));
  }

  // 사용자 검색 - 이름 또는 이메일로 검색 (내 회사 + 공유 회의체 스코프, MT-3)
  @GetMapping("/search")
  public ResponseEntity<ApiResponse<List<UserResponse>>> searchUsers(
      Authentication authentication,
      @RequestParam String q,
      @RequestParam(required = false) Integer page,
      @RequestParam(required = false) Integer size) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.searchUsers(callerId, q, page, size)));
  }

  // ID 목록으로 사용자 조회 - 편집 모달 참석자 미리채우기용 (가시성 범위로 제한)
  @GetMapping("/by-ids")
  public ResponseEntity<ApiResponse<List<UserResponse>>> getUsersByIds(
      Authentication authentication, @RequestParam String ids) {
    Long callerId = Long.parseLong(authentication.getName());
    List<Long> idList =
        Arrays.stream(ids.split(","))
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(Long::parseLong)
            .collect(Collectors.toList());
    return ResponseEntity.ok(ApiResponse.ok(userService.getUsersByIds(callerId, idList)));
  }

  // 사용자 목록 (내 회사 + 공유 회의체 스코프, MT-3)
  @GetMapping
  public ResponseEntity<ApiResponse<List<UserResponse>>> getAllUsers(
      Authentication authentication,
      @RequestParam(required = false) Integer page,
      @RequestParam(required = false) Integer size) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.getAllUsers(callerId, page, size)));
  }

  // 조직 권한 변경 (COMPANY_ADMIN 부여/회수) — SYSTEM_ADMIN만. 본문 키는 기존대로 role(신규 company_role도 허용)
  @PatchMapping("/{userId}/role")
  public ResponseEntity<ApiResponse<UserResponse>> updateCompanyRole(
      Authentication authentication,
      @PathVariable Long userId,
      @RequestBody Map<String, String> body) {
    Long callerId = Long.parseLong(authentication.getName());
    String companyRole = body.getOrDefault("role", body.getOrDefault("company_role", ""));
    return ResponseEntity.ok(
        ApiResponse.ok(userService.updateCompanyRole(callerId, userId, companyRole)));
  }

  // 구성원 일괄 생성 (임시 비밀번호 + 변경 강제) — SYSTEM/COMPANY_ADMIN만
  @PostMapping("/bulk")
  public ResponseEntity<ApiResponse<List<Map<String, Object>>>> createMembers(
      Authentication authentication, @RequestBody List<Map<String, String>> rows) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.createMembers(callerId, rows)));
  }

  // 특정 사용자 정보 수정 — SYSTEM_ADMIN 또는 같은 회사 COMPANY_ADMIN만, 비밀번호 변경 불가 (MT-1)
  @PatchMapping("/{userId}")
  public ResponseEntity<ApiResponse<UserResponse>> updateUser(
      Authentication authentication,
      @PathVariable Long userId,
      @RequestBody UpdateUserRequest request) {
    Long callerId = Long.parseLong(authentication.getName());
    return ResponseEntity.ok(ApiResponse.ok(userService.updateUser(callerId, userId, request)));
  }
}
