--
-- PostgreSQL database dump
--

\restrict poeMsshXiqTMgZDb5jIlLjOMA3UcH3Xrdb2IF61kdlIbDD99bqt3jBmvjoQcld8

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
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    role character varying(128) NOT NULL,
    status public.agent_status DEFAULT 'active'::public.agent_status NOT NULL,
    last_activity character varying(256) NOT NULL,
    use_areas character varying(32)[] NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: carbon_credits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.carbon_credits (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    type character varying(16) NOT NULL,
    price character varying(32) NOT NULL,
    buyer_match integer NOT NULL,
    closure_prob integer NOT NULL,
    traceability integer NOT NULL,
    repriced_at timestamp with time zone,
    buyer_matched_at timestamp with time zone,
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_carbon_credits_ck_carbon_credits_buyer_match_range CHECK (((buyer_match >= 0) AND (buyer_match <= 100))),
    CONSTRAINT ck_carbon_credits_ck_carbon_credits_closure_prob_range CHECK (((closure_prob >= 0) AND (closure_prob <= 100))),
    CONSTRAINT ck_carbon_credits_ck_carbon_credits_traceability_range CHECK (((traceability >= 0) AND (traceability <= 100)))
);


--
-- Name: causal_edges; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_edges (
    id uuid NOT NULL,
    source_node_id uuid NOT NULL,
    target_node_id uuid NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: causal_nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_nodes (
    id uuid NOT NULL,
    label character varying(128) NOT NULL,
    x double precision NOT NULL,
    y double precision NOT NULL,
    metric character varying(128) NOT NULL,
    trend character varying(32) NOT NULL,
    drivers jsonb NOT NULL,
    action character varying(256) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: causal_qa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.causal_qa (
    id uuid NOT NULL,
    category public.qa_category DEFAULT 'mobility'::public.qa_category NOT NULL,
    question text NOT NULL,
    answer text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: collections_agents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collections_agents (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    status public.agent_status DEFAULT 'active'::public.agent_status NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: collections_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collections_cases (
    id uuid NOT NULL,
    customer character varying(128) NOT NULL,
    dpd integer NOT NULL,
    outstanding character varying(32) NOT NULL,
    roll_forward_risk integer NOT NULL,
    channel character varying(64) NOT NULL,
    action character varying(128) NOT NULL,
    prob integer NOT NULL,
    compliance_flag public.collections_compliance_flag DEFAULT 'ok'::public.collections_compliance_flag NOT NULL,
    status public.collections_case_status DEFAULT 'pending'::public.collections_case_status NOT NULL,
    modified_action character varying(128),
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_collections_cases_ck_collections_cases_prob_range CHECK (((prob >= 0) AND (prob <= 100))),
    CONSTRAINT ck_collections_cases_ck_collections_cases_roll_forward__e725 CHECK (((roll_forward_risk >= 0) AND (roll_forward_risk <= 100)))
);


--
-- Name: compliance_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compliance_rules (
    id uuid NOT NULL,
    label character varying(128) NOT NULL,
    status character varying(32) DEFAULT 'OK'::character varying NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: copilot_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.copilot_messages (
    id uuid NOT NULL,
    session_id uuid NOT NULL,
    role public.copilot_role NOT NULL,
    content text NOT NULL,
    result jsonb,
    confidence integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: copilot_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.copilot_sessions (
    id uuid NOT NULL,
    title character varying(256),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: customer_twins; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customer_twins (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    location character varying(128) NOT NULL,
    income_stability character varying(32) NOT NULL,
    repayment character varying(32) NOT NULL,
    products jsonb NOT NULL,
    nba jsonb NOT NULL,
    risk_decomposition jsonb NOT NULL,
    cross_sell jsonb NOT NULL,
    approval_status public.twin_approval_status DEFAULT 'draft'::public.twin_approval_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: dealer_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dealer_leads (
    id uuid NOT NULL,
    dealer_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    vehicle character varying(64) NOT NULL,
    score integer NOT NULL,
    prob integer NOT NULL,
    action character varying(256) NOT NULL,
    revenue character varying(32) NOT NULL,
    status public.dealer_lead_status DEFAULT 'warm'::public.dealer_lead_status NOT NULL,
    test_drive_slot character varying(64),
    message_sent_at timestamp with time zone,
    converted_at timestamp with time zone,
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_dealer_leads_ck_dealer_leads_prob_range CHECK (((prob >= 0) AND (prob <= 100))),
    CONSTRAINT ck_dealer_leads_ck_dealer_leads_score_range CHECK (((score >= 0) AND (score <= 100)))
);


--
-- Name: dealers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dealers (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    name character varying(128) NOT NULL,
    leads integer NOT NULL,
    hot_leads integer NOT NULL,
    test_drives_pending integer NOT NULL,
    booking_prob integer NOT NULL,
    revenue_at_risk character varying(32) NOT NULL,
    leakage_pct integer NOT NULL,
    bay_util_pct integer NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_dealers_ck_dealers_bay_util_pct_range CHECK (((bay_util_pct >= 0) AND (bay_util_pct <= 100))),
    CONSTRAINT ck_dealers_ck_dealers_booking_prob_range CHECK (((booking_prob >= 0) AND (booking_prob <= 100))),
    CONSTRAINT ck_dealers_ck_dealers_leakage_pct_range CHECK (((leakage_pct >= 0) AND (leakage_pct <= 100)))
);


--
-- Name: finance_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.finance_products (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    customers character varying(32) NOT NULL,
    risk character varying(32) NOT NULL,
    cross_sell character varying(32) NOT NULL,
    opportunity character varying(64) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kpi_drivers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpi_drivers (
    id uuid NOT NULL,
    kpi_id uuid NOT NULL,
    driver_text text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: kpis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kpis (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    trend character varying(32) NOT NULL,
    trend_up boolean DEFAULT true NOT NULL,
    confidence integer NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_kpis_ck_kpis_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
);


--
-- Name: logistics_routes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.logistics_routes (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    sla_risk integer NOT NULL,
    delay_prob integer NOT NULL,
    cost character varying(32) NOT NULL,
    recommended_action character varying(128) NOT NULL,
    rerouted boolean DEFAULT false NOT NULL,
    rerouted_at timestamp with time zone,
    auto_healed boolean DEFAULT false NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_logistics_routes_ck_logistics_routes_delay_prob_range CHECK (((delay_prob >= 0) AND (delay_prob <= 100))),
    CONSTRAINT ck_logistics_routes_ck_logistics_routes_sla_risk_range CHECK (((sla_risk >= 0) AND (sla_risk <= 100)))
);


--
-- Name: mobility_kpis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mobility_kpis (
    id uuid NOT NULL,
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    trend character varying(32) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: poc_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.poc_items (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    bucket character varying(128) NOT NULL,
    priority character varying(16),
    complexity character varying(16),
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: recommendations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recommendations (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    title text NOT NULL,
    impact character varying(128) NOT NULL,
    confidence integer NOT NULL,
    risk public.recommendation_risk DEFAULT 'low'::public.recommendation_risk NOT NULL,
    status public.recommendation_status DEFAULT 'pending'::public.recommendation_status NOT NULL,
    decided_at timestamp with time zone,
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_recommendations_ck_recommendations_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
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
    id uuid NOT NULL,
    domain public.simulation_domain NOT NULL,
    inputs jsonb NOT NULL,
    outputs jsonb NOT NULL,
    confidence integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_simulation_runs_ck_simulation_runs_confidence_range CHECK (((confidence IS NULL) OR ((confidence >= 0) AND (confidence <= 100))))
);


--
-- Name: solution_buckets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.solution_buckets (
    id uuid NOT NULL,
    name character varying(128) NOT NULL,
    tag character varying(64) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: solutions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.solutions (
    id uuid NOT NULL,
    bucket_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    problem text NOT NULL,
    solution text NOT NULL,
    differentiator text NOT NULL,
    impact character varying(128) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: suggested_prompts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.suggested_prompts (
    id uuid NOT NULL,
    text text NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: trust_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trust_decisions (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    use_case character varying(256) NOT NULL,
    recommendation character varying(256) NOT NULL,
    data_sources character varying(256) NOT NULL,
    confidence integer NOT NULL,
    approval public.trust_approval DEFAULT 'pending'::public.trust_approval NOT NULL,
    risk public.trust_risk NOT NULL,
    audit public.trust_audit DEFAULT 'pending'::public.trust_audit NOT NULL,
    rejection_reason text,
    lineage jsonb NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_trust_decisions_ck_trust_decisions_confidence_range CHECK (((confidence >= 0) AND (confidence <= 100)))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid NOT NULL,
    email character varying(256) NOT NULL,
    full_name character varying(128) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
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
    id uuid NOT NULL,
    panel public.signal_panel DEFAULT 'warehouse'::public.signal_panel NOT NULL,
    label character varying(128) NOT NULL,
    value character varying(64) NOT NULL,
    tone character varying(16) DEFAULT 'success'::character varying NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: xr_experiences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.xr_experiences (
    id uuid NOT NULL,
    code character varying(32) NOT NULL,
    title character varying(128) NOT NULL,
    use_case character varying(128) NOT NULL,
    feature character varying(128) NOT NULL,
    impact character varying(128) NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Data for Name: ai_agents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.ai_agents (id, name, role, status, last_activity, use_areas, sort_order, created_at, updated_at) FROM stdin;
644f1756-dc6a-5492-9a59-2fdfe8f43451	Data Agent	Ingest & normalize signals	active	Refreshed dealer feed 2m ago	{Auto,Finance}	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7e92af1d-fde2-5232-88f6-e68f8aa48c01	Prediction Agent	Forecast outcomes	active	Forecast bookings Pune	{Auto,Logistics}	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
be686630-37e2-5bbd-a90d-af31ffac077d	Causal Graph Agent	Explain drivers	active	Explained cancellation drivers	{Auto}	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
93310247-779b-5c55-aa37-74b6516db187	Simulation Agent	What-if scenarios	reviewing	Tested exchange bonus	{Auto,Finance}	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9cc4459c-cb54-5a18-a545-e6f4be7cad51	Code Analytics Agent	NL→SQL/Python	active	Generated warranty query	{All}	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c2be7a93-2dfc-5ed0-956b-2195b06da0ff	Compliance Agent	Guardrails & policy	active	Blocked risky offer	{Finance}	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
37cca17b-3601-5acf-87b4-91a8d1d1a4ed	Action Agent	Execute approved actions	recommended	Sent WhatsApp to 214 leads	{Auto}	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c7bb6561-60a9-566c-b263-cb1108e535a8	Human Review Agent	Route to human	active	3 items pending	{All}	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
09f7b9a1-94b2-5107-b01f-9846265275ed	Learning Agent	Feedback learning	active	Updated propensity model	{All}	8	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
43f1ec5e-bec9-5ab6-b505-1e4a9a64ee0c	Memory Agent	Long-term memory	active	Stored 1,204 decisions	{All}	9	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.alembic_version (version_num) FROM stdin;
0001
\.


--
-- Data for Name: carbon_credits; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.carbon_credits (id, code, type, price, buyer_match, closure_prob, traceability, repriced_at, buyer_matched_at, sort_order, deleted_at, created_at, updated_at) FROM stdin;
df734223-2589-58ea-bdb7-ad48409657e6	CR-2214	Carbon	₹1,240	82	71	88	\N	\N	0	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f0618bf5-ce68-5e5a-8a6a-513570fad4f6	CR-2215	EPR	₹840	74	63	79	\N	\N	1	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b3705f8f-273f-5980-be54-644dc6fa025b	CR-2216	SDG	₹2,180	66	48	72	\N	\N	2	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
bd1653be-fd95-586c-b583-ed55dc2c98d3	CR-2217	CD	₹1,560	88	79	91	\N	\N	3	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
83d1b7b5-89db-502d-9633-1e3f8e187293	CR-2218	Carbon	₹1,120	58	41	68	\N	\N	4	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: causal_edges; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_edges (id, source_node_id, target_node_id, sort_order, created_at, updated_at) FROM stdin;
4c656a36-9650-53a4-9bdd-5bc6dfc1ad07	b77926ac-9114-5907-be9e-0659ceeeb4b3	50e247c9-b9d6-5c5b-b3f7-10988532d9c4	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
415ca78c-b1dd-508b-8f88-24fe0b44ddf7	50e247c9-b9d6-5c5b-b3f7-10988532d9c4	9b2c34bb-fbea-54e7-be0d-7364840fc8fe	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b1891b7f-50fc-5aca-87fe-e9dcfbf6f97d	9b2c34bb-fbea-54e7-be0d-7364840fc8fe	8c328e7a-2290-57f6-aa67-9337f15eed63	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2b8629a6-f57d-515a-9d28-ecfdc051cd9f	8c328e7a-2290-57f6-aa67-9337f15eed63	34b1ec3f-53a2-5dde-98ae-5a9deb53225e	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
77bbeb36-48ac-5dbc-a4ef-d595ea6311ca	346fece7-67a7-5029-92d5-49d7541ff3a3	34b1ec3f-53a2-5dde-98ae-5a9deb53225e	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
345a0e0d-7716-5da0-8610-ead5eeb2b2c0	34b1ec3f-53a2-5dde-98ae-5a9deb53225e	a75ea265-7ceb-55d8-9d2e-0987fc6f4f70	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
401d59ec-9946-5bb2-ba4e-36ec578965ec	a75ea265-7ceb-55d8-9d2e-0987fc6f4f70	1dcc2162-0f30-513f-9f39-06bf8e49085a	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
86f16500-234e-5701-9a96-ca2cd73b0cef	1dcc2162-0f30-513f-9f39-06bf8e49085a	b97c6ae1-c337-50e2-ad15-09a4ae8cd243	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
16c31b78-eb72-5e68-af7a-8d0b4c90057a	30712a3e-68e1-524e-9014-79116f15c1b5	b97c6ae1-c337-50e2-ad15-09a4ae8cd243	8	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
fb495f03-e5f0-56a2-8fda-032608d06d76	b97c6ae1-c337-50e2-ad15-09a4ae8cd243	0c1e2fc1-5106-5f21-8b3f-5a10d2e29c62	9	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
3277eb90-fe49-58b8-9377-2a6c0e1c1360	6b5a5c55-b7b9-5ef4-957c-d6078e07afec	b97c6ae1-c337-50e2-ad15-09a4ae8cd243	10	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7a19dddb-ced7-5de1-9d4d-c0a95288fd2f	30712a3e-68e1-524e-9014-79116f15c1b5	6b5a5c55-b7b9-5ef4-957c-d6078e07afec	11	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: causal_nodes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_nodes (id, label, x, y, metric, trend, drivers, action, sort_order, created_at, updated_at) FROM stdin;
b77926ac-9114-5907-be9e-0659ceeeb4b3	Campaign Spend	50	60	₹4.2 Cr	+8%	["Digital-heavy allocation", "Regional festive push"]	Reallocate 12% to programmatic	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
50e247c9-b9d6-5c5b-b3f7-10988532d9c4	Lead Quality	180	60	Score 72	+4	["Better source mix", "Improved landing pages"]	Increase retargeting	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9b2c34bb-fbea-54e7-be0d-7364840fc8fe	Dealer Follow-up	320	60	SLA 74%	+6%	["NBA adoption", "WhatsApp templates"]	Escalate stale leads > 2h	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
8c328e7a-2290-57f6-aa67-9337f15eed63	Test Drive	460	60	72% completion	+4%	["AI scheduler", "SMS reminders"]	Add Sunday slots	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
34b1ec3f-53a2-5dde-98ae-5a9deb53225e	Booking	600	60	17.4%	+2.1	["Exchange bonus", "Finance TAT"]	Bundle offers	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
346fece7-67a7-5029-92d5-49d7541ff3a3	Finance Approval	50	180	78%	+3%	["Alt-data model", "Faster KYC"]	Pre-approve rural	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
a75ea265-7ceb-55d8-9d2e-0987fc6f4f70	Vehicle Allocation	180	180	89% utilization	+5%	["Demand model", "Dealer capacity"]	Rebalance West	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
1dcc2162-0f30-513f-9f39-06bf8e49085a	Delivery Delay	320	180	9.4 d	-3.1d	["Reduced waiting", "Better allocation"]	Monitor Q1	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b97c6ae1-c337-50e2-ad15-09a4ae8cd243	Customer Satisfaction	460	180	NPS 62	+5	["Delivery experience", "Service quality"]	Expand digital handover	8	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
30712a3e-68e1-524e-9014-79116f15c1b5	Service Experience	600	180	82% CSAT	+3%	["Bay utilization", "AR technician guide"]	Roll out to 40 more dealers	9	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6b5a5c55-b7b9-5ef4-957c-d6078e07afec	Warranty Claims	180	300	Batch B-2214 flagged	spike	["Component supplier variance"]	Quarantine batch	10	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
0c1e2fc1-5106-5f21-8b3f-5a10d2e29c62	Repeat Purchase	460	300	24%	+2%	["Loyalty program", "Cross-sell"]	Bundle insurance renewal	11	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: causal_qa; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.causal_qa (id, category, question, answer, sort_order, created_at, updated_at) FROM stdin;
538c0227-4341-5c89-a9cd-050368e98af9	mobility	Why did bookings drop in Pune?	Bookings dropped due to follow-up leakage at 2 Pune dealers (47%), competitor promo (28%), finance TAT (15%). Recommend: exchange bonus + follow-up SLA.	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
ba3ca0dd-2b11-544f-aa3d-d9bd6d7f5ab4	mobility	What is causing delivery delay in West Zone?	West Zone waiting is elevated by uneven allocation between Pune/Nashik vs Nagpur (63% of delay). Reallocate 120 units.	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
1a509a84-0b6a-5e57-8693-3d343d1fba0e	mobility	Which factor has highest impact on cancellation?	Finance approval TAT (>4 days) explains 41% of cancellations. Pre-approval for low-risk rural cuts it by 22%.	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
44f73249-9465-5146-8c8a-cdec5886b3ee	mobility	How can we improve finance-assisted conversions?	Pair thin-file credit twin with dealer NBA. Expected +6.4% conversion, -2.1% NPA risk.	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
31206452-5807-51d2-a351-1d48594c76a3	dmrv	Estimate carbon credits for this batch.	Estimated 214 tCO2e from batch RVSF-Nagpur-Q3, of which 182 are verification-ready.	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
d0b12732-41b6-54ef-a2d3-2914f51fe22d	dmrv	Which fields are incomplete?	Missing: origin geo-tag, weight tickets for 12 vehicles, technician attestation for 4 units.	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
30b3a1e3-2d6b-5ed0-98eb-ae490caa56db	dmrv	Is this verification-ready?	78% ready — after adding origin geo-tags, verification confidence rises to 92%.	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
58be5119-07f5-555a-916d-5f3720788159	dmrv	Generate audit summary.	Audit summary generated. 5 batches, 214 tCO2e, 91% traceable, 3 pending human reviews.	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: collections_agents; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collections_agents (id, name, status, sort_order, created_at, updated_at) FROM stdin;
cd2a9dd1-d23a-5ed7-afec-e8d2c2cc5510	Risk Prediction Agent	active	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
603ddbff-1466-5404-baf6-3a537f4e2d10	Channel Optimization Agent	active	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
4ce4b848-9902-5afc-b87c-cc1ad76bafae	Offer Recommendation Agent	recommended	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
147e19cb-0d07-5ecd-af9a-f1e0b0cbeaf8	Field Route Agent	active	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
43b894b5-42c9-527d-8f06-aa50b8ba8239	Compliance Guardrail Agent	reviewing	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b2bd21ea-de8d-5ffc-a425-217c394736b4	Human Review Agent	active	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: collections_cases; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collections_cases (id, customer, dpd, outstanding, roll_forward_risk, channel, action, prob, compliance_flag, status, modified_action, sort_order, deleted_at, created_at, updated_at) FROM stdin;
5c361661-bf3f-533d-8d64-daab09638eaa	Ganesh Kulkarni	42	₹1.24L	74	Voice + WhatsApp	Restructure offer	68	ok	pending	\N	0	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7769cd00-26c8-56b2-8ea0-e876bc5f45df	Farah Ansari	28	₹86K	58	Digital-first	Pay-link nudge	71	ok	pending	\N	1	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
5c1bedde-25ad-5f4e-b7b7-c772bf3728aa	Mohan Rathi	61	₹2.14L	82	Field visit	Field officer + settlement	54	review	pending	\N	2	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9cea8e58-6fab-5688-95f3-fa00b7f87945	Kavita Iyer	15	₹42K	34	Auto-debit retry	Retry + reminder	84	ok	pending	\N	3	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
840e96e8-b15a-5898-b662-09102a9c923c	Vikram Singh	88	₹3.62L	91	Legal	Legal notice review	38	escalate	pending	\N	4	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: compliance_rules; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.compliance_rules (id, label, status, sort_order, created_at, updated_at) FROM stdin;
9af7985d-3649-5058-a40e-d729af0051bc	Consent check	OK	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6531409d-d1f3-51e9-b9d3-323d0779cc69	Bias / fairness check	OK	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6b31b016-4f80-5c74-8ba9-c445aa88beb0	Regulatory rule check	OK	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
446bf962-ec09-58e5-b623-0d740fdf95e5	Business policy check	1 pending	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6ec710c6-789f-550c-a4c0-d5026dcad7d7	Audit trail complete	OK	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: copilot_messages; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.copilot_messages (id, session_id, role, content, result, confidence, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: copilot_sessions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.copilot_sessions (id, title, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: customer_twins; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.customer_twins (id, name, location, income_stability, repayment, products, nba, risk_decomposition, cross_sell, approval_status, created_at, updated_at) FROM stdin;
6e6cd8d1-ceae-51d6-a821-42a470f2ecca	Suresh Jadhav	Sangli, Maharashtra	Medium-High	Good	["Tractor Loan", "Motor Insurance", "Fixed Deposit"]	{"risk": "Low", "headline": "Offer ₹4.5L pre-approved SME working capital loan", "confidence": 87, "expected_margin": "₹42K"}	{"Geography": "A", "Agri-cycle": "B+", "Alt-data signal": "A-", "Repayment history": "A"}	{"SIP": "41%", "SME loan": "87%", "Life insurance": "62%"}	draft	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: dealer_leads; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dealer_leads (id, dealer_id, name, vehicle, score, prob, action, revenue, status, test_drive_slot, message_sent_at, converted_at, sort_order, deleted_at, created_at, updated_at) FROM stdin;
e862178c-3ce1-58b6-99cd-32a406442335	1ebacafb-4da9-58b2-813a-0071aebfdf6d	Rakesh Patil	XUV700	92	74	Call within 2 hours + exchange bonus	₹19.8L	hot	\N	\N	\N	0	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
1f0f4ccb-2935-563c-972f-c0908735bfb2	1ebacafb-4da9-58b2-813a-0071aebfdf6d	Asha Verma	Thar	86	68	Offer test drive slot	₹16.4L	warm	\N	\N	\N	1	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
bbfd0787-5d84-5db7-9f71-dd04b660b272	1ebacafb-4da9-58b2-813a-0071aebfdf6d	Imran Shaikh	Scorpio-N	79	61	Send finance pre-approval	₹17.2L	warm	\N	\N	\N	2	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b143d3bc-a306-5a3e-8e5f-caf3c0c63b3d	1ebacafb-4da9-58b2-813a-0071aebfdf6d	Priya Nair	XUV 3XO	72	54	WhatsApp video brochure	₹11.6L	warm	\N	\N	\N	3	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
093634e7-0132-575d-8d12-050e87d9a2e1	1ebacafb-4da9-58b2-813a-0071aebfdf6d	Sandeep Rao	Bolero	68	49	Schedule finance advisor callback	₹9.8L	cool	\N	\N	\N	4	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: dealers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.dealers (id, code, name, leads, hot_leads, test_drives_pending, booking_prob, revenue_at_risk, leakage_pct, bay_util_pct, sort_order, created_at, updated_at) FROM stdin;
1ebacafb-4da9-58b2-813a-0071aebfdf6d	d1	Pune Auto World	142	28	14	71	₹1.8 Cr	12	82	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
87575f15-d589-5725-98e8-651a817fca8e	d2	Nashik Mobility Hub	98	21	9	66	₹1.1 Cr	17	74	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
030eb983-0866-55b6-abd1-fb1b9450fdc6	d3	Jaipur SUV Center	121	33	18	69	₹1.4 Cr	9	79	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
adef959e-2237-509b-b562-efd3b7562ad4	d4	Chennai Auto Prime	88	19	11	63	₹0.9 Cr	14	68	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c2d9686e-5090-51b9-bd52-3133470e0d33	d5	Lucknow Motors	76	15	8	58	₹0.7 Cr	21	61	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: finance_products; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.finance_products (id, name, customers, risk, cross_sell, opportunity, sort_order, created_at, updated_at) FROM stdin;
9a4b0738-212f-5c7e-a821-3b792173be34	Vehicle Loans	1.42M	Low	High	Repeat buyers	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
02fdbb0d-045a-5acd-a117-aba7ad28bb68	SME Loans	84K	Medium	High	Working capital	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e8506287-6458-516f-8d2e-3ed59e21f0a5	Digital Finance	612K	Low	Medium	Instant top-up	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
49dd3845-e165-5008-b294-c2b80a73fc2a	Fixed Deposits	241K	Very Low	Medium	Family FD	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
da65b2b3-f86f-5203-bd9d-9d04ac2693d6	Leasing	38K	Low	Low	Fleet upgrade	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
032772f4-5afd-56b5-8e79-2c655795dc53	Rural Housing Finance	182K	Medium	Medium	Land + build	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
dc7d7a40-7c3d-5307-a51e-e23bd7b10e82	Insurance Broking	920K	Low	Very High	Motor renewal	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2d8ee99d-94fa-5198-8552-80dcf2ef5eeb	Mutual Funds	156K	Low	High	SIP upgrade	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: kpi_drivers; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.kpi_drivers (id, kpi_id, driver_text, sort_order, created_at, updated_at) FROM stdin;
91ced09f-d236-5deb-8605-8d9274834076	dd2fae30-969f-5ca4-a27a-fa04dc943030	West Zone booking conversion +12%	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
08f31c08-cba8-523a-9de3-5fa77c53a10a	dd2fae30-969f-5ca4-a27a-fa04dc943030	Rural low-risk finance approval +9%	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
5b1edfb2-ff54-5678-9d57-720c85e4a599	dd2fae30-969f-5ca4-a27a-fa04dc943030	Dealer follow-up leakage -14%	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
4b6240ee-0c43-5681-ac89-d9c3cad7b67e	dd2fae30-969f-5ca4-a27a-fa04dc943030	XUV700 exchange bonus response +18%	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
3353c02e-de20-5252-a06c-bb5d63cab80d	6a092391-19ce-5ced-ae1b-99655b9e8cad	Warranty anomaly caught in batch B-2214	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
04aa5e06-da9e-5288-9719-185aadcbc5a4	6a092391-19ce-5ced-ae1b-99655b9e8cad	Duplicate collections outreach avoided	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2adaf5f0-01ab-5860-8cf3-2979a2c51593	6a092391-19ce-5ced-ae1b-99655b9e8cad	Dealer discount policy breach flagged	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
dbdaa331-f830-56bb-aa28-0727f6264d78	6a092391-19ce-5ced-ae1b-99655b9e8cad	Route reassignment prevented SLA penalty	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
86747f87-22a5-534b-9f3e-cc06f4cd8428	0feccab6-3ffa-5eb2-93fe-2f87b25da6bd	Next-best-action pitch adoption 71%	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
dc448671-8d77-5016-ae19-d2a2d523a1a1	0feccab6-3ffa-5eb2-93fe-2f87b25da6bd	Test-drive slot AI scheduler	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
5acb36d4-a6f0-50f6-9228-61561a36a6b7	0feccab6-3ffa-5eb2-93fe-2f87b25da6bd	Finance pre-approval speed -37%	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9a29ed45-0063-5527-ac58-f17c9b5f0202	0feccab6-3ffa-5eb2-93fe-2f87b25da6bd	Personalized WhatsApp brochures	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
1660f370-ebe1-5153-923b-fdaf83484aea	86710297-c143-55e6-842d-174d47f6a20e	Thin-file rural credit twin	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f097b67f-9d30-5b54-82de-739e9c3eaf79	86710297-c143-55e6-842d-174d47f6a20e	Early roll-forward detection	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
db30d57a-f124-5b9d-9c7f-9ff9431d01fd	86710297-c143-55e6-842d-174d47f6a20e	Channel optimization for medium risk	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
299d115e-88d3-5a63-b957-f56a22e222bc	86710297-c143-55e6-842d-174d47f6a20e	Fraud graph flagged 214 anomalies	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9729a034-46ab-5d80-acfc-07e4165ef32a	8088086d-fafa-5787-b5d3-9e9a70954c32	Predictive delay model on 5 corridors	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2c1c2c8a-ef4e-572a-910c-c397cfa9e1ff	8088086d-fafa-5787-b5d3-9e9a70954c32	Auto-heal reroute workflows	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
024325f6-5c9b-5c81-b98f-71a0a5e7a32c	8088086d-fafa-5787-b5d3-9e9a70954c32	Warehouse dock congestion signal	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6f829111-09f1-52ec-9438-0396b980f232	8088086d-fafa-5787-b5d3-9e9a70954c32	Weather-adjusted ETA	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2354dd12-8def-5203-8078-5a01d78fe680	83a26072-ff9c-5d14-9b5b-f13952c459b7	ELV valuation optimization	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e891d329-bd16-5829-888c-75f42e10f416	83a26072-ff9c-5d14-9b5b-f13952c459b7	Carbon credit repricing	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
4ca4e579-1e2a-5fbd-a39d-e77ff47f0bf0	83a26072-ff9c-5d14-9b5b-f13952c459b7	dMRV completeness +23%	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e422a733-db6f-5bb8-a37e-7309970772b2	83a26072-ff9c-5d14-9b5b-f13952c459b7	Buyer match score improved	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: kpis; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.kpis (id, code, label, value, trend, trend_up, confidence, sort_order, created_at, updated_at) FROM stdin;
dd2fae30-969f-5ca4-a27a-fa04dc943030	rev	Predicted Revenue Uplift	₹412 Cr	+8.4%	t	92	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6a092391-19ce-5ced-ae1b-99655b9e8cad	leak	Leakage Prevented	₹86 Cr	+4.1%	t	88	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
0feccab6-3ffa-5eb2-93fe-2f87b25da6bd	conv	Dealer Conversion Uplift	+7.8%	+2.2 pts	t	90	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
86710297-c143-55e6-842d-174d47f6a20e	risk	Financial Risk Reduction	-11.4%	-1.6 pts	t	87	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
8088086d-fafa-5787-b5d3-9e9a70954c32	sla	SLA Breach Avoidance	23,420	+12%	t	85	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
83a26072-ff9c-5d14-9b5b-f13952c459b7	esg	ESG / Circularity Value	₹38 Cr	+6.2%	t	81	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: logistics_routes; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.logistics_routes (id, name, sla_risk, delay_prob, cost, recommended_action, rerouted, rerouted_at, auto_healed, sort_order, created_at, updated_at) FROM stdin;
4dfe60a5-b2aa-54bc-9c78-0f73553ca5cd	Mumbai → Pune	22	34	₹1.2L	Reroute via Panvel	f	\N	f	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
fded83f3-9bf9-5201-abae-fa7b636f9bac	Chennai → Bengaluru	41	52	₹2.4L	Shift to night lane	f	\N	f	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
cfdf0978-4dd9-5dbf-a0ec-c1b1018af9ee	Delhi → Jaipur	18	24	₹0.8L	Maintain	f	\N	f	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
af640dad-47ac-50b1-ba61-727cf07578c0	Mundra Port → NCR	58	67	₹4.1L	Split load + air uplift	f	\N	f	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
576446f0-1fc8-5324-863e-d497478ad994	Kolkata → Guwahati	47	61	₹3.2L	Weather delay buffer	f	\N	f	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: mobility_kpis; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.mobility_kpis (id, label, value, trend, sort_order, created_at, updated_at) FROM stdin;
4f0e2aa6-b822-54c7-97a5-a5eedf181229	Lead → booking conversion	17.4%	+2.1 pts	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7b2247a5-b4e2-5e5d-b787-a4898d45556c	Test drive completion	72%	+4%	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c0ad7d50-12dc-5446-afaa-c0870c185644	Cancellation risk	6.8%	-1.2 pts	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c32693ca-c712-59b7-8f62-9bb8752bf1a1	Delivery delay	9.4 d	-3.1 d	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
bf7f21ea-2a4e-5d4e-b192-c977d69f1374	Warranty risk	Low	stable	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
5de54776-2659-57db-b4df-2d2a17ca5389	Finance approval rate	78%	+3%	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
149246f3-6ef4-57e8-8031-c533809648f7	Dealer follow-up leakage	12%	-4%	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: poc_items; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.poc_items (id, name, bucket, priority, complexity, sort_order, deleted_at, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: recommendations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.recommendations (id, code, title, impact, confidence, risk, status, decided_at, sort_order, deleted_at, created_at, updated_at) FROM stdin;
4bfd9899-a361-5865-8127-c652a22f5c97	r1	Reallocate 120 XUV units from low-conversion dealers to West Zone	₹18.4 Cr revenue	91	low	pending	\N	0	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
beec1802-d24d-5db6-953b-11fc61a20dfa	r2	Launch targeted exchange-bonus campaign for Pune & Nashik	+9.2% bookings	87	low	pending	\N	1	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
889b02fd-5281-59b0-bf65-2c15ea637842	r3	Prioritize 8,420 medium-risk collections cases for digital outreach	₹6.1 Cr recovery	89	medium	pending	\N	2	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
8828b28a-943b-5880-9768-f5f0ef11b448	r4	Reprice 36 circularity certificates with low closure probability	₹1.8 Cr ESG revenue	78	medium	pending	\N	3	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
ec7efd07-6fa5-56a3-8b68-9e19c9f7293e	r5	Investigate warranty anomaly in vehicle batch B-2214	Prevent ₹2.4 Cr claims	84	high	pending	\N	4	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
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

COPY public.simulation_runs (id, domain, inputs, outputs, confidence, created_at, updated_at) FROM stdin;
4bc34bb3-2275-51d0-be31-02f2358e8fb8	auto_sales	{"bonus": 30000, "model": "XUV700", "region": "West", "intensity": "High", "discount_pct": 8, "campaign_spend": 4}	{"uplift_pct": 41, "revenue_index": 113, "cancellation_pct": 4, "margin_impact_pct": -10}	89	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: solution_buckets; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.solution_buckets (id, name, tag, sort_order, created_at, updated_at) FROM stdin;
5804bb0c-26cf-5b07-82ce-f9959a788d40	Auto, Mobility & Dealer Intelligence	Auto	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9dcf0bd5-25a5-5784-98c3-3b3070a98c7d	Financial Services Intelligence	Finance	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
ca2db371-5fbd-5092-be11-a9d86512ca74	AI Simulation Center	Simulation	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
acb9404c-9919-52b2-ba48-5df81e3ae4f6	Non-Auto Growth Businesses	Logistics	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
13a83364-9062-5e3b-a859-38e89d5b043e	Circular Economy & ESG Intelligence	Circularity	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
8f3ea819-2b46-5742-9597-51fa0666cf2f	Horizontal AI Factory	Agentic AI	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: solutions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.solutions (id, bucket_id, name, problem, solution, differentiator, impact, sort_order, created_at, updated_at) FROM stdin;
9e6219ff-71a2-5ece-9b8b-89adb603e8fb	5804bb0c-26cf-5b07-82ce-f9959a788d40	Auto Mobility Causal Twin	Fragmented view of demand→delivery→service	Causal decision graph linking OEM to CX	Causal + counterfactual reasoning	+7% conversion, -12% cancellation	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f639002c-5a57-5490-bb7c-9ed14bf93d20	5804bb0c-26cf-5b07-82ce-f9959a788d40	Dealer Revenue Optimizer	Leaked leads & inconsistent follow-up	Next-best-action for every lead	Learns dealer-specific behavior	+₹42 Cr dealer revenue	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7fc7bf15-681d-5428-be0d-4a4a0eb69fed	5804bb0c-26cf-5b07-82ce-f9959a788d40	Warranty & Quality Early-Warning Graph	Late warranty spike detection	Graph anomaly detection on components	Batch-level causal linkage	-18% claim cost	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
51939a04-d2ee-5754-a875-5038d85da303	5804bb0c-26cf-5b07-82ce-f9959a788d40	Aftermarket & Pre-Owned Commerce AI	Weak pricing & matching	Dynamic pricing + buyer match	Multi-channel demand signal fusion	+11% margin	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
0e6409d9-e30e-5fdc-8328-62678431f48d	5804bb0c-26cf-5b07-82ce-f9959a788d40	AR/VR/XR Experience Intelligence	Static showroom & training	Immersive AI journeys	Personalized to role & context	+22% training ROI	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
bf6e4f92-1447-5266-8a7f-cf16497b42c2	9dcf0bd5-25a5-5784-98c3-3b3070a98c7d	Thin-File Rural Credit Twin	Limited traditional credit data	Alternate-data credit twin	Behavior + geo + agri signals	+14% approval, -9% NPA	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
4a97132c-977d-5d7b-9020-22dfbaedd2ba	9dcf0bd5-25a5-5784-98c3-3b3070a98c7d	Collections & Recovery AI Swarm	Blunt collections strategy	Multi-agent decisioning	Compliance-guarded agents	+11% recovery	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2b510bfc-5d29-519a-8c74-9768b7bdb5ab	9dcf0bd5-25a5-5784-98c3-3b3070a98c7d	Insurance, MF & Wealth Copilots	Underused customer signal	Cross-product copilot	Unified customer twin	+18% cross-sell	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9ac99388-b296-5d6e-aa86-50c0fecca02b	9dcf0bd5-25a5-5784-98c3-3b3070a98c7d	Fraud, Mis-selling & Business Quality Graph	Reactive fraud detection	Graph-based anomaly network	Explainable to auditor	-24% mis-selling	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f082052c-8966-5e4c-9b77-a6c8c3405003	ca2db371-5fbd-5092-be11-a9d86512ca74	What-if Business Simulations	Decisions made without testing	Business flight simulator	Causal + optimization loop	Faster, safer decisions	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
3c3833d1-173f-5d73-b25a-a36a65f058d1	ca2db371-5fbd-5092-be11-a9d86512ca74	Causal Impact Analysis	Correlation ≠ causation	Counterfactual reasoning	Boardroom-ready explanations	Higher trust	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e5c2e932-4dd9-5e17-9034-a7b150b2b6a7	ca2db371-5fbd-5092-be11-a9d86512ca74	Predictive Optimization	Reactive planning	Constraint-aware optimization	Explainable trade-offs	+8% margin	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
fe7f3979-67ba-5be8-8077-550902446ed5	ca2db371-5fbd-5092-be11-a9d86512ca74	Scenario Planning	Ad-hoc annual planning	Continuous scenario library	Reusable scenario templates	Faster response	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f9186031-3232-5413-a89e-82afafb4174c	acb9404c-9919-52b2-ba48-5df81e3ae4f6	Logistics AI Control Tower	SLA visibility gaps	Predictive + auto-heal ops	Causal delay attribution	-32% SLA breach	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
17b68cdf-7b2a-5ba0-a435-9ef008618bab	acb9404c-9919-52b2-ba48-5df81e3ae4f6	Real Estate & Hospitality Intelligence	Static occupancy planning	Demand + guest experience AI	Cross-property learning	+9% RevPAR	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e181b8c4-ca09-5a68-8bea-f6e0fcd1ce87	acb9404c-9919-52b2-ba48-5df81e3ae4f6	Renewable Energy Asset Intelligence	Underused telemetry	Asset health + generation forecast	Weather-fused causal	-14% downtime	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b207e7e0-d394-5636-83f1-ef3cd3858bc5	13a83364-9062-5e3b-a859-38e89d5b043e	ELV Valuation	Inconsistent scrap pricing	AI valuation model	Doc-completeness aware	+₹6 Cr margin	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2b6c9d36-ba3e-51ef-b5a0-fd30f272cf5b	13a83364-9062-5e3b-a859-38e89d5b043e	RVSF Operations Intelligence	Throughput bottlenecks	Job-card delay prediction	dMRV integrated	+21% throughput	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
5726ec8c-1297-5fbb-b111-75aa850e3b10	13a83364-9062-5e3b-a859-38e89d5b043e	Carbon / SDG Credit Intelligence	Illiquid credits	Dynamic pricing + buyer match	Traceability-driven trust	+₹18 Cr ESG value	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
a361888e-5359-5514-a4d3-92eb178cd11a	13a83364-9062-5e3b-a859-38e89d5b043e	dMRV & Compliance Trust Layer	Manual verification	Continuous digital MRV	Audit-ready lineage	-60% audit time	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
6774d2b2-955d-5ea8-ab49-7f4f5b308839	8f3ea819-2b46-5742-9597-51fa0666cf2f	Multi-Agent Ecosystem	Siloed AI models	Orchestrated agent registry	Memory + guardrails + HITL	Reusable Group-wide	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
9d066f4c-b622-577f-a559-2a16594c93e2	8f3ea819-2b46-5742-9597-51fa0666cf2f	Auto-Code Analytics Copilot	Slow analyst cycles	NL → SQL/Python + charts	Executive-ready outputs	10x analyst throughput	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
ccdfd1f6-ac67-5ce0-b11d-a18f66c5cfa3	8f3ea819-2b46-5742-9597-51fa0666cf2f	HITL Learning	Static models	Human feedback learning	Continuous improvement	Model drift avoided	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
992243ba-2413-59b6-87ab-8609f48ad0e5	8f3ea819-2b46-5742-9597-51fa0666cf2f	Auto-Heal Workflows	Manual incident response	AI-driven remediation	Approval-gated automation	-45% MTTR	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
c3060804-1717-5978-a1d9-3ee5bc4e1fc9	8f3ea819-2b46-5742-9597-51fa0666cf2f	Governance & Compliance	Ad-hoc AI oversight	Trust ledger for every decision	Data lineage + confidence	Audit-ready	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: suggested_prompts; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.suggested_prompts (id, text, sort_order, created_at, updated_at) FROM stdin;
a7a3dcd5-4149-5557-8de0-35c2b2d828c4	Why did bookings drop in Pune last week?	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
102d0ae0-4239-5f5d-aea9-068a9d247f8a	Which dealers have the highest revenue leakage?	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
b4c7a336-1e60-5326-8ee0-9e070611d16c	Which finance customers are most likely to roll forward?	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
022af42a-f572-5736-9c5c-2fe43bf9c4ca	Which logistics routes are likely to breach SLA?	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
dc92d486-9b28-5b51-aab0-3735459c7546	Which circularity credits should be repriced?	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2801ace9-b39c-5d3d-a49d-81852f7642d6	What is the highest ROI AI use case for Mahindra to start with?	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
a06a1182-0fb5-5f6e-ad1d-9ae30935443d	Show me the top causal drivers of warranty claims.	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
64e210e0-befb-5e57-b842-f4d0927da76f	Generate a board summary of AI impact.	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: trust_decisions; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.trust_decisions (id, code, use_case, recommendation, data_sources, confidence, approval, risk, audit, rejection_reason, lineage, sort_order, deleted_at, created_at, updated_at) FROM stdin;
dd93c5c9-9fb2-59a6-89dd-e6535fbdc5bf	AUTO-1042	Vehicle allocation to West Zone	Reallocate 120 units	Bookings, dealer capacity, waiting list	91	approved	low	complete	\N	[{"step": 1, "title": "Data used", "detail": "Bookings, dealer capacity, waiting list"}, {"step": 2, "title": "Recommendation", "detail": "Reallocate 120 units · confidence 91%"}, {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"}, {"step": 4, "title": "Approval", "detail": "Approved"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	0	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
328b2a68-ac0a-5d71-bf9b-2b0d537751a7	FIN-8821	Rural SME loan approval	Approve ₹4.5L	Alternate credit, geo, agri	87	approved	low	complete	\N	[{"step": 1, "title": "Data used", "detail": "Alternate credit, geo, agri"}, {"step": 2, "title": "Recommendation", "detail": "Approve ₹4.5L · confidence 87%"}, {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"}, {"step": 4, "title": "Approval", "detail": "Approved"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	1	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
825d0c97-0029-57c1-91a2-919e72ae2f14	COLL-3329	Restructuring offer	Offer 6-month plan	DPD, income stability	78	human_review	medium	pending	\N	[{"step": 1, "title": "Data used", "detail": "DPD, income stability"}, {"step": 2, "title": "Recommendation", "detail": "Offer 6-month plan · confidence 78%"}, {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"}, {"step": 4, "title": "Approval", "detail": "Human review"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	2	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
dfcda66f-a13a-578b-873f-a727dbbdd322	CIRC-7712	Carbon credit repricing	Reprice batch -12%	Buyer demand, traceability	74	pending	medium	pending	\N	[{"step": 1, "title": "Data used", "detail": "Buyer demand, traceability"}, {"step": 2, "title": "Recommendation", "detail": "Reprice batch -12% · confidence 74%"}, {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"}, {"step": 4, "title": "Approval", "detail": "Pending"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	3	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
0bcdb09a-dd1a-58bf-889c-bfec10b794bc	LOG-2281	SLA reroute	Split load via air	Route telemetry, weather	82	approved	low	complete	\N	[{"step": 1, "title": "Data used", "detail": "Route telemetry, weather"}, {"step": 2, "title": "Recommendation", "detail": "Split load via air · confidence 82%"}, {"step": 3, "title": "Model reasoning", "detail": "Predictive + causal weighted signals"}, {"step": 4, "title": "Approval", "detail": "Approved"}, {"step": 5, "title": "Action taken", "detail": "Executed via Action Agent · SLA logged"}, {"step": 6, "title": "Feedback captured", "detail": "Outcome fed to Learning Agent"}]	4	\N	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, email, full_name, is_active, created_at, updated_at) FROM stdin;
00000000-0000-0000-0000-000000000001	demo@mahindra-nexus.local	Demo User	t	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
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

COPY public.warehouse_signals (id, panel, label, value, tone, sort_order, created_at, updated_at) FROM stdin;
45b423d8-1780-55fb-af69-5f074cdc6a3d	warehouse	Dock congestion	62%	warning	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e4fef4f3-41aa-5d26-9b2c-b53a52905b69	warehouse	Picking delay	9 min	warning	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
71da2f41-9b8b-50e8-953f-9ce01c849558	warehouse	Inventory imbalance	-14%	danger	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
0a27e79e-3baa-5e50-9321-021fa12b5662	warehouse	Vehicle availability	78%	success	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
2d9ae2d5-eb5d-52bc-aaad-ce629dc961f6	warehouse	Load utilization	84%	success	4	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
758e4dc9-cc32-5a4b-b21f-0b944ca027ee	collections_metrics	Accounts at risk	12,842	default	5	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f914e9f8-2c71-5be2-abfa-52e0c4ad4a45	collections_metrics	Predicted roll-forward	3,214	default	6	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
e88a5fb4-c467-5f3b-9616-9b1bbce7f30b	collections_metrics	Recovery opportunity	₹42 Cr	default	7	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
7214ed62-790c-597f-9cac-f7fb9550ae20	collections_metrics	Field visit optimization	-28% cost	default	8	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
46f46367-9014-5855-857a-29451a6f7cc7	collections_metrics	Compliance alerts	6 flagged	default	9	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
206d80e7-d923-54ae-8afe-b1094a89b4dd	rvsf	Job-card delay prediction	2.4 hrs	warning	10	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
8a05d245-0304-55bc-91f4-eaa5601c4521	rvsf	Throughput	141 vehicles / day	success	11	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
132a2b2f-673b-579a-81c4-cb4667083f64	rvsf	Bottleneck	De-pollution bay	danger	12	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
35c01735-73cc-5a40-a44f-4e7c5941fc97	rvsf	dMRV completeness	78%	warning	13	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
268f9463-c3b6-5d3c-9b6c-fcdc439274eb	rvsf	Compliance risk	Low	success	14	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Data for Name: xr_experiences; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.xr_experiences (id, code, title, use_case, feature, impact, sort_order, created_at, updated_at) FROM stdin;
4b68f1f0-87a4-53f9-9a32-4f4c5a07e8a2	showroom	AI Virtual Showroom	Immersive vehicle exploration	Generative sales assistant + config	+18% online-to-visit conversion	0	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
ae100bcb-126e-5294-8380-6226e851f244	config	3D Vehicle Configurator	Personalized configurations	Real-time AI recommendations	+12% variant upsell	1	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
a23271f9-5cd3-528a-93e7-4cb2ba11c201	repair	AR Technician Repair Guide	Step-by-step service	Component-aware AR overlays	-24% repair time	2	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
f7dbf612-644d-55f6-ab07-6f4c87ceb964	training	VR Dealer Sales Training	Immersive skill building	AI feedback on pitch & objections	+22% training ROI	3	2026-08-05 12:13:18.359865+00	2026-08-05 12:13:18.359865+00
\.


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


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
-- Name: ix_ai_agents_use_areas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ai_agents_use_areas ON public.ai_agents USING gin (use_areas);


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

\unrestrict poeMsshXiqTMgZDb5jIlLjOMA3UcH3Xrdb2IF61kdlIbDD99bqt3jBmvjoQcld8

