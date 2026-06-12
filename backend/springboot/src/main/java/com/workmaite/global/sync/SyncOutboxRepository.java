package com.workmaite.global.sync;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface SyncOutboxRepository extends JpaRepository<SyncOutbox, Long> {

    List<SyncOutbox> findTop50ByStatusOrderByIdAsc(String status);
}
