package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MeetingMemberRepository extends JpaRepository<MeetingMember, Long> {

  List<MeetingMember> findByMeetingId(Long meetingId);

  Optional<MeetingMember> findByMeetingIdAndUserId(Long meetingId, Long userId);

  boolean existsByMeetingIdAndUserId(Long meetingId, Long userId);

  boolean existsByMeetingIdAndUserIdAndRole(Long meetingId, Long userId, MeetingMemberRole role);

  List<MeetingMember> findByMeetingIdInAndRole(List<Long> meetingIds, MeetingMemberRole role);

  List<MeetingMember> findByMeetingIdIn(List<Long> meetingIds);

  List<MeetingMember> findByUserId(Long userId);
}
