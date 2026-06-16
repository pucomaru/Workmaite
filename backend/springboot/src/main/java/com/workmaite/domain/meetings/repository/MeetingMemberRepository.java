package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MeetingMemberRepository extends JpaRepository<MeetingMember, Long> {

  List<MeetingMember> findByMeetingId(Long meetingId);

  // 회의체 삭제 시: 참여자 일괄 삭제.
  @Modifying
  @Query("DELETE FROM MeetingMember m WHERE m.meetingId = :meetingId")
  void deleteByMeetingId(@Param("meetingId") Long meetingId);

  Optional<MeetingMember> findByMeetingIdAndUserId(Long meetingId, Long userId);

  boolean existsByMeetingIdAndUserId(Long meetingId, Long userId);

  boolean existsByMeetingIdAndUserIdAndMeetingRole(
      Long meetingId, Long userId, MeetingMemberRole meetingRole);

  List<MeetingMember> findByMeetingIdInAndMeetingRole(
      List<Long> meetingIds, MeetingMemberRole meetingRole);

  List<MeetingMember> findByMeetingIdIn(List<Long> meetingIds);

  List<MeetingMember> findByUserId(Long userId);
}
