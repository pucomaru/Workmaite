package com.workmaite.domain.organization.repository;

import com.workmaite.domain.organization.entity.MemberRole;
import com.workmaite.domain.organization.entity.OrganizationMember;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface OrganizationMemberRepository extends JpaRepository<OrganizationMember, Long> {

    Page<OrganizationMember> findByNameContainingIgnoreCaseOrEmailContainingIgnoreCase(
            String name, String email, Pageable pageable);

    Page<OrganizationMember> findByRole(MemberRole role, Pageable pageable);

    List<OrganizationMember> findByMeetingId(Long meetingId);

    Optional<OrganizationMember> findByUserId(Long userId);
}
