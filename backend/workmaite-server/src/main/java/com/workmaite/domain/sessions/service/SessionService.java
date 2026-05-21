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

    private MeetingSession findSessionById(Long sessionId) {
        return sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND));
    }
}
