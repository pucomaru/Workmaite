package com.workmaite.domain.meetings.repository;

import com.workmaite.domain.meetings.entity.Meeting;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface MeetingRepository extends JpaRepository<Meeting, Long> {

    List<Meeting> findByTitleContainingIgnoreCaseOrPurposeContainingIgnoreCase(
            String title, String purpose);
}
