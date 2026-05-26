package com.workmaite.domain.organization.service;

import com.workmaite.domain.organization.dto.OrganizationMemberResponse;
import com.workmaite.domain.organization.dto.OrganizationMemberUpdateRequest;
import com.workmaite.domain.organization.entity.MemberRole;
import com.workmaite.domain.organization.entity.OrganizationMember;
import com.workmaite.domain.organization.repository.OrganizationMemberRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * 조직 구성원 비즈니스 로직
 * - 목록 조회: keyword(이름·이메일) 또는 role 필터 지원, 페이징 처리
 * - 회의체별 조회: 특정 회의체에 배정된 구성원 반환
 * - 수정·삭제: userId 기준으로 처리
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class OrganizationService {

    private final OrganizationMemberRepository organizationMemberRepository;

    public Page<OrganizationMemberResponse> getMembers(String keyword, MemberRole role, Pageable pageable) {
        if (keyword != null && !keyword.isBlank()) {
            return organizationMemberRepository
                    .findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(keyword, keyword, pageable)
                    .map(OrganizationMemberResponse::from);
        }
        if (role != null) {
            return organizationMemberRepository.findByRole(role, pageable)
                    .map(OrganizationMemberResponse::from);
        }
        return organizationMemberRepository.findAll(pageable)
                .map(OrganizationMemberResponse::from);
    }

    public List<OrganizationMemberResponse> getMembersByMeeting(Long meetingId) {
        return organizationMemberRepository.findByMeetingId(meetingId).stream()
                .map(OrganizationMemberResponse::from)
                .toList();
    }

    @Transactional
    public OrganizationMemberResponse updateMember(Long userId, OrganizationMemberUpdateRequest request) {
        OrganizationMember member = findByUserIdOrThrow(userId);
        member.update(request.getRole());
        return OrganizationMemberResponse.from(member);
    }

    @Transactional
    public void deleteMember(Long userId) {
        organizationMemberRepository.delete(findByUserIdOrThrow(userId));
    }

    private OrganizationMember findByUserIdOrThrow(Long userId) {
        return organizationMemberRepository.findByUserId(userId)
                .orElseThrow(() -> new BusinessException(ErrorCode.ORGANIZATION_MEMBER_NOT_FOUND));
    }
}
