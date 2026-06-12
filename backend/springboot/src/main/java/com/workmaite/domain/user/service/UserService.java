package com.workmaite.domain.user.service;

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
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 사용자 정보 비즈니스 로직
 * - 내 정보 조회: JWT userId로 DB 조회
 * - 회원정보 수정: 이름, 회사, 부서, 직책 변경 (이메일, 비밀번호 변경 불가)
 * - 사용자 검색: 이름/이메일로 검색
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;
    private final MeetingMemberRepository meetingMemberRepository;
    private final MeetingRepository meetingRepository;

    public UserResponse getMe(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        return UserResponse.from(user);
    }

    @Transactional
    @AuditLogged(action = "UPDATE", entityType = "user")
    public UserResponse updateMe(Long userId, UpdateUserRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.update(request.getName(), request.getCompany(), request.getDepartment(), request.getPosition());
        if (request.getPassword() != null && !request.getPassword().isBlank()) {
            user.updatePassword(passwordEncoder.encode(request.getPassword()));
        }
        return UserResponse.from(user);
    }

    /** 이름 또는 이메일로 사용자 검색 — 디렉터리 가시성 스코프 적용 (MT-3) */
    public List<UserResponse> searchUsers(Long callerId, String q) {
        List<User> found = userRepository.findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(q, q);
        return scopeVisible(callerId, found).stream().map(UserResponse::from).toList();
    }

    public List<UserResponse> getUsersByIds(List<Long> ids) {
        return userRepository.findAllById(ids).stream().map(UserResponse::from).toList();
    }

    /** 사용자 목록 조회 (참여 회의체 title 포함) — 디렉터리 가시성 스코프 적용 (MT-3) */
    public List<UserResponse> getAllUsers(Long callerId) {
        List<User> users = scopeVisible(callerId, userRepository.findAll());
        List<MeetingMember> allMembers = meetingMemberRepository.findAll();

        // meetingId → title 맵 (한 번만 조회)
        List<Long> meetingIds = allMembers.stream().map(MeetingMember::getMeetingId).distinct().toList();
        Map<Long, String> titleMap = meetingRepository.findAllById(meetingIds).stream()
                .collect(Collectors.toMap(m -> m.getId(), m -> m.getTitle()));

        // userId → memberList 맵
        Map<Long, List<MeetingMember>> membersByUser = allMembers.stream()
                .collect(Collectors.groupingBy(MeetingMember::getUserId));

        return users.stream().map(user -> {
            List<Map<String, Object>> meetings = membersByUser.getOrDefault(user.getId(), List.of())
                    .stream()
                    .map(mm -> Map.<String, Object>of(
                            "id", mm.getMeetingId(),
                            "title", titleMap.getOrDefault(mm.getMeetingId(), ""),
                            "member_id", mm.getId()))
                    .toList();
            return UserResponse.from(user, meetings);
        }).toList();
    }

    /**
     * 특정 사용자 정보 수정 (MT-1 차단)
     * - SYSTEM_ADMIN, 또는 같은 회사의 COMPANY_ADMIN만 가능
     * - 타인 비밀번호 변경은 어떤 권한으로도 불가 (계정 탈취 벡터 — 본인은 PATCH /users/me 사용)
     */
    @Transactional
    @AuditLogged(action = "UPDATE", entityType = "user")
    public UserResponse updateUser(Long callerId, Long userId, UpdateUserRequest request) {
        User caller = userRepository.findById(callerId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));

        boolean sameCompanyAdmin = caller.getRole() == UserRole.COMPANY_ADMIN
                && caller.getCompany() != null && !caller.getCompany().isBlank()
                && caller.getCompany().trim().equalsIgnoreCase(
                        user.getCompany() == null ? "" : user.getCompany().trim());
        if (caller.getRole() != UserRole.SYSTEM_ADMIN && !sameCompanyAdmin) {
            throw new BusinessException(ErrorCode.ACCESS_DENIED);
        }

        user.update(request.getName(), request.getCompany(), request.getDepartment(), request.getPosition());
        return UserResponse.from(user);
    }

    /**
     * 디렉터리 가시성 (MT-3): 본인 + 내 회사 구성원 + 나와 같은 회의체에 속한 인원만.
     * SYSTEM_ADMIN은 전체.
     */
    private List<User> scopeVisible(Long callerId, List<User> users) {
        User caller = userRepository.findById(callerId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        if (caller.getRole() == UserRole.SYSTEM_ADMIN) {
            return users;
        }

        String company = caller.getCompany() == null ? "" : caller.getCompany().trim();
        List<Long> myMeetingIds = meetingMemberRepository.findByUserId(callerId)
                .stream().map(MeetingMember::getMeetingId).toList();
        Set<Long> sharedUserIds = myMeetingIds.isEmpty() ? Set.of()
                : meetingMemberRepository.findByMeetingIdIn(myMeetingIds)
                        .stream().map(MeetingMember::getUserId).collect(Collectors.toSet());

        return users.stream()
                .filter(u -> u.getId().equals(callerId)
                        || (!company.isBlank() && u.getCompany() != null
                            && company.equalsIgnoreCase(u.getCompany().trim()))
                        || sharedUserIds.contains(u.getId()))
                .toList();
    }
}
