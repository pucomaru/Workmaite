package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import java.util.List;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface MeetingRepository extends JpaRepository<Meeting, Long> {

  List<Meeting> findByTitleContainingIgnoreCaseOrDescriptionContainingIgnoreCase(
      String title, String description);

  @Query(
      "SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId) AND m.status = :status")
  List<Meeting> findByUserIdAndStatus(
      @Param("userId") Long userId, @Param("status") MeetingStatus status);

  @Query(
      "SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId)")
  List<Meeting> findByUserId(@Param("userId") Long userId);

  // 회사 관리자 조회 범위: 자사 구성원이 한 명이라도 참여한 회의체 (MT/SEC-5)
  @Query(
      "SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm "
          + "WHERE mm.userId IN (SELECT u.id FROM User u WHERE u.company.id = :companyId))")
  List<Meeting> findByParticipatingCompany(@Param("companyId") Long companyId);

  // P8-4: 페이지네이션 변형 (파라미터 없는 기존 메서드는 호환용으로 유지)
  @Query(
      "SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId)")
  List<Meeting> findByUserId(@Param("userId") Long userId, Pageable pageable);

  List<Meeting> findByTitleContainingIgnoreCaseOrDescriptionContainingIgnoreCase(
      String title, String description, Pageable pageable);
}
