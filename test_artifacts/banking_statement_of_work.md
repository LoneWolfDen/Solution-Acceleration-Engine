# Statement of Work: Project Prometheus Core Migration

## 1. Executive Summary
This Statement of Work (SoW) defines the delivery framework for migrating the Retail Banking Core Ledger (Legacy System Architecture) from the current on-premises IBM mainframe setup to an AWS cloud-native distributed architecture.

## 2. Project Scope & Deliverables
* Migrating 45 million active customer accounts to AWS Aurora PostgreSQL global databases.
* Refactoring the COBOL-based interest calculation engine into stateless AWS Lambda microservices written in Go.
* Implementing a real-time event-driven transaction ledger using AWS MSK (Managed Streaming for Kafka).

## 3. Timeline & Milestone Schedule
The client requires an absolute, unalterable go-live date due to regulatory data center lease exits in the UK.
* **Milestone 1 (T+30 Days):** Complete target schema definition and initial data mapping.
* **Milestone 2 (T+60 Days):** Complete full refactoring of interest engine to AWS Lambda.
* **Milestone 3 (T+90 Days):** Execution of parallel run, dry-run cutover, and full cloud ledger go-live.

## 4. Assumptions & Dependencies
* The client will guarantee 99.999% availability of upstream source systems during the intensive 48-hour cutover window.
* Baseline network latency between remaining on-prem clearing frameworks and AWS London region will not exceed 2ms over the standard VPN connection.
