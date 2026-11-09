# Capstone Acceptance Criteria

## 1. Hosted Service Availability

The hosted application must be accessible through its deployed URL. To verify availability, send an HTTP GET request to the `/health` endpoint three separate times.

- **Action:** Send three HTTP GET requests to `/health` using the deployed application URL.
- **Expected result:** Each request returns HTTP `200 OK` with a response body indicating that the service is healthy.
- **Target:** 3 out of 3 successful responses.
- **Why this target:** A health endpoint provides a reliable way to verify that the hosted application is running and accessible without requiring a dedicated main webpage.
- **Failure condition:** The criterion fails if any of the three requests returns a non-200 status code, times out, or returns an unexpected response body.

## 2. Protection of Logs and Operations

The application must protect access to its existing `/log` and `/operations` endpoints to prevent unauthorized users from accessing operational information.

- **Action:** Send HTTP GET requests to `/log` and `/operations` without valid authentication credentials.
- **Expected result:** Both endpoints reject unauthorized requests with HTTP `401 Unauthorized` or `403 Forbidden`, according to the application's authentication design. No protected log or operation data should be exposed in the response.
- **Target:** 3 out of 3 unauthorized access attempts are rejected for each endpoint.
- **Why this target:** Logs and operation records may contain sensitive application information that should only be accessible to authorized users.
- **Failure condition:** The criterion fails if any unauthorized request successfully retrieves protected information or returns HTTP `200 OK` with sensitive data.

## 3. Latency

The hosted application's `/health` endpoint must respond within an acceptable time limit under normal operating conditions.

- **Action:** Send three sequential HTTP GET requests to `/health` and measure the response time of each request, including the initial request.
- **Expected result:** Each request receives an HTTP `200 OK` response within 1,000 milliseconds.
- **Target:** 3 out of 3 requests complete within 1,000 ms.
- **Why this target:** A response time of one second or less provides a reasonable baseline for responsiveness and helps identify hosting or connectivity issues.
- **Failure condition:** The criterion fails if any request exceeds 1,000 milliseconds, times out, or returns an unsuccessful HTTP status code.

## 4. Error Handling

The application must return an appropriate HTTP error response when a client submits an invalid HTTP request to an existing endpoint.

- **Action:** Send an HTTP POST request to `/health`, which only supports HTTP GET.
- **Expected result:** The application returns HTTP `405 Method Not Allowed` with a response body containing an appropriate error message. The response must not expose internal stack traces or sensitive implementation details.
- **Target:** 3 out of 3 invalid requests return HTTP `405` with the expected error response.
- **Why this target:** Proper HTTP error handling helps users and developers understand invalid requests while preventing unnecessary exposure of internal application details.
- **Failure condition:** The criterion fails if the application returns an unexpected status code, processes the invalid request successfully, or exposes internal debugging information.

## 5. Sensitive Data Exclusion

The application's instrumentation and operational responses must not expose sensitive information such as passwords, authentication tokens, API keys, or other credentials.

- **Action:** Submit three test operations using predefined dummy credentials and inspect the resulting `/log` and `/operations` responses.
- **Expected result:** Sensitive test values are excluded or appropriately redacted from all returned log and operation records.
- **Target:** 0 occurrences of unredacted sensitive test values across all inspected responses in the three trials.
- **Why this target:** Preventing sensitive information from appearing in application logs and operational records reduces the risk of credential exposure and unauthorized access.
- **Failure condition:** The criterion fails if any inspected response contains an unredacted password, authentication token, API key, or other predefined sensitive test value.