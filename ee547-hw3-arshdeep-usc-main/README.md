# q3

## Error Handling & Permission Failures

- **Fail fast on authentication issues** (invalid or missing credentials).
- **Service-level permission errors** (e.g., no access to IAM, EC2, or S3) are caught and logged, and the scan continues.
- **Resource-level failures** (e.g., one S3 bucket inaccessible) are skipped without stopping the overall process.
- **Network timeouts** are retried once to handle transient connectivity issues.

---

## Assumptions About AWS Account Configuration

- **Valid AWS credentials** are already configured (CLI profile, environment variables, or IAM role).
- A **region is specified or configured** in the AWS CLI.
- It operates in a **single AWS account** (no cross-account role assumption).
- EC2 and Security Groups are inspected in **one region only**.
- The IAM role used has at least read/list permissions for the services being scanned.
- The account size is moderate (pagination and large-scale optimization are not implemented).

Arshdeep Dhillon

ID: 2881665401
