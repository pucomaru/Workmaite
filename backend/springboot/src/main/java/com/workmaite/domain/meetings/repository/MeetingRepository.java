package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface MeetingRepository extends JpaRepository<Meeting, Long> {

    List<Meeting> findByTitleContainingIgnoreCaseOrPurposeContainingIgnoreCase(
            String title, String purpose);

    @Query("SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId) AND m.status = :status")
    List<Meeting> findByUserIdAndStatus(@Param("userId") Long userId, @Param("status") MeetingStatus status);

    @Query("SELECT m FROM Meeting m WHERE m.id IN (SELECT mm.meetingId FROM MeetingMember mm WHERE mm.userId = :userId)")
    List<Meeting> findByUserId(@Param("userId") Long userId);
}
