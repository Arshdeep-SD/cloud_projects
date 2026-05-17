# RobustHTTPClient Retry Strategy

## 1. When a Retry Occurs

A retry is attempted only for certain types of failures:

- **Server errors (5xx)** – Temporary issues on the server.  
- **Timeouts** – When the server does not respond in time.  
- **Connection errors** – Network failures, DNS resolution errors, or other connectivity issues.

**Client errors (4xx)** are not retried, as they indicate a problem with the request itself.

---

## 2. Retry Attempts

- Each URL request is attempted **up to 4 times** by default:  
  - 1 initial request  
  - Up to 3 retries  
- Each retry is logged, along with the reason for the retry.

---

## 3. Backoff Strategy

- Retries use **exponential backoff**, i.e. the wait time increases exponentially after each failure.  
- A small **random jitter** is added to prevent multiple clients from retrying simultaneously.  
- The wait time is capped at a maximum value to prevent excessive delays.

---

## 4. Logging

- Each retry is logged with:
  - The URL  
  - Retry attempt number  
  - Wait duration  
  - Reason for the retry (timeout, server error, connection error)  
- If all retries fail, the final failure is logged as **maximum retries reached**.

---

# **Usage Example**

Refer to testing.ipynb for usage examples.

