
-- Foreign keys

ALTER TABLE "agenda" ADD CONSTRAINT "agenda_assignee_id_fkey" FOREIGN KEY (assignee_id) REFERENCES users(id);

ALTER TABLE "agenda" ADD CONSTRAINT "agenda_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "agenda" ADD CONSTRAINT "agenda_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "agent_logs" ADD CONSTRAINT "agent_logs_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "agent_logs" ADD CONSTRAINT "agent_logs_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "agent_logs" ADD CONSTRAINT "agent_logs_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_actor_id_fkey" FOREIGN KEY (actor_id) REFERENCES users(id);

ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_agent_log_id_fkey" FOREIGN KEY (agent_log_id) REFERENCES agent_logs(id);

ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_message_id_fkey" FOREIGN KEY (message_id) REFERENCES chat_messages(id);

ALTER TABLE "chat_feedback" ADD CONSTRAINT "chat_feedback_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE "chat_messages" ADD CONSTRAINT "chat_messages_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "chat_messages" ADD CONSTRAINT "chat_messages_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "chat_messages" ADD CONSTRAINT "chat_messages_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE "hitl_reviews" ADD CONSTRAINT "hitl_reviews_agenda_id_fkey" FOREIGN KEY (agenda_id) REFERENCES agenda(id) ON DELETE SET NULL;

ALTER TABLE "hitl_reviews" ADD CONSTRAINT "hitl_reviews_agent_log_id_fkey" FOREIGN KEY (agent_log_id) REFERENCES agent_logs(id);

ALTER TABLE "hitl_reviews" ADD CONSTRAINT "hitl_reviews_report_id_fkey" FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE SET NULL;

ALTER TABLE "hitl_reviews" ADD CONSTRAINT "hitl_reviews_reviewer_id_fkey" FOREIGN KEY (reviewer_id) REFERENCES users(id);

ALTER TABLE "meeting_members" ADD CONSTRAINT "meeting_members_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "meeting_members" ADD CONSTRAINT "meeting_members_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id);

ALTER TABLE "meeting_sessions" ADD CONSTRAINT "meeting_sessions_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "meetings" ADD CONSTRAINT "meetings_created_by_fkey" FOREIGN KEY (created_by) REFERENCES users(id);

ALTER TABLE "minutes" ADD CONSTRAINT "minutes_recorder_id_fkey" FOREIGN KEY (recorder_id) REFERENCES users(id);

ALTER TABLE "minutes" ADD CONSTRAINT "minutes_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "refresh_tokens" ADD CONSTRAINT "refresh_tokens_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE "report_agendas" ADD CONSTRAINT "report_agendas_agenda_id_fkey" FOREIGN KEY (agenda_id) REFERENCES agenda(id) ON DELETE CASCADE;

ALTER TABLE "report_agendas" ADD CONSTRAINT "report_agendas_report_id_fkey" FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE;

ALTER TABLE "report_scores" ADD CONSTRAINT "report_scores_report_id_fkey" FOREIGN KEY (report_id) REFERENCES reports(id);

ALTER TABLE "reports" ADD CONSTRAINT "reports_meeting_id_fkey" FOREIGN KEY (meeting_id) REFERENCES meetings(id);

ALTER TABLE "reports" ADD CONSTRAINT "reports_parent_id_fkey" FOREIGN KEY (parent_id) REFERENCES reports(id);

ALTER TABLE "reports" ADD CONSTRAINT "reports_upload_id_fkey" FOREIGN KEY (upload_id) REFERENCES users(id);

ALTER TABLE "session_members" ADD CONSTRAINT "session_members_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id) ON DELETE CASCADE;

ALTER TABLE "session_members" ADD CONSTRAINT "session_members_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE "session_summary_blocks" ADD CONSTRAINT "session_summary_blocks_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "stt_segments" ADD CONSTRAINT "stt_segments_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id);

ALTER TABLE "stt_segments" ADD CONSTRAINT "stt_segments_speaker_user_id_fkey" FOREIGN KEY (speaker_user_id) REFERENCES users(id);

ALTER TABLE "token_usage_logs" ADD CONSTRAINT "token_usage_logs_agent_log_id_fkey" FOREIGN KEY (agent_log_id) REFERENCES agent_logs(id);

ALTER TABLE "users" ADD CONSTRAINT "users_company_id_fkey" FOREIGN KEY (company_id) REFERENCES companies(id);

ALTER TABLE "session_agendas" ADD CONSTRAINT "session_agendas_session_id_fkey" FOREIGN KEY (session_id) REFERENCES meeting_sessions(id) ON DELETE CASCADE;

ALTER TABLE "session_agendas" ADD CONSTRAINT "session_agendas_agenda_id_fkey" FOREIGN KEY (agenda_id) REFERENCES agenda(id) ON DELETE CASCADE;
