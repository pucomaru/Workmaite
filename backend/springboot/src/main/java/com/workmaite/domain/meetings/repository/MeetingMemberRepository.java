package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MeetingMemberRepository extends JpaRepository<MeetingMember, Integer> {

  List<MeetingMember> findByMeetingId(Integer meetingId);

  Optional<MeetingMember> findByMeetingIdAndUserId(Integer meetingId, Integer userId);

  boolean existsByMeetingIdAndUserId(Integer meetingId, Integer userId);

  boolean existsByMeetingIdAndUserIdAndRole(Integer meetingId, Integer userId, MeetingMemberRole role);

  List<MeetingMember> findByMeetingIdInAndRole(List<Integer> meetingIds, MeetingMemberRole role);

  List<MeetingMember> findByMeetingIdIn(List<Integer> meetingIds);

  List<MeetingMember> findByUserId(Integer userId);
}
