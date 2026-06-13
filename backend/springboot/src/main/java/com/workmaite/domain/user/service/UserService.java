package com.workmaite.domain.user.service;

import com.workmaite.domain.company.service.CompanyService;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.entity.UserRole;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 사용자 정보 비즈니스 로직 - 내 정보 조회: JWT userId로 DB 조회 - 회원정보 수정: 이름, 회사, 부서, 직책 변경 (이메일, 비밀번호 변경 불가) - 사용자
 * 검색: 이름/이메일로 검색
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {

  private final UserRepository userRepository;
  private final PasswordEncoder passwordEncoder;
  private final MeetingMemberRepository meetingMemberRepository;
  private final MeetingRepository meetingRepository;
  private final CompanyService companyService;

  public UserResponse getMe(Long userId) {
    User user =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    return UserResponse.from(user);
  }

  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "user")
  public UserResponse updateMe(Long userId, UpdateUserRequest request) {
    User user =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    user.update(request.getName(), request.getDepartment(), request.getPosition());
    user.assignCompany(companyService.getOrCreate(request.getCompany()));
    if (request.getPassword() != null && !request.getPassword().isBlank()) {
      user.updatePassword(passwordEncoder.encode(request.getPassword()));
    }
    return UserResponse.from(user);
  }

  /** 이름 또는 이메일로 사용자 검색 — 디렉터리 가시성 스코프 적용 (MT-3) */
  public List<UserResponse> searchUsers(Long callerId, String q, Integer page, Integer size) {
    List<User> found =
        userRepository.findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(q, q);
    return paginate(scopeVisible(callerId, found), page, size).stream()
        .map(UserResponse::from)
        .toList();
  }

  // 스코프(메모리 필터) 결과를 페이지로 자른다 (P8-4). size 미지정 시 전체(호환).
  private static <T> List<T> paginate(List<T> list, Integer page, Integer size) {
    if (size == null) return list;
    int s = Math.min(Math.max(size, 1), 200);
    int from = Math.min(Math.max(page == null ? 0 : page, 0) * s, list.size());
    return list.subList(from, Math.min(from + s, list.size()));
  }

  public List<UserResponse> getUsersByIds(List<Long> ids) {
    return userRepository.findAllById(ids).stream().map(UserResponse::from).toList();
  }

  /** 사용자 목록 조회 (참여 회의체 title 포함) — 디렉터리 가시성 스코프 적용 (MT-3) */
  public List<UserResponse> getAllUsers(Long callerId, Integer page, Integer size) {
    List<User> users = paginate(scopeVisible(callerId, userRepository.findAll()), page, size);
    List<MeetingMember> allMembers = meetingMemberRepository.findAll();

    // meetingId → title 맵 (한 번만 조회)
    List<Long> meetingIds =
        allMembers.stream().map(MeetingMember::getMeetingId).distinct().toList();
    Map<Long, String> titleMap =
        meetingRepository.findAllById(meetingIds).stream()
            .collect(Collectors.toMap(m -> m.getId(), m -> m.getTitle()));

    // userId → memberList 맵
    Map<Long, List<MeetingMember>> membersByUser =
        allMembers.stream().collect(Collectors.groupingBy(MeetingMember::getUserId));

    return users.stream()
        .map(
            user -> {
              List<Map<String, Object>> meetings =
                  membersByUser.getOrDefault(user.getId(), List.of()).stream()
                      .map(
                          mm ->
                              Map.<String, Object>of(
                                  "id", mm.getMeetingId(),
                                  "title", titleMap.getOrDefault(mm.getMeetingId(), ""),
                                  "member_id", mm.getId()))
                      .toList();
              return UserResponse.from(user, meetings);
            })
        .toList();
  }

  /**
   * 특정 사용자 정보 수정 (MT-1 차단) - SYSTEM_ADMIN, 또는 같은 회사의 COMPANY_ADMIN만 가능 - 타인 비밀번호 변경은 어떤 권한으로도 불가
   * (계정 탈취 벡터 — 본인은 PATCH /users/me 사용)
   */
  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "user")
  public UserResponse updateUser(Long callerId, Long userId, UpdateUserRequest request) {
    User caller =
        userRepository
            .findById(callerId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    User user =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

    boolean sameCompanyAdmin =
        caller.getCompanyRole() == UserRole.COMPANY_ADMIN
            && caller.getCompanyId() != null
            && caller.getCompanyId().equals(user.getCompanyId());
    if (caller.getCompanyRole() != UserRole.SYSTEM_ADMIN && !sameCompanyAdmin) {
      throw new BusinessException(ErrorCode.ACCESS_DENIED);
    }

    user.update(request.getName(), request.getDepartment(), request.getPosition());
    user.assignCompany(companyService.getOrCreate(request.getCompany()));
    return UserResponse.from(user);
  }

  /** 조직 권한 변경 (P1-7② — COMPANY_ADMIN 부여/회수). SYSTEM_ADMIN만 가능. */
  @Transactional
  public UserResponse updateCompanyRole(Long callerId, Long userId, String companyRole) {
    User caller =
        userRepository
            .findById(callerId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    if (caller.getCompanyRole() != UserRole.SYSTEM_ADMIN) {
      throw new BusinessException(ErrorCode.ACCESS_DENIED);
    }
    User user =
        userRepository
            .findById(userId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    UserRole newRole;
    try {
      newRole = UserRole.valueOf(companyRole);
    } catch (Exception e) {
      throw new BusinessException(ErrorCode.INVALID_INPUT_VALUE);
    }
    user.changeCompanyRole(newRole);
    return UserResponse.from(user);
  }

  /**
   * 구성원 일괄 생성 (P1-7② 개정 — 임시 비밀번호 방식). SYSTEM_ADMIN 또는 COMPANY_ADMIN만. 임시 비밀번호는 행마다 필수이며
   * must_change_password=true로 생성되어 최초 로그인 시 변경이 강제된다.
   */
  @Transactional
  public List<Map<String, Object>> createMembers(Long callerId, List<Map<String, String>> rows) {
    User caller =
        userRepository
            .findById(callerId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    if (caller.getCompanyRole() != UserRole.SYSTEM_ADMIN && caller.getCompanyRole() != UserRole.COMPANY_ADMIN) {
      throw new BusinessException(ErrorCode.ACCESS_DENIED);
    }
    List<Map<String, Object>> results = new java.util.ArrayList<>();
    for (Map<String, String> row : rows) {
      String email = row.getOrDefault("email", "").trim();
      String name = row.getOrDefault("name", "").trim();
      String password = row.getOrDefault("password", "");
      Map<String, Object> r = new java.util.HashMap<>();
      r.put("email", email);
      r.put("name", name);
      if (email.isBlank() || name.isBlank()) {
        r.put("ok", false);
        r.put("reason", "이름/이메일 누락");
      } else if (password.length() < 8) {
        r.put("ok", false);
        r.put("reason", "임시 비밀번호(8자 이상) 필수");
      } else if (userRepository.existsByEmail(email)) {
        r.put("ok", false);
        r.put("reason", "이미 가입된 이메일");
      } else {
        userRepository.save(
            User.builder()
                .email(email)
                .name(name)
                .passwordHash(passwordEncoder.encode(password))
                .company(caller.getCompany()) // 관리자와 같은 회사 (정규화 엔티티)
                .department(blankToNull(row.get("department")))
                .position(blankToNull(row.get("position")))
                .mustChangePassword(true) // 최초 로그인 시 변경 강제
                .build());
        r.put("ok", true);
      }
      results.add(r);
    }
    return results;
  }

  private static String blankToNull(String s) {
    return s == null || s.isBlank() ? null : s.trim();
  }

  /** 디렉터리 가시성 (MT-3): 본인 + 내 회사 구성원 + 나와 같은 회의체에 속한 인원만. SYSTEM_ADMIN은 전체. */
  private List<User> scopeVisible(Long callerId, List<User> users) {
    User caller =
        userRepository
            .findById(callerId)
            .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
    // 탈퇴(소프트 삭제) 계정은 디렉터리 목록·검색에서 제외 (MT-6).
    // by-ids 조회(getUsersByIds)는 작성자·참석자 이름 해석용이라 비활성도 포함한다.
    users = users.stream().filter(User::isActive).toList();
    if (caller.getCompanyRole() == UserRole.SYSTEM_ADMIN) {
      return users;
    }

    Long companyId = caller.getCompanyId();
    List<Long> myMeetingIds =
        meetingMemberRepository.findByUserId(callerId).stream()
            .map(MeetingMember::getMeetingId)
            .toList();
    Set<Long> sharedUserIds =
        myMeetingIds.isEmpty()
            ? Set.of()
            : meetingMemberRepository.findByMeetingIdIn(myMeetingIds).stream()
                .map(MeetingMember::getUserId)
                .collect(Collectors.toSet());

    return users.stream()
        .filter(
            u ->
                u.getId().equals(callerId)
                    || (companyId != null && companyId.equals(u.getCompanyId()))
                    || sharedUserIds.contains(u.getId()))
        .toList();
  }
}
