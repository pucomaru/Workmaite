package com.workmaite.domain.home.service;

import com.workmaite.domain.home.dto.ActiveMeetingResponse;
import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.dto.CalendarSessionItem;
import com.workmaite.domain.home.dto.UpcomingSessionResponse;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import com.workmaite.domain.meetings.entity.MeetingStatus;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
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
    private final MeetingMemberRepository meetingMemberRepository;
    private final SessionRepository sessionRepository;
    private final UserRepository userRepository;

    public List<ActiveMeetingResponse> getActiveMeetings(Long userId) {
        List<Meeting> meetings = meetingRepository.findByUserIdAndStatus(userId, MeetingStatus.ACTIVE);
        if (meetings.isEmpty()) return List.of();

        List<Long> meetingIds = meetings.stream().map(Meeting::getId).toList();

        List<MeetingMember> secretaries = meetingMemberRepository
                .findByMeetingIdInAndRole(meetingIds, MeetingMemberRole.SECRETARY);

        List<Long> secretaryUserIds = secretaries.stream()
                .map(MeetingMember::getUserId).distinct().toList();

        Map<Long, String> userNameMap = userRepository.findAllById(secretaryUserIds)
                .stream()
                .collect(Collectors.toMap(User::getId, User::getName));

        // 한 회의체에 secretary가 여러 명일 경우 첫 번째만 사용
        Map<Long, String> secretaryNameMap = secretaries.stream()
                .collect(Collectors.toMap(
                        MeetingMember::getMeetingId,
                        m -> userNameMap.getOrDefault(m.getUserId(), ""),
                        (first, second) -> first
                ));

        return meetings.stream()
                .map(m -> ActiveMeetingResponse.from(m, secretaryNameMap.get(m.getId())))
                .toList();
    }

    public List<UpcomingSessionResponse> getUpcomingSessions(Long userId) {
        List<MeetingSession> sessions = sessionRepository.findUpcomingByUserId(userId, SessionStatus.SCHEDULED);
        if (sessions.isEmpty()) return List.of();

        List<Long> meetingIds = sessions.stream().map(MeetingSession::getMeetingId).distinct().toList();
        Map<Long, String> meetingTitleMap = meetingRepository.findAllById(meetingIds)
                .stream()
                .collect(Collectors.toMap(Meeting::getId, Meeting::getTitle));

        LocalDate today = LocalDate.now();
        return sessions.stream()
                .map(s -> UpcomingSessionResponse.from(s, meetingTitleMap.get(s.getMeetingId()), today))
                .toList();
    }

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
