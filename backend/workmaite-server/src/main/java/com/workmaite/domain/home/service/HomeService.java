package com.workmaite.domain.home.service;

import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.dto.CalendarSessionItem;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.repository.SessionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class HomeService {

    private final MeetingRepository meetingRepository;
    private final SessionRepository sessionRepository;

    public CalendarResponse getCalendar(Long userId, String view, String dateStr) {
        LocalDate date = LocalDate.parse(dateStr);
        LocalDateTime start;
        LocalDateTime end;

        switch (view) {
            case "month" -> {
                start = date.withDayOfMonth(1).atStartOfDay();
                end = date.withDayOfMonth(date.lengthOfMonth()).atTime(23, 59, 59);
            }
            case "week" -> {
                LocalDate monday = date.with(DayOfWeek.MONDAY);
                start = monday.atStartOfDay();
                end = monday.plusDays(6).atTime(23, 59, 59);
            }
            default -> {
                start = date.atStartOfDay();
                end = date.atTime(23, 59, 59);
            }
        }

        List<MeetingSession> sessions = sessionRepository.findByUserIdAndScheduledAtBetween(userId, start, end);

        List<Long> meetingIds = sessions.stream().map(MeetingSession::getMeetingId).distinct().toList();
        Map<Long, String> meetingTitleMap = meetingIds.isEmpty() ? Map.of() :
                meetingRepository.findAllById(meetingIds)
                        .stream()
                        .collect(Collectors.toMap(Meeting::getId, Meeting::getTitle));

        List<CalendarSessionItem> sessionItems = sessions.stream()
                .map(s -> CalendarSessionItem.from(s, meetingTitleMap.get(s.getMeetingId())))
                .toList();

        return CalendarResponse.of(sessionItems);
    }
}
