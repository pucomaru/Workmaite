package com.workmaite.domain.home.service;

import com.workmaite.domain.agendas.entity.Agenda;
import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.domain.home.dto.CalendarAgendaItem;
import com.workmaite.domain.home.dto.CalendarResponse;
import com.workmaite.domain.home.dto.CalendarSessionItem;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.repository.SessionRepository;
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 홈 화면 비즈니스 로직 - 일정 조회: 로그인 유저가 속한 회의체의 예정 세션을 월/주/일 뷰로 반환 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class HomeService {

  private final MeetingRepository meetingRepository;
  private final SessionRepository sessionRepository;
  private final AgendaRepository agendaRepository;

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

    List<MeetingSession> sessions =
        sessionRepository.findByUserIdAndScheduledAtBetween(userId, start, end);
    List<Agenda> agendas =
        agendaRepository.findByAssigneeIdAndDueDateBetween(userId, start, end);

    List<Long> allMeetingIds =
        Stream.concat(
                sessions.stream().map(MeetingSession::getMeetingId),
                agendas.stream().map(Agenda::getMeetingId))
            .distinct()
            .toList();

    Map<Long, String> meetingTitleMap =
        allMeetingIds.isEmpty()
            ? Map.of()
            : meetingRepository.findAllById(allMeetingIds).stream()
                .collect(Collectors.toMap(Meeting::getId, Meeting::getTitle));

    List<CalendarSessionItem> sessionItems =
        sessions.stream()
            .map(s -> CalendarSessionItem.from(s, meetingTitleMap.get(s.getMeetingId())))
            .toList();

    List<CalendarAgendaItem> agendaItems =
        agendas.stream()
            .map(a -> CalendarAgendaItem.from(a, meetingTitleMap.get(a.getMeetingId())))
            .toList();

    return CalendarResponse.of(sessionItems, agendaItems);
  }
}
