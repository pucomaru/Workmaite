package com.workmaite.domain.user.service;

import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.user.dto.UpdateUserRequest;
import com.workmaite.domain.user.dto.UserResponse;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
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
    public UserResponse updateMe(Long userId, UpdateUserRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.update(request.getName(), request.getCompany(), request.getDepartment(), request.getPosition());
        if (request.getPassword() != null && !request.getPassword().isBlank()) {
            user.updatePassword(passwordEncoder.encode(request.getPassword()));
        }
        return UserResponse.from(user);
    }

    /** 이름 또는 이메일로 사용자 검색 */
    public List<UserResponse> searchUsers(String q) {
        return userRepository.findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(q, q)
                .stream().map(UserResponse::from).toList();
    }

    public List<UserResponse> getUsersByIds(List<Long> ids) {
        return userRepository.findAllById(ids).stream().map(UserResponse::from).toList();
    }

    /** 전체 사용자 목록 조회 (참여 회의체 title 포함) */
    public List<UserResponse> getAllUsers() {
        List<User> users = userRepository.findAll();
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

    /** 특정 사용자 정보 수정 (관리자 기능) */
    @Transactional
    public UserResponse updateUser(Long userId, UpdateUserRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
        user.update(request.getName(), request.getCompany(), request.getDepartment(), request.getPosition());
        if (request.getPassword() != null && !request.getPassword().isBlank()) {
            user.updatePassword(passwordEncoder.encode(request.getPassword()));
        }
        return UserResponse.from(user);
    }
}
