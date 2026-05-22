package com.workmaite.domain.meetings.service;

import com.workmaite.domain.meetings.dto.*;
import com.workmaite.domain.meetings.entity.*;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 회의체 비즈니스 로직
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

    public List<MeetingResponse> getMeetings(String keyword) {
        List<Meeting> meetings = (keyword != null && !keyword.isBlank())
                ? meetingRepository.findByTitleContainingIgnoreCaseOrPurposeContainingIgnoreCase(keyword, keyword)
                : meetingRepository.findAll();
        return meetings.stream().map(MeetingResponse::from).toList();
    }

    public MeetingDetailResponse getMeeting(Long meetingId) {
        Meeting meeting = findMeetingOrThrow(meetingId);
        List<MeetingMember> members = meetingMemberRepository.findByMeetingId(meetingId);
        return MeetingDetailResponse.from(meeting, members);
    }

    @Transactional
    public MeetingResponse updateMeeting(Long meetingId, Long requesterId, MeetingUpdateRequest request) {
        checkSecretaryPermission(meetingId, requesterId);
        Meeting meeting = findMeetingOrThrow(meetingId);
        meeting.update(
                request.getTitle(), request.getPurpose(), request.getGuidelines(),
                request.getPriority(), request.getType(),
                request.getStartDate(), request.getEndDate(), request.getStatus()
        );
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
        return MeetingMemberResponse.from(meetingMemberRepository.save(member));
    }

    @Transactional
    public void removeMember(Long meetingId, Long requesterId, Long userId) {
        checkSecretaryPermission(meetingId, requesterId);
        meetingMemberRepository.delete(findMemberOrThrow(meetingId, userId));
    }

    @Transactional
    public MeetingMemberResponse updateMemberRole(Long meetingId, Long requesterId,
                                                   Long userId, MeetingMemberUpdateRequest request) {
        checkSecretaryPermission(meetingId, requesterId);
        MeetingMember member = findMemberOrThrow(meetingId, userId);
        member.updateRole(request.getRole());
        return MeetingMemberResponse.from(member);
    }

    private Meeting findMeetingOrThrow(Long meetingId) {
        return meetingRepository.findById(meetingId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_NOT_FOUND));
    }

    private MeetingMember findMemberOrThrow(Long meetingId, Long userId) {
        return meetingMemberRepository.findByMeetingIdAndUserId(meetingId, userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_MEMBER_NOT_FOUND));
    }

    // secretary 권한이 없으면 403 예외 발생
    private void checkSecretaryPermission(Long meetingId, Long requesterId) {
        if (!meetingMemberRepository.existsByMeetingIdAndUserIdAndRole(meetingId, requesterId, MeetingMemberRole.SECRETARY)) {
            throw new BusinessException(ErrorCode.MEETING_ACCESS_DENIED);
        }
    }
}
