package com.workmaite.global.sync;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SyncOutboxRepository extends JpaRepository<SyncOutbox, Long> {

  List<SyncOutbox> findTop50ByStatusOrderByIdAsc(String status);
}
