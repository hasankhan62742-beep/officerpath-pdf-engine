-- OfficerPath AI — Alembic 0001-0009 applied to LIVE via SQL Editor.
-- Generated 2026-11-23 on the VM: real `alembic upgrade head` run
-- against a local Postgres 16 scratch DB seeded with the live
-- documents/jobs tables (015 + 018 + 019), then pg_dumped.
-- Contains: alembic_version table, 27 engine tables (0001-0009),
-- 13 subject seeds + 1 PPSC marking-config seed, and the version row.
-- It does NOT touch documents/jobs (already live via 015/017/018/019).
-- Run as ONE query. On ANY error: stop, report the error, do not re-run.

--
--






--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
--

--
--




--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--



--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--





--
-- Name: answer_evidence; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answer_evidence (
    id uuid NOT NULL,
    answer_id uuid NOT NULL,
    source_type character varying(32) NOT NULL,
    source_id uuid,
    value_original character varying(64),
    value_normalized character varying(16),
    page_number integer,
    bbox jsonb,
    detector character varying(64),
    detector_confidence double precision,
    artifact_ref text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: answer_sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.answer_sources (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    source_type character varying(32) NOT NULL,
    title character varying(256),
    page_numbers jsonb,
    bbox jsonb,
    raw_text text,
    detector character varying(64),
    detector_confidence double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id uuid NOT NULL,
    user_id uuid,
    document_id uuid,
    action character varying(64) NOT NULL,
    target_type character varying(32),
    target_id uuid,
    detail jsonb,
    correlation_id character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_pages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_pages (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    page_number integer NOT NULL,
    classification character varying(16) NOT NULL,
    classification_method character varying(32) NOT NULL,
    classification_confidence double precision,
    width_px integer,
    height_px integer,
    dpi_estimate double precision,
    rotation_degrees integer,
    skew_degrees double precision,
    blur_score double precision,
    noise_score double precision,
    contrast_score double precision,
    has_text_layer boolean,
    original_render_path text,
    processed_render_path text,
    preprocessing_applied jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    layout_applied jsonb
);


--
-- Name: extracted_answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extracted_answers (
    id uuid NOT NULL,
    question_id uuid NOT NULL,
    document_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    resolved_label character varying(16),
    resolution_method character varying(64),
    resolution_score double precision,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: extracted_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extracted_questions (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    job_id uuid,
    question_number character varying(32),
    original_text text NOT NULL,
    normalized_text text NOT NULL,
    source_pages jsonb,
    bbox jsonb,
    extraction_method character varying(64),
    rule_set_version character varying(32),
    ocr_confidence double precision,
    extraction_confidence double precision,
    validation_status character varying(32) DEFAULT 'unreviewed'::character varying NOT NULL,
    content_fingerprint character varying(64),
    duplicate_of_id uuid,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: extraction_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extraction_reports (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    job_id uuid,
    rule_set_version character varying(32),
    pages_processed integer DEFAULT 0 NOT NULL,
    pages_failed integer DEFAULT 0 NOT NULL,
    questions_extracted integer DEFAULT 0 NOT NULL,
    questions_missing_options integer DEFAULT 0 NOT NULL,
    uncertain_answers integer DEFAULT 0 NOT NULL,
    conflicting_answers integer DEFAULT 0 NOT NULL,
    unmatched_key_entries integer DEFAULT 0 NOT NULL,
    duplicates_found integer DEFAULT 0 NOT NULL,
    engine_disagreements integer DEFAULT 0 NOT NULL,
    requires_review boolean DEFAULT false NOT NULL,
    review_reasons jsonb,
    summary jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: manual_corrections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.manual_corrections (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    user_id uuid NOT NULL,
    target_type character varying(32) NOT NULL,
    field_name character varying(64) NOT NULL,
    target_id uuid NOT NULL,
    old_value text,
    new_value text,
    reason text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: marking_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.marking_configs (
    id uuid NOT NULL,
    name text NOT NULL,
    correct_marks double precision DEFAULT '1'::double precision NOT NULL,
    incorrect_marks double precision DEFAULT '-0.25'::double precision NOT NULL,
    unattempted_marks double precision DEFAULT '0'::double precision NOT NULL,
    is_default boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    type character varying(32) NOT NULL,
    title character varying(200) NOT NULL,
    body text NOT NULL,
    link character varying(500),
    is_read boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_notification_type CHECK (((type)::text = ANY ((ARRAY['upload_done'::character varying, 'upload_failed'::character varying, 'review_needed'::character varying, 'test_submitted'::character varying, 'result_ready'::character varying, 'subscription_change'::character varying])::text[])))
);


--
-- Name: ocr_blocks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ocr_blocks (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    page_id uuid,
    page_number integer NOT NULL,
    engine character varying(32) NOT NULL,
    engine_version character varying(32),
    language character varying(16),
    text text NOT NULL,
    bbox_x_min double precision,
    bbox_y_min double precision,
    bbox_x_max double precision,
    bbox_y_max double precision,
    reading_order integer,
    confidence double precision,
    word_confidences jsonb,
    style jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: processing_errors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processing_errors (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    job_id uuid,
    page_number integer,
    stage character varying(32),
    error_code character varying(64) NOT NULL,
    message text NOT NULL,
    detail jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: processing_stages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.processing_stages (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    job_id uuid,
    page_number integer,
    stage character varying(32) NOT NULL,
    status character varying(16) NOT NULL,
    detail jsonb,
    error_code character varying(64),
    error_message text,
    correlation_id character varying(64),
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: question_assets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_assets (
    id uuid NOT NULL,
    question_id uuid NOT NULL,
    document_id uuid NOT NULL,
    asset_type character varying(32) NOT NULL,
    storage_path text NOT NULL,
    bbox jsonb,
    page_number integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: question_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_options (
    id uuid NOT NULL,
    question_id uuid NOT NULL,
    original_label character varying(16),
    normalized_label character varying(16),
    label_inferred boolean DEFAULT false NOT NULL,
    original_text text NOT NULL,
    normalized_text text NOT NULL,
    bbox jsonb,
    "position" integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: question_subjects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.question_subjects (
    id uuid NOT NULL,
    question_id uuid NOT NULL,
    subject_id uuid,
    topic_id uuid,
    assigned_by uuid NOT NULL,
    confidence character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: review_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_history (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    reviewer_id uuid NOT NULL,
    target_type character varying(32) NOT NULL,
    target_id uuid NOT NULL,
    decision character varying(32) NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: rule_set_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rule_set_versions (
    id uuid NOT NULL,
    name character varying(64) NOT NULL,
    version character varying(32) NOT NULL,
    rules jsonb NOT NULL,
    active boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: student_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.student_profiles (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    full_name text NOT NULL,
    phone text,
    preferred_exam text,
    education_level text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: student_question_collections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.student_question_collections (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    question_id uuid NOT NULL,
    collection_type character varying(32) NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_collection_type CHECK (((collection_type)::text = ANY ((ARRAY['bookmark'::character varying, 'mistake'::character varying, 'custom'::character varying])::text[])))
);


--
-- Name: student_responses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.student_responses (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    user_id uuid NOT NULL,
    selected_index integer,
    marked_for_review boolean DEFAULT false NOT NULL,
    answered_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: subjects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subjects (
    id uuid NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: test_question_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_question_snapshots (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    question_id uuid,
    "position" integer NOT NULL,
    question_text text NOT NULL,
    options json NOT NULL,
    correct_index integer NOT NULL,
    answer_source character varying(64),
    source_document_id uuid,
    source_page integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: test_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_results (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    user_id uuid NOT NULL,
    total_questions integer NOT NULL,
    correct_count integer NOT NULL,
    incorrect_count integer NOT NULL,
    unattempted_count integer NOT NULL,
    unknown_count integer DEFAULT 0 NOT NULL,
    total_marks numeric(10,2) NOT NULL,
    max_marks numeric(10,2) NOT NULL,
    percentage numeric(5,2) NOT NULL,
    time_taken_seconds integer NOT NULL,
    subject_breakdown json,
    topic_breakdown json,
    marking_config_id uuid NOT NULL,
    submitted_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: test_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_sessions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    template_id uuid,
    title text NOT NULL,
    question_count integer NOT NULL,
    marking_config_id uuid NOT NULL,
    status character varying(32) DEFAULT 'created'::character varying NOT NULL,
    started_at timestamp with time zone,
    submitted_at timestamp with time zone,
    expires_at timestamp with time zone,
    time_limit_seconds integer,
    server_started_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: test_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_templates (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    name text NOT NULL,
    description text,
    question_count integer NOT NULL,
    source_type character varying(32) NOT NULL,
    source_ids json,
    allow_repetition boolean DEFAULT false NOT NULL,
    include_unknown boolean DEFAULT false NOT NULL,
    selection_seed integer,
    excluded_unknown integer DEFAULT 0 NOT NULL,
    excluded_no_options integer DEFAULT 0 NOT NULL,
    marking_config_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topics (
    id uuid NOT NULL,
    subject_id uuid NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: answer_evidence answer_evidence_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_evidence
    ADD CONSTRAINT answer_evidence_pkey PRIMARY KEY (id);


--
-- Name: answer_sources answer_sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_sources
    ADD CONSTRAINT answer_sources_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: document_pages document_pages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_pkey PRIMARY KEY (id);


--
-- Name: extracted_answers extracted_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_answers
    ADD CONSTRAINT extracted_answers_pkey PRIMARY KEY (id);


--
-- Name: extracted_questions extracted_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_questions
    ADD CONSTRAINT extracted_questions_pkey PRIMARY KEY (id);


--
-- Name: extraction_reports extraction_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_reports
    ADD CONSTRAINT extraction_reports_pkey PRIMARY KEY (id);


--
-- Name: question_subjects ix_question_subjects_qst; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_subjects
    ADD CONSTRAINT ix_question_subjects_qst UNIQUE (question_id, subject_id, topic_id);


--
-- Name: test_question_snapshots ix_snapshots_session_position; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_question_snapshots
    ADD CONSTRAINT ix_snapshots_session_position UNIQUE (session_id, "position");


--
-- Name: topics ix_topics_subject_slug; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT ix_topics_subject_slug UNIQUE (subject_id, slug);


--
-- Name: manual_corrections manual_corrections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_corrections
    ADD CONSTRAINT manual_corrections_pkey PRIMARY KEY (id);


--
-- Name: marking_configs marking_configs_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marking_configs
    ADD CONSTRAINT marking_configs_name_key UNIQUE (name);


--
-- Name: marking_configs marking_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marking_configs
    ADD CONSTRAINT marking_configs_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: ocr_blocks ocr_blocks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocr_blocks
    ADD CONSTRAINT ocr_blocks_pkey PRIMARY KEY (id);


--
-- Name: processing_errors processing_errors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_errors
    ADD CONSTRAINT processing_errors_pkey PRIMARY KEY (id);


--
-- Name: processing_stages processing_stages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_stages
    ADD CONSTRAINT processing_stages_pkey PRIMARY KEY (id);


--
-- Name: question_assets question_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_assets
    ADD CONSTRAINT question_assets_pkey PRIMARY KEY (id);


--
-- Name: question_options question_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_options
    ADD CONSTRAINT question_options_pkey PRIMARY KEY (id);


--
-- Name: question_subjects question_subjects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_subjects
    ADD CONSTRAINT question_subjects_pkey PRIMARY KEY (id);


--
-- Name: review_history review_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_history
    ADD CONSTRAINT review_history_pkey PRIMARY KEY (id);


--
-- Name: rule_set_versions rule_set_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_set_versions
    ADD CONSTRAINT rule_set_versions_pkey PRIMARY KEY (id);


--
-- Name: student_profiles student_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_profiles
    ADD CONSTRAINT student_profiles_pkey PRIMARY KEY (id);


--
-- Name: student_profiles student_profiles_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_profiles
    ADD CONSTRAINT student_profiles_user_id_key UNIQUE (user_id);


--
-- Name: student_question_collections student_question_collections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_question_collections
    ADD CONSTRAINT student_question_collections_pkey PRIMARY KEY (id);


--
-- Name: student_responses student_responses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_responses
    ADD CONSTRAINT student_responses_pkey PRIMARY KEY (id);


--
-- Name: subjects subjects_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subjects
    ADD CONSTRAINT subjects_name_key UNIQUE (name);


--
-- Name: subjects subjects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subjects
    ADD CONSTRAINT subjects_pkey PRIMARY KEY (id);


--
-- Name: subjects subjects_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subjects
    ADD CONSTRAINT subjects_slug_key UNIQUE (slug);


--
-- Name: test_question_snapshots test_question_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_question_snapshots
    ADD CONSTRAINT test_question_snapshots_pkey PRIMARY KEY (id);


--
-- Name: test_results test_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_results
    ADD CONSTRAINT test_results_pkey PRIMARY KEY (id);


--
-- Name: test_sessions test_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_sessions
    ADD CONSTRAINT test_sessions_pkey PRIMARY KEY (id);


--
-- Name: test_templates test_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_templates
    ADD CONSTRAINT test_templates_pkey PRIMARY KEY (id);


--
-- Name: topics topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_pkey PRIMARY KEY (id);


--
-- Name: student_question_collections uq_collection_user_question_type; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_question_collections
    ADD CONSTRAINT uq_collection_user_question_type UNIQUE (user_id, question_id, collection_type);


--
-- Name: document_pages uq_document_pages_doc_page; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT uq_document_pages_doc_page UNIQUE (document_id, page_number);


--
-- Name: student_responses uq_response_session_snapshot; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_responses
    ADD CONSTRAINT uq_response_session_snapshot UNIQUE (session_id, snapshot_id);


--
-- Name: rule_set_versions uq_rulesets_name_version; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rule_set_versions
    ADD CONSTRAINT uq_rulesets_name_version UNIQUE (name, version);


--
-- Name: test_results uq_test_results_session; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_results
    ADD CONSTRAINT uq_test_results_session UNIQUE (session_id);


--
-- Name: ix_audit_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_doc ON public.audit_log USING btree (document_id, created_at);


--
-- Name: ix_collections_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collections_question ON public.student_question_collections USING btree (question_id, created_at);


--
-- Name: ix_collections_user_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collections_user_type_created ON public.student_question_collections USING btree (user_id, collection_type, created_at);


--
-- Name: ix_corrections_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_corrections_doc ON public.manual_corrections USING btree (document_id, created_at);


--
-- Name: ix_errors_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_errors_doc ON public.processing_errors USING btree (document_id, created_at);


--
-- Name: ix_notifications_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_created ON public.notifications USING btree (user_id, created_at);


--
-- Name: ix_notifications_user_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_user_unread ON public.notifications USING btree (user_id, is_read, created_at);


--
-- Name: ix_ocr_blocks_doc_page; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ocr_blocks_doc_page ON public.ocr_blocks USING btree (document_id, page_number);


--
-- Name: ix_processing_stages_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_processing_stages_doc ON public.processing_stages USING btree (document_id, created_at);


--
-- Name: ix_question_subjects_subject; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_question_subjects_subject ON public.question_subjects USING btree (subject_id, created_at);


--
-- Name: ix_questions_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_questions_doc ON public.extracted_questions USING btree (document_id, created_at);


--
-- Name: ix_questions_fingerprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_questions_fingerprint ON public.extracted_questions USING btree (content_fingerprint);


--
-- Name: ix_reports_doc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reports_doc ON public.extraction_reports USING btree (document_id, created_at);


--
-- Name: ix_snapshots_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_snapshots_session ON public.test_question_snapshots USING btree (session_id, created_at);


--
-- Name: ix_student_profiles_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_student_profiles_user_created ON public.student_profiles USING btree (user_id, created_at);


--
-- Name: ix_student_responses_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_student_responses_session ON public.student_responses USING btree (session_id, updated_at);


--
-- Name: ix_student_responses_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_student_responses_user_created ON public.student_responses USING btree (user_id, updated_at);


--
-- Name: ix_test_results_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_test_results_user_created ON public.test_results USING btree (user_id, created_at);


--
-- Name: ix_test_sessions_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_test_sessions_user_created ON public.test_sessions USING btree (user_id, created_at);


--
-- Name: ix_test_templates_user_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_test_templates_user_created ON public.test_templates USING btree (user_id, created_at);


--
-- Name: answer_evidence answer_evidence_answer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_evidence
    ADD CONSTRAINT answer_evidence_answer_id_fkey FOREIGN KEY (answer_id) REFERENCES public.extracted_answers(id) ON DELETE CASCADE;


--
-- Name: answer_evidence answer_evidence_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_evidence
    ADD CONSTRAINT answer_evidence_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.answer_sources(id) ON DELETE SET NULL;


--
-- Name: answer_sources answer_sources_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.answer_sources
    ADD CONSTRAINT answer_sources_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: audit_log audit_log_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: document_pages document_pages_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_pages
    ADD CONSTRAINT document_pages_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: extracted_answers extracted_answers_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_answers
    ADD CONSTRAINT extracted_answers_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: extracted_answers extracted_answers_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_answers
    ADD CONSTRAINT extracted_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE CASCADE;


--
-- Name: extracted_questions extracted_questions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_questions
    ADD CONSTRAINT extracted_questions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: extracted_questions extracted_questions_duplicate_of_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_questions
    ADD CONSTRAINT extracted_questions_duplicate_of_id_fkey FOREIGN KEY (duplicate_of_id) REFERENCES public.extracted_questions(id) ON DELETE SET NULL;


--
-- Name: extracted_questions extracted_questions_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extracted_questions
    ADD CONSTRAINT extracted_questions_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: extraction_reports extraction_reports_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_reports
    ADD CONSTRAINT extraction_reports_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: extraction_reports extraction_reports_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_reports
    ADD CONSTRAINT extraction_reports_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: manual_corrections manual_corrections_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.manual_corrections
    ADD CONSTRAINT manual_corrections_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: ocr_blocks ocr_blocks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocr_blocks
    ADD CONSTRAINT ocr_blocks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: ocr_blocks ocr_blocks_page_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ocr_blocks
    ADD CONSTRAINT ocr_blocks_page_id_fkey FOREIGN KEY (page_id) REFERENCES public.document_pages(id) ON DELETE CASCADE;


--
-- Name: processing_errors processing_errors_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_errors
    ADD CONSTRAINT processing_errors_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: processing_errors processing_errors_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_errors
    ADD CONSTRAINT processing_errors_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: processing_stages processing_stages_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_stages
    ADD CONSTRAINT processing_stages_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: processing_stages processing_stages_job_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.processing_stages
    ADD CONSTRAINT processing_stages_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.jobs(id) ON DELETE SET NULL;


--
-- Name: question_assets question_assets_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_assets
    ADD CONSTRAINT question_assets_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: question_assets question_assets_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_assets
    ADD CONSTRAINT question_assets_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE CASCADE;


--
-- Name: question_options question_options_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_options
    ADD CONSTRAINT question_options_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE CASCADE;


--
-- Name: question_subjects question_subjects_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_subjects
    ADD CONSTRAINT question_subjects_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE CASCADE;


--
-- Name: question_subjects question_subjects_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_subjects
    ADD CONSTRAINT question_subjects_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subjects(id) ON DELETE SET NULL;


--
-- Name: question_subjects question_subjects_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.question_subjects
    ADD CONSTRAINT question_subjects_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.topics(id) ON DELETE SET NULL;


--
-- Name: review_history review_history_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_history
    ADD CONSTRAINT review_history_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: student_question_collections student_question_collections_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_question_collections
    ADD CONSTRAINT student_question_collections_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE CASCADE;


--
-- Name: student_responses student_responses_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_responses
    ADD CONSTRAINT student_responses_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.test_sessions(id) ON DELETE CASCADE;


--
-- Name: student_responses student_responses_snapshot_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.student_responses
    ADD CONSTRAINT student_responses_snapshot_id_fkey FOREIGN KEY (snapshot_id) REFERENCES public.test_question_snapshots(id) ON DELETE CASCADE;


--
-- Name: test_question_snapshots test_question_snapshots_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_question_snapshots
    ADD CONSTRAINT test_question_snapshots_question_id_fkey FOREIGN KEY (question_id) REFERENCES public.extracted_questions(id) ON DELETE SET NULL;


--
-- Name: test_question_snapshots test_question_snapshots_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_question_snapshots
    ADD CONSTRAINT test_question_snapshots_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.test_sessions(id) ON DELETE CASCADE;


--
-- Name: test_results test_results_marking_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_results
    ADD CONSTRAINT test_results_marking_config_id_fkey FOREIGN KEY (marking_config_id) REFERENCES public.marking_configs(id) ON DELETE SET NULL;


--
-- Name: test_results test_results_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_results
    ADD CONSTRAINT test_results_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.test_sessions(id) ON DELETE CASCADE;


--
-- Name: test_sessions test_sessions_marking_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_sessions
    ADD CONSTRAINT test_sessions_marking_config_id_fkey FOREIGN KEY (marking_config_id) REFERENCES public.marking_configs(id) ON DELETE SET NULL;


--
-- Name: test_sessions test_sessions_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_sessions
    ADD CONSTRAINT test_sessions_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.test_templates(id) ON DELETE SET NULL;


--
-- Name: test_templates test_templates_marking_config_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_templates
    ADD CONSTRAINT test_templates_marking_config_id_fkey FOREIGN KEY (marking_config_id) REFERENCES public.marking_configs(id) ON DELETE SET NULL;


--
-- Name: topics topics_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subjects(id) ON DELETE CASCADE;


--
--

--
--




--
-- Data for Name: marking_configs; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.marking_configs VALUES ('75d4243a-fda6-40d4-9521-b7581d236f95', 'PPSC default', 1, -0.25, 0, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');


--
-- Data for Name: subjects; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.subjects VALUES ('f09814ad-a38b-44e4-85e8-350ad1b1d9a2', 'General Knowledge', 'general-knowledge', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('cadcf54e-358b-451c-a564-813580adcaa8', 'Pakistan Affairs', 'pakistan-affairs', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('69b669f0-7369-40c6-8378-7d5f021dbed2', 'Current Affairs', 'current-affairs', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('5681f6ef-b890-4e83-97c1-1d7a701deb7e', 'Islamic Studies', 'islamic-studies', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('4f81dab6-08ff-4bd6-a7d0-8c17b620a73d', 'Everyday Science', 'everyday-science', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('94336bf0-17cd-49d5-8039-e2f3a49c63e9', 'English', 'english', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('a894828e-73d7-4a3e-9484-fb7051d4d69b', 'Mathematics', 'mathematics', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('6f9396d3-f993-42cf-b9ce-be6af91f4751', 'Computer Science', 'computer-science', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('ebf5699d-e440-4958-8410-70b1e25174a9', 'Urdu', 'urdu', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('cf673560-d9ba-4515-81b7-e8899b20bb3b', 'Geography', 'geography', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('c2de9dc0-1581-425c-a36d-10cee94db93e', 'History', 'history', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('f6b8d670-46a6-4af2-b5af-7217d5174e14', 'Political Science', 'political-science', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');
INSERT INTO public.subjects VALUES ('2056f57a-590c-42d8-a430-9c0d2aa3da7b', 'General Ability', 'general-ability', NULL, true, '2026-11-23 10:01:41.87219+00', '2026-11-23 10:01:41.87219+00');


--
--

INSERT INTO public.alembic_version (version_num) VALUES ('0009_m9_notifications');
