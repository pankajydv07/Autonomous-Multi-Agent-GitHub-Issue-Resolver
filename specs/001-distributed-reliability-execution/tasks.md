# Tasks: Distributed Worker Architecture & Reliability Features

**Input**: Design documents from `/specs/001-distributed-reliability-execution/`

**Prerequisites**: [plan.md](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/specs/001-distributed-reliability-execution/plan.md) (required), [spec.md](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/specs/001-distributed-reliability-execution/spec.md) (required for user stories), [research.md](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/specs/001-distributed-reliability-execution/research.md), [data-model.md](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/specs/001-distributed-reliability-execution/data-model.md), [metrics-and-endpoints.md](file:///run/media/pankaj/PANKAJ/VScode/githubissue/Autonomous-Multi-Agent-GitHub-Issue-Resolver/specs/001-distributed-reliability-execution/contracts/metrics-and-endpoints.md)

**Tests**: Tests are included to verify critical retry queuing, distributed locking, circuit breakers, and shutdown scenarios.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Setup prometheus configuration in `prometheus/prometheus.yml`
- [x] T002 Initialize Grafana datasource configs in `grafana/provisioning/datasources/datasource.yml`
- [x] T003 Setup Grafana dashboard dashboard rules in `grafana/provisioning/dashboards/dashboard.yml`
- [x] T004 Define visual Grafana dashboards panels in `grafana/provisioning/dashboards/worker-metrics.json`
- [x] T005 Update services configuration in `docker-compose.yml` to include prometheus, grafana, and worker nodes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 [P] Implement Redis distributed locking helper methods in `shared/redis_client.py`
- [x] T007 [P] Add queue enqueue, reliable dequeue, and backoff methods in `shared/redis_client.py`
- [x] T008 [P] Implement circuit breaker logic wrapper inside the LLM client helper in `shared/llm_client.py`
- [x] T009 Create a dedicated file for structured Prometheus registry and metrics collection in `shared/metrics.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Fault-Tolerant Task Execution (Priority: P1) 🎯 MVP

**Goal**: Support reliable task execution with retry queues, exponential backoff, and DLQ quarantine.

**Independent Test**: Trigger tasks that encounter transient failures and check backoff logs. Check that failed tasks above retry limits go to DLQ.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T010 [P] [US1] Create unit tests for retry queues and backoff delays in `tests/test_retries.py`
- [x] T011 [P] [US1] Create unit tests for Dead Letter Queue transitions in `tests/test_dlq.py`
- [x] T012 [US1] Implement retry execution and DLQ routing loop inside `orchestrator/worker.py`
- [x] T013 [US1] Update task execution routing inside REST endpoints in `orchestrator/main.py`
- [x] T014 [US1] Coordinate run start and error state queries in `gateway/src/resolvers/runs.ts`

**Checkpoint**: User Story 1 is fully functional and testable independently.

---

## Phase 4: User Story 2 - Distributed Worker Scale-Out (Priority: P1)

**Goal**: Run multiple worker containers consuming from a central queue concurrently, protected from race conditions by distributed locks.

**Independent Test**: Spin up multiple workers and verify no single task ID is processed more than once.

### Tests for User Story 2

- [x] T015 [P] [US2] Create unit tests for distributed lock acquisition and expiry behaviors in `tests/test_locking.py`

### Implementation for User Story 2

- [x] T016 [US2] Wrap dequeue operations with distributed lock checks inside `orchestrator/worker.py`
- [x] T017 [US2] Scale number of worker containers configured in `docker-compose.yml`

**Checkpoint**: User Stories 1 and 2 work together. Multiple workers scale out execution safely.

---

## Phase 5: User Story 3 - Health & Performance Observability Dashboard (Priority: P2)

**Goal**: Expose Prometheus endpoints and view queue depths, latency, worker health, and throughput on Grafana.

**Independent Test**: Query `/metrics` endpoint and verify graphs render correctly on Grafana.

### Implementation for User Story 3

- [x] T018 [P] [US3] Implement Prometheus metric logging calls in `shared/metrics.py`
- [x] T019 [US3] Expose the `/metrics` scrapable HTTP endpoint in `orchestrator/main.py`
- [x] T020 [US3] Define Grafana panel mappings for worker counts and queue depths in `grafana/provisioning/dashboards/worker-metrics.json`

**Checkpoint**: Observability is fully operational.

---

## Phase 6: User Story 4 - Resilient Worker Lifecycle & Graceful Shutdown (Priority: P2)

**Goal**: Ensure workers finish active tasks and refuse new tasks when receiving termination signals (SIGTERM/SIGINT). Expose a health endpoint.

**Independent Test**: Send SIGTERM to a worker during execution and verify it finishes before terminating.

### Tests for User Story 4

- [x] T021 [P] [US4] Create unit tests for worker signal capture and exit handling in `tests/test_shutdown.py`

### Implementation for User Story 4

- [x] T022 [US4] Implement SIGTERM/SIGINT signal capture and graceful processing termination in `orchestrator/worker.py`
- [x] T023 [US4] Expose database and Redis connection health statuses on endpoints in `orchestrator/main.py` and `gateway/src/index.ts`

**Checkpoint**: All user stories are independently functional and resilient.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, formatting, validation, and final checks

- [x] T024 Lint and formatting checks on all Python services via `orchestrator/pyproject.toml`
- [x] T025 TypeScript validation checks on gateway via `gateway/package.json`
- [x] T026 Run end-to-end verification tests defined in `specs/001-distributed-reliability-execution/quickstart.md`
- [x] T027 Update system architecture and setup details in `README.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel or sequentially (US1 -> US2 -> US3 -> US4)
- **Polish (Final Phase)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Can start after US1 is functional - Integrates with locking
- **User Story 3 (P3)**: Can start after US1 and US2 are stable
- **User Story 4 (P4)**: Can start after US1/US2/US3 are completed

### Parallel Opportunities

- All Setup tasks (T001-T005) can run in parallel.
- All Foundational helper tasks (T006-T008) can run in parallel.
- Retry queue unit tests (T010, T011) and locking unit tests (T015) can be developed in parallel before code changes.
- Observability and dashboard configurations (T018-T020) can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Launch test-driven development tests for User Story 1:
Task: "Create unit tests for retry queues and backoff delays in tests/test_retries.py"
Task: "Create unit tests for Dead Letter Queue transitions in tests/test_dlq.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Reliable execution + DLQ)
4. **STOP and VALIDATE**: Verify retry, backoff, and DLQ quarantine behavior.

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently (MVP)
3. Add User Story 2 -> Test distributed workers safety
4. Add User Story 3 -> Verify dashboards
5. Add User Story 4 -> Verify signal handling and shutdowns
