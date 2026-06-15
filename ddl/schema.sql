CREATE TABLE "agenda" (
  "id" bigserial NOT NULL,
  "meeting_id" bigint NOT NULL,
  "session_id" bigint,
  "title" character varying(255) NOT NULL,
  "status" character varying(20) DEFAULT 'draft'::character varying,
  "assignee_id" bigint,
  "department" jsonb,
  "due_date" timestamp without time zone,
  "priority" character varying(20) DEFAULT 'medium'::character varying,
  "created_at" timestamp without time zone DEFAULT now(),
  "ai_evidence" text,
  CONSTRAINT "agenda_pkey" PRIMARY KEY (id)
);

CREATE TABLE "agent_logs" (
  "id" bigserial NOT NULL,
  "task_id" character varying(100) NOT NULL,
  "context_type" character varying(30) NOT NULL,
  "meeting_id" bigint,
  "session_id" bigint,
  "user_id" bigint,
  "status" character varying(20) DEFAULT 'pending'::character varying,
  "input_data" jsonb,
  "output_data" jsonb,
  "reasoning_steps" jsonb,
  "loop_count" integer DEFAULT 0,
  "error_message" text,
  "ended_at" timestamp without time zone,
  "created_at" timestamp without time zone DEFAULT now(),
  "trace_id" character varying(64),
  CONSTRAINT "agent_logs_pkey" PRIMARY KEY (id),
  CONSTRAINT "agent_logs_task_id_key" UNIQUE (task_id)
);

CREATE TABLE "audit_logs" (
  "id" bigserial NOT NULL,
  "actor_id" bigint,
  "action" character varying(40) NOT NULL,
  "entity_type" character varying(40) NOT NULL,
  "entity_id" bigint,
  "meeting_id" bigint,
  "detail" jsonb,
  "ip_addr" character varying(45),
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "audit_logs_pkey" PRIMARY KEY (id)
);

CREATE TABLE "chat_feedback" (
  "id" bigserial NOT NULL,
  "user_id" bigint NOT NULL,
  "thread_id" character varying(100) NOT NULL,
  "message_id" bigint,
  "agent_log_id" bigint,
  "rating" smallint NOT NULL,
  "reason" text,
  "content_snippet" text,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "chat_feedback_pkey" PRIMARY KEY (id)
);

CREATE TABLE "chat_messages" (
  "id" bigserial NOT NULL,
  "thread_id" character varying(100) NOT NULL,
  "user_id" bigint NOT NULL,
  "role" character varying(10) NOT NULL,
  "content" text,
  "file_path" character varying(500),
  "file_name" character varying(255),
  "context_type" character varying(20),
  "meeting_id" bigint,
  "session_id" bigint,
  "created_at" timestamp without time zone DEFAULT now(),
  CONSTRAINT "chat_messages_pkey" PRIMARY KEY (id)
);

CREATE TABLE "companies" (
  "id" bigserial NOT NULL,
  "name" character varying(100) NOT NULL,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "companies_pkey" PRIMARY KEY (id),
  CONSTRAINT "companies_name_key" UNIQUE (name)
);

CREATE TABLE "hitl_reviews" (
  "id" bigserial NOT NULL,
  "agent_log_id" bigint,
  "target_type" character varying(30) NOT NULL,
  "ai_rationale" text,
  "status" character varying(20) DEFAULT 'pending'::character varying,
  "reviewer_id" bigint,
  "reviewed_at" timestamp without time zone,
  "created_at" timestamp without time zone DEFAULT now(),
  "agenda_id" bigint,
  "report_id" bigint,
  "comment" text,
  CONSTRAINT "hitl_reviews_pkey" PRIMARY KEY (id)
);

CREATE TABLE "meeting_members" (
  "id" bigserial NOT NULL,
  "meeting_id" bigint NOT NULL,
  "user_id" bigint NOT NULL,
  "role" character varying(20) NOT NULL,
  "priority" character varying(20) DEFAULT 'medium'::character varying,
  CONSTRAINT "meeting_members_pkey" PRIMARY KEY (id),
  CONSTRAINT "uq_meeting_members" UNIQUE (meeting_id, user_id)
);

CREATE TABLE "meeting_sessions" (
  "id" bigserial NOT NULL,
  "meeting_id" bigint NOT NULL,
  "title" character varying(255),
  "description" character varying(255),
  "location" character varying(255),
  "type" character varying(50) NOT NULL,
  "scheduled_at" timestamp without time zone,
  "started_at" timestamp without time zone,
  "ended_at" timestamp without time zone,
  "status" character varying(20) DEFAULT 'scheduled'::character varying,
  "context" text,
  "recording_seconds" bigint DEFAULT 0 NOT NULL,
  "last_resumed_at" timestamp without time zone,
  CONSTRAINT "meeting_sessions_pkey" PRIMARY KEY (id)
);

CREATE TABLE "meetings" (
  "id" bigserial NOT NULL,
  "title" character varying(255) NOT NULL,
  "description" text,
  "guidelines" text,
  "type" character varying(20),
  "start_date" timestamp without time zone,
  "end_date" timestamp without time zone,
  "status" character varying(20) DEFAULT 'active'::character varying,
  "created_by" bigint,
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "context" text,
  CONSTRAINT "meetings_pkey" PRIMARY KEY (id)
);

CREATE TABLE "minutes" (
  "id" bigserial NOT NULL,
  "session_id" bigint NOT NULL,
  "file_name" character varying(255),
  "file_path" character varying(500),
  "recorder_id" bigint,
  "content_original" text,
  "content_summary" text,
  "status" character varying(20) DEFAULT 'draft'::character varying,
  "generated_at" timestamp without time zone DEFAULT now(),
  CONSTRAINT "minutes_pkey" PRIMARY KEY (id),
  CONSTRAINT "minutes_session_id_key" UNIQUE (session_id)
);

CREATE TABLE "neo4j_sync_outbox" (
  "id" bigserial NOT NULL,
  "entity_type" character varying(30) NOT NULL,
  "entity_id" bigint NOT NULL,
  "op" character varying(10) NOT NULL,
  "payload" jsonb,
  "status" character varying(15) DEFAULT 'pending'::character varying NOT NULL,
  "retry_count" integer DEFAULT 0 NOT NULL,
  "last_error" text,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  "processed_at" timestamp without time zone,
  CONSTRAINT "neo4j_sync_outbox_pkey" PRIMARY KEY (id)
);

CREATE TABLE "refresh_tokens" (
  "id" bigserial NOT NULL,
  "user_id" bigint NOT NULL,
  "token_hash" character varying(64) NOT NULL,
  "expires_at" timestamp without time zone NOT NULL,
  "created_at" timestamp without time zone DEFAULT now() NOT NULL,
  CONSTRAINT "refresh_tokens_pkey" PRIMARY KEY (id),
  CONSTRAINT "refresh_tokens_token_hash_key" UNIQUE (token_hash)
);

CREATE TABLE "report_agendas" (
  "report_id" bigint NOT NULL,
  "agenda_id" bigint NOT NULL,
  CONSTRAINT "report_agendas_pkey" PRIMARY KEY (report_id, agenda_id)
);

CREATE TABLE "report_scores" (
  "id" bigserial NOT NULL,
  "report_id" bigint NOT NULL,
  "ai_status" character varying(20) DEFAULT 'pending'::character varying NOT NULL,
  "total_score" double precision,
  "detail_scores" jsonb,
  "feedback" text,
  "created_at" timestamp without time zone DEFAULT now(),
  CONSTRAINT "report_scores_pkey" PRIMARY KEY (id)
);

CREATE TABLE "reports" (
  "id" bigserial NOT NULL,
  "meeting_id" bigint NOT NULL,
  "parent_id" bigint,
  "upload_id" bigint NOT NULL,
  "version" integer DEFAULT 1 NOT NULL,
  "submitter_department" character varying(255) NOT NULL,
  "file_name" character varying(255),
  "file_path" character varying(500),
  "human_status" character varying(20) DEFAULT 'pending'::character varying,
  "created_at" timestamp without time zone DEFAULT now(),
  "related_agenda_ids" jsonb DEFAULT '[]'::jsonb,
  CONSTRAINT "ck_reports_human_status" CHECK (((human_status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying])::text[]))),
  CONSTRAINT "reports_pkey" PRIMARY KEY (id)
);

CREATE TABLE "session_members" (
  "id" bigserial NOT NULL,
  "session_id" bigint NOT NULL,
  "user_id" bigint NOT NULL,
  "role" character varying(20) DEFAULT 'member'::character varying,
  CONSTRAINT "session_members_pkey" PRIMARY KEY (id),
  CONSTRAINT "uq_session_members" UNIQUE (session_id, user_id)
);

CREATE TABLE "session_summary_blocks" (
  "id" bigserial NOT NULL,
  "session_id" bigint NOT NULL,
  "block_index" integer NOT NULL,
  "title" character varying(500),
  "bullets" jsonb,
  "created_at" timestamp without time zone DEFAULT now(),
  "recording_start_sec" double precision,
  "recording_end_sec" double precision,
  CONSTRAINT "session_summary_blocks_pkey" PRIMARY KEY (id)
);

CREATE TABLE "stt_segments" (
  "id" bigserial NOT NULL,
  "session_id" bigint NOT NULL,
  "speaker_label" character varying(50) NOT NULL,
  "speaker_user_id" bigint,
  "content" text NOT NULL,
  "start_sec" double precision NOT NULL,
  "end_sec" double precision NOT NULL,
  "confidence" double precision,
  "created_at" timestamp without time zone DEFAULT now(),
  "provider" character varying(30),
  CONSTRAINT "stt_segments_pkey" PRIMARY KEY (id)
);

CREATE TABLE "token_usage_logs" (
  "id" bigserial NOT NULL,
  "agent_log_id" bigint NOT NULL,
  "model_name" character varying(50) NOT NULL,
  "prompt_tokens" integer NOT NULL,
  "completion_tokens" integer NOT NULL,
  "estimated_cost_usd" double precision,
  "created_at" timestamp without time zone DEFAULT now(),
  CONSTRAINT "token_usage_logs_pkey" PRIMARY KEY (id)
);

CREATE TABLE "users" (
  "id" bigserial NOT NULL,
  "name" character varying(100) NOT NULL,
  "email" character varying(255) NOT NULL,
  "password_hash" character varying(255) NOT NULL,
  "department" character varying(100),
  "position" character varying(100),
  "created_at" timestamp without time zone DEFAULT now(),
  "updated_at" timestamp without time zone DEFAULT now(),
  "role" character varying(30) DEFAULT 'USER'::character varying NOT NULL,
  "company_id" bigint,
  "must_change_password" boolean DEFAULT false NOT NULL,
  "is_active" boolean DEFAULT true NOT NULL,
  CONSTRAINT "users_pkey" PRIMARY KEY (id),
  CONSTRAINT "users_email_key" UNIQUE (email)
);


CREATE TABLE "session_agendas" (
  "session_id" bigint NOT NULL,
  "agenda_id" bigint NOT NULL,
  CONSTRAINT "session_agendas_pkey" PRIMARY KEY (session_id, agenda_id),
  CONSTRAINT "session_agendas_session_id_fkey" FOREIGN KEY (session_id) REFERENCES "meeting_sessions" (id) ON DELETE CASCADE,
  CONSTRAINT "session_agendas_agenda_id_fkey" FOREIGN KEY (agenda_id) REFERENCES "agenda" (id) ON DELETE CASCADE
);


-- 그래프 수동 관계 (구조 FK 외 자유 관계). 소스 오브 트루스=PG, Neo4j에 동기화.
CREATE TABLE "graph_relations" (
  "id" bigserial NOT NULL,
  "from_node_id" text NOT NULL,
  "rel_type" text NOT NULL,
  "to_node_id" text NOT NULL,
  "created_by" bigint,
  "created_at" timestamp DEFAULT now() NOT NULL,
  CONSTRAINT "graph_relations_pkey" PRIMARY KEY (id),
  CONSTRAINT "uq_graph_relations" UNIQUE (from_node_id, rel_type, to_node_id),
  CONSTRAINT "graph_relations_created_by_fkey" FOREIGN KEY (created_by) REFERENCES "users" (id)
);
CREATE INDEX "idx_graph_relations_from" ON "graph_relations" (from_node_id);
CREATE INDEX "idx_graph_relations_to" ON "graph_relations" (to_node_id);