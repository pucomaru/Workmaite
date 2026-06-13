package com.workmaite.domain.user.entity;

/**
 * 시스템 수준 역할 (RBAC, P1-3). 회의체 수준 권한(간사/구성원)은 meeting_members.role을 사용한다. - USER: 일반 사용자 -
 * SYSTEM_ADMIN: 전체 회의체 조회 등 운영 권한 (DB에서 직접 부여) - COMPANY_ADMIN: 자기 회사 구성원 관리 (P1-7 멀티테넌시에서 사용 예정)
 */
public enum UserRole {
  USER,
  SYSTEM_ADMIN,
  COMPANY_ADMIN
}
