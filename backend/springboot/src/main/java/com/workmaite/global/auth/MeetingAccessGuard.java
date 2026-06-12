package com.workmaite.global.auth;

import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 회의체 멤버십 인가 가드 (P1-4, SEC-5 IDOR 차단).
 * "ID만 알면 타인 회의체 데이터 접근 가능" 문제를 막기 위해
 * 모든 도메인 서비스가 조회/변경 전에 호출한다.
 * SYSTEM_ADMIN은 전체 통과, 그 외에는 meeting_members 멤버십을 요구한다.
 */
@Component
@RequiredArgsConstructor
public class MeetingAccessGuard {

    private final MeetingMemberRepository meetingMemberRepository;
    private final SessionRepository sessionRepository;
    private final ReportRepository reportRepository;
    private final AgendaRepository agendaRepository;

    /** 현재 사용자가 회의체 멤버인지 검증 */
    public void requireMember(Long meetingId) {
        if (CurrentUser.isSystemAdmin()) {
            return;
        }
        Long userId = CurrentUser.id();
        if (!meetingMemberRepository.existsByMeetingIdAndUserId(meetingId, userId)) {
            throw new BusinessException(ErrorCode.ACCESS_DENIED);
        }
    }

    /** 현재 사용자가 회의체 간사(admin)인지 검증 */
    public void requireAdmin(Long meetingId) {
        if (CurrentUser.isSystemAdmin()) {
            return;
        }
        Long userId = CurrentUser.id();
        if (!meetingMemberRepository.existsByMeetingIdAndUserIdAndRole(
                meetingId, userId, MeetingMemberRole.ADMIN)) {
            throw new BusinessException(ErrorCode.MEETING_ACCESS_DENIED);
        }
    }

    /** 세션 ID로 소속 회의체 멤버십 검증 */
    public void requireMemberBySession(Long sessionId) {
        Long meetingId = sessionRepository.findById(sessionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND))
                .getMeetingId();
        requireMember(meetingId);
    }

    /** 보고서 ID로 소속 회의체 멤버십 검증 */
    public void requireMemberByReport(Long reportId) {
        Long meetingId = reportRepository.findById(reportId)
                .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND))
                .getMeetingId();
        requireMember(meetingId);
    }

    /** 아젠다 ID로 소속 회의체 멤버십 검증 */
    public void requireMemberByAgenda(Long agendaId) {
        Long meetingId = agendaRepository.findById(agendaId)
                .orElseThrow(() -> new BusinessException(ErrorCode.AGENDA_NOT_FOUND))
                .getMeetingId();
        requireMember(meetingId);
    }
}
