package com.workmaite.global.auth;

import com.workmaite.domain.agendas.repository.AgendaRepository;
import com.workmaite.domain.meetings.entity.MeetingMember;
import com.workmaite.domain.meetings.entity.MeetingMemberRole;
import com.workmaite.domain.meetings.repository.MeetingMemberRepository;
import com.workmaite.domain.meetings.repository.MeetingRepository;
import com.workmaite.domain.reports.repository.ReportRepository;
import com.workmaite.domain.sessions.repository.SessionRepository;
import com.workmaite.domain.user.entity.User;
import com.workmaite.domain.user.entity.UserRole;
import com.workmaite.domain.user.repository.UserRepository;
import com.workmaite.global.exception.BusinessException;
import com.workmaite.global.exception.ErrorCode;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

/**
 * 회의체 인가 가드 (P1-4, SEC-5 IDOR 차단).
 *
 * <p>두 권한 축을 결합한다: 조직 권한 company_role(SYSTEM_ADMIN/COMPANY_ADMIN/USER)과 회의체 권한 meeting_role(간사
 * admin/참여자 member). 회사 귀속 = meetings.created_by의 회사이며, 세션·아젠다·회의록·보고서는 소속 회의체의 회사를 상속한다.
 *
 * <ul>
 *   <li>{@link #requireView}: SYSTEM_ADMIN | (COMPANY_ADMIN & 자사가 참여한 회의체) | 멤버
 *   <li>{@link #requireMeetingEdit}: SYSTEM_ADMIN | (COMPANY_ADMIN & 자사 소유 회의체) | 간사 — 회의체 하위 전체 편집
 *   <li>{@link #requireOwnedEdit}: 위 + 소유자 본인 — 참여자는 자신의 것만
 * </ul>
 *
 * <p>레거시 {@link #requireMember}/{@link #requireAdmin} 계열은 하위 호환으로 유지한다.
 */
@Component
@RequiredArgsConstructor
public class MeetingAccessGuard {

  private final MeetingMemberRepository meetingMemberRepository;
  private final SessionRepository sessionRepository;
  private final ReportRepository reportRepository;
  private final AgendaRepository agendaRepository;
  private final MeetingRepository meetingRepository;
  private final UserRepository userRepository;

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
    if (!meetingMemberRepository.existsByMeetingIdAndUserIdAndMeetingRole(
        meetingId, userId, MeetingMemberRole.ADMIN)) {
      throw new BusinessException(ErrorCode.MEETING_ACCESS_DENIED);
    }
  }

  /** 세션 ID로 소속 회의체 멤버십 검증 */
  public void requireMemberBySession(Long sessionId) {
    Long meetingId =
        sessionRepository
            .findById(sessionId)
            .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND))
            .getMeetingId();
    requireMember(meetingId);
  }

  /** 보고서 ID로 소속 회의체 멤버십 검증 */
  public void requireMemberByReport(Long reportId) {
    Long meetingId =
        reportRepository
            .findById(reportId)
            .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND))
            .getMeetingId();
    requireMember(meetingId);
  }

  /** 아젠다 ID로 소속 회의체 멤버십 검증 */
  public void requireMemberByAgenda(Long agendaId) {
    Long meetingId =
        agendaRepository
            .findById(agendaId)
            .orElseThrow(() -> new BusinessException(ErrorCode.AGENDA_NOT_FOUND))
            .getMeetingId();
    requireMember(meetingId);
  }

  // ───────────────────── 회사/소유 결합 인가 (company_role × meeting_role) ─────────────────────

  private User caller() {
    return userRepository
        .findById(CurrentUser.id())
        .orElseThrow(() -> new BusinessException(ErrorCode.USER_NOT_FOUND));
  }

  /** 회의체 소유 회사 = 생성자(created_by)의 회사. 생성자/회사가 없으면 null. */
  private Long meetingCompanyId(Long meetingId) {
    Long creatorId =
        meetingRepository
            .findById(meetingId)
            .orElseThrow(() -> new BusinessException(ErrorCode.MEETING_NOT_FOUND))
            .getCreatedBy();
    if (creatorId == null) return null;
    return userRepository.findById(creatorId).map(User::getCompanyId).orElse(null);
  }

  /** 호출자 회사가 해당 회의체에 멤버를 한 명이라도 갖는가 (회사 관리자 조회 범위). */
  private boolean companyParticipatesIn(Long meetingId, Long companyId) {
    if (companyId == null) return false;
    List<Long> memberIds =
        meetingMemberRepository.findByMeetingId(meetingId).stream()
            .map(MeetingMember::getUserId)
            .toList();
    if (memberIds.isEmpty()) return false;
    return userRepository.findAllById(memberIds).stream()
        .anyMatch(u -> companyId.equals(u.getCompanyId()));
  }

  /** 회의체 전체 편집 권한 보유 여부: 시스템관리자 | (회사관리자 & 자사 소유 회의체) | 간사. */
  private boolean canEditMeeting(User c, Long meetingId) {
    if (c.getCompanyRole() == UserRole.SYSTEM_ADMIN) return true;
    if (c.getCompanyRole() == UserRole.COMPANY_ADMIN
        && c.getCompanyId() != null
        && c.getCompanyId().equals(meetingCompanyId(meetingId))) return true;
    return meetingMemberRepository.existsByMeetingIdAndUserIdAndMeetingRole(
        meetingId, c.getId(), MeetingMemberRole.ADMIN);
  }

  /** 조회 권한: 시스템관리자 | (회사관리자 & 자사가 참여한 회의체) | 멤버. */
  public void requireView(Long meetingId) {
    User c = caller();
    if (c.getCompanyRole() == UserRole.SYSTEM_ADMIN) return;
    if (c.getCompanyRole() == UserRole.COMPANY_ADMIN
        && companyParticipatesIn(meetingId, c.getCompanyId())) return;
    if (meetingMemberRepository.existsByMeetingIdAndUserId(meetingId, c.getId())) return;
    throw new BusinessException(ErrorCode.ACCESS_DENIED);
  }

  /** 회의체 하위 전체 편집 권한 요구 (간사/회사관리자/시스템관리자). */
  public void requireMeetingEdit(Long meetingId) {
    if (!canEditMeeting(caller(), meetingId)) {
      throw new BusinessException(ErrorCode.MEETING_ACCESS_DENIED);
    }
  }

  /** 소유물 편집 권한 요구: 회의체 전체 편집 권한자 | 소유자 본인(참여자는 자신의 것만). */
  public void requireOwnedEdit(Long meetingId, Long ownerId) {
    User c = caller();
    if (canEditMeeting(c, meetingId)) return;
    if (ownerId != null && ownerId.equals(c.getId())) return;
    throw new BusinessException(ErrorCode.ACCESS_DENIED);
  }

  /** 세션 ID로 조회 권한 검증. */
  public void requireViewBySession(Long sessionId) {
    requireView(meetingIdOfSession(sessionId));
  }

  /** 보고서 ID로 조회 권한 검증. */
  public void requireViewByReport(Long reportId) {
    requireView(meetingIdOfReport(reportId));
  }

  /** 세션 → 소속 회의체 id. */
  public Long meetingIdOfSession(Long sessionId) {
    return sessionRepository
        .findById(sessionId)
        .orElseThrow(() -> new BusinessException(ErrorCode.SESSION_NOT_FOUND))
        .getMeetingId();
  }

  /** 보고서 → 소속 회의체 id. */
  public Long meetingIdOfReport(Long reportId) {
    return reportRepository
        .findById(reportId)
        .orElseThrow(() -> new BusinessException(ErrorCode.REPORT_NOT_FOUND))
        .getMeetingId();
  }
}
