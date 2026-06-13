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
  private Integer id;

  @Column(name = "meeting_id", nullable = false)
  private Integer meetingId;

  @Column(name = "user_id", nullable = false)
  private Integer userId;

  // SECRETARY(admin) | MEMBER(presenter)
  @Convert(converter = MeetingMemberRoleConverter.class)
  @Column(length = 20, nullable = false)
  private MeetingMemberRole role;

  // high | medium | low
  @Column(length = 20)
  private String priority = "medium";

  public static MeetingMember create(Integer meetingId, Integer userId, MeetingMemberRole role) {
    MeetingMember member = new MeetingMember();
    member.meetingId = meetingId;
    member.userId = userId;
    member.role = (role != null) ? role : MeetingMemberRole.MEMBER;
    return member;
  }

  public void updateRole(MeetingMemberRole role) {
    this.role = role;
  }
}
