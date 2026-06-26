# Simulation-Alpha — Version 2: Corrected Proposal (The Correction)

## 1. Project Overview

Simulation-Alpha is an enterprise-grade financial data processing platform
to be delivered over 18 months. The system will ingest, process, and expose
transaction data across three geographic regions for a regulated banking client.
This version addresses the security and compliance gap identified during v1 review.

## 2. Scope

- Real-time transaction ingestion pipeline (Kafka-backed)
- Multi-region data replication with eventual consistency guarantees
- Analytics dashboard for business users (read-only, aggregated views)
- REST API surface for downstream integrations (partner banks, regulators)
- Batch reconciliation engine for end-of-day settlement
- End-to-end encryption (AES-256 at rest, TLS 1.3 in transit)
- PCI DSS Level 1 compliance programme

## 3. Architecture

The platform uses a microservices pattern deployed on Kubernetes (EKS) with
RBAC and network policies enforced at the namespace level. Event streaming via
Apache Kafka (MSK). Transactional storage in PostgreSQL (RDS Aurora) with
encryption at rest enabled. Redis for caching hot data paths.

A Web Application Firewall (WAF — AWS WAF) protects all public-facing API
endpoints. API Gateway enforces mutual TLS for partner integrations.

All secrets are managed via HashiCorp Vault; no credentials are stored in
environment variables or configuration files. Snyk is integrated into the
CI/CD pipeline for continuous vulnerability scanning.

Services communicate via asynchronous message passing over encrypted
channels. Observability: Prometheus + Grafana + PagerDuty alerting.

## 4. Delivery Timeline

| Phase   | Duration    | Scope                                                              |
|---------|-------------|---------------------------------------------------------------------|
| Phase 1 | Months 1–6  | Core ingestion, Kafka topology, storage, security baseline          |
| Phase 2 | Months 7–12 | Analytics dashboard, REST API, partner integrations, pen testing    |
| Phase 3 | Months 13–18| Multi-region replication, DR failover, PCI DSS compliance audit     |

Milestones at end of Phase 1 and Phase 3 are contractual payment triggers.
Phase 2 includes a mandatory penetration test window (Months 10–11) conducted
by an approved external vendor; remediation sprint in Month 12.

## 5. Resources

- 12 software engineers (FE + BE split, including 2 dedicated security engineers)
- 2 platform/infrastructure architects
- 1 delivery manager
- 1 QA lead
- 1 external security consultant (Phase 1–2, part-time advisory)

## 6. Commercial

Fixed-price contract at £4,400,000. Payment schedule:
- £1,900,000 at Phase 1 completion
- £2,500,000 at Phase 3 completion

The £200,000 uplift over v1 covers: 2 security engineers (Phases 1–2),
external security consultant retainer, penetration testing vendor fees,
and PCI DSS compliance audit costs.

## 7. Security & Compliance

### Encryption
- Data at rest: AES-256 on all RDS instances and S3 buckets
- Data in transit: TLS 1.3 enforced on all service-to-service and external paths
- Key management: AWS KMS with automatic annual rotation

### Access Management
- Kubernetes RBAC: least-privilege service accounts per namespace
- Human access: SSO via Okta + MFA enforced for all production access
- API authentication: OAuth 2.0 with short-lived JWT tokens

### Compliance Targets
- PCI DSS Level 1: scoping workshop in Month 1; QSA engaged by Month 3
- GDPR: data residency controls enforced at storage layer (EU regions only)
- FCA: audit trail retention for 7 years (append-only event log in S3)

### Vulnerability Management
- Snyk integrated in CI/CD for dependency and container scanning (day one)
- OWASP Top 10 mitigations built into API design standards (reviewed in PR)
- Penetration test: Months 10–11, external vendor, full scope
- Remediation: Month 12 sprint, findings tracked in JIRA

### Secrets Management
- HashiCorp Vault: dynamic secrets for DB credentials, auto-rotated
- No static credentials in code, config files, or environment variables
- Vault audit log forwarded to SIEM
