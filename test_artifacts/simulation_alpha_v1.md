# Simulation-Alpha — Version 1: Initial Proposal (The Gap)

## 1. Project Overview

Simulation-Alpha is an enterprise-grade financial data processing platform
to be delivered over 18 months. The system will ingest, process, and expose
transaction data across three geographic regions for a regulated banking client.

## 2. Scope

- Real-time transaction ingestion pipeline (Kafka-backed)
- Multi-region data replication with eventual consistency guarantees
- Analytics dashboard for business users (read-only, aggregated views)
- REST API surface for downstream integrations (partner banks, regulators)
- Batch reconciliation engine for end-of-day settlement

## 3. Architecture

The platform uses a microservices pattern deployed on Kubernetes (EKS).
Event streaming via Apache Kafka (MSK). Transactional storage in PostgreSQL
(RDS Aurora). Redis for caching hot data paths. An API Gateway fronts all
external-facing services.

Services communicate via asynchronous message passing. The reconciliation
engine runs as a CronJob. Observability is provided by Prometheus + Grafana.

## 4. Delivery Timeline

| Phase   | Duration    | Scope                                                |
|---------|-------------|------------------------------------------------------|
| Phase 1 | Months 1–6  | Core ingestion pipeline, Kafka topology, storage     |
| Phase 2 | Months 7–12 | Analytics dashboard, REST API, partner integrations  |
| Phase 3 | Months 13–18| Multi-region replication, DR failover                |

Milestones at end of Phase 1 and Phase 3 are contractual payment triggers.

## 5. Resources

- 12 software engineers (FE + BE split)
- 2 platform/infrastructure architects
- 1 delivery manager
- 1 QA lead

## 6. Commercial

Fixed-price contract at £4,200,000. Payment schedule:
- £1,800,000 at Phase 1 completion
- £2,400,000 at Phase 3 completion

Assumptions: scope fixed at contract signature; change requests subject to
a formal impact assessment and commercial re-negotiation.

## NOTE — SECURITY GAP

Security controls, encryption standards, access management policies,
identity and access management (IAM) design, vulnerability assessment plans,
and regulatory compliance requirements (PCI DSS, GDPR, FCA) are NOT
documented in this version of the proposal.

Penetration testing schedule: TBD.
Secrets management approach: TBD.
Data classification and handling policy: TBD.
