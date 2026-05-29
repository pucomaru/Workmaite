package com.workmaite.domain.meetings.service;

import com.workmaite.domain.meetings.dto.*;
import com.workmaite.domain.meetings.entity.*;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 회의체 비즈니스 로직
 * - 생성: 생성자를 간사로 자동 등록
 * - 내 진행중인 회의체: 로그인 유저가 속한 active 회의체 + 담당 간사명 조합
 * - 목록/검색: keyword가 있으면 제목·목적 필드에서 검색, 없으면 전체 반환
 * - 상세 조회: 참여자 목록을 함께 반환
 * - 수정·참여자 관리: 요청자가 해당 회의체의 secretary인지 확인 후 처리
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MeetingService {

    private final MeetingRepository meetingRepository;
    private final MeetingMemberRepository meetingMemberRepository;
    private final UserRepository userRepository;
    private final NeoSyncService neoSyncService;

    @Transactional
    public MeetingResponse createMeeting(Long requesterId, MeetingCreateRequest request) {
        Meeting meeting = Meeting.create(
                request.getTitle(), request.getPurpose(), request.getGuidelines(),
                request.getPriority(), request.getType(),
                request.getStartDateTime(), request.getEndDateTime(),
                requesterId
        );
        Meeting saved = meetingRepository.save(meeting);
        MeetingMember secretary = MeetingMember.create(saved.getId(), requesterId, MeetingMemberRole.SECRETARY);
        meetingMemberRepository.save(secretary);
        neoSyncService.syncMeeting(saved.getId());
        neoSyncService.syncMember(saved.getId(), requesterId);
        return MeetingResponse.from(saved);
    }

    public List<MeetingResponse> getMeetings(Long userId, String keyword) {
        List<Meeting> all = (keyword != null && !keyword.isBlank())
                ? meetingRepository.findByTitleContainingIgnoreCaseOrPurposeContainingIgnoreCase(keyword, keyword)
                : meetingRepository.findByUserId(userId);

        // Build role map for this user
        List<Long> meetingIds = all.stream().map(Meeting::getId).toList();
        Map<Long, String> roleMap = meetingMemberRepository.findByUserId(userId).stream()
                .filter(mm -> meetingIds.contains(mm.getMeetingId()))
                .collect(Collectors.toMap(
                        MeetingMember::getMeetingId,
                        mm -> mm.getRole() == MeetingMemberRole.SECRETARY ? "admin" : "presenter",
                        (a, b) -> a));

        return all.stream()
                .filter(m -> roleMap.containsKey(m.getId()))
                .map(m -> MeetingResponse.from(m, roleMap.get(m.getId())))
                .toList();
    }

    // secretary가 여러 명일 경우 첫 번째만 담당자로 사용
    public List<ActiveMeetingResponse> getMyActiveMeetings(Long userId) {
        List<Meeting> meetings = meetingRepository.findByUserIdAndStatus(userId, MeetingStatus.ACTIVE);
        if (meetings.isEmpty()) return List.of();

        List<Long> meetingIds = meetings.stream().map(Meeting::getId).toList();
        List<MeetingMember> secretaries = meetingMemberRepository
                .findByMeetingIdInAndRole(meetingIds, MeetingMemberRole.SECRETARY);

        List<Long> secretaryUserIds = secretaries.stream().map(MeetingMember::getUserId).distinct().toList();
        Map<Long, String> userNameMap = userRepository.findAllById(secretaryUserIds)
                .stream().collect(Collectors.toMap(User::getId, User::getName));

        Map<Long, String> secretaryNameMap = secretaries.stream()
                .collect(Collectors.toMap(
                        MeetingMember::getMeetingId,
                        m -> userNameMap.getOrDefault(m.getUserId(), ""),
                        (first, second) -> first
                ));

        return meetings.stream()
                .map(m -> ActiveMeetingResponse.from(m, secretaryNameMap.get(m.getId())))
                .toList();
    }

    public MeetingDetailResponse getMeeting(Long meetingId) {
        Meeting meeting = findMeetingOrThrow(meetingId);
        List<MeetingMember> members = meetingMemberRepository.findByMeetingId(meetingId);
        Map<Long, User> userMap = buildUserMap(members);
        return MeetingDetailResponse.from(meeting, members, userMap);
    }

    public List<MeetingMemberResponse> findMembers(Long meetingId) {
        List<MeetingMember> members = meetingMemberRepository.findByMeetingId(meetingId);
        Map<Long, User> userMap = buildUserMap(members);
        return members.stream().map(mm -> MeetingMemberResponse.from(mm, userMap.get(mm.getUserId()))).toList();
    }

    @Transactional
    public MeetingResponse updateMeeting(Long meetingId, Long requesterId, MeetingUpdateRequest request) {
        checkSecretaryPermission(meetingId, requesterId);
        Meeting meeting = findMeetingOrThrow(meetingId);
        meeting.update(
                request.getTitle(), request.getPurpose(), request.getGuidelines(),
                request.getPriority(), request.getType(),
                request.getStartDateTime(), request.getEndDateTime(), request.getStatus()
        );
        neoSyncService.syncMeeting(meetingId);
        return MeetingResponse.from(meeting);
    }

    @Transactional
    public MeetingMemberResponse addMember(Long meetingId, Long requesterId, MeetingMemberAddRequest request) {
        checkSecretaryPermission(meetingId, requesterId);
        findMeetingOrThrow(meetingId);
        if (meetingMemberRepository.existsByMeetingIdAndUserId(meetingId, request.getUserId())) {
            throw new BusinessException(ErrorCode.MEETING_MEMBER_ALREADY_EXISTS);
        }
        MeetingMember member = MeetingMember.create(meetingId, request.getUserId(), request.getRole());
        MeetingMember saved = meetingMemberRepository.save(member);
        User user = userRepository.findById(saved.getUserId()).orElse(null);
        neoSyncService.syncMember(meetingId, request.getUserId());
        return MeetingMemberResponse.from(saved, user);
    }

    @Transactional
    public void removeMember(Long meetingId, Long requesterId, Long memberId) {
        checkSecretaryPermission(meetingId, requesterId);
        MeetingMember member = meetingMemberRepository.findById(memberId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_MEMBER_NOT_FOUND));
        Long userId = member.getUserId();
        meetingMemberRepository.delete(member);
        neoSyncService.deleteMember(meetingId, userId);
    }

    @Transactional
    public MeetingMemberResponse updateMemberRole(Long meetingId, Long requesterId,
                                                   Long memberId, MeetingMemberUpdateRequest request) {
        checkSecretaryPermission(meetingId, requesterId);
        MeetingMember member = meetingMemberRepository.findById(memberId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_MEMBER_NOT_FOUND));
        member.updateRole(request.getRole());
        User user = userRepository.findById(member.getUserId()).orElse(null);
        neoSyncService.syncMember(meetingId, member.getUserId());
        return MeetingMemberResponse.from(member, user);
    }

    /** 현재 사용자의 특정 회의체 내 역할 반환 (없으면 null) */
    public String getMyRole(Long meetingId, Long userId) {
        return meetingMemberRepository.findByMeetingIdAndUserId(meetingId, userId)
                .map(m -> m.getRole() == MeetingMemberRole.SECRETARY ? "admin" : "presenter")
                .orElse(null);
    }

    private Meeting findMeetingOrThrow(Long meetingId) {
        return meetingRepository.findById(meetingId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_NOT_FOUND));
    }

    private Map<Long, User> buildUserMap(List<MeetingMember> members) {
        List<Long> userIds = members.stream().map(MeetingMember::getUserId).distinct().toList();
        return userRepository.findAllById(userIds).stream()
                .collect(Collectors.toMap(User::getId, u -> u));
    }

    // secretary 권한이 없으면 403 예외 발생
    private void checkSecretaryPermission(Long meetingId, Long requesterId) {
        if (!meetingMemberRepository.existsByMeetingIdAndUserIdAndRole(meetingId, requesterId, MeetingMemberRole.SECRETARY)) {
            throw new BusinessException(ErrorCode.MEETING_ACCESS_DENIED);
        }
    }
}
