package com.workmaite.domain.meetings.entity;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

/** 회의 참여자 엔티티 - meeting_members 테이블 매핑 */
@Entity
@Table(
    name = "meeting_members",
    uniqueConstraints = @UniqueConstraint(columnNames = {"meeting_id", "user_id"}))
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class MeetingMember {

  @Id
  @GeneratedValue(strategy = GenerationType.IDENTITY)
  private Long id;

  @Column(name = "meeting_id", nullable = false)
  private Long meetingId;

  @Column(name = "user_id", nullable = false)
  private Long userId;

  // 회의체 수준 권한: SECRETARY(admin) | MEMBER(presenter) — 조직 권한(users.role=companyRole)과 구분.
  // DB 컬럼명은 role 유지(매핑만 meeting_role 의미로 명명).
  @Convert(converter = MeetingMemberRoleConverter.class)
  @Column(name = "role", length = 20, nullable = false)
  private MeetingMemberRole meetingRole;

  // high | medium | low
  @Column(length = 20)
  private String priority = "medium";

  public static MeetingMember create(Long meetingId, Long userId, MeetingMemberRole meetingRole) {
    MeetingMember member = new MeetingMember();
    member.meetingId = meetingId;
    member.userId = userId;
    member.meetingRole = (meetingRole != null) ? meetingRole : MeetingMemberRole.MEMBER;
    return member;
  }

  public void updateMeetingRole(MeetingMemberRole meetingRole) {
    this.meetingRole = meetingRole;
  }
}
