# Non-Functional Requirements (NFR) Specifications: Clinical Data Factory

## 1. Data Integrity & Regulatory Compliance (GxP / HIPAA)
To comply with FDA Title 21 CFR Part 11 regulations, every modification to a clinical trial record must generate a cryptographically sealed immutable audit log.
* **Storage Invariant:** All raw and processed datasets must be stored inside AWS S3 buckets configured with Object Lock in strict Compliance Mode with a mandatory 7-year retention lease. 

## 2. High-Performance Compute & Deep Learning Specifications
The platform must run nightly automated deep learning training cycles on distributed transformer models to detect adverse drug reactions.
* **Compute Infrastructure Requirements:** The AI engine requires dedicated, always-on clusters of 8x AWS p4d.24xlarge instances (equipped with NVIDIA A100 GPUs) running inside an AWS UltraCluster placement group to achieve the mandatory processing windows.

### Critical Structural Cost Overrun Note:
The public standard on-demand pricing for a single AWS p4d.24xlarge instance is roughly £32.77 per hour. Running a dedicated, always-on cluster of 8 instances yields a baseline baseline compute cost of approximately £191,376 per month, exclusive of high-performance EBS storage, cross-AZ data egress charges, and automated S3 object replication overheads.
