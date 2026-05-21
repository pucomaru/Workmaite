package com.workmaite.domain.sessions.service;

import com.workmaite.domain.sessions.dto.SessionCreateRequest;
import com.workmaite.domain.sessions.dto.SessionResponse;
import com.workmaite.domain.sessions.dto.SessionUpdateRequest;
import com.workmaite.domain.sessions.entity.MeetingSession;
import com.workmaite.domain.sessions.entity.SessionStatus;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class SessionService {

    private final SessionRepository sessionRepository;

    public List<SessionResponse> getSessions(Long meetingId, SessionStatus status) {
        List<MeetingSession> sessions = (status != null)
                ? sessionRepository.findByMeetingIdAndStatus(meetingId, status)
                : sessionRepository.findByMeetingId(meetingId);
        return sessions.stream()
                .map(SessionResponse::from)
                .toList();
    }

    @Transactional
    public SessionResponse createSession(Long meetingId, SessionCreateRequest request) {
        MeetingSession session = MeetingSession.create(
                meetingId,
                request.getTitle(),
                request.getLocation(),
                request.getScheduledAt()
        );
        return SessionResponse.from(sessionRepository.save(session));
    }

    public SessionResponse getSession(Long sessionId) {
        MeetingSession session = findSessionById(sessionId);
        return SessionResponse.from(session);
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

        session.update(request.getTitle(), request.getLocation(), request.getScheduledAt());
        return SessionResponse.from(session);
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
        return SessionResponse.from(session);
    }

    private MeetingSession findSessionById(Long sessionId) {
        return sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND));
    }
}
