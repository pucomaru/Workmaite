package com.workmaite.domain.sessions.service;

import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.domain.chat.repository.ChatMessageRepository;
import com.workmaite.domain.logs.repository.AgentLogRepository;
import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.meetings.service.MeetingService;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.domain.minutes.repository.MinutesRepository;
import com.workmaite.domain.scripts.repository.ScriptRepository;
import com.workmaite.domain.sessions.dto.AttendeeRequest;
import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.dto.SummaryBlockResponse;
import com.workmaite.domain.sessions.dto.UpcomingSessionResponse;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionAgenda;
import com.workmaite.domain.sessions.entity.SessionMember;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.repository.SessionAgendaRepository;
import com.workmaite.domain.sessions.repository.SessionMemberRepository;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.domain.sessions.repository.SessionSummaryBlockRepository;
import com.workmaite.global.audit.AuditLogged;
import com.workmaite.global.auth.MeetingAccessGuard;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회의 비즈니스 로직 - 내 예정된 회의: 로그인 유저가 속한 전체 회의체의 SCHEDULED 세션을 일시 순으로 반환, D-day 포함 - 목록 조회: 특정 회의체의 세션
 * 목록, status 필터 가능 - 생성·수정·삭제: secretary 권한 확인은 Controller에서 처리 - 진행 상태 전환: SCHEDULED → ONGOING →
 * ENDED 단방향 흐름
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class SessionService {

  private final SessionRepository sessionRepository;
  private final SessionMemberRepository sessionMemberRepository;
  private final SessionSummaryBlockRepository summaryBlockRepository;
  private final SessionAgendaRepository sessionAgendaRepository;
  private final MeetingRepository meetingRepository;
  private final MeetingService meetingService;
  private final UserRepository userRepository;
  private final NeoSyncService neoSyncService;
  private final ScriptRepository scriptRepository;
  private final MinutesRepository minutesRepository;
  private final MeetingAccessGuard meetingAccessGuard;
  private final ChatMessageRepository chatMessageRepository;
  private final AgentLogRepository agentLogRepository;
  private final AgendaRepository agendaRepository;

  // 역할 기반 가시 회의체의 예정 세션을 일시 오름차순으로 반환 (SYSTEM_ADMIN=전체, COMPANY_ADMIN=자사, USER=소속)
  public List<UpcomingSessionResponse> getMyUpcomingSessions(Long userId) {
    User user = userRepository.findById(userId).orElseThrow();
    List<Long> meetingIds = meetingService.getVisibleMeetings(user)
        .stream()
        .filter(m -> !"ended".equalsIgnoreCase(m.getStatus().name())
                  && !"archived".equalsIgnoreCase(m.getStatus().name()))
        .map(Meeting::getId)
        .toList();
    if (meetingIds.isEmpty()) return List.of();

    List<MeetingSession> sessions =
        sessionRepository.findByMeetingIdInAndStatusOrderByScheduledAtAsc(
            meetingIds, SessionStatus.SCHEDULED);
    if (sessions.isEmpty()) return List.of();

    Map<Long, String> meetingTitleMap =
        meetingRepository.findAllById(meetingIds).stream()
            .collect(Collectors.toMap(Meeting::getId, Meeting::getTitle));

    LocalDate today = LocalDate.now();
    return sessions.stream()
        .map(s -> UpcomingSessionResponse.from(s, meetingTitleMap.get(s.getMeetingId()), today))
        .toList();
  }

  public List<SessionResponse> getSessions(Long meetingId, SessionStatus status) {
    meetingAccessGuard.requireView(meetingId);
    List<MeetingSession> sessions =
        (status != null)
            ? sessionRepository.findByMeetingIdAndStatus(meetingId, status)
            : sessionRepository.findByMeetingId(meetingId);
    return sessions.stream()
        .map(s -> SessionResponse.from(s, sessionMemberRepository.findBySessionId(s.getId())))
        .toList();
  }

  @Transactional
  @AuditLogged(action = "CREATE", entityType = "session")
  public SessionResponse createSession(Long meetingId, SessionCreateRequest request) {
    // 세션 생성은 회의체 운영 행위 — 간사/회사관리자/시스템관리자만
    meetingAccessGuard.requireMeetingEdit(meetingId);
    MeetingSession session =
        MeetingSession.create(
            meetingId,
            request.getTitle(),
            request.getDescription(),
            request.getLocation(),
            request.getType(),
            request.getScheduledAt());
    if (request.getContext() != null) session.updateContext(request.getContext());
    sessionRepository.save(session);

    // 참석자 저장
    List<AttendeeRequest> requested =
        request.getAttendees() != null ? request.getAttendees() : List.of();
    List<SessionMember> members =
        requested.stream()
            .map(a -> SessionMember.of(session.getId(), a.getUserId(), a.getRole()))
            .collect(Collectors.toList());
    sessionMemberRepository.saveAll(members);

    // 선택된 안건 저장
    List<Long> agendaIds = request.getAgendaIds();
    if (agendaIds != null && !agendaIds.isEmpty()) {
      List<SessionAgenda> sessionAgendas =
          agendaIds.stream().map(agendaId -> SessionAgenda.of(session.getId(), agendaId)).toList();
      sessionAgendaRepository.saveAll(sessionAgendas);
    }

    neoSyncService.syncSession(session.getId());
    return SessionResponse.from(session, members);
  }

  public List<Long> getSessionAgendaIds(Long sessionId) {
    findSessionById(sessionId);
    return sessionAgendaRepository.findBySessionId(sessionId).stream()
        .map(SessionAgenda::getAgendaId)
        .toList();
  }

  public SessionResponse getSession(Long sessionId) {
    MeetingSession session = findSessionById(sessionId);
    List<SummaryBlockResponse> blocks =
        summaryBlockRepository.findBySessionIdOrderByBlockIndexAsc(sessionId).stream()
            .map(SummaryBlockResponse::from)
            .toList();
    return SessionResponse.from(
        session, sessionMemberRepository.findBySessionId(sessionId), blocks);
  }

  @Transactional
  @AuditLogged(action = "UPDATE", entityType = "session")
  public SessionResponse updateSession(Long sessionId, SessionUpdateRequest request) {
    MeetingSession session = findSessionForEdit(sessionId);

    session.update(
        request.getTitle(),
        request.getDescription(),
        request.getLocation(),
        request.getType(),
        request.getScheduledAt());
    if (request.getContext() != null) session.updateContext(request.getContext());

    List<AttendeeRequest> attendees = request.getAttendees();
    if (attendees != null) {
      sessionMemberRepository.deleteBySessionId(sessionId);
      if (!attendees.isEmpty()) {
        List<SessionMember> members =
            attendees.stream()
                .map(a -> SessionMember.of(sessionId, a.getUserId(), a.getRole()))
                .toList();
        sessionMemberRepository.saveAll(members);
      }
    }

    List<Long> agendaIds = request.getAgendaIds();
    if (agendaIds != null) {
      sessionAgendaRepository.deleteBySessionId(sessionId);
      if (!agendaIds.isEmpty()) {
        List<SessionAgenda> sessionAgendas =
            agendaIds.stream().map(id -> SessionAgenda.of(sessionId, id)).toList();
        sessionAgendaRepository.saveAll(sessionAgendas);
      }
    }

    return SessionResponse.from(session, sessionMemberRepository.findBySessionId(sessionId));
  }

  @Transactional
  @AuditLogged(action = "DELETE", entityType = "session")
  public void deleteSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);
    scriptRepository.deleteAllBySessionId(sessionId);
    summaryBlockRepository.deleteAllBySessionId(sessionId);
    sessionMemberRepository.deleteBySessionId(sessionId);
    sessionAgendaRepository.deleteBySessionId(sessionId);
    minutesRepository.deleteBySessionId(sessionId);
    // CASCADE 없는 잔여 FK 정리 — 미처리 시 FK 위반으로 세션 삭제 500.
    // 챗·에이전트로그·아젠다는 이력/데이터라 '보존'하고 세션 링크(session_id)만 해제한다.
    // (행을 지우지 않으므로 token_usage_logs·hitl_reviews·chat_feedback 등 손자 FK도 안전)
    chatMessageRepository.detachSession(sessionId);
    agentLogRepository.detachSession(sessionId);
    agendaRepository.detachSession(sessionId);
    sessionRepository.delete(session);
    neoSyncService.deleteSession(sessionId); // 삭제 전파 (DATA-4)
  }

  // SCHEDULED 상태일 때만 시작 가능, 그 외 상태면 SESSION_ALREADY_STARTED 에러
  @Transactional
  @AuditLogged(action = "START", entityType = "session")
  public SessionResponse startSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);

    if (session.getStatus() != SessionStatus.SCHEDULED) {
      throw new BusinessException(ErrorCode.SESSION_ALREADY_STARTED);
    }

    session.start();
    neoSyncService.syncSession(sessionId);
    return SessionResponse.from(session);
  }

  // ONGOING 상태일 때만 일시정지 가능
  @Transactional
  public SessionResponse pauseSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);

    if (session.getStatus() != SessionStatus.ONGOING) {
      throw new BusinessException(ErrorCode.SESSION_NOT_STARTED);
    }

    session.pause();
    neoSyncService.syncSession(sessionId);
    return SessionResponse.from(session);
  }

  // ONGOING 상태일 때만 재개 가능
  @Transactional
  public SessionResponse resumeSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);

    if (session.getStatus() != SessionStatus.ONGOING) {
      throw new BusinessException(ErrorCode.SESSION_NOT_STARTED);
    }

    session.resume();
    neoSyncService.syncSession(sessionId);
    return SessionResponse.from(session);
  }

  // ONGOING 상태일 때만 종료 가능, 그 외 상태면 SESSION_ALREADY_ENDED 에러
  @Transactional
  @AuditLogged(action = "END", entityType = "session")
  public SessionResponse endSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);

    if (session.getStatus() != SessionStatus.ONGOING) {
      throw new BusinessException(ErrorCode.SESSION_ALREADY_ENDED);
    }

    session.end();
    neoSyncService.syncSession(sessionId);
    return SessionResponse.from(session);
  }

  @Transactional
  public SessionResponse archiveSession(Long sessionId) {
    MeetingSession session = findSessionForEdit(sessionId);

    if (session.getStatus() != SessionStatus.ENDED) {
      throw new BusinessException(ErrorCode.SESSION_NOT_FOUND);
    }

    session.archive();
    return SessionResponse.from(session);
  }

  @Transactional
  public SessionResponse updateContext(Long sessionId, String context) {
    MeetingSession session = findSessionForEdit(sessionId);
    session.updateContext(context);
    return SessionResponse.from(session);
  }

  // 조회 단일 진입점 — 조회 권한 검증 포함 (IDOR 차단)
  private MeetingSession findSessionById(Long sessionId) {
    MeetingSession session = fetchSession(sessionId);
    meetingAccessGuard.requireView(session.getMeetingId());
    return session;
  }

  // 편집 단일 진입점 — 세션은 회의체 운영물이라 간사/회사관리자/시스템관리자만 변경 가능
  private MeetingSession findSessionForEdit(Long sessionId) {
    MeetingSession session = fetchSession(sessionId);
    meetingAccessGuard.requireMeetingEdit(session.getMeetingId());
    return session;
  }

  private MeetingSession fetchSession(Long sessionId) {
    return sessionRepository
        .findById(sessionId)
        .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND));
  }
}
