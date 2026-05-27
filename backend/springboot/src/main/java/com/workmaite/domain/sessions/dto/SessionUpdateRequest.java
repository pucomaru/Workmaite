package com.workmaite.domain.sessions.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@NoArgsConstructor
public class SessionUpdateRequest {

    private String title;

    private String location;

    private LocalDateTime scheduledAt;
}
