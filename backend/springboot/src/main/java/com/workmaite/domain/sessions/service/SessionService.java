package com.workmaite.domain.sessions.service;

import com.workmaite.domain.meetings.entity.Meeting;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.sessions.dto.AttendeeRequest;
import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.dto.UpcomingSessionResponse;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionMember;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.repository.SessionMemberRepository;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import com.workmaite.global.sync.NeoSyncService;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * 회의 비즈니스 로직
 * - 내 예정된 회의: 로그인 유저가 속한 전체 회의체의 SCHEDULED 세션을 일시 순으로 반환, D-day 포함
 * - 목록 조회: 특정 회의체의 세션 목록, status 필터 가능
 * - 생성·수정·삭제: secretary 권한 확인은 Controller에서 처리
 * - 진행 상태 전환: SCHEDULED → ONGOING → ENDED 단방향 흐름
 */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class SessionService {

    private final SessionRepository sessionRepository;
    private final SessionMemberRepository sessionMemberRepository;
    private final MeetingRepository meetingRepository;
    private final NeoSyncService neoSyncService;

    // 내가 속한 모든 회의체의 예정 세션을 일시 오름차순으로 반환, D-day는 오늘 기준 계산
    public List<UpcomingSessionResponse> getMyUpcomingSessions(Long userId) {
        List<MeetingSession> sessions = sessionRepository.findUpcomingByUserId(userId, SessionStatus.SCHEDULED);
        if (sessions.isEmpty()) return List.of();

        List<Long> meetingIds = sessions.stream().map(MeetingSession::getMeetingId).distinct().toList();
        Map<Long, String> meetingTitleMap = meetingRepository.findAllById(meetingIds)
                .stream().collect(Collectors.toMap(Meeting::getId, Meeting::getTitle));

        LocalDate today = LocalDate.now();
        return sessions.stream()
                .map(s -> UpcomingSessionResponse.from(s, meetingTitleMap.get(s.getMeetingId()), today))
                .toList();
    }

    public List<SessionResponse> getSessions(Long meetingId, SessionStatus status) {
        List<MeetingSession> sessions = (status != null)
                ? sessionRepository.findByMeetingIdAndStatus(meetingId, status)
                : sessionRepository.findByMeetingId(meetingId);
        return sessions.stream()
                .map(s -> SessionResponse.from(s, sessionMemberRepository.findBySessionId(s.getId())))
                .toList();
    }

    @Transactional
    public SessionResponse createSession(Long meetingId, SessionCreateRequest request) {
        MeetingSession session = MeetingSession.create(
                meetingId,
                request.getTitle(),
                request.getDescription(),
                request.getLocation(),
                request.getType(),
                request.getScheduledAt()
        );
        sessionRepository.save(session);

        // 참석자 저장
        List<AttendeeRequest> requested = request.getAttendees() != null ? request.getAttendees() : List.of();
        List<SessionMember> members = requested.stream()
                .map(a -> SessionMember.of(session.getId(), a.getUserId(), a.getRole()))
                .collect(Collectors.toList());
        sessionMemberRepository.saveAll(members);

        neoSyncService.syncSession(session.getId());
        return SessionResponse.from(session, members);
    }

    public SessionResponse getSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);
        return SessionResponse.from(session, sessionMemberRepository.findBySessionId(sessionId));
    }

    @Transactional
    public SessionResponse updateSession(Long sessionId, SessionUpdateRequest request) {
        MeetingSession session = findSessionById(sessionId);

        if (session.getStatus() == SessionStatus.ONGOING) {
            throw new BusinessException(ErrorCode.SESSION_ALREADY_STARTED);
        }
        if (session.getStatus() == SessionStatus.ENDED) {
            throw new BusinessException(ErrorCode.SESSION_ALREADY_ENDED);
        }

        session.update(request.getTitle(), request.getDescription(), request.getLocation(), request.getType(), request.getScheduledAt());

        List<AttendeeRequest> attendees = request.getAttendees();
        if (attendees != null) {
            sessionMemberRepository.deleteBySessionId(sessionId);
            if (!attendees.isEmpty()) {
                List<SessionMember> members = attendees.stream()
                        .map(a -> SessionMember.of(sessionId, a.getUserId(), a.getRole()))
                        .toList();
                sessionMemberRepository.saveAll(members);
            }
        }

        return SessionResponse.from(session, sessionMemberRepository.findBySessionId(sessionId));
    }

    @Transactional
    public void deleteSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);
        sessionRepository.delete(session);
    }

    // SCHEDULED 상태일 때만 시작 가능, 그 외 상태면 SESSION_ALREADY_STARTED 에러
    @Transactional
    public SessionResponse startSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);

        if (session.getStatus() != SessionStatus.SCHEDULED) {
            throw new BusinessException(ErrorCode.SESSION_ALREADY_STARTED);
        }

        session.start();
        neoSyncService.syncSession(sessionId);
        return SessionResponse.from(session);
    }

    // ONGOING 상태일 때만 일시정지 가능, 그 외 상태면 SESSION_NOT_STARTED 에러
    @Transactional
    public SessionResponse pauseSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);

        if (session.getStatus() != SessionStatus.ONGOING) {
            throw new BusinessException(ErrorCode.SESSION_NOT_STARTED);
        }

        session.pause();
        neoSyncService.syncSession(sessionId);
        return SessionResponse.from(session);
    }

    // ONGOING 상태일 때만 종료 가능, 그 외 상태면 SESSION_ALREADY_ENDED 에러
    @Transactional
    public SessionResponse endSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);

        if (session.getStatus() != SessionStatus.ONGOING) {
            throw new BusinessException(ErrorCode.SESSION_ALREADY_ENDED);
        }

        session.end();
        neoSyncService.syncSession(sessionId);
        return SessionResponse.from(session);
    }

    @Transactional
    public SessionResponse archiveSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);

        if (session.getStatus() != SessionStatus.ENDED) {
            throw new BusinessException(ErrorCode.SESSION_NOT_FOUND);
        }

        session.archive();
        return SessionResponse.from(session);
    }

    @Transactional
    public SessionResponse updateContext(Long sessionId, String context) {
        MeetingSession session = findSessionById(sessionId);
        session.updateContext(context);
        return SessionResponse.from(session);
    }

    private MeetingSession findSessionById(Long sessionId) {
        return sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND));
    }
}
