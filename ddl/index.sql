-- Indexes (non-constraint)

CREATE INDEX idx_agenda_meeting_status ON public.agenda USING btree (meeting_id, status);

CREATE INDEX idx_agenda_session ON public.agenda USING btree (session_id);

CREATE INDEX idx_agent_logs_meeting ON public.agent_logs USING btree (meeting_id, created_at);

CREATE INDEX idx_agent_logs_context ON public.agent_logs USING btree (context_type, created_at);

CREATE INDEX idx_audit_logs_actor ON public.audit_logs USING btree (actor_id, created_at);

CREATE INDEX idx_audit_logs_entity ON public.audit_logs USING btree (entity_type, entity_id);

CREATE INDEX idx_chat_feedback_thread ON public.chat_feedback USING btree (thread_id, created_at);

CREATE INDEX idx_chat_messages_thread ON public.chat_messages USING btree (thread_id, created_at);

CREATE INDEX idx_hitl_reviews_report ON public.hitl_reviews USING btree (report_id);

CREATE INDEX idx_hitl_reviews_agenda ON public.hitl_reviews USING btree (agenda_id);

CREATE INDEX idx_meeting_members_meeting ON public.meeting_members USING btree (meeting_id);

CREATE INDEX idx_meeting_members_user ON public.meeting_members USING btree (user_id);

CREATE INDEX idx_meeting_sessions_meeting ON public.meeting_sessions USING btree (meeting_id, status);

CREATE INDEX idx_minutes_session ON public.minutes USING btree (session_id);

CREATE INDEX idx_sync_outbox_pending ON public.neo4j_sync_outbox USING btree (status, created_at) WHERE ((status)::text <> 'done'::text);

CREATE INDEX idx_refresh_tokens_user ON public.refresh_tokens USING btree (user_id);

CREATE INDEX idx_report_agendas_agenda ON public.report_agendas USING btree (agenda_id);

CREATE INDEX idx_report_scores_report ON public.report_scores USING btree (report_id);

CREATE INDEX idx_reports_meeting ON public.reports USING btree (meeting_id);

CREATE INDEX idx_reports_parent ON public.reports USING btree (parent_id);

CREATE INDEX idx_session_members_session ON public.session_members USING btree (session_id);

CREATE INDEX idx_stt_segments_session ON public.stt_segments USING btree (session_id, start_sec);

CREATE INDEX idx_token_usage_agent_log ON public.token_usage_logs USING btree (agent_log_id);