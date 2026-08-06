--
-- PostgreSQL database dump
--

\restrict g06BhAXTTGBs1UXMFleoOAXkxB21nPTd7d7cDtTX3qcgYfWt6NCSgM7AFbLT7hI

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: agent_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.agent_status AS ENUM (
    'active',
    'reviewing',
    'recommended'
);


--
-- Name: collections_case_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.collections_case_status AS ENUM (
    'pending',
    'approved',
    'human_review',
    'modified'
);


--
-- Name: collections_compliance_flag; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.collections_compliance_flag AS ENUM (
    'ok',
    'review',
    'escalate'
);


--
-- Name: copilot_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.copilot_role AS ENUM (
    'user',
    'assistant'
);


--
-- Name: dealer_lead_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.dealer_lead_status AS ENUM (
    'hot',
    'warm',
    'cool',
    'message_sent',
    'converted'
);


--
-- Name: qa_category; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.qa_category AS ENUM (
    'mobility',
    'dmrv'
);


--
-- Name: recommendation_risk; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.recommendation_risk AS ENUM (
    'low',
    'medium',
    'high'
);


--
-- Name: recommendation_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.recommendation_status AS ENUM (
    'pending',
    'approved',
    'under_review'
);


--
-- Name: signal_panel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.signal_panel AS ENUM (
    'warehouse',
    'collections_metrics',
    'rvsf'
);


--
-- Name: simulation_domain; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.simulation_domain AS ENUM (
    'auto_sales',
    'dealer_allocation',
    'collections',
    'logistics_delay',
    'credit_pricing'
);


--
-- Name: trust_approval; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.trust_approval AS ENUM (
    'approved',
    'human_review',
    'pending',
    'rejected',
    'escalated'
);


--
-- Name: trust_audit; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.trust_audit AS ENUM (
    'complete',
    'pending'
);


--
-- Name: trust_risk; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.trust_risk AS ENUM (
    'low',
    'medium',
    'high'
);


--
-- Name: twin_approval_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.twin_approval_status AS ENUM (
    'draft',
    'under_review',
    'approved'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ai_agents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_agents (
    name character varying(128) NOT NULL,
    role character varying(128) NOT NULL,
    status public.agent_status NOT NULL,
    last_activity character varying(256) NOT NULL,
    use_areas character varying(32)[] NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: carbon_credits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.carbon_credits (
    code character varying(32) NOT NULL,
    type character varying(16) NOT NULL,
    price character varying(32) NOT NULL,
    buyer_match integer NOT NULL,
    closure_prob integer NOT NULL,
    traceability integer NOT NULL,
    repriced_at timestamp with time zone,
    buyer_matched_at timestamp with time zone,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_carbon_credits_buyer_match_range CHECK (((buyer_match >= 0) AND (buyer_match <= 100))),
    CONSTRAINT ck_carbon_credits_closure_prob_range CHECK (((closure_prob >= 0) AND (closure_prob <= 100))),
    CONSTRAINT ck_carbon_credits_traceability_range CHECK (((traceability >= 0) AND (traceability <= 100)))
);


--
-- Name: causal_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_edges (
    source_node_id uuid NOT NULL,
    target_node_id uuid NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: causal_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_nodes (
    label character varying(128) NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    metric character varying(128) NOT NULL,
    trend character varying(32) NOT NULL,
    drivers jsonb NOT NULL,
    action character varying(256) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: causal_qa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_qa (
    category public.qa_category NOT NULL,
    question text NOT NULL,
    answer text NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: collections_agents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collections_agents (
    name character varying(128) NOT NULL,
    status public.agent_status NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: collections_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collections_cases (
    customer character varying(128) NOT NULL,
    dpd integer NOT NULL,
    outstanding character varying(32) NOT NULL,
    roll_forward_risk integer NOT NULL,
    channel character varying(64) NOT NULL,
    action character varying(128) NOT NULL,
    prob integer NOT NULL,
    compliance_flag public.collections_compliance_flag NOT NULL,
    status public.collections_case_status NOT NULL,
    modified_action character varying(128),
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_collections_cases_prob_range CHECK (((prob >= 0) AND (prob <= 100))),
    CONSTRAINT ck_collections_cases_roll_forward_risk_range CHECK (((roll_forward_risk >= 0) AND (roll_forward_risk <= 100)))
);


--
-- Name: compliance_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compliance_rules (
    label character varying(128) NOT NULL,
    status character varying(32) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: copilot_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.copilot_messages (
    session_id uuid NOT NULL,
    role public.copilot_role NOT NULL,
    content text NOT NULL,
    result jsonb,
    confidence integer,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: copilot_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.copilot_sessions (
    title character varying(256),
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: customer_twins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_twins (
    name character varying(128) NOT NULL,
    location character varying(128) NOT NULL,
    income_stability character varying(32) NOT NULL,
    repayment character varying(32) NOT NULL,
    products jsonb NOT NULL,
    nba jsonb NOT NULL,
    risk_decomposition jsonb NOT NULL,
    cross_sell jsonb NOT NULL,
    approval_status public.twin_approval_status NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dealer_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dealer_leads (
    dealer_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    vehicle character varying(64) NOT NULL,
    score integer NOT NULL,
    prob integer NOT NULL,
    action character varying(256) NOT NULL,
    revenue character varying(32) NOT NULL,
    status public.dealer_lead_status NOT NULL,
    test_drive_slot character varying(64),
    message_sent_at timestamp with time zone,
    converted_at timestamp with time zone,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_dealer_leads_prob_range CHECK (((prob >= 0) AND (prob <= 100))),
    CONSTRAINT ck_dealer_leads_score_range CHECK (((score >= 0) AND (score <= 100)))
);


--
-- Name: dealers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dealers (
    code character varying(32) NOT NULL,
    name character varying(128) NOT NULL,
    leads integer NOT NULL,
    hot_leads integer NOT NULL,
    test_drives_pending integer NOT NULL,
    booking_prob integer NOT NULL,
    revenue_at_risk character varying(32) NOT NULL,
    leakage_pct integer NOT NULL,
    bay_util_pct integer NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_dealers_bay_util_pct_range CHECK (((bay_util_pct >= 0) AND (bay_util_pct <= 100))),
    CONSTRAINT ck_dealers_booking_prob_range CHECK (((booking_prob >= 0) AND (booking_prob <= 100))),
    CONSTRAINT ck_dealers_leakage_pct_range CHECK (((leakage_pct >= 0) AND (leakage_pct <= 100)))
);


--
-- Name: finance_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.finance_products (
    name character varying(128) NOT NULL,
    customers character varying(32) NOT NULL,
    risk character varying(32) NOT NULL,
    cross_sell character varying(32) NOT NULL,
    opportunity character varying(64) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kpi_drivers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpi_drivers (
    kpi_id uuid NOT NULL,
    driver_text text NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kpis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpis (
    code character varying(32) NOT NULL,
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    trend character varying(32) NOT NULL,
    trend_up boolean NOT NULL,
    confidence integer NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_kpis_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
);


--
-- Name: logistics_routes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logistics_routes (
    name character varying(128) NOT NULL,
    sla_risk integer NOT NULL,
    delay_prob integer NOT NULL,
    cost character varying(32) NOT NULL,
    recommended_action character varying(128) NOT NULL,
    rerouted boolean NOT NULL,
    rerouted_at timestamp with time zone,
    auto_healed boolean NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_logistics_routes_delay_prob_range CHECK (((delay_prob >= 0) AND (delay_prob <= 100))),
    CONSTRAINT ck_logistics_routes_sla_risk_range CHECK (((sla_risk >= 0) AND (sla_risk <= 100)))
);


--
-- Name: mobility_kpis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mobility_kpis (
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    trend character varying(32) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: poc_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.poc_items (
    name character varying(128) NOT NULL,
    bucket character varying(128) NOT NULL,
    priority character varying(16),
    complexity character varying(16),
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone
);


--
-- Name: recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recommendations (
    code character varying(32) NOT NULL,
    title text NOT NULL,
    impact character varying(128) NOT NULL,
    confidence integer NOT NULL,
    risk public.recommendation_risk NOT NULL,
    status public.recommendation_status NOT NULL,
    decided_at timestamp with time zone,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_recommendations_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
);


--
-- Name: regions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.regions (
    code character varying(32) NOT NULL
);


--
-- Name: simulation_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.simulation_runs (
    domain public.simulation_domain NOT NULL,
    inputs jsonb NOT NULL,
    outputs jsonb NOT NULL,
    confidence integer,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_simulation_runs_confidence_range CHECK (((confidence IS NULL) OR ((confidence >= 0) AND (confidence <= 100))))
);


--
-- Name: solution_buckets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.solution_buckets (
    name character varying(128) NOT NULL,
    tag character varying(64) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: solutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.solutions (
    bucket_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    problem text NOT NULL,
    solution text NOT NULL,
    differentiator text NOT NULL,
    impact character varying(128) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: suggested_prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggested_prompts (
    text text NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: trust_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trust_decisions (
    code character varying(32) NOT NULL,
    use_case character varying(256) NOT NULL,
    recommendation character varying(256) NOT NULL,
    data_sources character varying(256) NOT NULL,
    confidence integer NOT NULL,
    approval public.trust_approval NOT NULL,
    risk public.trust_risk NOT NULL,
    audit public.trust_audit NOT NULL,
    rejection_reason text,
    lineage jsonb NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    deleted_at timestamp with time zone,
    CONSTRAINT ck_trust_decisions_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    email character varying(256) NOT NULL,
    full_name character varying(128) NOT NULL,
    is_active boolean NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: vehicle_models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vehicle_models (
    name character varying(64) NOT NULL
);


--
-- Name: warehouse_signals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.warehouse_signals (
    panel public.signal_panel NOT NULL,
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    tone character varying(16) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: xr_experiences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.xr_experiences (
    code character varying(32) NOT NULL,
    title character varying(128) NOT NULL,
    use_case character varying(128) NOT NULL,
    feature character varying(128) NOT NULL,
    impact character varying(128) NOT NULL,
    sort_order integer NOT NULL,
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Data for Name: ai_agents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.ai_agents (name, role, status, last_activity, use_areas, sort_order, id, created_at, updated_at) FROM stdin;
Data Agent	Ingest & normalize signals	recommended	91 items pending review	{Auto,Finance}	0	5bba2d94-9ba1-5159-b8ab-619e73e606a6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Prediction Agent	Forecast outcomes	active	Refreshed dealer feed 192m ago	{Auto,Logistics}	1	ed6339f8-5c18-5f90-826d-8ac422d50620	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Causal Graph Agent	Explain drivers	reviewing	Explained cancellation drivers	{Auto}	2	c6bbcf62-61c4-5582-b9f3-fa0a24f1bd7e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Simulation Agent	What-if scenarios	reviewing	Blocked 204 risky offers	{Auto,Finance}	3	ecd3d66f-1e35-5b49-bdc4-578e2a422b1d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Code Analytics Agent	NL→SQL/Python	reviewing	Tested exchange bonus scenario	{All}	4	5550aec9-f02a-579f-a828-a148e8cba4fb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Compliance Agent	Guardrails & policy	active	Sent WhatsApp to 47 leads	{Finance}	5	53f87203-75b4-558a-962c-78a9f0cdfb32	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Action Agent	Execute approved actions	active	Generated warranty query	{Auto}	6	7a4f418c-00b8-539a-8fb3-548d17493438	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Human Review Agent	Route to human	active	Explained cancellation drivers	{All}	7	ee041320-b41e-5f5b-9dce-c633eb731271	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Learning Agent	Feedback learning	active	Updated propensity model	{All}	8	a17ab954-79af-5a8b-8a6d-1ab69935d7e7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Memory Agent	Long-term memory	active	Blocked 13 risky offers	{All}	9	b0de0901-e8d4-5370-a2b2-e9e4129813d4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Anomaly Agent	Detect signal spikes	active	Forecast bookings Chennai	{Logistics,Circularity}	10	184d6069-88a8-5c9b-abad-adfc4870c3a9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Pricing Agent	Dynamic credit pricing	recommended	Sent WhatsApp to 85 leads	{Circularity}	11	05bcc93c-ee80-5808-9f36-ca6e5d90f6e0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: carbon_credits; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.carbon_credits (code, type, price, buyer_match, closure_prob, traceability, repriced_at, buyer_matched_at, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
SYN-RVSF-2301	EPR	₹1,516	73	70	89	\N	\N	1	f92f7057-32bb-57ad-b303-e1bdd6b6079a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2302	CD	₹779	53	46	53	\N	\N	2	db2c95fb-b367-5ccd-a321-c9d3ef6d567c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-Plant-2303	EPR	₹1,954	67	66	83	\N	\N	3	8a2a8f38-6567-5804-a6bd-d208367fea61	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2304	Carbon	₹692	38	25	49	\N	\N	4	da8553b3-b3bf-53d8-8b5b-6fc0799de640	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2305	CD	₹706	35	32	52	\N	\N	5	34640fc6-8be5-5669-a110-93b4c881c433	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-Plant-2306	CD	₹856	56	46	65	\N	\N	6	aa63d529-7929-5451-8f0e-b1d4db65ad8c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2307	CD	₹1,251	57	55	59	\N	\N	7	45dadcdd-a0b0-5c7a-9cc3-ab459ff2854c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2308	SDG	₹693	78	63	95	\N	\N	8	c505693f-33df-5c71-bcd8-9f1753ce7369	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2309	EPR	₹1,908	26	18	46	\N	\N	9	e536eaaa-3f03-59de-b3e4-5e8071da4b6f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2310	EPR	₹676	75	68	90	\N	\N	10	3bf3b25c-85f9-5ce6-bfe8-08e0f1066294	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2311	EPR	₹1,167	86	85	95	\N	\N	11	af455866-68a5-54bf-bd60-8712aa0f02f9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2312	SDG	₹1,279	65	47	71	\N	\N	12	14b11877-feb8-576a-a182-b789b5f32c55	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2313	SDG	₹1,067	26	22	46	\N	\N	13	fa3a22ad-d08b-56a3-ae16-7a395b9ef1db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2314	Carbon	₹1,066	43	30	51	\N	\N	14	95afca99-c31d-5159-b37a-6e96700d3c5c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-Plant-2315	CD	₹732	36	23	51	\N	\N	15	dc18440b-a13f-5717-abab-76a1420e73f1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-ELV-2316	SDG	₹617	80	76	84	\N	\N	16	c4fef17c-1702-5c93-942b-fa143c79ab77	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2317	CD	₹1,174	37	31	53	\N	\N	17	6a8c244e-b8c9-5fc1-8edd-8766380542f8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-RVSF-2318	EPR	₹860	51	38	56	\N	\N	18	a730eb34-733b-5ffd-8d35-1db28bbcd0ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-Plant-2319	EPR	₹1,117	60	49	67	\N	\N	19	d9c3f718-0536-5bf3-bd41-b058eb91b6ca	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
SYN-Plant-2300	CD	₹634	81	65	91	2026-08-06 07:08:19.547567+00	\N	0	4812bd49-9254-57bd-b5c5-476c31ed060a	2026-08-06 04:41:53.792545+00	2026-08-06 07:08:19.538351+00	\N
\.


--
-- Data for Name: causal_edges; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_edges (source_node_id, target_node_id, sort_order, id, created_at, updated_at) FROM stdin;
8d3d33d6-0fdf-50b2-9258-ea1b10c7ac3e	d96f88c8-d23c-529c-9fbc-ed5e6cf5c802	0	4c364dae-3ce2-5ce0-87c1-71358b82de0d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
d96f88c8-d23c-529c-9fbc-ed5e6cf5c802	49317ed9-4919-524d-9ff9-01f22ed1676c	1	1701f33b-e845-5f40-bc03-9de3d6a840e0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
49317ed9-4919-524d-9ff9-01f22ed1676c	19f21e71-ff74-5335-b821-3b85f6c28e7c	2	1ca7ffbd-e945-5547-a4ad-52a2abee5a65	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
19f21e71-ff74-5335-b821-3b85f6c28e7c	a787ace4-cdf2-5b83-9865-b441b5bb03da	3	a97c3ed2-f817-5045-9631-01dd21062fe4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
70309943-93c3-561a-8e7c-ce88ae96f129	a787ace4-cdf2-5b83-9865-b441b5bb03da	4	7c3070c5-ee18-5dbb-b5dc-21abc419ee20	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
a787ace4-cdf2-5b83-9865-b441b5bb03da	21d35971-dc43-5476-b67e-520769c5ae7c	5	bb8917f8-74c7-571b-9715-417827d193bb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
21d35971-dc43-5476-b67e-520769c5ae7c	1e3d6f0f-309f-5946-a8f4-57dcddfe33d6	6	90036667-1905-51b0-98b9-6e5ee38bdee7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
1e3d6f0f-309f-5946-a8f4-57dcddfe33d6	661ea2ce-d814-598d-ab37-ff7eb32b75cb	7	1b49578c-936c-5845-bfe3-4cf6c6ccbdb7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3707a576-8698-5cd4-8a9b-ae9815a9da45	661ea2ce-d814-598d-ab37-ff7eb32b75cb	8	cd1edbda-f86c-5beb-9a26-e86ccda427c0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
661ea2ce-d814-598d-ab37-ff7eb32b75cb	4670fd15-b7e3-571d-9ccd-5f555f58e1da	9	8e197240-481b-57f2-8574-069f6d433d09	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
1efba7c9-68b3-564a-968e-81974debabe4	661ea2ce-d814-598d-ab37-ff7eb32b75cb	10	0f693196-8512-56e3-b8c0-5edb51f3cfd0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3707a576-8698-5cd4-8a9b-ae9815a9da45	1efba7c9-68b3-564a-968e-81974debabe4	11	74bc00b6-e367-5a7d-8d28-c8d53bd17a07	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: causal_nodes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_nodes (label, x, y, metric, trend, drivers, action, sort_order, id, created_at, updated_at) FROM stdin;
Campaign Spend	50	60	₹2.7 Cr	+4%	["Digital-heavy allocation", "Regional festive push"]	Expand digital handover	0	8d3d33d6-0fdf-50b2-9258-ea1b10c7ac3e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Lead Quality	180	60	Score 29	+4%	["Better source mix", "Improved landing pages"]	Bundle insurance renewal	1	d96f88c8-d23c-529c-9fbc-ed5e6cf5c802	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Dealer Follow-up	320	60	SLA 64%	spike	["NBA adoption", "WhatsApp templates"]	Quarantine batch	2	49317ed9-4919-524d-9ff9-01f22ed1676c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Test Drive	460	60	64% completion	+2.1	["AI scheduler", "SMS reminders"]	Escalate stale leads > 2h	3	19f21e71-ff74-5335-b821-3b85f6c28e7c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Booking	600	60	12.4%	+4%	["Exchange bonus", "Finance TAT"]	Expand digital handover	4	a787ace4-cdf2-5b83-9865-b441b5bb03da	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Finance Approval	50	180	57%	-3.1d	["Alt-data model", "Faster KYC"]	Monitor Q1	5	70309943-93c3-561a-8e7c-ce88ae96f129	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Vehicle Allocation	180	180	89% utilization	+2%	["Demand model", "Dealer capacity"]	Quarantine batch	6	21d35971-dc43-5476-b67e-520769c5ae7c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Delivery Delay	320	180	8.4 d	+8%	["Reduced waiting", "Better allocation"]	Monitor Q1	7	1e3d6f0f-309f-5946-a8f4-57dcddfe33d6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Customer Satisfaction	460	180	NPS 72	+2%	["Delivery experience", "Service quality"]	Increase retargeting	8	661ea2ce-d814-598d-ab37-ff7eb32b75cb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Service Experience	600	180	80% CSAT	-3.1d	["Bay utilization", "AR technician guide"]	Bundle offers	9	3707a576-8698-5cd4-8a9b-ae9815a9da45	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Warranty Claims	180	300	Batch B-2134 flagged	+2%	["Component supplier variance"]	Add Sunday slots	10	1efba7c9-68b3-564a-968e-81974debabe4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Repeat Purchase	460	300	29%	+2%	["Loyalty program", "Cross-sell"]	Increase retargeting	11	4670fd15-b7e3-571d-9ccd-5f555f58e1da	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: causal_qa; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_qa (category, question, answer, sort_order, id, created_at, updated_at) FROM stdin;
mobility	Why did bookings drop in Delhi?	Bookings dropped due to follow-up leakage at 2 Chennai dealers (42%), competitor promo (14%), finance TAT (10%). Recommend: exchange bonus + follow-up SLA.	0	eeb3f6b4-4d61-5b54-846f-4809e11c8134	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	What is causing delivery delay in North Zone?	East Zone waiting is elevated by uneven allocation (38% of delay). Reallocate 93 units.	1	6d3d7749-2497-558d-9fba-61c5c65f4d8a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	Which factor has highest impact on cancellation?	Finance approval TAT (>4 days) explains 39% of cancellations. Pre-approval for low-risk rural cuts it by 21%.	2	891261b1-9aa8-59c0-a428-473febf8b1dd	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	How can we improve finance-assisted conversions?	Pair thin-file credit twin with dealer NBA. Expected +4.5% conversion, -1.3% NPA risk.	3	35f4ec63-894a-5659-ade0-27b75f84e147	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	Where should exchange bonus be targeted?	Target 206 Bolero prospects in South Zone — propensity 24% with current exchange values.	4	0d19234b-5ada-5024-b6cd-8b911b2a2b4b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	Which dealers leak the most revenue?	Chennai dealers show 33% leakage from stale leads; escalation SLA recovers ~₹233 L/month.	5	64523c26-9a95-578c-97ac-058e05d7a131	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	What drives repeat purchase?	Loyalty program + cross-sell timing; CSAT above 63 lifts repeat rate by 6%.	6	15123bc2-495c-5861-942b-310c86253ba8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
mobility	Why are warranty claims spiking?	Component supplier variance on batch B-2395; quarantine recommended.	7	85c7aafe-94cb-50d1-a720-b93afad60076	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Estimate carbon credits for this batch.	Estimated 275 tCO2e from batch RVSF-Chennai-Q2, of which 74 are verification-ready.	8	c925caec-21aa-5d5a-9d1f-0fbf049861ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Which fields are incomplete?	Missing: origin geo-tag, weight tickets for 240 vehicles, technician attestation for 131 units.	9	053d1330-7e5d-56c3-9e5a-c00d938f9f55	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Is this verification-ready?	68% ready — after adding origin geo-tags, verification confidence rises to 88%.	10	fccd1c94-f947-546f-bf3e-ce3d0f59b484	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Generate audit summary.	Audit summary generated. 231 batches, 190 tCO2e, 75% traceable, 3 pending human reviews.	11	02cdfba0-920d-5949-93d0-acc41510cf14	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Which credits should be repriced?	Reprice 141 credits with traceability below 71% — expected closure uplift 11%.	12	a4a3f697-d157-5256-a1c7-964ef361a60e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dmrv	Show EPR compliance status.	80% of EPR certificates verified; 1 awaiting buyer confirmation.	13	7ab0cfa7-b67d-50b0-904b-935ad8fb67d3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: collections_agents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collections_agents (name, status, sort_order, id, created_at, updated_at) FROM stdin;
Prioritization Agent	active	0	c1c57b8e-25d8-5bd8-8743-8f8c08fe5cda	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Channel Selection Agent	active	1	1f7fb194-4068-5c7f-948f-611b9444daff	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Negotiation Agent	active	2	bcdc6528-6770-54fd-b280-a0cbd10453bf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Compliance Guard Agent	active	3	75386ded-5d83-51a9-8b1c-82360319c052	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Field Visit Optimizer	active	4	041038b1-15ba-5bc2-9e7f-2951c227d472	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Promise-to-Pay Tracker	active	5	59d564dd-f097-53d6-b286-638fee9cd3c1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Restructuring Advisor	active	6	d840133e-0668-5c5e-bb64-e7d52b00bbd7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Escalation Router	reviewing	7	2637ef28-b1b6-5456-bf75-4c665483cff1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: collections_cases; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collections_cases (customer, dpd, outstanding, roll_forward_risk, channel, action, prob, compliance_flag, status, modified_action, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
Falguni Dugar	88	₹19.6 L	52	Tele-calling	Negotiated part-payment	39	review	pending	\N	1	83cd71be-38af-5f02-bb7b-128ee65d79ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Damyanti Majumdar	69	₹8.3 L	56	Tele-calling	Negotiated part-payment	45	review	pending	\N	2	6a2d6d54-5579-57c8-bcd3-ecbd5a8527c7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Fiyaz Sastry	3	₹2.4 L	27	Email	IVR nudge	71	ok	pending	\N	3	117592b6-8e98-52bf-9704-3ffdffe8df9d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Hiral Choudhury	29	₹17.9 L	36	WhatsApp	WhatsApp reminder	56	ok	pending	\N	4	37725df7-78ef-5dcc-b01e-1016d59956e8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Divya Krishnan	18	₹3.7 L	35	Tele-calling	WhatsApp reminder	68	ok	pending	\N	5	da123a2e-47bb-544a-bd20-4299bb7fd6a7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Darpan Kalita	113	₹14.5 L	72	WhatsApp	Restructure with 6-month plan	19	review	pending	\N	6	523a3924-dec8-5342-9d43-e0b79ff09959	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Harish Sarkar	7	₹7.5 L	26	Email	WhatsApp reminder	74	ok	pending	\N	7	c5361551-764e-54e0-adc9-5b5d541bb748	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Eiravati Dada	112	₹7.3 L	63	SMS	Negotiated part-payment	38	review	pending	\N	8	f8aa750f-0f2d-53b8-8084-78646924b1cd	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Rachana Madan	173	₹2.6 L	100	Email	Restructure with 6-month plan	0	escalate	pending	\N	9	bea6c702-7aee-5f80-b961-38bef1e071a5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Atharv Bhardwaj	69	₹23.9 L	50	SMS	Negotiated part-payment	42	review	pending	\N	10	a55e6de3-4586-56ef-98b2-ae3db4949b59	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Sneha Sachdev	76	₹3.3 L	53	Tele-calling	Negotiated part-payment	41	review	pending	\N	11	08de8152-31dd-52cd-a9c9-b209410ce1cb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Anjali Bassi	90	₹21.1 L	64	SMS	Negotiated part-payment	39	review	pending	\N	12	0dd81724-da4b-5532-beab-0c7c937fd4f6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Aahana Sarin	156	₹6.4 L	88	SMS	Restructure with 6-month plan	9	escalate	pending	\N	13	bdfc8ca8-38f1-5581-80fa-799cdac0c1da	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Hemangini Mane	70	₹8.4 L	56	Email	Negotiated part-payment	38	review	pending	\N	14	51318a6f-c808-5a72-aba4-e464acc4baf0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Ekanta Chada	97	₹3.0 L	64	Field visit	Negotiated part-payment	37	review	pending	\N	15	b3ba8487-1167-563e-acea-36df54de06ec	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Mugdha Edwin	173	₹22.1 L	93	IVR	Restructure with 6-month plan	7	escalate	pending	\N	16	1dde2b76-4080-54b7-8c7d-1bf51107d3d9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Warhi Badal	17	₹4.7 L	26	Tele-calling	Tele-calling	64	ok	pending	\N	17	15f71f52-2f8d-52d7-b7f0-c28a0c266d0c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Udyati Sheth	3	₹15.9 L	19	Field visit	IVR nudge	80	ok	pending	\N	18	9f6aaf14-185f-542b-a2e7-b5f65763cff2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Aadhya Mohan	170	₹13.0 L	88	Tele-calling	Restructure with 6-month plan	5	escalate	pending	\N	19	67204b5a-fec3-5e6b-89dd-d7a1cffd59b2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Gabriel Jani	36	₹11.6 L	44	IVR	IVR nudge	47	ok	pending	\N	20	0996b3d2-534c-5273-aef8-046f1a22ade0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Daniel Prakash	2	₹4.6 L	18	Email	Tele-calling	87	ok	pending	\N	21	9d0820f3-33da-56c3-923a-cea2d2cf75f9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Yagnesh Boase	106	₹4.7 L	64	Email	Negotiated part-payment	33	review	pending	\N	22	cbd3695c-c7a7-559c-8fb1-32af3910a74b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Jai Atwal	170	₹3.9 L	91	IVR	Restructure with 6-month plan	9	review	pending	\N	23	c96f950e-9fcb-5987-9c3e-8632a79b2642	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Chanakya Bhavsar	42	₹21.1 L	47	IVR	Negotiated part-payment	50	review	pending	\N	24	1987d9cd-fc86-5a68-a177-355e128acf55	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Wishi Gill	71	₹8.5 L	59	Tele-calling	Negotiated part-payment	41	review	pending	\N	25	d94d96de-0e4d-5966-bb3e-ebc052188827	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Pahal Golla	13	₹6.3 L	20	SMS	WhatsApp reminder	83	ok	pending	\N	26	7780260d-9daf-57d5-a488-dbb3e56862c9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Laksh Deol	45	₹25.0 L	32	WhatsApp	IVR nudge	64	ok	pending	\N	27	700fd6c8-6caf-5904-a0e1-22449957b913	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Amrita Bhatt	56	₹8.7 L	48	WhatsApp	Negotiated part-payment	53	review	pending	\N	28	86ccc943-d339-5537-854c-708449a40d93	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Owen Sekhon	22	₹24.3 L	29	Field visit	Tele-calling	70	ok	pending	\N	29	816475d6-aa89-595a-9a43-6d631bdccaef	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Bhavya Bobal	18	₹13.6 L	22	Email	Tele-calling	83	ok	pending	\N	30	564b2f48-558a-57a4-8442-7b6a109c18cf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Parth Buch	30	₹23.1 L	34	SMS	WhatsApp reminder	67	ok	pending	\N	31	d3d46843-57b2-534c-a32d-7607bed07582	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Tanish Toor	106	₹9.8 L	73	SMS	Restructure with 6-month plan	25	review	pending	\N	32	3d5aa1c1-3abc-5247-93df-03b5ed135986	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Hemal Bandi	7	₹24.2 L	24	Field visit	Tele-calling	76	ok	pending	\N	33	ba52739f-0d05-5cd5-9125-51b990aa3783	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Yuvraj Natarajan	79	₹18.8 L	62	SMS	Negotiated part-payment	42	review	pending	\N	34	b86042eb-85af-5b9a-82f6-11b3aa528e73	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Yatan Manne	60	₹19.2 L	55	Field visit	Negotiated part-payment	39	review	pending	\N	35	3bdb2d72-aaa7-5f89-914c-a153cd6f5054	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Sai Vaidya	63	₹6.1 L	53	Field visit	Negotiated part-payment	46	review	pending	\N	36	1a8cd5cc-6909-544e-9eab-3f2075caafa0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Faqid Choudhury	68	₹3.9 L	54	Tele-calling	Negotiated part-payment	38	review	pending	\N	37	6b4c5d81-73c5-57b2-a2a1-3ce4ca122c38	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Noah Saraf	31	₹13.2 L	26	Email	IVR nudge	65	ok	pending	\N	38	4450b62f-ea56-546f-87b4-9e58dbbcfe25	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Anita Mane	43	₹10.2 L	43	Tele-calling	IVR nudge	55	ok	pending	\N	39	018a6f65-e1e2-51ad-bda6-7cf7cb41e1ff	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Balendra Choudhury	90	₹2.8 L	60	SMS	Negotiated part-payment	31	review	approved	\N	0	2fc243bf-c97e-57f9-a8f5-b2a6c7975c80	2026-08-06 04:41:53.792545+00	2026-08-06 07:08:03.680034+00	\N
\.


--
-- Data for Name: compliance_rules; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.compliance_rules (label, status, sort_order, id, created_at, updated_at) FROM stdin;
Consent check	OK	0	17761742-4b3e-586c-bd40-e8cef9dac7eb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Bias / fairness check	OK	1	3e1ee4f1-7255-5c82-a791-c9b0de716850	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Regulatory rule check	OK	2	742f4763-42be-5041-a04f-aac15b419462	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Business policy check	2 pending	3	6d469ac6-2a4d-5953-8796-a51c0afeb1c1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Audit trail complete	OK	4	ca170d64-db2e-5324-991f-dabe072381b9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Data retention check	OK	5	4a72fd34-bd6e-5e63-acec-731448549e04	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: copilot_messages; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.copilot_messages (session_id, role, content, result, confidence, id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: copilot_sessions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.copilot_sessions (title, id, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: customer_twins; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customer_twins (name, location, income_stability, repayment, products, nba, risk_decomposition, cross_sell, approval_status, id, created_at, updated_at) FROM stdin;
Ayush Chaudhari	Lucknow	High	On-time	["Insurance"]	{"risk": "Low", "headline": "Pitch insurance renewal bundling", "confidence": 76, "expected_margin": "₹1"}	{"credit": "23%", "income": "7%", "market": "15%", "behaviour": "6%"}	{"EMI Shield": "80%", "Warranty Ext.": "81%"}	approved	b1be8868-911b-5981-ac06-e1f67b526a44	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Gautam Rai	Nashik	Medium	1 late	["Exchange", "Vehicle Loan", "Insurance", "EMI Shield"]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 58, "expected_margin": "₹1"}	{"credit": "12%", "income": "10%", "market": "15%", "behaviour": "21%"}	{"Service Plan": "59%", "Warranty Ext.": "80%"}	draft	572f4dac-fcbb-55d4-b228-0e6a5f56d929	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Warda Tandon	Chennai	Medium	1 late	["Insurance", "Service Plan"]	{"risk": "Low", "headline": "Refer to relationship manager", "confidence": 62, "expected_margin": "₹0"}	{"credit": "38%", "income": "6%", "market": "12%", "behaviour": "18%"}	{"Exchange": "81%", "Vehicle Loan": "63%", "Warranty Ext.": "78%"}	draft	eea476cb-bd68-545e-852d-7b1ed8891f75	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Zinal Dara	Ranchi	High	On-time	["Insurance", "Warranty Ext.", "Service Plan", "Exchange"]	{"risk": "Low", "headline": "Send service plan discount", "confidence": 77, "expected_margin": "₹0"}	{"credit": "30%", "income": "15%", "market": "9%", "behaviour": "5%"}	{"EMI Shield": "92%", "Vehicle Loan": "71%"}	approved	39582554-5433-5c28-8c0e-d461206dc37b	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Samesh Palla	Nagpur	Medium	1 late	["Service Plan", "Vehicle Loan"]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 64, "expected_margin": "₹1"}	{"credit": "23%", "income": "10%", "market": "6%", "behaviour": "15%"}	{"Exchange": "79%", "EMI Shield": "93%", "Warranty Ext.": "88%"}	draft	541a459e-639b-5a9d-91fa-435faa21f477	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ishani Hans	Dehradun	Medium	On-time	["EMI Shield"]	{"risk": "Low", "headline": "Upgrade to premium variant with exchange", "confidence": 64, "expected_margin": "₹1"}	{"credit": "16%", "income": "15%", "market": "14%", "behaviour": "18%"}	{"Insurance": "68%", "Vehicle Loan": "95%", "Warranty Ext.": "87%"}	draft	53340113-f8b6-5609-b3f8-595163cf578d	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Lipika Chawla	Hyderabad	Medium	On-time	["EMI Shield", "Vehicle Loan"]	{"risk": "Medium", "headline": "Send service plan discount", "confidence": 65, "expected_margin": "₹1"}	{"credit": "26%", "income": "15%", "market": "13%", "behaviour": "19%"}	{"Insurance": "71%", "Service Plan": "76%", "Warranty Ext.": "92%"}	draft	ab19fe9b-6e3e-542c-8163-c2e7e0931460	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Irya Dugal	Raipur	High	On-time	["Vehicle Loan", "Exchange"]	{"risk": "Medium", "headline": "Upgrade to premium variant with exchange", "confidence": 79, "expected_margin": "₹1"}	{"credit": "17%", "income": "26%", "market": "7%", "behaviour": "15%"}	{"Insurance": "79%", "Service Plan": "91%"}	approved	f1ac0e8f-4495-5433-aaa4-d4fe8dde6812	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Divya Virk	Nashik	Medium	On-time	["Insurance", "Vehicle Loan", "Service Plan"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 65, "expected_margin": "₹1"}	{"credit": "45%", "income": "14%", "market": "10%", "behaviour": "9%"}	{"EMI Shield": "79%", "Warranty Ext.": "89%"}	draft	1929a388-7720-5459-b886-a8f11be6e817	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Banjeet Gill	Ludhiana	Medium	On-time	["Service Plan", "EMI Shield", "Exchange", "Warranty Ext."]	{"risk": "Medium", "headline": "Pre-approve top-up loan", "confidence": 68, "expected_margin": "₹1"}	{"credit": "38%", "income": "21%", "market": "11%", "behaviour": "19%"}	{"Insurance": "87%", "Vehicle Loan": "67%"}	draft	7f062756-86f3-5837-ba6a-e0e6e964b7cd	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Yasti Mallick	Vijayawada	High	On-time	["Insurance", "Vehicle Loan", "Warranty Ext."]	{"risk": "Medium", "headline": "Upgrade to premium variant with exchange", "confidence": 73, "expected_margin": "₹0"}	{"credit": "11%", "income": "9%", "market": "8%", "behaviour": "10%"}	{"EMI Shield": "80%", "Service Plan": "76%"}	approved	0d3e1471-831d-5314-820c-ed5804b6cab3	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Adya Saini	Kolkata	High	On-time	["Insurance", "Exchange"]	{"risk": "Low", "headline": "Send service plan discount", "confidence": 71, "expected_margin": "₹1"}	{"credit": "11%", "income": "23%", "market": "9%", "behaviour": "11%"}	{"EMI Shield": "92%", "Vehicle Loan": "65%", "Warranty Ext.": "81%"}	approved	2e7ee8af-1564-5ecc-a05f-0c43cf766d09	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Shaurya Boase	Mumbai	High	On-time	["Service Plan", "EMI Shield", "Exchange", "Warranty Ext."]	{"risk": "Medium", "headline": "Refer to relationship manager", "confidence": 82, "expected_margin": "₹0"}	{"credit": "44%", "income": "19%", "market": "5%", "behaviour": "5%"}	{"Insurance": "64%", "Vehicle Loan": "70%"}	approved	04bc70b1-d4de-59d1-a300-4daa135d25ed	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Siddharth Kala	Lucknow	Medium	1 late	["EMI Shield", "Exchange"]	{"risk": "Medium", "headline": "Upgrade to premium variant with exchange", "confidence": 67, "expected_margin": "₹0"}	{"credit": "29%", "income": "5%", "market": "6%", "behaviour": "11%"}	{"Insurance": "65%", "Service Plan": "67%", "Vehicle Loan": "71%"}	draft	6085a125-5d74-5782-9221-bc933e8b858b	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Eta Kibe	Coimbatore	High	On-time	["Warranty Ext.", "Service Plan", "EMI Shield"]	{"risk": "Medium", "headline": "Pitch insurance renewal bundling", "confidence": 72, "expected_margin": "₹1"}	{"credit": "29%", "income": "30%", "market": "10%", "behaviour": "21%"}	{"Exchange": "75%", "Vehicle Loan": "74%"}	approved	7ba57935-b2a3-5122-b5c5-6e71bada52b3	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Vritti Viswanathan	Guwahati	Medium	1 late	["Exchange", "Warranty Ext.", "Insurance", "EMI Shield"]	{"risk": "Medium", "headline": "Send service plan discount", "confidence": 66, "expected_margin": "₹1"}	{"credit": "27%", "income": "6%", "market": "10%", "behaviour": "24%"}	{"Service Plan": "63%", "Vehicle Loan": "86%"}	draft	86b461f5-6272-5145-bfce-a60237ae1b22	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ishanvi Pathak	Ahmedabad	High	On-time	["Exchange", "Vehicle Loan", "Warranty Ext."]	{"risk": "Low", "headline": "Pre-approve top-up loan", "confidence": 77, "expected_margin": "₹1"}	{"credit": "17%", "income": "26%", "market": "10%", "behaviour": "5%"}	{"Insurance": "86%", "EMI Shield": "83%", "Service Plan": "94%"}	approved	d0751f7f-e938-569c-8f97-a4439d4749f3	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
William Wagle	Jaipur	High	On-time	["Insurance"]	{"risk": "Low", "headline": "Refer to relationship manager", "confidence": 82, "expected_margin": "₹0"}	{"credit": "23%", "income": "5%", "market": "8%", "behaviour": "19%"}	{"Exchange": "79%", "EMI Shield": "74%", "Service Plan": "95%"}	approved	f0c6ba39-1ca1-5b6d-861e-75ca257cb2c6	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Tanveer Bora	Coimbatore	High	On-time	["Exchange", "EMI Shield", "Service Plan", "Warranty Ext."]	{"risk": "Medium", "headline": "Pre-approve top-up loan", "confidence": 70, "expected_margin": "₹1"}	{"credit": "19%", "income": "20%", "market": "7%", "behaviour": "11%"}	{"Insurance": "85%", "Vehicle Loan": "88%"}	approved	4f97f30f-e1b6-540d-89c4-41004cefc857	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Bachittar Chacko	Bhubaneswar	Medium	On-time	["EMI Shield", "Warranty Ext."]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 64, "expected_margin": "₹1"}	{"credit": "28%", "income": "7%", "market": "6%", "behaviour": "19%"}	{"Exchange": "70%", "Service Plan": "65%", "Vehicle Loan": "88%"}	draft	d419032b-0fab-5c28-920f-599713901de5	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Aarnav Kanda	Nashik	Medium	1 late	["Warranty Ext.", "Service Plan", "Vehicle Loan", "Exchange"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 67, "expected_margin": "₹1"}	{"credit": "40%", "income": "14%", "market": "6%", "behaviour": "21%"}	{"Insurance": "71%", "EMI Shield": "74%"}	draft	bf5a7e80-ee76-56c8-9109-ce91b6ce5f04	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ekaraj Sengupta	Chandigarh	High	On-time	["Warranty Ext.", "Insurance", "Vehicle Loan", "Exchange"]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 85, "expected_margin": "₹1"}	{"credit": "35%", "income": "7%", "market": "14%", "behaviour": "21%"}	{"EMI Shield": "75%", "Service Plan": "89%"}	approved	a9ebd361-7611-5f54-a1a1-0f65d6938ddb	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Quincy Gandhi	Coimbatore	Medium	1 late	["Insurance", "Warranty Ext."]	{"risk": "Medium", "headline": "Refer to relationship manager", "confidence": 69, "expected_margin": "₹0"}	{"credit": "16%", "income": "11%", "market": "5%", "behaviour": "19%"}	{"Exchange": "89%", "Service Plan": "91%"}	draft	1e3ea378-ff96-53fb-8a1c-9a89f8775b29	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Yuvraj Wali	Guwahati	High	On-time	["Warranty Ext.", "Exchange", "Insurance"]	{"risk": "Low", "headline": "Send service plan discount", "confidence": 75, "expected_margin": "₹1"}	{"credit": "13%", "income": "30%", "market": "9%", "behaviour": "10%"}	{"Service Plan": "77%", "Vehicle Loan": "71%"}	approved	0499f10c-e929-5a74-84f5-046e89cbfaba	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Zashil Dara	Indore	High	On-time	["Warranty Ext.", "Insurance", "EMI Shield"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 76, "expected_margin": "₹1"}	{"credit": "30%", "income": "16%", "market": "3%", "behaviour": "18%"}	{"Service Plan": "90%", "Vehicle Loan": "69%"}	approved	573d9c31-e77f-5ee1-a08c-0bd603ce7d28	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Vrinda Kamdar	Jaipur	Medium	1 late	["Exchange", "Vehicle Loan"]	{"risk": "Medium", "headline": "Refer to relationship manager", "confidence": 68, "expected_margin": "₹0"}	{"credit": "20%", "income": "11%", "market": "10%", "behaviour": "22%"}	{"Insurance": "73%", "EMI Shield": "86%"}	draft	952f6229-806b-5c45-80ba-948f50835c10	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Qadim Baral	Hyderabad	Medium	1 late	["Vehicle Loan", "Warranty Ext."]	{"risk": "Medium", "headline": "Pitch insurance renewal bundling", "confidence": 65, "expected_margin": "₹1"}	{"credit": "38%", "income": "17%", "market": "12%", "behaviour": "17%"}	{"Exchange": "82%", "Service Plan": "73%"}	draft	1f01cf8e-eb55-5eea-a6a8-f170fd863c88	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ranveer Chandra	Ranchi	Medium	1 late	["Insurance", "Exchange", "Vehicle Loan", "Service Plan"]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 63, "expected_margin": "₹0"}	{"credit": "11%", "income": "30%", "market": "15%", "behaviour": "5%"}	{"EMI Shield": "83%", "Warranty Ext.": "85%"}	draft	35a3335e-43dd-5b7b-ac26-26f334736ef5	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Zaid Sem	Indore	Medium	On-time	["EMI Shield", "Service Plan", "Exchange", "Insurance"]	{"risk": "Medium", "headline": "Refer to relationship manager", "confidence": 63, "expected_margin": "₹1"}	{"credit": "36%", "income": "14%", "market": "7%", "behaviour": "5%"}	{"Vehicle Loan": "64%", "Warranty Ext.": "60%"}	draft	99012a2b-ffbc-5238-a1a2-343aa1979c71	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
David Rout	Lucknow	Medium	1 late	["Service Plan", "Insurance", "Vehicle Loan", "Exchange"]	{"risk": "Medium", "headline": "Pitch insurance renewal bundling", "confidence": 65, "expected_margin": "₹1"}	{"credit": "30%", "income": "8%", "market": "9%", "behaviour": "9%"}	{"EMI Shield": "82%", "Warranty Ext.": "74%"}	draft	865112d8-9d87-5cce-b0f4-5477a3a14961	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Xiti Krishna	Bengaluru	Medium	On-time	["Exchange", "Service Plan", "EMI Shield", "Insurance"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 57, "expected_margin": "₹1"}	{"credit": "28%", "income": "19%", "market": "7%", "behaviour": "21%"}	{"Vehicle Loan": "77%", "Warranty Ext.": "80%"}	draft	3aabf133-7a67-5dc2-94ef-4f3580d81a78	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Theodore Jayaraman	Bhubaneswar	Medium	1 late	["Insurance", "Exchange", "EMI Shield"]	{"risk": "Medium", "headline": "Send service plan discount", "confidence": 61, "expected_margin": "₹0"}	{"credit": "16%", "income": "26%", "market": "10%", "behaviour": "15%"}	{"Service Plan": "82%", "Vehicle Loan": "82%", "Warranty Ext.": "70%"}	draft	34718756-1fc5-5ab3-b888-cebd841a9373	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Nikita Kara	Indore	High	On-time	["Warranty Ext."]	{"risk": "Low", "headline": "Pitch insurance renewal bundling", "confidence": 78, "expected_margin": "₹1"}	{"credit": "21%", "income": "20%", "market": "6%", "behaviour": "25%"}	{"EMI Shield": "87%", "Service Plan": "88%", "Vehicle Loan": "90%"}	approved	ec5916da-5c36-5833-abaa-5c0c366235bc	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ekani Dhingra	Lucknow	High	On-time	["Vehicle Loan", "Insurance", "Service Plan", "Warranty Ext."]	{"risk": "Medium", "headline": "Pitch insurance renewal bundling", "confidence": 77, "expected_margin": "₹0"}	{"credit": "34%", "income": "25%", "market": "9%", "behaviour": "14%"}	{"Exchange": "74%", "EMI Shield": "94%"}	approved	72c33f83-dd63-584c-b094-1a208d61e607	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Radhika Arya	Hyderabad	High	On-time	["Service Plan", "EMI Shield", "Vehicle Loan"]	{"risk": "Medium", "headline": "Pre-approve top-up loan", "confidence": 77, "expected_margin": "₹0"}	{"credit": "24%", "income": "15%", "market": "2%", "behaviour": "7%"}	{"Exchange": "88%", "Warranty Ext.": "93%"}	approved	e3a8c08b-1790-5bc9-844f-3d21d2f161ca	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Thomas Jaggi	Guwahati	Medium	1 late	["Service Plan", "Exchange"]	{"risk": "Low", "headline": "Pitch insurance renewal bundling", "confidence": 67, "expected_margin": "₹0"}	{"credit": "44%", "income": "13%", "market": "6%", "behaviour": "23%"}	{"Vehicle Loan": "93%", "Warranty Ext.": "70%"}	draft	3cb302b9-ada7-5afa-9f5c-9f0f61b70e05	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Tejas Halder	Surat	High	On-time	["Vehicle Loan", "Service Plan"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 73, "expected_margin": "₹1"}	{"credit": "39%", "income": "20%", "market": "6%", "behaviour": "24%"}	{"Exchange": "64%", "EMI Shield": "79%"}	approved	004bac53-9b69-56de-adc6-06012cc89d45	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Ekta Naik	Jaipur	High	On-time	["Warranty Ext."]	{"risk": "Low", "headline": "Pitch insurance renewal bundling", "confidence": 78, "expected_margin": "₹0"}	{"credit": "34%", "income": "22%", "market": "4%", "behaviour": "25%"}	{"Exchange": "95%", "Service Plan": "90%", "Vehicle Loan": "76%"}	approved	05726d18-c0ee-5772-b3aa-b53babfa4653	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Aryan Tank	Vijayawada	High	On-time	["Insurance", "Vehicle Loan"]	{"risk": "Low", "headline": "Upgrade to premium variant with exchange", "confidence": 73, "expected_margin": "₹1"}	{"credit": "41%", "income": "5%", "market": "13%", "behaviour": "9%"}	{"EMI Shield": "92%", "Service Plan": "88%", "Warranty Ext.": "95%"}	approved	a2c40ee8-f9ed-5c73-85d5-c33d23fccaad	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Yagnesh Baria	Ranchi	High	On-time	["Vehicle Loan"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 70, "expected_margin": "₹1"}	{"credit": "32%", "income": "9%", "market": "14%", "behaviour": "15%"}	{"EMI Shield": "68%", "Warranty Ext.": "69%"}	approved	0da385ca-8351-5db3-81b6-dea82d2f45f4	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Oscar Mohanty	Nashik	Medium	1 late	["Insurance", "EMI Shield", "Vehicle Loan"]	{"risk": "Low", "headline": "Refer to relationship manager", "confidence": 69, "expected_margin": "₹1"}	{"credit": "31%", "income": "17%", "market": "7%", "behaviour": "17%"}	{"Exchange": "68%", "Warranty Ext.": "85%"}	draft	ab9ca5b7-3011-5634-aa16-fc4beed65882	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Lohit Bali	Delhi	High	On-time	["Vehicle Loan", "EMI Shield", "Service Plan", "Exchange"]	{"risk": "Low", "headline": "Offer EMI holiday for 2 months", "confidence": 83, "expected_margin": "₹2"}	{"credit": "17%", "income": "30%", "market": "4%", "behaviour": "18%"}	{"Insurance": "87%", "Warranty Ext.": "71%"}	approved	18a54a6a-77fd-5fd9-a064-846de945ce5f	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Varsha Ramakrishnan	Bengaluru	Medium	On-time	["Insurance", "EMI Shield", "Service Plan"]	{"risk": "Low", "headline": "Upgrade to premium variant with exchange", "confidence": 65, "expected_margin": "₹1"}	{"credit": "19%", "income": "29%", "market": "8%", "behaviour": "15%"}	{"Exchange": "86%", "Vehicle Loan": "88%", "Warranty Ext.": "76%"}	draft	152e3b36-81e6-5333-9ba6-64431a9288c5	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Lila Sami	Ranchi	High	On-time	["Insurance", "Vehicle Loan", "Service Plan"]	{"risk": "Low", "headline": "Refer to relationship manager", "confidence": 70, "expected_margin": "₹2"}	{"credit": "27%", "income": "14%", "market": "4%", "behaviour": "22%"}	{"Exchange": "89%", "Warranty Ext.": "87%"}	approved	630e7091-27d1-5db3-b61d-6545f3f6c76d	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Samuel Sharma	Ahmedabad	High	On-time	["Insurance"]	{"risk": "Low", "headline": "Pre-approve top-up loan", "confidence": 74, "expected_margin": "₹1"}	{"credit": "17%", "income": "11%", "market": "10%", "behaviour": "7%"}	{"Service Plan": "73%", "Warranty Ext.": "82%"}	approved	639adcae-d5d8-5c9d-83f6-53463fc09bfc	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Yatan Sethi	Ludhiana	High	On-time	["Service Plan", "Vehicle Loan", "Warranty Ext."]	{"risk": "Low", "headline": "Pre-approve top-up loan", "confidence": 73, "expected_margin": "₹1"}	{"credit": "35%", "income": "17%", "market": "15%", "behaviour": "9%"}	{"Exchange": "95%", "Insurance": "85%"}	approved	51fd8e09-b434-57c1-b6db-f27f3c063450	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Sathvik Goyal	Coimbatore	Medium	1 late	["Exchange", "Insurance"]	{"risk": "Medium", "headline": "Pre-approve top-up loan", "confidence": 64, "expected_margin": "₹2"}	{"credit": "24%", "income": "9%", "market": "3%", "behaviour": "15%"}	{"Vehicle Loan": "86%", "Warranty Ext.": "68%"}	draft	a505a9f4-33c1-571d-830d-6ad86c31a827	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
Gayathri Luthra	Kolkata	Medium	On-time	["Service Plan", "EMI Shield"]	{"risk": "Medium", "headline": "Offer EMI holiday for 2 months", "confidence": 56, "expected_margin": "₹1"}	{"credit": "12%", "income": "18%", "market": "15%", "behaviour": "23%"}	{"Insurance": "84%", "Vehicle Loan": "71%", "Warranty Ext.": "83%"}	draft	4ef1bc45-0f9f-5a61-957a-150c8f0f29ba	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00
\.


--
-- Data for Name: dealer_leads; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dealer_leads (dealer_id, name, vehicle, score, prob, action, revenue, status, test_drive_slot, message_sent_at, converted_at, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
f320e6d3-97a6-5033-af4c-75500878c35c	Krishna Bala	Bolero	33	55	Schedule test drive this weekend	₹10.2 L	warm	Sat 11:00	\N	\N	1	e92ec85f-8a8e-5f4e-a74c-98a4d006c055	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
f320e6d3-97a6-5033-af4c-75500878c35c	Xavier Tank	XUV700	15	37	WhatsApp follow-up with exchange offer	₹16.5 L	warm	\N	\N	\N	2	80ad8c97-3135-5567-a4cb-5313be20e15c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
f320e6d3-97a6-5033-af4c-75500878c35c	Samesh Bandi	Thar	31	46	Send festive bonus campaign	₹17.2 L	warm	Sat 17:00	\N	\N	3	edf7b6e9-7573-537c-912b-26d0f76b5192	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Frederick Taneja	Scorpio-N	16	38	Share EMI calculator link	₹20.1 L	warm	Sat 11:00	\N	\N	1	5c90264a-130e-5922-bb06-0b1cd0d86221	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Jagrati Bhalla	Scorpio-N	54	59	Escalate to sales manager (stale > 48h)	₹24.0 L	cool	Sun 16:30	\N	\N	2	6ed6640f-93dd-5b45-85b3-b314e9c9d2a4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Odika Shan	Bolero	43	58	Call with finance pre-approval pitch	₹10.0 L	warm	\N	\N	\N	3	6979ffcd-1fb4-59da-ad47-cef35e021097	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Ladli Master	Scorpio-N	50	55	Send festive bonus campaign	₹13.8 L	cool	Sat 11:00	\N	\N	4	8d71e2b0-0652-5066-8fd0-645c455a18b6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Jonathan Sarkar	XUV700	31	47	Share EMI calculator link	₹19.6 L	cool	Sun 16:30	\N	\N	5	f396abcb-dd8a-530f-96c8-7ba558783745	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Hemang D’Alia	XUV 3XO	35	56	Call with finance pre-approval pitch	₹13.8 L	warm	Sat 11:00	\N	\N	6	3a11e765-b9a5-582e-83f6-38ad55a0300f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Ikbal Khalsa	Thar	96	91	Call with finance pre-approval pitch	₹13.2 L	hot	Sat 17:00	\N	\N	0	e0de74b5-45a4-542f-b0e1-468d75e7f861	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Raksha Badal	Thar	82	79	Call with finance pre-approval pitch	₹15.9 L	hot	\N	\N	\N	1	a31bd2d0-b230-57ca-ad80-070ccc7178e3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Warjas Mall	Bolero	80	74	Call with finance pre-approval pitch	₹7.9 L	hot	\N	\N	\N	2	fdc0c4f9-8d8e-5b32-8a28-bb83a78c2fa7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Sachi Nigam	XUV700	80	74	Send festive bonus campaign	₹17.3 L	hot	Sat 17:00	\N	\N	3	e11e24a0-2f21-5c4c-bc97-07b15b508ac5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Hemangini Gopal	Thar	79	80	Call with finance pre-approval pitch	₹12.4 L	hot	Sun 16:30	\N	\N	4	3b148005-833a-5a9f-bb2b-1c75d15316ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Shivani Saran	XUV700	94	82	Schedule test drive this weekend	₹14.1 L	hot	Sat 17:00	\N	\N	5	5bc259ce-584c-52db-b8b1-e650d76dd121	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Isha Dewan	Bolero	72	74	Call with finance pre-approval pitch	₹8.3 L	message_sent	Sun 16:30	2026-07-28 10:30:00+00	\N	6	c34720be-a2a7-5c79-8f32-f10a2dda2763	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	Faras Deep	XUV 3XO	86	84	Escalate to sales manager (stale > 48h)	₹8.7 L	hot	Sat 11:00	\N	\N	7	6485abcd-e3eb-5f9c-996c-8c85f290c9e1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Jagat Patla	Bolero	29	46	Call with finance pre-approval pitch	₹10.2 L	warm	Sat 11:00	\N	\N	1	c8eab2c1-cd1c-5a38-a75a-2a07e0d891da	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Bachittar Malhotra	Scorpio-N	29	44	Schedule test drive this weekend	₹19.5 L	cool	Sat 17:00	\N	\N	2	cd561e51-cccf-538e-a034-ac1a3490feca	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Damini Pandey	Bolero	34	55	WhatsApp follow-up with exchange offer	₹8.8 L	warm	Sun 16:30	\N	\N	3	34f22e0d-879e-5456-92a7-a1358a3a2b79	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Amaira Sengupta	Scorpio-N	63	72	Call with finance pre-approval pitch	₹20.0 L	converted	Sun 16:30	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	4	cc6ec6c5-b1f7-57e0-bd6b-b5a711e7052f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Praneel Kara	Scorpio-N	54	60	Send festive bonus campaign	₹23.7 L	cool	Sat 17:00	\N	\N	5	ae3309ba-2f71-5763-a79f-c95d142bd6bf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Michael Patla	Bolero	25	49	WhatsApp follow-up with exchange offer	₹8.7 L	warm	Sat 17:00	\N	\N	6	cd3b3e12-7b4e-5ec1-9f9b-8099f919bec6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Tejas Deol	XUV700	64	71	Escalate to sales manager (stale > 48h)	₹20.5 L	message_sent	Sun 16:30	2026-07-28 10:30:00+00	\N	7	d1928b04-91a4-51c4-9a7a-cb29629b9730	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Chakradhar Khosla	XUV700	14	33	WhatsApp follow-up with exchange offer	₹23.9 L	cool	Sat 11:00	\N	\N	0	b5b899cb-2c8a-5770-991d-e28a3178d747	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Meghana Buch	Thar	43	58	Schedule test drive this weekend	₹13.4 L	cool	Sat 11:00	\N	\N	1	352e7e6c-f8df-513f-9f9f-3e02ae46943a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Kevin Dixit	Bolero	27	42	Escalate to sales manager (stale > 48h)	₹7.8 L	warm	Sun 16:30	\N	\N	2	084d1fc8-3c9f-53f0-ad43-4f7582c374de	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Ekapad Sengupta	Bolero	41	51	Send festive bonus campaign	₹8.2 L	cool	Sat 11:00	\N	\N	3	a9bddb24-43db-5084-be01-58add28be81a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Sai Ramakrishnan	XUV 3XO	28	45	Call with finance pre-approval pitch	₹9.2 L	cool	Sat 11:00	\N	\N	4	bc44b8c5-90d1-57b7-8918-a3a99ffca567	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c5ffe366-5bf3-5335-8af0-4387365cd2fd	Triveni Tara	XUV700	42	57	WhatsApp follow-up with exchange offer	₹23.6 L	warm	Sun 16:30	\N	\N	5	f34f667f-4e66-5493-b04b-10e89b9263f0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Omaja Palan	Bolero	52	66	Escalate to sales manager (stale > 48h)	₹10.2 L	cool	Sat 11:00	\N	\N	0	3519b460-45b4-5108-b69b-8aca4b83d9ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Arunima Sule	XUV 3XO	57	61	Escalate to sales manager (stale > 48h)	₹14.5 L	message_sent	Sun 16:30	2026-07-28 10:30:00+00	\N	1	23b2a01f-5234-5e0d-b23b-90f6083f50ea	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Onkar Amble	Bolero	53	60	Share EMI calculator link	₹9.6 L	cool	Sun 16:30	\N	\N	2	54aa8ce0-b294-58cd-8950-7af6f6a57e39	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Jairaj Ramaswamy	XUV 3XO	18	44	Send festive bonus campaign	₹10.9 L	warm	Sat 11:00	\N	\N	3	0c4e983d-9273-56bf-b343-7beab2379868	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Arjun Chowdhury	XUV 3XO	49	63	WhatsApp follow-up with exchange offer	₹9.6 L	warm	Sat 11:00	\N	\N	4	7a908a8e-2121-5f64-b8b3-24cd388d514f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Amrita Kalla	XUV 3XO	45	62	Escalate to sales manager (stale > 48h)	₹9.7 L	cool	Sat 11:00	\N	\N	5	dc429c29-310e-5232-9079-e963c0459b3d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
2fd412f6-8784-5129-9369-21046a8f9682	Parth Sur	XUV700	49	63	Schedule test drive this weekend	₹20.1 L	warm	Sun 16:30	\N	\N	6	0480ef99-ec77-5d39-bb8b-f58c23b24973	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Zaitra Wable	Thar	57	69	Share EMI calculator link	₹15.7 L	converted	Sat 17:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	0	a5c8d1ff-c90f-5525-8cd9-f2d1ab703a3d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Manbir Narayan	Scorpio-N	23	48	Call with finance pre-approval pitch	₹22.8 L	cool	Sat 11:00	\N	\N	1	357c62ab-5213-519d-863f-826abc078f19	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Mitali Krishna	XUV 3XO	35	47	Escalate to sales manager (stale > 48h)	₹11.4 L	warm	\N	\N	\N	2	40b8d2ec-cdcf-58ba-9fa0-36bf985a8c45	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Ganga Chhabra	XUV700	40	52	WhatsApp follow-up with exchange offer	₹18.4 L	cool	Sat 11:00	\N	\N	3	97a032d4-f076-54cb-ab2a-7e08c9a2476d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
bfe3aa47-0df0-57db-a271-2e053d38beb3	Ucchal Deshmukh	Scorpio-N	28	51	Escalate to sales manager (stale > 48h)	₹20.3 L	message_sent	Sun 16:30	2026-08-06 05:09:44.030357+00	\N	0	680f324d-7693-5fc9-890e-df6648a4dfcc	2026-08-06 04:41:53.792545+00	2026-08-06 05:09:44.02385+00	\N
fca56e3a-201b-5e67-8f1e-6a97a54de974	Anamika Narula	Bolero	31	49	Send festive bonus campaign	₹9.4 L	converted	Sat 17:00	\N	2026-08-06 05:25:21.36233+00	0	5853868b-cbc4-5aea-911c-20f9c8db2a0e	2026-08-06 04:41:53.792545+00	2026-08-06 05:25:21.349583+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Ekani Sanghvi	Scorpio-N	30	43	Schedule test drive this weekend	₹14.3 L	warm	Sat 11:00	\N	\N	4	5cdd9528-409d-526a-af09-388b15b1c290	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Harshil Bath	Bolero	46	62	Call with finance pre-approval pitch	₹8.2 L	warm	Sat 11:00	\N	\N	5	faff0f50-122c-5de0-9f99-52a32e1b1e93	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
7d6fbdd4-80fc-5d44-a950-cb49290189ef	Nitesh Toor	Scorpio-N	22	46	WhatsApp follow-up with exchange offer	₹22.3 L	warm	Sat 17:00	\N	\N	6	b00999b2-f14d-541e-933a-c1684fb997e5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
addd6a3e-8a0a-57c5-8b1c-0b394155b548	Yug Panchal	Scorpio-N	42	52	Share EMI calculator link	₹21.8 L	warm	Sat 17:00	\N	\N	0	489b6864-791d-5840-9a2d-da9cd9b94c8d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
addd6a3e-8a0a-57c5-8b1c-0b394155b548	Imaran Mann	XUV 3XO	42	57	Schedule test drive this weekend	₹11.1 L	cool	\N	\N	\N	1	1572c351-6d7f-5ea7-8e3e-04bed84ff578	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
addd6a3e-8a0a-57c5-8b1c-0b394155b548	Neel Modi	Scorpio-N	48	54	Call with finance pre-approval pitch	₹15.3 L	cool	Sat 11:00	\N	\N	2	704f0aea-5c88-5aad-a6cd-1fbdd3b0b51b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
addd6a3e-8a0a-57c5-8b1c-0b394155b548	Kamala Wali	XUV 3XO	49	54	WhatsApp follow-up with exchange offer	₹11.8 L	warm	\N	\N	\N	3	c2bbb2df-71b5-5ce6-aaee-301a6c163bc0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a35a713f-ab92-5e7d-8e37-510e872498f3	Ishita Nayar	Scorpio-N	66	71	Send festive bonus campaign	₹21.1 L	converted	Sun 16:30	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	0	f4e5fb3e-93a7-5b84-85ce-e574bb9baa6a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a35a713f-ab92-5e7d-8e37-510e872498f3	Bhavna Modi	Thar	46	63	Escalate to sales manager (stale > 48h)	₹17.4 L	warm	Sat 11:00	\N	\N	1	80b223b2-19e9-5cb6-aac7-31de08e2c90e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a35a713f-ab92-5e7d-8e37-510e872498f3	Jyoti Pant	XUV700	75	80	Call with finance pre-approval pitch	₹14.7 L	hot	Sat 11:00	\N	\N	2	8328c3fa-0836-5915-8b56-e65f3eb3410c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a35a713f-ab92-5e7d-8e37-510e872498f3	Gaurika Soni	XUV 3XO	45	62	Send festive bonus campaign	₹11.1 L	warm	\N	\N	\N	3	95474a52-4ee6-55dc-a735-f29586e1165f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a35a713f-ab92-5e7d-8e37-510e872498f3	Priya Narasimhan	XUV700	55	59	Schedule test drive this weekend	₹19.6 L	message_sent	Sat 17:00	2026-07-28 10:30:00+00	\N	4	71b9413a-e6ff-52ab-9fc9-5d48b033876a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Ishwar Morar	XUV 3XO	96	84	Schedule test drive this weekend	₹14.4 L	hot	Sun 16:30	\N	\N	0	31c4a52d-2fea-5135-9bc6-3bb08bd9f23e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Anthony Sampath	Scorpio-N	88	80	Share EMI calculator link	₹23.1 L	hot	Sat 11:00	\N	\N	1	ca91d3f5-aebf-5294-b67d-39b2af274e0e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Gautami Chadha	XUV 3XO	87	80	Share EMI calculator link	₹11.0 L	hot	Sat 17:00	\N	\N	2	2eccc887-d902-528a-aa5e-10cde87d1b02	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Mugdha Mitra	Bolero	93	88	Schedule test drive this weekend	₹10.5 L	hot	Sat 17:00	\N	\N	3	453bf3e0-d406-5e70-859f-a4f049245a0f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Jhalak Madan	Scorpio-N	84	80	Share EMI calculator link	₹17.5 L	hot	Sun 16:30	\N	\N	4	165ef82c-44b4-55b3-8a63-d5a131929859	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
54257627-24ea-5867-978a-84a6ebf61e91	Jalsa Nagarajan	Scorpio-N	74	78	Share EMI calculator link	₹17.2 L	converted	Sat 17:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	5	b4f838e6-9cfd-562f-8943-cdb8735172d8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Janya Kalita	Thar	38	56	Schedule test drive this weekend	₹12.0 L	cool	Sat 11:00	\N	\N	0	c1fb7a38-c92e-5f32-be72-fd9b9299db96	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Yatan Koshy	Thar	44	59	Call with finance pre-approval pitch	₹11.5 L	cool	\N	\N	\N	1	29bb124c-4e64-58aa-8fac-c93aeb983852	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Dev Chanda	XUV 3XO	19	42	Schedule test drive this weekend	₹13.0 L	warm	Sat 11:00	\N	\N	2	44654f6d-1728-5742-98bc-a401c2155cf8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Thomas Behl	XUV 3XO	38	57	WhatsApp follow-up with exchange offer	₹12.8 L	warm	Sat 17:00	\N	\N	3	2d67417b-b75a-5058-b711-0aaa65eb6f91	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Hema Sunder	Scorpio-N	43	61	Schedule test drive this weekend	₹23.0 L	warm	\N	\N	\N	4	31afaa9a-3fc4-559d-92c0-71eccbe83090	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Shaurya Salvi	XUV 3XO	46	57	WhatsApp follow-up with exchange offer	₹10.1 L	cool	\N	\N	\N	5	a9245d3e-3415-5fd4-8695-d30447974ec9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Aarini Hegde	Bolero	39	55	Share EMI calculator link	₹9.7 L	warm	Sat 17:00	\N	\N	6	d493a770-24dc-5dc3-86dc-2edb2d2b7f99	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d10b4481-5c27-55ee-9885-e908f834f426	Yuvraj Sant	Bolero	49	63	Schedule test drive this weekend	₹9.4 L	warm	Sat 11:00	\N	\N	7	1984ae64-74b9-592b-a101-7ee797c94ac2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Gagan Mahajan	Scorpio-N	91	90	Call with finance pre-approval pitch	₹16.7 L	hot	Sun 16:30	\N	\N	0	c885553f-b997-5c0d-954c-8dccd13ae4f9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Dalbir Jhaveri	Scorpio-N	100	89	Share EMI calculator link	₹16.4 L	hot	Sat 17:00	\N	\N	1	fca01a0d-c20d-5f00-bd55-348dfdd9e9e4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Nihal Sha	Bolero	90	86	Send festive bonus campaign	₹9.3 L	hot	Sat 11:00	\N	\N	2	e09082b8-5129-57b9-b37e-c2e6b1d6c891	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Azaan Sibal	XUV700	81	77	Share EMI calculator link	₹23.1 L	hot	Sat 11:00	\N	\N	3	627c2ef1-a5e4-5f00-832f-f57f64531aa4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Guneet Gulati	XUV700	85	76	Share EMI calculator link	₹25.7 L	hot	\N	\N	\N	4	e2a8d49e-44a1-591b-90d8-fe6fce00060a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	Gaurang Sathe	XUV700	96	88	Escalate to sales manager (stale > 48h)	₹24.1 L	hot	Sat 11:00	\N	\N	5	04897dda-389c-5b86-845b-0b20e74d6c7c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Hredhaan Natarajan	XUV700	30	49	Share EMI calculator link	₹15.3 L	cool	Sat 11:00	\N	\N	0	0b4bd3b8-eab0-5a23-861b-0fdd6d5d11bf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Umang Karpe	Bolero	23	44	Send festive bonus campaign	₹8.4 L	cool	\N	\N	\N	1	379dc5d3-08a4-5554-b6e8-b0b206e73ff1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Urvashi Shere	Scorpio-N	41	54	Schedule test drive this weekend	₹14.7 L	cool	\N	\N	\N	2	5bb364d8-7657-5ff5-9aaf-aa74ef2673b8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Radha Mandal	XUV700	41	51	Call with finance pre-approval pitch	₹25.0 L	warm	Sat 17:00	\N	\N	3	7027a8ae-171f-585c-a4de-c03ea9b28bb5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Watika Borah	Bolero	24	45	Send festive bonus campaign	₹9.9 L	warm	\N	\N	\N	4	a3a86a65-3ca0-519d-87ce-1ec865cd7a06	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Adweta Narain	XUV700	27	42	WhatsApp follow-up with exchange offer	₹13.6 L	cool	Sun 16:30	\N	\N	5	f011784c-8a77-52fe-9325-5c560d3a143c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Ekavir Gour	Bolero	37	51	Schedule test drive this weekend	₹8.4 L	warm	Sat 11:00	\N	\N	6	2cffc821-f90b-5365-95f7-c7ed0c5005fc	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
c0c42c6f-9218-5121-9206-6c36af338888	Devansh Ganguly	Scorpio-N	15	42	WhatsApp follow-up with exchange offer	₹18.6 L	cool	\N	\N	\N	7	e662d1b8-35ee-54d2-b94a-37fc5acc3121	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Ranbir Koshy	XUV700	49	57	Share EMI calculator link	₹14.8 L	warm	Sat 11:00	\N	\N	0	9da2cbb6-fdfe-50ca-9bdf-8efe9cdc7522	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Ekanta Salvi	XUV 3XO	26	50	Call with finance pre-approval pitch	₹9.7 L	cool	Sat 17:00	\N	\N	1	7e7a45fb-faed-5774-8111-85a88af552db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Nachiket Prabhakar	XUV 3XO	44	56	Escalate to sales manager (stale > 48h)	₹10.2 L	warm	Sat 11:00	\N	\N	2	d33832a8-3142-5896-9270-10276e6daf08	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Gunbir Rajan	Thar	48	64	Call with finance pre-approval pitch	₹15.4 L	warm	Sat 17:00	\N	\N	3	6ed6150e-57e0-5e13-a53f-5df2abda169b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Tanay Kade	XUV 3XO	56	63	WhatsApp follow-up with exchange offer	₹9.1 L	converted	\N	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	4	bf805366-4441-5fa5-997c-7ab26dce6c89	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	Kashvi Kumer	Thar	64	63	WhatsApp follow-up with exchange offer	₹11.2 L	message_sent	\N	2026-07-28 10:30:00+00	\N	5	37ddc6c6-e32b-5e42-b209-4039e5dc38f7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Lucky Goswami	Scorpio-N	41	50	WhatsApp follow-up with exchange offer	₹24.1 L	warm	Sun 16:30	\N	\N	0	554cf29a-f2c7-594b-a9fe-2805c9bc8160	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Suhani Iyer	XUV 3XO	47	61	Escalate to sales manager (stale > 48h)	₹12.6 L	warm	Sat 11:00	\N	\N	1	1ca1fb27-9d56-50b8-b34e-d0069e73821d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Maanav Sarma	Thar	72	78	WhatsApp follow-up with exchange offer	₹11.8 L	converted	Sat 17:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	2	a32c0859-7631-59c9-9630-3d993842ce13	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Jason Manne	Thar	36	53	Send festive bonus campaign	₹13.7 L	cool	\N	\N	\N	3	a3ee5a25-851c-50ae-9f93-a565ab1011db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Saumya Andra	Bolero	68	74	Escalate to sales manager (stale > 48h)	₹9.1 L	message_sent	Sat 17:00	2026-07-28 10:30:00+00	\N	4	ce3517d3-be94-5de2-9827-5091caf39b6f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Avni Barad	Thar	52	63	Schedule test drive this weekend	₹16.6 L	warm	Sat 11:00	\N	\N	5	3e5a4844-ff55-5127-a2a4-9101e817ef9f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Ekantika Sidhu	Bolero	54	64	Call with finance pre-approval pitch	₹8.8 L	cool	\N	\N	\N	6	06ebf734-d48d-5e31-8bd4-ae84426060e1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3112bb9c-aaf9-549c-8b65-af781a6daa95	Anita Behl	XUV700	73	70	WhatsApp follow-up with exchange offer	₹16.2 L	warm	Sat 11:00	\N	\N	7	800e1256-ff72-52fa-bb26-41f457c07bbb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
29f5dcf7-c02f-5bba-a81c-cad1d889ff87	Kashish Kalla	Thar	79	72	Share EMI calculator link	₹13.7 L	hot	Sat 11:00	\N	\N	0	c92d2fd2-1245-565b-8275-3ba64aa5cee0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
29f5dcf7-c02f-5bba-a81c-cad1d889ff87	Mekhala Johal	Scorpio-N	56	69	Escalate to sales manager (stale > 48h)	₹18.7 L	converted	Sat 17:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	1	bf7a6965-d2d2-55df-a0a5-549c8ad1e9e4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
29f5dcf7-c02f-5bba-a81c-cad1d889ff87	Prisha Dhawan	XUV 3XO	69	74	Escalate to sales manager (stale > 48h)	₹8.1 L	warm	Sat 17:00	\N	\N	2	f52cf7ef-f2d5-5bca-bc00-3f6d47d1fde4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
29f5dcf7-c02f-5bba-a81c-cad1d889ff87	Ekalinga Karan	Thar	62	69	Send festive bonus campaign	₹11.2 L	converted	Sat 11:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	3	7825ff0d-6b28-58e0-8857-b4f13179021e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
b321bec9-e4bd-539c-ad02-26bf1bde8a50	Dayita Chaudry	Bolero	73	73	Escalate to sales manager (stale > 48h)	₹7.9 L	converted	Sun 16:30	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	0	fd50a006-4edf-54a1-9886-66f2ce362223	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
b321bec9-e4bd-539c-ad02-26bf1bde8a50	Ayush Aurora	Bolero	100	85	Share EMI calculator link	₹10.2 L	hot	\N	\N	\N	1	7f2a7f2a-018f-524c-a1b0-f97a1e6d738f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
b321bec9-e4bd-539c-ad02-26bf1bde8a50	Champak Butala	Thar	69	66	Send festive bonus campaign	₹12.1 L	converted	Sat 11:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	2	cf7ffdf5-9523-5833-9361-1ee444de85ad	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
b321bec9-e4bd-539c-ad02-26bf1bde8a50	Falan Pathak	XUV 3XO	77	81	Call with finance pre-approval pitch	₹14.4 L	hot	Sat 11:00	\N	\N	3	d2c84aac-be04-5000-bdae-267c67202a24	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
b321bec9-e4bd-539c-ad02-26bf1bde8a50	Upasna Sharaf	Thar	72	77	WhatsApp follow-up with exchange offer	₹15.8 L	converted	Sun 16:30	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	4	bd92a2d5-9d0f-5742-8021-c749cf847c07	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Isaac Karan	XUV 3XO	77	73	Schedule test drive this weekend	₹9.8 L	hot	Sat 11:00	\N	\N	0	db61d121-70d9-5d89-ac86-becd456104dc	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Jeevika Hegde	XUV700	48	56	Call with finance pre-approval pitch	₹25.4 L	cool	\N	\N	\N	1	595be406-57d4-52f1-9a91-e923482e0819	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Zarna Walla	XUV 3XO	55	58	Schedule test drive this weekend	₹8.2 L	converted	Sat 17:00	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	2	f3db0981-a6cd-5a37-a8f5-6098377b7257	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Ishaan Som	XUV 3XO	53	65	Schedule test drive this weekend	₹15.4 L	cool	\N	\N	\N	3	3a22f931-1581-5dd2-af68-aecd88992ccb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Theodore Dar	Scorpio-N	73	73	Call with finance pre-approval pitch	₹24.3 L	message_sent	\N	2026-07-28 10:30:00+00	\N	4	00b16908-3ec3-5f46-85c7-7b8f34cdd5d3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Aarnav Borra	XUV 3XO	88	83	Send festive bonus campaign	₹10.2 L	hot	Sat 11:00	\N	\N	5	3fee81fa-6978-5d18-8a64-396cf78525d1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
d330d70a-cd36-5d8b-8d2e-a382af6bb516	Samarth Rajagopal	XUV700	88	84	Schedule test drive this weekend	₹19.7 L	hot	Sat 11:00	\N	\N	6	c9b81441-076d-5ee9-a1eb-089149640323	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a36502e6-e27b-55d9-8059-6b59a8a89b64	Saanvi Biswas	Scorpio-N	48	58	Schedule test drive this weekend	₹18.0 L	warm	Sat 17:00	\N	\N	0	8dc30bad-cfd4-5f38-9f58-4f0c9d0f9efd	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a36502e6-e27b-55d9-8059-6b59a8a89b64	Varenya Desai	XUV700	16	45	WhatsApp follow-up with exchange offer	₹24.6 L	cool	Sat 11:00	\N	\N	1	9ad8a5d7-0181-5db2-87cd-241abdbb8346	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a36502e6-e27b-55d9-8059-6b59a8a89b64	Wriddhish Kar	Thar	18	38	Send festive bonus campaign	₹14.6 L	cool	Sat 11:00	\N	\N	2	34b7bf3b-3da9-52d6-b64b-b3d92203694f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a36502e6-e27b-55d9-8059-6b59a8a89b64	Faraj Pandit	XUV 3XO	38	56	Call with finance pre-approval pitch	₹14.1 L	cool	Sat 11:00	\N	\N	3	c0abba4f-24e9-51a5-a35f-b22863be4985	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
a36502e6-e27b-55d9-8059-6b59a8a89b64	Netra Amble	Thar	11	32	Call with finance pre-approval pitch	₹13.6 L	cool	Sat 17:00	\N	\N	4	62c8583d-20da-5300-9abe-5b2473349ac3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Indrajit Shan	XUV 3XO	37	57	Share EMI calculator link	₹8.3 L	cool	\N	\N	\N	0	ee267edf-2e51-537f-bc95-032a6f0e0549	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Pallavi Chaudhary	Thar	29	43	Schedule test drive this weekend	₹13.1 L	cool	Sat 11:00	\N	\N	1	5346b80d-730f-5169-b25f-4b84496442a4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Anika Date	XUV 3XO	20	46	Send festive bonus campaign	₹9.9 L	cool	Sat 17:00	\N	\N	2	6e684aad-968e-53a5-839f-48270d66a068	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Harsh Dani	Thar	39	51	WhatsApp follow-up with exchange offer	₹12.1 L	cool	Sat 17:00	\N	\N	3	e70b5d64-d8da-5fba-b010-06f589507419	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Jack Dey	XUV 3XO	17	43	WhatsApp follow-up with exchange offer	₹13.3 L	warm	Sun 16:30	\N	\N	4	591c2d8d-f496-5c92-8dc9-52dd00510f9e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Hardik Nadkarni	XUV700	39	49	Escalate to sales manager (stale > 48h)	₹21.6 L	warm	Sat 17:00	\N	\N	5	bd5664c6-1b09-5fe4-b003-e40e21e1ed24	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
47c5f037-e1d9-501a-9c4b-d3b50abe9e93	Amruta Agrawal	Bolero	26	46	WhatsApp follow-up with exchange offer	₹7.8 L	cool	\N	\N	\N	6	3a2407a0-f613-5aff-9415-6d3f0fbd3217	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Triya Goda	Bolero	70	67	Send festive bonus campaign	₹10.0 L	warm	Sat 11:00	\N	\N	0	75fb487c-91c5-5c95-b087-570298abcf3b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Chandran Ray	XUV700	69	66	Escalate to sales manager (stale > 48h)	₹23.6 L	warm	Sat 17:00	\N	\N	1	f2a64556-c8bb-5752-b7da-e29db3b97268	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Upma Warrior	Scorpio-N	64	69	Call with finance pre-approval pitch	₹16.4 L	converted	\N	2026-07-28 10:30:00+00	2026-07-30 14:05:00+00	2	27cbee35-f38f-5955-bbf4-d65029547a54	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Isaiah Golla	Thar	77	81	WhatsApp follow-up with exchange offer	₹14.9 L	hot	\N	\N	\N	3	beab9daa-be75-522b-8008-b7a0ad0b3868	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Kavya Warrior	Scorpio-N	92	81	Share EMI calculator link	₹15.6 L	hot	\N	\N	\N	4	cf93bd2d-73b9-54d4-a29c-10b81330f617	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	Riya Kale	Scorpio-N	66	75	WhatsApp follow-up with exchange offer	₹22.6 L	message_sent	\N	2026-07-28 10:30:00+00	\N	5	83405c48-ee26-5d05-9138-9b57ff761c9b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Advaith Khalsa	Scorpio-N	94	91	Escalate to sales manager (stale > 48h)	₹18.8 L	hot	Sat 11:00	\N	\N	0	3783ce89-feaf-58c5-a43c-56541ab735fb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Advay Parsa	Bolero	91	89	Call with finance pre-approval pitch	₹8.9 L	hot	Sun 16:30	\N	\N	1	8cefc511-4a04-55b0-a409-6772ccc0524e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Manya Loyal	Bolero	100	88	Schedule test drive this weekend	₹10.1 L	hot	Sat 11:00	\N	\N	2	f64bce39-0125-545f-8e55-89f1caa9aed5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Chanakya Suresh	XUV 3XO	99	92	WhatsApp follow-up with exchange offer	₹11.9 L	hot	Sat 11:00	\N	\N	3	afc8274f-43bf-5338-94aa-1711b9cafe2d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Ekaja Choudhury	XUV 3XO	100	85	WhatsApp follow-up with exchange offer	₹9.3 L	hot	\N	\N	\N	4	1662a18b-16ce-5101-a750-d39bb40a3075	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Tanveer Lala	Scorpio-N	100	85	Share EMI calculator link	₹14.7 L	hot	Sat 11:00	\N	\N	5	27096f48-706e-5c28-8a70-37cccfaee130	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
78a1fe53-ed0a-5edb-ad82-1522949e0936	Anmol Sampath	XUV700	100	95	Call with finance pre-approval pitch	₹17.4 L	hot	Sun 16:30	\N	\N	6	1b9b7660-21d6-5e24-8466-01be0ef4398f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Om Verma	Thar	100	89	Schedule test drive this weekend	₹15.4 L	hot	Sat 17:00	\N	\N	0	434f0005-6eee-5008-834e-401f3d7f0537	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Vihaan Bhasin	Scorpio-N	76	71	Call with finance pre-approval pitch	₹21.1 L	hot	Sat 17:00	\N	\N	1	f8a55648-6a6a-5e96-81ca-7369604cb2f5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Balhaar Swamy	Thar	100	90	Share EMI calculator link	₹15.6 L	hot	Sun 16:30	\N	\N	2	f3500a8e-2e0e-57c3-8f52-bfc69fa21608	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Leela Dua	Scorpio-N	69	75	Escalate to sales manager (stale > 48h)	₹20.9 L	warm	Sat 17:00	\N	\N	3	bc75983f-9362-5d33-aa80-c69e15010958	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Tarak Jaggi	XUV 3XO	68	68	Escalate to sales manager (stale > 48h)	₹13.3 L	warm	Sat 11:00	\N	\N	4	eb226981-f3a5-560e-9868-e4da851801f2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
3d03db39-0d0c-5783-be1e-b4923c639803	Harrison Handa	Thar	91	81	Escalate to sales manager (stale > 48h)	₹14.2 L	hot	\N	\N	\N	5	5a4fdf8d-adb6-5580-acb9-80c5ec0806b6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Rudra Tata	Thar	53	63	WhatsApp follow-up with exchange offer	₹15.2 L	warm	Sun 16:30	\N	\N	0	95e4af52-ae56-5a91-84ef-75d8c3044f29	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Lavanya Sankaran	Bolero	82	79	Escalate to sales manager (stale > 48h)	₹10.0 L	hot	Sat 17:00	\N	\N	1	e2233fd1-b1bc-52e9-914c-5d20acf15152	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Vyanjana Patel	Thar	52	62	Send festive bonus campaign	₹17.3 L	warm	Sun 16:30	\N	\N	2	cbf76d2e-238a-5526-bcb6-cb85b46a7a54	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Daksha Manne	XUV 3XO	92	85	Share EMI calculator link	₹13.9 L	hot	\N	\N	\N	3	3cc01481-2d12-528f-824d-63d54a8658de	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Naveen Cherian	Bolero	76	77	Share EMI calculator link	₹10.5 L	hot	Sat 11:00	\N	\N	4	8e4adac5-cff8-528e-892f-211d2d8972b3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
edea4375-e464-5b49-98d8-f81bbcaf66ee	Yadavi Andra	Bolero	75	80	Send festive bonus campaign	₹10.3 L	hot	Sun 16:30	\N	\N	5	bc9f21a1-ad84-5274-8562-b40d0c28da5e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
f320e6d3-97a6-5033-af4c-75500878c35c	Bahadurjit Padmanabhan	Bolero	17	44	Send festive bonus campaign	₹8.8 L	cool	\N	\N	\N	0	48ffc112-48d4-53a3-a289-dc4650c290cb	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00	\N
\.


--
-- Data for Name: dealers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dealers (code, name, leads, hot_leads, test_drives_pending, booking_prob, revenue_at_risk, leakage_pct, bay_util_pct, sort_order, id, created_at, updated_at) FROM stdin;
syn-d001	Surat Autolinks	218	18	10	59	₹3.9 Cr	72	94	0	f320e6d3-97a6-5033-af4c-75500878c35c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d002	Jaipur Auto Galaxy	90	10	4	51	₹1.2 Cr	72	72	1	bfe3aa47-0df0-57db-a271-2e053d38beb3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d003	Vijayawada Automobiles	200	56	22	71	₹9.7 Cr	21	74	2	8e1b5b3c-ff3c-581c-ab04-72f0b977d2d5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d004	Guwahati Auto Prime	85	11	4	61	₹2.1 Cr	57	69	3	fca56e3a-201b-5e67-8f1e-6a97a54de974	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d005	Ahmedabad Auto Prime	154	21	11	55	₹5.4 Cr	69	68	4	c5ffe366-5bf3-5335-8af0-4387365cd2fd	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d006	Ludhiana Automobiles	85	10	4	52	₹1.1 Cr	62	58	5	2fd412f6-8784-5129-9369-21046a8f9682	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d007	Coimbatore Autolinks	205	29	12	54	₹3.0 Cr	69	62	6	7d6fbdd4-80fc-5d44-a950-cb49290189ef	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d008	Kolkata Wheels	158	30	11	58	₹4.7 Cr	50	60	7	addd6a3e-8a0a-57c5-8b1c-0b394155b548	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d009	Surat SUV Center	140	22	11	65	₹3.4 Cr	43	88	8	a35a713f-ab92-5e7d-8e37-510e872498f3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d010	Ludhiana Auto Galaxy	180	43	19	78	₹7.4 Cr	28	67	9	54257627-24ea-5867-978a-84a6ebf61e91	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d011	Vijayawada Auto Galaxy	67	11	4	58	₹2.6 Cr	63	87	10	d10b4481-5c27-55ee-9885-e908f834f426	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d012	Raipur Auto Galaxy	213	88	52	83	₹9.5 Cr	18	81	11	a93cb3d8-f849-5e6b-bea9-f7e4d2d8ce4e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d013	Surat Wheels	101	12	6	58	₹1.8 Cr	68	84	12	c0c42c6f-9218-5121-9206-6c36af338888	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d014	Jaipur Mobility Hub	170	26	10	59	₹2.2 Cr	54	82	13	392bf1f3-c0a5-5d22-a05c-47f48b49a6d2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d015	Kochi Automobiles	168	37	20	63	₹5.6 Cr	44	69	14	3112bb9c-aaf9-549c-8b65-af781a6daa95	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d016	Kolkata Mobility Hub	205	46	21	69	₹10.4 Cr	25	88	15	29f5dcf7-c02f-5bba-a81c-cad1d889ff87	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d017	Nagpur Auto Galaxy	80	20	6	80	₹2.0 Cr	17	66	16	b321bec9-e4bd-539c-ad02-26bf1bde8a50	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d018	Chandigarh Mobility Hub	173	46	20	67	₹7.6 Cr	27	89	17	d330d70a-cd36-5d8b-8d2e-a382af6bb516	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d019	Coimbatore Auto Zone	120	10	5	57	₹2.2 Cr	67	90	18	a36502e6-e27b-55d9-8059-6b59a8a89b64	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d020	Ranchi SUV Center	163	23	7	62	₹3.1 Cr	67	56	19	47c5f037-e1d9-501a-9c4b-d3b50abe9e93	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d021	Mumbai Auto Zone	198	50	29	73	₹5.0 Cr	29	69	20	5eaa1879-4cd8-5ccf-bf38-f407ba53aeab	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d022	Delhi Motors	189	55	30	89	₹9.4 Cr	8	67	21	78a1fe53-ed0a-5edb-ad82-1522949e0936	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d023	Coimbatore SUV Center	73	27	8	79	₹4.1 Cr	12	79	22	3d03db39-0d0c-5783-be1e-b4923c639803	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
syn-d024	Guwahati Motors	113	32	18	76	₹8.0 Cr	29	58	23	edea4375-e464-5b49-98d8-f81bbcaf66ee	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: finance_products; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.finance_products (name, customers, risk, cross_sell, opportunity, sort_order, id, created_at, updated_at) FROM stdin;
Vehicle Loan	32K	23% low	+8.9%	Target 1182 thin-file customers with alt-data	0	22a5aa7d-b506-562c-9170-679622a42742	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Two-Wheeler Loan	21K	62% low	+8.4%	Bundle with XUV700 festive offer	1	6c0340f1-0786-50cb-a831-12d42e152033	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Commercial Vehicle Loan	20K	50% low	+8.4%	Bundle with XUV700 festive offer	2	1ab534ed-957d-5ade-a3a9-43685dcf79fe	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Loan Protection Insurance	58K	67% low	+6.1%	Bundle with XUV700 festive offer	3	71c6ac6e-b72a-5875-9884-289f136a07ba	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Comprehensive Vehicle Insurance	39K	47% low	+3.1%	Target 879 thin-file customers with alt-data	4	e1b7d2df-4c7f-5744-a1c5-3a261c9420a4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
EMI Shield	3K	47% low	+3.0%	Reduce TAT to lift conversion by 5.3%	5	e3a9ad3c-22c0-5c40-bae2-47f915f9c722	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Extended Warranty	27K	60% low	+7.2%	Renewal wave next quarter: 3742 policies	6	6baac0cb-fb6a-5f1d-8cb2-80ce26a3c7f8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Service Plan Bundle	10K	39% low	+5.9%	Bundle with XUV700 festive offer	7	90cce95e-a0b4-55ea-b0db-39e9964eb208	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Exchange Bonus Program	20K	50% low	+9.9%	Target 3583 thin-file customers with alt-data	8	c82a4c1d-5127-5d5a-889f-a6e988d45352	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Top-up Loan	12K	37% low	+3.7%	Renewal wave next quarter: 3450 policies	9	4ae4b5fb-e6bd-52b2-895d-dee24c2dbb25	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: kpi_drivers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.kpi_drivers (kpi_id, driver_text, sort_order, id, created_at, updated_at) FROM stdin;
931549cb-f64a-560d-b8e9-e87593313ad7	Nagpur Auto Galaxy booking conversion +10%	0	0c7b1afd-d2dc-5af5-af9b-f8b9393ced08	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
931549cb-f64a-560d-b8e9-e87593313ad7	Delhi Motors booking conversion +16%	1	4f8de3c0-e819-5d48-b294-896ca1bf805d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
931549cb-f64a-560d-b8e9-e87593313ad7	Rural low-risk finance approval +12%	2	654eeb39-846f-5eba-9423-0d902e8642d0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
931549cb-f64a-560d-b8e9-e87593313ad7	Dealer follow-up leakage -13%	3	41e8b812-e8f9-5f78-9faf-eb46c28e72c2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
531b8f1f-2b55-58ee-b629-f6a0bdd49630	3,548 leads scored across 24 dealers	0	86538e98-f069-5c4f-a5e2-4d565f7b7ce3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
531b8f1f-2b55-58ee-b629-f6a0bdd49630	733 hot leads actioned in SLA	1	bc3b6646-4c21-530d-895d-3f8516244934	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
9f2cb348-733b-5cc7-92d6-8b30b4279c74	13 converted leads in funnel	0	7e1ad269-69a7-582d-83d0-3ae3df1dc572	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
9f2cb348-733b-5cc7-92d6-8b30b4279c74	Test-drive SLA adherence 77%	1	4889e418-fb0c-5689-b161-cbce7098ff56	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
e0f360ac-90d4-5e5e-9e10-dbcfbbaadb85	Alt-data scoring on thin files	0	2d7009f6-99cd-58ac-a0bc-906aa940531a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
e0f360ac-90d4-5e5e-9e10-dbcfbbaadb85	KYC TAT reduced to 4 days	1	0b2d8b1d-1dd3-59b6-9b80-6bd7f7fe710b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
03722b7e-3e6c-5564-9fd9-5f5203ccf85a	Rebalanced West Zone allocation	0	9b07de06-ac42-5f2a-95c5-2a1c85bf447d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
03722b7e-3e6c-5564-9fd9-5f5203ccf85a	Waiting list normalized post-festive	1	14ff0498-43e4-5447-9750-9c77a021dc20	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
295d9f30-69fa-5590-b7bb-c8fb9d37975d	Delivery experience improvements	0	a436b642-428b-5068-9763-acd94a9318c4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
295d9f30-69fa-5590-b7bb-c8fb9d37975d	AR technician guide rollout	1	28600ba2-1975-5709-a4bf-c9be79b945c1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: kpis; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.kpis (code, label, value, trend, trend_up, confidence, sort_order, id, created_at, updated_at) FROM stdin;
rev	Predicted Revenue Uplift	₹87.0 Cr	+6.3%	t	86	0	931549cb-f64a-560d-b8e9-e87593313ad7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
leak	Leakage Prevented	₹30.4 Cr	-11.2%	t	92	1	531b8f1f-2b55-58ee-b629-f6a0bdd49630	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
book	Booking Conversion	65.7%	+2.2 pts	t	81	2	9f2cb348-733b-5cc7-92d6-8b30b4279c74	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
fin	Finance Approval Rate	77%	+6%	t	81	3	e0f360ac-90d4-5e5e-9e10-dbcfbbaadb85	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
del	Delivery Delay	8.0 d	-1.3 d	t	83	4	03722b7e-3e6c-5564-9fd9-5f5203ccf85a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
csat	Customer Satisfaction	NPS 72	+2	t	91	5	295d9f30-69fa-5590-b7bb-c8fb9d37975d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: logistics_routes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.logistics_routes (name, sla_risk, delay_prob, cost, recommended_action, rerouted, rerouted_at, auto_healed, sort_order, id, created_at, updated_at) FROM stdin;
Coimbatore → Surat	100	90	₹8.9 L	Split load via air for priority SKUs	f	\N	f	2	df4e56fa-0311-5575-9fdb-fbe8690a2d01	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Ahmedabad → Vijayawada	50	35	₹2.3 L	Consolidate with return leg	f	\N	f	3	94b4c9ff-3a4a-57b4-8e1b-443e1ac5f6d8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Dehradun → Delhi	7	16	₹3.8 L	Pre-dispatch 4h earlier via alternate corridor	f	\N	f	4	67f8c803-e456-50a6-876c-bf2e6eb4878a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Ranchi → Bengaluru	41	29	₹8.8 L	Shift 20% volume to rail	f	\N	f	5	027e1db8-f0a4-5cda-83d1-162452a2a6f4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Bengaluru → Ludhiana	72	58	₹2.5 L	Add buffer stock at destination hub	f	\N	f	6	9c4f95c1-597b-5083-9a2b-acb147197cf6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Nagpur → Hyderabad	30	16	₹5.9 L	Shift 20% volume to rail	f	\N	f	7	795b32d9-09f7-5118-8a45-ee41864bbb2f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Raipur → Nashik	37	39	₹4.2 L	Shift 20% volume to rail	f	\N	f	8	83b2da27-6a1f-5e9b-91b8-9d3dfde92d12	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Pune → Surat	69	57	₹3.7 L	Keep route; monitor weather window	f	\N	f	9	1f1ef307-1405-58c7-8a52-848d1252089c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Patna → Pune	48	49	₹2.3 L	Pre-dispatch 4h earlier via alternate corridor	f	\N	f	10	c0f865af-57cf-5c1e-b540-8b5e5e4b9c18	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Hyderabad → Kolkata	15	19	₹8.4 L	Split load via air for priority SKUs	f	\N	f	11	84b5d534-211f-5d88-85d8-d42faf880201	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Surat → Lucknow	90	78	₹4.9 L	Split load via air for priority SKUs	t	2026-08-06 05:24:47.027924+00	f	0	16fffee4-2c57-532d-a0af-8cffdc70f41a	2026-08-06 04:41:53.792545+00	2026-08-06 05:24:47.02232+00
Nagpur → Delhi	33	23	₹7.7 L	Add buffer stock at destination hub	t	2026-08-06 05:24:55.254276+00	f	1	7cd5d64f-6f52-5568-8b14-4d657e96ba7c	2026-08-06 04:41:53.792545+00	2026-08-06 05:24:55.253018+00
\.


--
-- Data for Name: mobility_kpis; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.mobility_kpis (label, value, trend, sort_order, id, created_at, updated_at) FROM stdin;
Lead → booking conversion	12.7%	+4.0 pts	0	155c6899-2f6f-5314-b70b-048ef13736f2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Test drive completion	65.6%	+1.3%	1	d1fa28d4-c454-5016-afaf-4fbc764c80f6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Cancellation risk	8.1%	-1.7 pts	2	4574f8b6-c775-5a17-b709-d622ee33b346	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Delivery delay	7.2 d	-3.1 d	3	9141d45e-b5ef-524c-af1d-504b042c79c4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Warranty risk	Low	stable	4	73424877-a62e-51e6-8cf6-b349715d0a50	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Finance approval rate	83.7%	+2.6%	5	f98ec4bb-6f10-5dae-9e0e-002cdddd843b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Dealer follow-up leakage	15.7%	-2.9%	6	3a513407-1449-5236-aaa4-8bcbbba26cd1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Service CSAT	77.2%	+3.2%	7	f01a0c45-ad6e-5d82-a77c-6a13ed6e4fa1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: poc_items; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.poc_items (name, bucket, priority, complexity, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
Anomaly detection 2 — Dealer Network	Revenue Intelligence	Low	High	0	2d3bcc97-5241-582c-8cae-f4bb298845b8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Dynamic pricing — Loan Book	Credit & Risk Intelligence	High	Medium	1	36a73fb3-e0d0-59f3-a775-816da8f92ed0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Anomaly detection — Ai Platform	Platform & MLOps	High	Low	2	fa8a242e-6730-5048-8a06-0184a6f48641	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Demand forecasting — Immersive Workflows	Immersive Experience	High	High	3	f5e7456c-ac34-582d-ab3e-2d3665442836	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Alt-data underwriting — Dealer Network	Revenue Intelligence	Low	Medium	4	ad6cddd1-af5d-5879-b172-7485c45f8da5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Churn prediction — Decision Ledger	Trust & Compliance	High	High	5	75df5e51-1ba4-5508-b7a7-e3e89797ec27	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
Dynamic pricing — Dealer Network	Auto	\N	\N	6	fb028290-4702-4965-a202-f67dd91100c2	2026-08-06 07:00:06.490679+00	2026-08-06 07:00:06.490679+00	\N
Demand forecasting — Recovery Pipeline	Collections	\N	\N	7	4982fb56-3e78-4759-b1d1-a03e07dbbf91	2026-08-06 07:00:31.213251+00	2026-08-06 07:00:31.213251+00	\N
\.


--
-- Data for Name: recommendations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.recommendations (code, title, impact, confidence, risk, status, decided_at, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
REC-SYN-003	Pre-approve rural thin-file customers	+8.7% finance conversion	86	medium	pending	\N	2	aad77e59-cc59-5874-bd1d-692531510c1d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-004	Rebalance allocation towards West Zone	-3.6 days delivery delay	82	medium	pending	\N	3	9be1dc06-dd94-5952-8f0e-b636eac08888	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-005	Reprice low-traceability carbon credits	+11.6% closure probability	88	low	pending	\N	4	2f171941-26cd-568b-862e-406f03dddf2b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-006	Bundle insurance renewal with service plan	+₹37.7 L cross-sell	78	low	pending	\N	5	9979146e-1eca-52fc-bb26-e54cc0f42df7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-007	Shift SLA-risk corridors to air split	-11.1% SLA breach risk	84	medium	pending	\N	6	c7a839d8-946a-55b7-bfa4-85238e8fb54b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-008	Deploy WhatsApp NBA across 128 dealers	+12.9% follow-up conversion	71	medium	pending	\N	7	3f7d039d-f161-543c-8fcd-6bb0a550ebc9	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
REC-SYN-001	Launch exchange bonus for XUV700 in North Zone	+₹24.9 Cr bookings	83	high	approved	2026-08-06 05:23:03.645308+00	0	21c4cc60-67ac-53a7-8695-91d34bb77f59	2026-08-06 04:41:53.792545+00	2026-08-06 05:23:03.580502+00	\N
REC-SYN-002	Escalate 127 stale leads at Pune dealers	Recover ₹27.0 L / month	68	low	approved	2026-08-06 05:23:25.384642+00	1	6832eb45-c9b2-54f8-94da-c6b8e567b640	2026-08-06 04:41:53.792545+00	2026-08-06 05:23:25.368524+00	\N
\.


--
-- Data for Name: regions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.regions (code) FROM stdin;
West
North
South
East
\.


--
-- Data for Name: simulation_runs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.simulation_runs (domain, inputs, outputs, confidence, id, created_at, updated_at) FROM stdin;
auto_sales	{"bonus": 40000, "model": "Bolero", "region": "South", "campaign": 3.3, "discount": 5.6, "intensity": "High"}	{"rev": 26712, "conf": 85, "cancel": 7, "margin": 0, "uplift": 1484, "recommendedAction": "Increase exchange bonus in high-propensity segments"}	85	cb9862c8-aa80-55c4-b6e8-e0c3e518cb26	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dealer_allocation	{"wait": 36, "units": 189, "demand": 42, "capacity": 43}	{"rev": 3024, "csat": 76, "delay": 14, "suggestedSplit": "West 41% · North 33% · South 26%"}	75	dca2d13a-0203-589d-8088-211c7170fe49	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections	{"risk": "High", "field": 59, "offer": "Waiver", "channel": "Voice"}	{"net": 1, "cost": 89, "prob": 56, "friction": 35}	75	f80b5758-cc9a-52b3-a5ca-88579e7e302d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
logistics_delay	{"sla": "Low", "route": "Mumbai → Pune", "vehicle": 38, "weather": 49, "warehouse": 79}	{"cost": 35096, "delay": 41, "breach": 31, "reroute": "Via Nagpur bypass"}	\N	847cf798-f815-5b7b-8e44-c29184ecbf15	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
credit_pricing	{"type": "Carbon", "trace": 51, "verif": 91, "demand": 13, "supply": 43}	{"match": 54, "closure": 47, "priceBandLow": 271, "priceBandHigh": 441, "complianceRisk": "Low"}	\N	5742e59d-6a98-52d7-be18-0624c2b73c53	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
auto_sales	{"bonus": 45000, "model": "XUV 3XO", "region": "West", "campaign": 4.5, "discount": 1.9, "intensity": "Low"}	{"rev": 16146, "conf": 67, "cancel": 9, "margin": 23, "uplift": 897, "recommendedAction": "Hold current pricing; monitor weekly"}	67	21ea4c40-8487-5f7d-a915-e4252d9c2741	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dealer_allocation	{"wait": 45, "units": 354, "demand": 72, "capacity": 98}	{"rev": 7434, "csat": 72, "delay": 18, "suggestedSplit": "West 31% · North 32% · South 37%"}	75	27a23722-f992-579a-99dc-e55cbce69425	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections	{"risk": "Medium", "field": 74, "offer": "Restructure", "channel": "Digital"}	{"net": 27, "cost": 86, "prob": 76, "friction": 20}	79	c409f143-9ca7-500c-bb92-f847c94e113e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
logistics_delay	{"sla": "High", "route": "Nagpur → Indore", "vehicle": 86, "weather": 3, "warehouse": 32}	{"cost": 14830, "delay": 10, "breach": 22, "reroute": "Keep primary corridor"}	\N	d634453f-ce64-582f-afb5-adcc650530ba	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
credit_pricing	{"type": "Carbon", "trace": 25, "verif": 45, "demand": 87, "supply": 92}	{"match": 79, "closure": 48, "priceBandLow": 395, "priceBandHigh": 644, "complianceRisk": "High"}	\N	84567169-b90c-552f-9f8b-e43de94ad98d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
auto_sales	{"bonus": 55000, "model": "Bolero", "region": "North", "campaign": 1.2, "discount": 5.9, "intensity": "High"}	{"rev": 23418, "conf": 80, "cancel": 8, "margin": 0, "uplift": 1301, "recommendedAction": "Increase exchange bonus in high-propensity segments"}	80	b171591d-74b6-5400-b2aa-d88552d25776	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dealer_allocation	{"wait": 6, "units": 279, "demand": 75, "capacity": 99}	{"rev": 5301, "csat": 88, "delay": 2, "suggestedSplit": "West 36% · North 27% · South 37%"}	74	d4c8c73f-6809-505c-9140-9f8c80b7e668	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections	{"risk": "Low", "field": 96, "offer": "Settlement", "channel": "Digital"}	{"net": 27, "cost": 108, "prob": 96, "friction": 45}	67	0617caf0-dd41-5317-b321-2e008bad82dc	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
logistics_delay	{"sla": "Low", "route": "Kolkata → Ranchi", "vehicle": 85, "weather": 39, "warehouse": 64}	{"cost": 28608, "delay": 24, "breach": 14, "reroute": "Keep primary corridor"}	\N	a0280119-b52e-5419-8997-1ffd75f3db7a	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
credit_pricing	{"type": "EPR", "trace": 15, "verif": 23, "demand": 23, "supply": 51}	{"match": 57, "closure": 31, "priceBandLow": 247, "priceBandHigh": 518, "complianceRisk": "High"}	\N	8c11ccf2-3edc-5305-b292-a14d2da1aa25	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
auto_sales	{"bonus": 0, "model": "Bolero", "region": "South", "campaign": 1.0, "discount": 1.6, "intensity": "High"}	{"rev": 8064, "conf": 68, "cancel": 11, "margin": 26, "uplift": 448, "recommendedAction": "Hold current pricing; monitor weekly"}	68	1f7c0ce1-bf87-5a0a-b39c-9092c429131d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dealer_allocation	{"wait": 9, "units": 71, "demand": 84, "capacity": 100}	{"rev": 1207, "csat": 86, "delay": 4, "suggestedSplit": "West 31% · North 20% · South 49%"}	64	8b0d3ea7-a1c2-5681-8492-b96a651fb48e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections	{"risk": "Low", "field": 78, "offer": "Waiver", "channel": "Digital"}	{"net": 40, "cost": 90, "prob": 96, "friction": 35}	77	6168cb52-f803-5de1-996d-a86c3311c219	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
logistics_delay	{"sla": "Medium", "route": "Mumbai → Pune", "vehicle": 34, "weather": 21, "warehouse": 46}	{"cost": 41160, "delay": 30, "breach": 30, "reroute": "Via Nagpur bypass"}	\N	95f08fdb-edf6-5710-b50d-8423d9624875	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
credit_pricing	{"type": "Circular Materials", "trace": 68, "verif": 13, "demand": 59, "supply": 26}	{"match": 69, "closure": 59, "priceBandLow": 666, "priceBandHigh": 950, "complianceRisk": "High"}	\N	087dc168-064a-5942-920d-fc922d38dbea	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
auto_sales	{"bonus": 20000, "model": "XUV700", "region": "North", "campaign": 4.1, "discount": 4.3, "intensity": "Medium"}	{"rev": 23148, "conf": 70, "cancel": 8, "margin": 1, "uplift": 1286, "recommendedAction": "Increase exchange bonus in high-propensity segments"}	70	9e332be0-8732-54a4-8e1c-f2a786af8dd2	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dealer_allocation	{"wait": 15, "units": 306, "demand": 62, "capacity": 80}	{"rev": 4590, "csat": 84, "delay": 6, "suggestedSplit": "West 42% · North 21% · South 37%"}	69	70ae7fce-96d2-55b5-bc39-e850aa72f026	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections	{"risk": "High", "field": 42, "offer": "Settlement", "channel": "Digital"}	{"net": 14, "cost": 54, "prob": 56, "friction": 45}	69	ac4cb22a-a445-5276-9816-24233d2d4962	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
logistics_delay	{"sla": "Low", "route": "Mumbai → Pune", "vehicle": 77, "weather": 8, "warehouse": 18}	{"cost": 12298, "delay": 11, "breach": 1, "reroute": "Keep primary corridor"}	\N	1fc6d7a0-c9e3-5a83-89fc-577a3ce0bbcb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
credit_pricing	{"type": "EPR", "trace": 94, "verif": 66, "demand": 86, "supply": 85}	{"match": 78, "closure": 56, "priceBandLow": 500, "priceBandHigh": 848, "complianceRisk": "Medium"}	\N	0778893a-dd63-5e18-8a0c-9fba9e4b7add	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: solution_buckets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.solution_buckets (name, tag, sort_order, id, created_at, updated_at) FROM stdin;
Revenue Intelligence	Auto	0	1f5aed2a-da86-537b-84e7-978cb172373d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Credit & Risk Intelligence	Finance	1	6158e086-6bc3-5d6a-ba75-77824448de38	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Recovery Optimization	Collections	2	71ed13f1-3a4a-5257-b95d-2296b0bdef4f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Supply Chain Control Tower	Logistics	3	3893bffe-54be-51c2-ae97-efce181722f3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Circular Value Recovery	Circularity	4	c7be675f-bfee-561a-a900-6486d189ecaa	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Trust & Compliance	Trust	5	ccb4d8ef-3651-5c55-9fbb-48e203f36d23	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Conversational Analytics	Copilot	6	540f1ea2-a011-52ad-838a-84515817b6f7	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Immersive Experience	XR	7	ac93d06b-52ec-5ee1-bcbd-4fa0a861e0db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Platform & MLOps	Platform	8	284b3ae5-07a2-5435-a6a9-d6771f081366	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: solutions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.solutions (bucket_id, name, problem, solution, differentiator, impact, sort_order, id, created_at, updated_at) FROM stdin;
1f5aed2a-da86-537b-84e7-978cb172373d	Alt-data underwriting — Dealer Network	Underwrite thin-file customers with alternate data across the dealer network.	Explainable risk decomposition powering alt-data underwriting for the dealer network.	Mahindra group data fabric + causal explanations tuned to the dealer network.	+21.0% approvals	0	eef33343-1dda-56af-b432-4811db30ac9e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
1f5aed2a-da86-537b-84e7-978cb172373d	Dynamic pricing — Dealer Network	Reprice credits & offers with demand signals across the dealer network.	Buyer-match intelligence powering dynamic pricing for the dealer network.	Mahindra group data fabric + causal explanations tuned to the dealer network.	+12.0% closure	1	b7bb7e1c-4453-5654-a42a-427fae64f09f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
1f5aed2a-da86-537b-84e7-978cb172373d	Anomaly detection — Dealer Network	Detect operational anomalies in real time across the dealer network.	Auto-heal workflows powering anomaly detection for the dealer network.	Mahindra group data fabric + causal explanations tuned to the dealer network.	-18.0% breaches	2	25d4e3bb-3816-5aa2-992d-978af419f6ab	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
1f5aed2a-da86-537b-84e7-978cb172373d	Anomaly detection 2 — Dealer Network	Detect operational anomalies in real time across the dealer network.	Auto-heal workflows powering anomaly detection for the dealer network.	Mahindra group data fabric + causal explanations tuned to the dealer network.	-12.0% breaches	3	2a44e97e-8a0d-5cdb-81a1-894c61b6ea08	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
6158e086-6bc3-5d6a-ba75-77824448de38	Demand forecasting — Loan Book	Forecast demand at dealer-model granularity across the loan book.	Causal driver explanations powering demand forecasting for the loan book.	Mahindra group data fabric + causal explanations tuned to the loan book.	+30.0% forecast accuracy	4	8d6c7dc2-400a-5728-a80f-3bf8fa9f0518	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
6158e086-6bc3-5d6a-ba75-77824448de38	Anomaly detection — Loan Book	Detect operational anomalies in real time across the loan book.	Auto-heal workflows powering anomaly detection for the loan book.	Mahindra group data fabric + causal explanations tuned to the loan book.	-27.0% breaches	5	25b671ad-1d1b-5b91-856a-7713f0f338db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
6158e086-6bc3-5d6a-ba75-77824448de38	Dynamic pricing — Loan Book	Reprice credits & offers with demand signals across the loan book.	Buyer-match intelligence powering dynamic pricing for the loan book.	Mahindra group data fabric + causal explanations tuned to the loan book.	+15.0% closure	6	a0ee9f77-0c1b-5a9f-a1e9-7b61496e711b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
71ed13f1-3a4a-5257-b95d-2296b0bdef4f	Demand forecasting — Recovery Pipeline	Forecast demand at dealer-model granularity across the recovery pipeline.	Causal driver explanations powering demand forecasting for the recovery pipeline.	Mahindra group data fabric + causal explanations tuned to the recovery pipeline.	+22.0% forecast accuracy	7	bf753748-f343-527c-ba29-85a639426c95	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
71ed13f1-3a4a-5257-b95d-2296b0bdef4f	Lead scoring — Recovery Pipeline	Score every lead on conversion propensity across the recovery pipeline.	NBA next-action engine powering lead scoring for the recovery pipeline.	Mahindra group data fabric + causal explanations tuned to the recovery pipeline.	+29.0% conversion	8	a3ded3d2-bb6a-5853-a779-5a3a7c6219e4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
71ed13f1-3a4a-5257-b95d-2296b0bdef4f	Churn prediction — Recovery Pipeline	Predict cancellation risk before booking loss across the recovery pipeline.	Intervention playbooks powering churn prediction for the recovery pipeline.	Mahindra group data fabric + causal explanations tuned to the recovery pipeline.	-10.0% cancellations	9	1d0c3d14-9ca4-5258-a1c9-7dcdaa684aa4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3893bffe-54be-51c2-ae97-efce181722f3	Lead scoring — Freight Corridors	Score every lead on conversion propensity across the freight corridors.	NBA next-action engine powering lead scoring for the freight corridors.	Mahindra group data fabric + causal explanations tuned to the freight corridors.	+16.0% conversion	10	f3bbdb42-1e79-5640-b860-855912ecebbe	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3893bffe-54be-51c2-ae97-efce181722f3	Demand forecasting — Freight Corridors	Forecast demand at dealer-model granularity across the freight corridors.	Causal driver explanations powering demand forecasting for the freight corridors.	Mahindra group data fabric + causal explanations tuned to the freight corridors.	+27.0% forecast accuracy	11	2dccd9a6-92c3-58b0-8ad8-2615d55f5dd3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3893bffe-54be-51c2-ae97-efce181722f3	Churn prediction — Freight Corridors	Predict cancellation risk before booking loss across the freight corridors.	Intervention playbooks powering churn prediction for the freight corridors.	Mahindra group data fabric + causal explanations tuned to the freight corridors.	-15.0% cancellations	12	0dbf394a-0de8-5908-9bd8-ff9984a62da1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3893bffe-54be-51c2-ae97-efce181722f3	Dynamic pricing — Freight Corridors	Reprice credits & offers with demand signals across the freight corridors.	Buyer-match intelligence powering dynamic pricing for the freight corridors.	Mahindra group data fabric + causal explanations tuned to the freight corridors.	+15.0% closure	13	ddf4ab62-df64-5b4c-a488-7e8ec2ab1c7f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
3893bffe-54be-51c2-ae97-efce181722f3	Anomaly detection — Freight Corridors	Detect operational anomalies in real time across the freight corridors.	Auto-heal workflows powering anomaly detection for the freight corridors.	Mahindra group data fabric + causal explanations tuned to the freight corridors.	-23.0% breaches	14	ecea32a5-db07-5515-8b3a-24c1d36e8fb4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
c7be675f-bfee-561a-a900-6486d189ecaa	Lead scoring — Credit Marketplace	Score every lead on conversion propensity across the credit marketplace.	NBA next-action engine powering lead scoring for the credit marketplace.	Mahindra group data fabric + causal explanations tuned to the credit marketplace.	+15.0% conversion	15	c8fd02bf-c370-5486-9210-bb9aa9b16128	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
c7be675f-bfee-561a-a900-6486d189ecaa	Document intelligence — Credit Marketplace	Extract & verify documents automatically across the credit marketplace.	Audit-grade lineage powering document intelligence for the credit marketplace.	Mahindra group data fabric + causal explanations tuned to the credit marketplace.	-23.0% TAT	16	b42ff179-4903-552f-9dc5-4e096503131c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
c7be675f-bfee-561a-a900-6486d189ecaa	Alt-data underwriting — Credit Marketplace	Underwrite thin-file customers with alternate data across the credit marketplace.	Explainable risk decomposition powering alt-data underwriting for the credit marketplace.	Mahindra group data fabric + causal explanations tuned to the credit marketplace.	+14.0% approvals	17	bfb8b644-9a1b-5151-9765-0812d983b2bf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
c7be675f-bfee-561a-a900-6486d189ecaa	Dynamic pricing — Credit Marketplace	Reprice credits & offers with demand signals across the credit marketplace.	Buyer-match intelligence powering dynamic pricing for the credit marketplace.	Mahindra group data fabric + causal explanations tuned to the credit marketplace.	+26.0% closure	18	23769e91-6b38-5da8-bee3-2846fd86c248	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ccb4d8ef-3651-5c55-9fbb-48e203f36d23	Lead scoring — Decision Ledger	Score every lead on conversion propensity across the decision ledger.	NBA next-action engine powering lead scoring for the decision ledger.	Mahindra group data fabric + causal explanations tuned to the decision ledger.	+28.0% conversion	19	1e23b5ee-4e0b-56d8-ab71-3104eee2e7cf	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ccb4d8ef-3651-5c55-9fbb-48e203f36d23	Dynamic pricing — Decision Ledger	Reprice credits & offers with demand signals across the decision ledger.	Buyer-match intelligence powering dynamic pricing for the decision ledger.	Mahindra group data fabric + causal explanations tuned to the decision ledger.	+8.0% closure	20	e684da37-b35c-5e87-a7d8-434223825d07	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ccb4d8ef-3651-5c55-9fbb-48e203f36d23	Churn prediction — Decision Ledger	Predict cancellation risk before booking loss across the decision ledger.	Intervention playbooks powering churn prediction for the decision ledger.	Mahindra group data fabric + causal explanations tuned to the decision ledger.	-13.0% cancellations	21	109322cf-425b-5ec3-8b50-826e30a2f924	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ccb4d8ef-3651-5c55-9fbb-48e203f36d23	Demand forecasting — Decision Ledger	Forecast demand at dealer-model granularity across the decision ledger.	Causal driver explanations powering demand forecasting for the decision ledger.	Mahindra group data fabric + causal explanations tuned to the decision ledger.	+26.0% forecast accuracy	22	3dcdac44-71f9-5283-b3a8-2151474b4e24	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
540f1ea2-a011-52ad-838a-84515817b6f7	Churn prediction — Analytics Copilot	Predict cancellation risk before booking loss across the analytics copilot.	Intervention playbooks powering churn prediction for the analytics copilot.	Mahindra group data fabric + causal explanations tuned to the analytics copilot.	-21.0% cancellations	23	c9d8c150-57eb-585e-9933-fe54b6d43f53	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
540f1ea2-a011-52ad-838a-84515817b6f7	Document intelligence — Analytics Copilot	Extract & verify documents automatically across the analytics copilot.	Audit-grade lineage powering document intelligence for the analytics copilot.	Mahindra group data fabric + causal explanations tuned to the analytics copilot.	-16.0% TAT	24	d67b66fe-e6e2-5ed0-a7aa-e675de69f2d1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
540f1ea2-a011-52ad-838a-84515817b6f7	Document intelligence 2 — Analytics Copilot	Extract & verify documents automatically across the analytics copilot.	Audit-grade lineage powering document intelligence for the analytics copilot.	Mahindra group data fabric + causal explanations tuned to the analytics copilot.	-26.0% TAT	25	849ca510-6293-57ec-9464-902e0278ed09	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
540f1ea2-a011-52ad-838a-84515817b6f7	Anomaly detection — Analytics Copilot	Detect operational anomalies in real time across the analytics copilot.	Auto-heal workflows powering anomaly detection for the analytics copilot.	Mahindra group data fabric + causal explanations tuned to the analytics copilot.	-31.0% breaches	26	886b6ed7-620f-5a3b-bb48-7aeb5b57aa9f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
540f1ea2-a011-52ad-838a-84515817b6f7	Churn prediction 2 — Analytics Copilot	Predict cancellation risk before booking loss across the analytics copilot.	Intervention playbooks powering churn prediction for the analytics copilot.	Mahindra group data fabric + causal explanations tuned to the analytics copilot.	-17.0% cancellations	27	76de7926-d0f5-5143-b2d7-1f30cf2a0909	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ac93d06b-52ec-5ee1-bcbd-4fa0a861e0db	Anomaly detection — Immersive Workflows	Detect operational anomalies in real time across the immersive workflows.	Auto-heal workflows powering anomaly detection for the immersive workflows.	Mahindra group data fabric + causal explanations tuned to the immersive workflows.	-18.0% breaches	28	5da6214a-5b6d-5c81-b41f-fb8b108b5662	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ac93d06b-52ec-5ee1-bcbd-4fa0a861e0db	Dynamic pricing — Immersive Workflows	Reprice credits & offers with demand signals across the immersive workflows.	Buyer-match intelligence powering dynamic pricing for the immersive workflows.	Mahindra group data fabric + causal explanations tuned to the immersive workflows.	+20.0% closure	29	69e2fb79-e032-5ab2-b910-e2185efd02bb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
ac93d06b-52ec-5ee1-bcbd-4fa0a861e0db	Demand forecasting — Immersive Workflows	Forecast demand at dealer-model granularity across the immersive workflows.	Causal driver explanations powering demand forecasting for the immersive workflows.	Mahindra group data fabric + causal explanations tuned to the immersive workflows.	+17.0% forecast accuracy	30	9a713e79-9841-50e1-b2cf-38da7297d8f6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
284b3ae5-07a2-5435-a6a9-d6771f081366	Demand forecasting — Ai Platform	Forecast demand at dealer-model granularity across the AI platform.	Causal driver explanations powering demand forecasting for the AI platform.	Mahindra group data fabric + causal explanations tuned to the AI platform.	+30.0% forecast accuracy	31	b337324d-3533-506e-b762-47d0fdc82fac	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
284b3ae5-07a2-5435-a6a9-d6771f081366	Alt-data underwriting — Ai Platform	Underwrite thin-file customers with alternate data across the AI platform.	Explainable risk decomposition powering alt-data underwriting for the AI platform.	Mahindra group data fabric + causal explanations tuned to the AI platform.	+12.0% approvals	32	55e38398-efbe-521b-a91b-e5273b90a01c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
284b3ae5-07a2-5435-a6a9-d6771f081366	Dynamic pricing — Ai Platform	Reprice credits & offers with demand signals across the AI platform.	Buyer-match intelligence powering dynamic pricing for the AI platform.	Mahindra group data fabric + causal explanations tuned to the AI platform.	+27.0% closure	33	4a6397f1-8102-5b15-b5a1-84b3a1f8b9a8	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
284b3ae5-07a2-5435-a6a9-d6771f081366	Anomaly detection — Ai Platform	Detect operational anomalies in real time across the AI platform.	Auto-heal workflows powering anomaly detection for the AI platform.	Mahindra group data fabric + causal explanations tuned to the AI platform.	-13.0% breaches	34	7a2d65f1-6641-5faf-8788-01bf2afe3197	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
284b3ae5-07a2-5435-a6a9-d6771f081366	Alt-data underwriting 2 — Ai Platform	Underwrite thin-file customers with alternate data across the AI platform.	Explainable risk decomposition powering alt-data underwriting for the AI platform.	Mahindra group data fabric + causal explanations tuned to the AI platform.	+17.0% approvals	35	edca4041-817f-5baf-adf3-b6570c5cf298	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: suggested_prompts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.suggested_prompts (text, sort_order, id, created_at, updated_at) FROM stdin;
Why did bookings drop in Guwahati last week?	0	9e99448d-804c-58c7-9b4e-748cacc88478	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Which dealers have the highest revenue leakage?	1	43f19d42-157a-5d16-9eb6-a9d262299359	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Which finance customers are most likely to roll forward?	2	4a0db65f-c878-5b61-81ad-3b1306791751	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Which logistics routes are likely to breach SLA?	3	2064fb50-7e1d-55b8-86db-514c6e458ee5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Which circularity credits should be repriced?	4	d19f2b12-2d03-525b-acb0-e248042342ba	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
What is the highest ROI AI use case for Mahindra to start with?	5	05819b62-9fd2-54db-97d3-d53f5e856ce5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Show me the top causal drivers of warranty claims.	6	0f749369-8ae6-5261-8cee-c519acc0e24b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Generate a board summary of AI impact.	7	af4e2471-f6e6-5bce-8377-fa60996ea499	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
How should we rebalance Bolero allocation across South Zone?	8	b7ad9092-2d87-55f9-b78a-b17ea4692062	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
Which Jaipur dealers need follow-up escalation today?	9	405d0be6-048d-572a-b9f4-60bc3bceb492	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: trust_decisions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.trust_decisions (code, use_case, recommendation, data_sources, confidence, approval, risk, audit, rejection_reason, lineage, sort_order, id, created_at, updated_at, deleted_at) FROM stdin;
FIN-5001	Carbon credit repricing	Reprice batch 9%	Buyer demand, traceability	96	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 4 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 96%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	1	00e58083-c98f-5e31-9c37-a151e05007dc	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
CIRC-5002	Dealer lead escalation	Escalate 12 stale leads	Lead scores, SLA telemetry	85	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 8 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 85%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	2	f3f61bcb-73f4-5c02-b489-994e95116e7c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
AUTO-5003	Vehicle allocation to North Zone	Reallocate 3 units	Bookings, dealer capacity, waiting list	67	pending	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 6 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 67%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	3	a8d299d2-9cbf-575a-9933-4cd93b136e3f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
FIN-5004	Dealer lead escalation	Escalate 5 stale leads	Lead scores, SLA telemetry	90	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 7 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 90%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	4	bf54bcc5-653f-5de2-8d20-e11f40271d73	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
DEAL-5005	Rural SME loan approval	Approve ₹3.9L	Alternate credit, geo, agri	73	human_review	low	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 7 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 73%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	5	469abd1a-13fd-58bc-a242-a93cff177df3	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
COLL-5006	Collections restructuring offer	Offer 12-month plan	DPD, income stability	57	human_review	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 57%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	6	ec883ea6-4be5-52b2-b938-54b5fe470339	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
DEAL-5007	Vehicle allocation to South Zone	Reallocate 12 units	Bookings, dealer capacity, waiting list	71	human_review	low	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 7 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 71%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	7	e246e552-5270-588b-bb14-f970640e9e8b	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
DEAL-5008	Vehicle allocation to South Zone	Reallocate 4 units	Bookings, dealer capacity, waiting list	86	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 5 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 86%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	8	0231dec5-46a9-5853-969b-04cd94c99dec	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
DEAL-5009	Vehicle allocation to West Zone	Reallocate 3 units	Bookings, dealer capacity, waiting list	86	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 86%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	9	9a1cd5b1-4341-506f-a096-d5245a3bbecd	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
FIN-5010	SLA reroute on corridor	Split load via air	Route telemetry, weather	61	human_review	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 61%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	10	584eaac7-76c2-5462-b361-2f401798e834	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
AUTO-5011	Exchange bonus targeting	Target 4 XUV700 prospects	Propensity, exchange values	59	pending	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 6 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 59%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	11	30b03898-c044-5353-bca9-733fecc9eb15	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
CIRC-5012	Collections restructuring offer	Offer 7-month plan	DPD, income stability	75	human_review	low	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 75%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	12	69889a50-f9c3-56e7-9d0d-f700f6a6af26	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
FIN-5013	Carbon credit repricing	Reprice batch 10%	Buyer demand, traceability	96	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 4 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 96%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	13	312285bc-2951-5c0d-8896-71006dc83743	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
COLL-5014	Collections restructuring offer	Offer 10-month plan	DPD, income stability	61	pending	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 7 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 61%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	14	a4566b4a-20bf-5139-ac17-b1046d89c0cb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
LOG-5015	SLA reroute on corridor	Split load via air	Route telemetry, weather	60	pending	high	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 60%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	15	dd9334bf-17d7-56ea-932e-a5a451ace278	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
CIRC-5016	Exchange bonus targeting	Target 8 XUV700 prospects	Propensity, exchange values	67	pending	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 9 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 67%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	16	4b98945e-7c20-5a8e-8e4c-ac885c40c052	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
FIN-5017	Carbon credit repricing	Reprice batch 9%	Buyer demand, traceability	80	approved	medium	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 7 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 80%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	17	156f535d-d847-51d2-8c4e-baef504c1371	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
FIN-5018	Rural SME loan approval	Approve ₹4.2L	Alternate credit, geo, agri	68	pending	high	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 4 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 68%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	18	6f1dc00e-e04e-5bd7-acb4-d4574dc86c63	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
AUTO-5019	Collections restructuring offer	Offer 7-month plan	DPD, income stability	86	approved	low	complete	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 8 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 86%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	19	45c87012-2c3c-5105-b8ca-5e42ca91e6a1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00	\N
CIRC-5000	Vehicle allocation to West Zone	Reallocate 5 units	Bookings, dealer capacity, waiting list	56	pending	high	pending	\N	[{"step": 1, "title": "Data ingested", "detail": "Signals collected from 3 sources"}, {"step": 2, "title": "Model scored", "detail": "Ensemble confidence 56%"}, {"step": 3, "title": "Policy checked", "detail": "All guardrails passed"}, {"step": 4, "title": "Recommendation issued", "detail": "Routed to decision queue"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	0	1437c3a7-a09a-5056-9f45-9050ce01846f	2026-08-06 04:41:53.792545+00	2026-08-06 05:08:17.699777+00	\N
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (email, full_name, is_active, id, created_at, updated_at) FROM stdin;
demo@mahindra.ai	Command Center Admin	t	22a18c7a-a7e0-5549-af1b-b9e62b60e6f6	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
epatla@bhandari.com	Manan Chana	t	9fc2ea4f-6fbc-52e1-81ed-d420ed73cc09	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
dvora@badal-sachar.com	Hitesh Gaba	t	97ed9dd8-7d0f-5d28-b707-d0c5bc1e368c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
vdutta@dash-kalita.com	Rayaan Deep	t	ea05e8f8-338e-5470-bb0d-1f9a656c578d	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
qarinoak@dutt.com	Pahal Agrawal	f	5b36b5fb-0b97-5e71-9fdf-d3ba6f7739e5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: vehicle_models; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.vehicle_models (name) FROM stdin;
XUV700
Scorpio-N
Thar
Bolero
XUV 3XO
\.


--
-- Data for Name: warehouse_signals; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.warehouse_signals (panel, label, value, tone, sort_order, id, created_at, updated_at) FROM stdin;
warehouse	Dock congestion	43%	warning	0	8fe95d9e-2091-58ea-86f7-7536166d889f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
warehouse	Picking delay	6 min	warning	1	6b6675b6-8d2c-5f9a-99c3-015d6bf19fd0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
warehouse	Inventory imbalance	-21%	danger	2	28b82025-ec82-5eff-be74-940bc69887a5	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
warehouse	Vehicle availability	86%	success	3	1c73c1ca-22ce-5e77-a0bd-04371ce961fb	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
warehouse	Load utilization	91%	success	4	41b7aa8f-2d0d-5279-bd70-af653a863ece	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
warehouse	Stock accuracy	99%	success	5	e1269ea3-b8c0-5dab-9db7-1b3846b921ae	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Accounts at risk	12,868	default	6	f5e6f9d8-4507-52c7-b22a-ad0f745f6360	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Predicted roll-forward	3,469	default	7	f651e169-52a7-589f-bc75-c5198530690c	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Recovery opportunity	₹22 Cr	default	8	1528f78c-7989-5dfc-a957-8d2e915248db	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Field visit optimization	-30% cost	default	9	6a3f6dc8-61d5-558e-a2ff-8e1b289edc72	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Compliance alerts	4 flagged	default	10	40bbaa08-ae65-5f18-af0a-64cfb36645c0	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
collections_metrics	Promise-to-pay keep rate	77%	default	11	8c85e642-ca37-5eec-9a19-19aa6d3d3cbe	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	Job-card delay prediction	6 hrs	warning	12	a337411d-710c-536b-85ee-235472944438	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	Throughput	149 vehicles / day	success	13	f806221b-5cef-580c-96ce-09ddea2bea44	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	Bottleneck	De-pollution bay	danger	14	c0d15e8d-9b15-549c-9050-611cad61757f	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	dMRV completeness	78%	warning	15	84bc32d9-a831-5e40-a47c-ce92e1fe0c82	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	Compliance risk	Low	success	16	0bf8c7c9-a4fb-51c9-a5f8-d118972ec49e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
rvsf	Parts recovery rate	77%	success	17	b7bf195b-9924-5c01-a8a2-ef1f06d68030	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Data for Name: xr_experiences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.xr_experiences (code, title, use_case, feature, impact, sort_order, id, created_at, updated_at) FROM stdin;
showroom	AI Virtual Showroom	Immersive vehicle exploration	Generative sales assistant + config	+18% online-to-visit conversion	0	d5c67142-bcf9-5fb5-afd6-34f5775221c4	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
config	3D Vehicle Configurator	Personalized configurations	Real-time AI recommendations	+12% variant upsell	1	9987728d-3b7a-5844-9fd6-340a03ce0548	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
repair	AR Technician Repair Guide	Step-by-step service	Component-aware AR overlays	-24% repair time	2	f0ded5ed-d8e0-5f82-878b-65921b731aa1	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
training	VR Dealer Sales Training	Immersive skill building	AI feedback on pitch & objections	+22% training ROI	3	2b643bff-4278-5274-846c-5e7156ab8482	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
inspect	AR Pre-Delivery Inspection	Guided quality checks	Defect auto-capture	-31% inspection time	4	8c44c2d5-9ae2-556c-9d3b-9c49328fe11e	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
support	VR Customer Handover	Feature walkthrough	Personalized onboarding	+15% NPS	5	bc2fee8f-b74a-5fa0-aa61-665638b58573	2026-08-06 04:41:53.792545+00	2026-08-06 04:41:53.792545+00
\.


--
-- Name: ai_agents pk_ai_agents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agents
    ADD CONSTRAINT pk_ai_agents PRIMARY KEY (id);


--
-- Name: carbon_credits pk_carbon_credits; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carbon_credits
    ADD CONSTRAINT pk_carbon_credits PRIMARY KEY (id);


--
-- Name: causal_edges pk_causal_edges; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_edges
    ADD CONSTRAINT pk_causal_edges PRIMARY KEY (id);


--
-- Name: causal_nodes pk_causal_nodes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_nodes
    ADD CONSTRAINT pk_causal_nodes PRIMARY KEY (id);


--
-- Name: causal_qa pk_causal_qa; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_qa
    ADD CONSTRAINT pk_causal_qa PRIMARY KEY (id);


--
-- Name: collections_agents pk_collections_agents; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collections_agents
    ADD CONSTRAINT pk_collections_agents PRIMARY KEY (id);


--
-- Name: collections_cases pk_collections_cases; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collections_cases
    ADD CONSTRAINT pk_collections_cases PRIMARY KEY (id);


--
-- Name: compliance_rules pk_compliance_rules; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_rules
    ADD CONSTRAINT pk_compliance_rules PRIMARY KEY (id);


--
-- Name: copilot_messages pk_copilot_messages; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.copilot_messages
    ADD CONSTRAINT pk_copilot_messages PRIMARY KEY (id);


--
-- Name: copilot_sessions pk_copilot_sessions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.copilot_sessions
    ADD CONSTRAINT pk_copilot_sessions PRIMARY KEY (id);


--
-- Name: customer_twins pk_customer_twins; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customer_twins
    ADD CONSTRAINT pk_customer_twins PRIMARY KEY (id);


--
-- Name: dealer_leads pk_dealer_leads; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealer_leads
    ADD CONSTRAINT pk_dealer_leads PRIMARY KEY (id);


--
-- Name: dealers pk_dealers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealers
    ADD CONSTRAINT pk_dealers PRIMARY KEY (id);


--
-- Name: finance_products pk_finance_products; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.finance_products
    ADD CONSTRAINT pk_finance_products PRIMARY KEY (id);


--
-- Name: kpi_drivers pk_kpi_drivers; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_drivers
    ADD CONSTRAINT pk_kpi_drivers PRIMARY KEY (id);


--
-- Name: kpis pk_kpis; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpis
    ADD CONSTRAINT pk_kpis PRIMARY KEY (id);


--
-- Name: logistics_routes pk_logistics_routes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_routes
    ADD CONSTRAINT pk_logistics_routes PRIMARY KEY (id);


--
-- Name: mobility_kpis pk_mobility_kpis; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobility_kpis
    ADD CONSTRAINT pk_mobility_kpis PRIMARY KEY (id);


--
-- Name: poc_items pk_poc_items; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.poc_items
    ADD CONSTRAINT pk_poc_items PRIMARY KEY (id);


--
-- Name: recommendations pk_recommendations; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendations
    ADD CONSTRAINT pk_recommendations PRIMARY KEY (id);


--
-- Name: regions pk_regions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.regions
    ADD CONSTRAINT pk_regions PRIMARY KEY (code);


--
-- Name: simulation_runs pk_simulation_runs; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.simulation_runs
    ADD CONSTRAINT pk_simulation_runs PRIMARY KEY (id);


--
-- Name: solution_buckets pk_solution_buckets; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.solution_buckets
    ADD CONSTRAINT pk_solution_buckets PRIMARY KEY (id);


--
-- Name: solutions pk_solutions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.solutions
    ADD CONSTRAINT pk_solutions PRIMARY KEY (id);


--
-- Name: suggested_prompts pk_suggested_prompts; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_prompts
    ADD CONSTRAINT pk_suggested_prompts PRIMARY KEY (id);


--
-- Name: trust_decisions pk_trust_decisions; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trust_decisions
    ADD CONSTRAINT pk_trust_decisions PRIMARY KEY (id);


--
-- Name: users pk_users; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT pk_users PRIMARY KEY (id);


--
-- Name: vehicle_models pk_vehicle_models; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.vehicle_models
    ADD CONSTRAINT pk_vehicle_models PRIMARY KEY (name);


--
-- Name: warehouse_signals pk_warehouse_signals; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.warehouse_signals
    ADD CONSTRAINT pk_warehouse_signals PRIMARY KEY (id);


--
-- Name: xr_experiences pk_xr_experiences; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.xr_experiences
    ADD CONSTRAINT pk_xr_experiences PRIMARY KEY (id);


--
-- Name: ai_agents uq_ai_agents_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_agents
    ADD CONSTRAINT uq_ai_agents_name UNIQUE (name);


--
-- Name: carbon_credits uq_carbon_credits_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.carbon_credits
    ADD CONSTRAINT uq_carbon_credits_code UNIQUE (code);


--
-- Name: causal_edges uq_causal_edges_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_edges
    ADD CONSTRAINT uq_causal_edges_pair UNIQUE (source_node_id, target_node_id);


--
-- Name: causal_nodes uq_causal_nodes_label; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_nodes
    ADD CONSTRAINT uq_causal_nodes_label UNIQUE (label);


--
-- Name: collections_agents uq_collections_agents_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collections_agents
    ADD CONSTRAINT uq_collections_agents_name UNIQUE (name);


--
-- Name: compliance_rules uq_compliance_rules_label; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.compliance_rules
    ADD CONSTRAINT uq_compliance_rules_label UNIQUE (label);


--
-- Name: dealers uq_dealers_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealers
    ADD CONSTRAINT uq_dealers_code UNIQUE (code);


--
-- Name: finance_products uq_finance_products_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.finance_products
    ADD CONSTRAINT uq_finance_products_name UNIQUE (name);


--
-- Name: kpis uq_kpis_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpis
    ADD CONSTRAINT uq_kpis_code UNIQUE (code);


--
-- Name: logistics_routes uq_logistics_routes_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.logistics_routes
    ADD CONSTRAINT uq_logistics_routes_name UNIQUE (name);


--
-- Name: mobility_kpis uq_mobility_kpis_label; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobility_kpis
    ADD CONSTRAINT uq_mobility_kpis_label UNIQUE (label);


--
-- Name: poc_items uq_poc_items_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.poc_items
    ADD CONSTRAINT uq_poc_items_name UNIQUE (name);


--
-- Name: recommendations uq_recommendations_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendations
    ADD CONSTRAINT uq_recommendations_code UNIQUE (code);


--
-- Name: solution_buckets uq_solution_buckets_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.solution_buckets
    ADD CONSTRAINT uq_solution_buckets_name UNIQUE (name);


--
-- Name: solutions uq_solutions_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.solutions
    ADD CONSTRAINT uq_solutions_name UNIQUE (name);


--
-- Name: suggested_prompts uq_suggested_prompts_text; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.suggested_prompts
    ADD CONSTRAINT uq_suggested_prompts_text UNIQUE (text);


--
-- Name: trust_decisions uq_trust_decisions_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trust_decisions
    ADD CONSTRAINT uq_trust_decisions_code UNIQUE (code);


--
-- Name: users uq_users_email; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT uq_users_email UNIQUE (email);


--
-- Name: xr_experiences uq_xr_experiences_code; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.xr_experiences
    ADD CONSTRAINT uq_xr_experiences_code UNIQUE (code);


--
-- Name: ix_carbon_credits_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_carbon_credits_deleted_at ON public.carbon_credits USING btree (deleted_at);


--
-- Name: ix_causal_edges_source_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_causal_edges_source_node_id ON public.causal_edges USING btree (source_node_id);


--
-- Name: ix_causal_edges_target_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_causal_edges_target_node_id ON public.causal_edges USING btree (target_node_id);


--
-- Name: ix_causal_qa_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_causal_qa_category ON public.causal_qa USING btree (category);


--
-- Name: ix_causal_qa_category_question; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_causal_qa_category_question ON public.causal_qa USING btree (category, question);


--
-- Name: ix_collections_cases_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collections_cases_deleted_at ON public.collections_cases USING btree (deleted_at);


--
-- Name: ix_copilot_messages_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_copilot_messages_session_id ON public.copilot_messages USING btree (session_id);


--
-- Name: ix_dealer_leads_dealer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dealer_leads_dealer_id ON public.dealer_leads USING btree (dealer_id);


--
-- Name: ix_dealer_leads_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dealer_leads_deleted_at ON public.dealer_leads USING btree (deleted_at);


--
-- Name: ix_kpi_drivers_kpi_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_kpi_drivers_kpi_id ON public.kpi_drivers USING btree (kpi_id);


--
-- Name: ix_poc_items_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_poc_items_deleted_at ON public.poc_items USING btree (deleted_at);


--
-- Name: ix_recommendations_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recommendations_deleted_at ON public.recommendations USING btree (deleted_at);


--
-- Name: ix_recommendations_status_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_recommendations_status_pending ON public.recommendations USING btree (status) WHERE (status = 'pending'::public.recommendation_status);


--
-- Name: ix_simulation_runs_domain; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_simulation_runs_domain ON public.simulation_runs USING btree (domain);


--
-- Name: ix_solution_buckets_tag; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_solution_buckets_tag ON public.solution_buckets USING btree (tag);


--
-- Name: ix_solutions_bucket_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_solutions_bucket_id ON public.solutions USING btree (bucket_id);


--
-- Name: ix_trust_decisions_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trust_decisions_deleted_at ON public.trust_decisions USING btree (deleted_at);


--
-- Name: ix_warehouse_signals_panel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_warehouse_signals_panel ON public.warehouse_signals USING btree (panel);


--
-- Name: causal_edges fk_causal_edges_source_node_id_causal_nodes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_edges
    ADD CONSTRAINT fk_causal_edges_source_node_id_causal_nodes FOREIGN KEY (source_node_id) REFERENCES public.causal_nodes(id) ON DELETE CASCADE;


--
-- Name: causal_edges fk_causal_edges_target_node_id_causal_nodes; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.causal_edges
    ADD CONSTRAINT fk_causal_edges_target_node_id_causal_nodes FOREIGN KEY (target_node_id) REFERENCES public.causal_nodes(id) ON DELETE CASCADE;


--
-- Name: copilot_messages fk_copilot_messages_session_id_copilot_sessions; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.copilot_messages
    ADD CONSTRAINT fk_copilot_messages_session_id_copilot_sessions FOREIGN KEY (session_id) REFERENCES public.copilot_sessions(id) ON DELETE CASCADE;


--
-- Name: dealer_leads fk_dealer_leads_dealer_id_dealers; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dealer_leads
    ADD CONSTRAINT fk_dealer_leads_dealer_id_dealers FOREIGN KEY (dealer_id) REFERENCES public.dealers(id) ON DELETE CASCADE;


--
-- Name: kpi_drivers fk_kpi_drivers_kpi_id_kpis; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.kpi_drivers
    ADD CONSTRAINT fk_kpi_drivers_kpi_id_kpis FOREIGN KEY (kpi_id) REFERENCES public.kpis(id) ON DELETE CASCADE;


--
-- Name: solutions fk_solutions_bucket_id_solution_buckets; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.solutions
    ADD CONSTRAINT fk_solutions_bucket_id_solution_buckets FOREIGN KEY (bucket_id) REFERENCES public.solution_buckets(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

\unrestrict g06BhAXTTGBs1UXMFleoOAXkxB21nPTd7d7cDtTX3qcgYfWt6NCSgM7AFbLT7hI

