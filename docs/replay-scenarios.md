# Evaluation Scenarios

This document defines replay scenarios for deterministic evaluation.

## Scenario Structure

Each scenario consists of:
- **Baseline**: Complete telemetry coverage
- **Degraded variants**: Missing sources, fields, or retention windows

All scenarios stored in `tests/fixtures/replay/scenarios/{scenario_name}/`

## Scenario Definitions

12 baseline scenarios, 3 degraded variants each = 48 total test cases

### 1. Credential Change Baseline

**Investigation Question**: Did this principal's credentials change during the time window?

**Setup:**
- Principal: alice@example.com
- Time range: 2026-01-01 to 2026-01-31
- Expected outcome: Password reset on 2026-01-15, MFA enrollment on 2026-01-16

**Telemetry:**
- 50 authentication events (successful logins)
- 2 credential change events (password reset, MFA enrollment)
- 10 entities (principal, 2 credentials, 5 sessions, 2 devices)
- 8 relationships (session → principal, credential → principal, device → session)

**Coverage:**
- Identity provider: complete
- Source fields: all present
- Overall status: complete

**Expected Confidence:**
- Hypothesis "credentials changed": likelihood=1.0, confidence_cap=1.0 (final=1.0)

**Degraded Variants:**
- **1a. Missing Source (Retention Gap)**: Identity provider unavailable 2026-01-10 to 2026-01-20
  - Expected: likelihood=0.5 (partial evidence), confidence_cap=0.6 (gap includes event window)
- **1b. Missing Fields**: `source_ip` and `user_agent` fields absent from all events
  - Expected: likelihood=1.0 (core fields present), confidence_cap=0.8 (context limited)
- **1c. Partial Source**: Only password events, MFA events missing
  - Expected: likelihood=0.7 (partial evidence), confidence_cap=0.7 (MFA visibility gap)

---

### 2. Privilege Escalation Baseline

**Investigation Question**: Was this principal granted elevated privileges during the incident window?

**Setup:**
- Principal: bob@example.com
- Time range: 2026-01-10 to 2026-01-12
- Expected outcome: Added to "admin" group on 2026-01-11 at 14:32 UTC

**Telemetry:**
- 30 authentication events
- 1 privilege change event (group membership add)
- 1 authorization policy change event
- 12 entities (principal, 2 credentials, 3 sessions, 2 groups, 4 devices)
- 10 relationships (principal → group, session → principal)

**Coverage:**
- Identity provider: complete
- Authorization system: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "privilege escalation occurred": likelihood=1.0, confidence_cap=1.0

**Degraded Variants:**
- **2a. Authorization System Unavailable**: Authorization logs missing for entire window
  - Expected: likelihood=0.3 (indirect evidence only), confidence_cap=0.4 (critical source missing)
- **2b. Group Membership Fields Missing**: Group change events present but `group_name` field absent
  - Expected: likelihood=0.6 (event present, details unclear), confidence_cap=0.7 (limited attribution)
- **2c. Delayed Ingestion**: Privilege change event has 24h data latency
  - Expected: likelihood=1.0 (event visible), confidence_cap=0.8 (latency introduces uncertainty)

---

### 3. Session Hijacking Baseline

**Investigation Question**: Did this session exhibit indicators of hijacking (IP/device change mid-session)?

**Setup:**
- Principal: carol@example.com
- Session ID: session-abc123
- Time range: 2026-01-05 to 2026-01-06
- Expected outcome: Session IP changed from 10.0.1.5 to 45.67.89.10 mid-session (no re-auth)

**Telemetry:**
- 20 authentication events (1 session start, 19 actions within session)
- 3 entities (principal, 1 session, 2 devices)
- 4 relationships (session → principal, device → session)
- Context fields: `source_ip`, `user_agent`, `auth_method`

**Coverage:**
- Identity provider: complete
- Network metadata: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "session hijacked": likelihood=0.9, confidence_cap=1.0

**Degraded Variants:**
- **3a. Network Metadata Missing**: `source_ip` field absent from all events
  - Expected: likelihood=0.4 (cannot verify IP change), confidence_cap=0.5 (key indicator missing)
- **3b. Partial Session Visibility**: Events for first half of session missing
  - Expected: likelihood=0.5 (partial timeline), confidence_cap=0.6 (gap at critical transition)
- **3c. Device Tracking Unavailable**: Device entities missing, only session entity present
  - Expected: likelihood=0.6 (IP change visible, device correlation missing), confidence_cap=0.7

---

### 4. Account Compromise Baseline

**Investigation Question**: What actions did this principal take after suspected compromise?

**Setup:**
- Principal: dave@example.com
- Time range: 2026-01-20 to 2026-01-22
- Expected outcome: 45 events after compromise (file access, data export, lateral movement)

**Telemetry:**
- 50 events (5 pre-compromise baseline, 45 post-compromise)
- 15 entities (principal, 3 credentials, 8 sessions, 2 devices, 1 file resource)
- 12 relationships (session → principal, session → resource)

**Coverage:**
- Identity provider: complete
- Resource access logs: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "compromise led to data exfiltration": likelihood=0.95, confidence_cap=1.0

**Degraded Variants:**
- **4a. Resource Access Logs Missing**: File access events absent
  - Expected: likelihood=0.5 (authentication visible, actions unclear), confidence_cap=0.6 (critical plane missing)
- **4b. Pre-Compromise Baseline Missing**: Events before 2026-01-20 unavailable
  - Expected: likelihood=0.7 (post-compromise visible), confidence_cap=0.75 (no behavior baseline)
- **4c. Credential Change Events Missing**: Cannot verify if attacker changed credentials
  - Expected: likelihood=0.8 (actions visible), confidence_cap=0.85 (persistence mechanism unclear)

---

### 5. Failed Authentication Spike Baseline

**Investigation Question**: Was there a brute-force attempt against this principal?

**Setup:**
- Principal: eve@example.com
- Time range: 2026-01-03 08:00 to 2026-01-03 08:30
- Expected outcome: 150 failed auth attempts from 3 source IPs within 30 minutes

**Telemetry:**
- 150 failed auth events
- 5 successful auth events (legitimate user)
- 8 entities (principal, 1 credential, 5 sessions, 1 device)
- Context: `source_ip`, `user_agent`, `auth_method`

**Coverage:**
- Identity provider: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "brute force attack occurred": likelihood=1.0, confidence_cap=1.0

**Degraded Variants:**
- **5a. Failed Auth Logging Disabled**: Only successful auth events logged
  - Expected: likelihood=0.1 (no direct evidence), confidence_cap=0.2 (critical events missing)
- **5b. Source IP Field Missing**: Failed events present, `source_ip` absent
  - Expected: likelihood=0.7 (event count visible), confidence_cap=0.8 (attribution limited)
- **5c. Time Window Gap**: Events for 08:10-08:20 missing (middle of attack window)
  - Expected: likelihood=0.6 (partial pattern visible), confidence_cap=0.65 (peak timing unclear)

---

### 6. Rapid IP Change Baseline

**Investigation Question**: Did this principal authenticate from multiple source IPs within a suspicious time window?

**Setup:**
- Principal: frank@example.com
- Time range: 2026-01-08 12:00 to 2026-01-08 12:30
- Expected outcome: 5 logins from 5 different source IPs within 30 minutes

**Telemetry:**
- 5 authentication events (all successful)
- 5 entities (principal, 5 sessions)
- Context: `source_ip`, `user_agent`
- Source IPs: 10.0.1.5, 45.67.89.10, 192.168.1.100, 203.0.113.5, 198.51.100.42

**Coverage:**
- Identity provider: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "rapid IP change indicates compromise": likelihood=0.85, confidence_cap=1.0

**Degraded Variants:**
- **6a. Source IP Field Missing**: Authentication events present, `source_ip` absent
  - Expected: likelihood=0.2 (cannot verify IP pattern), confidence_cap=0.3 (key field missing)
- **6b. Partial Event Visibility**: Only 3 of 5 authentication events visible
  - Expected: likelihood=0.5 (partial pattern), confidence_cap=0.6 (incomplete timeline)
- **6c. Coarse Timestamp Precision**: Event timestamps rounded to nearest 10 minutes
  - Expected: likelihood=0.6 (IP changes visible, rapid timing unclear), confidence_cap=0.7

---

### 7. Shared Source IP Baseline

**Investigation Question**: Did multiple principals authenticate from the same source IP within a time window?

**Setup:**
- Principals: alice@example.com, bob@example.com, carol@example.com, dave@example.com
- Source IP: 203.0.113.42
- Time range: 2026-01-09 14:00 to 2026-01-09 15:00
- Expected outcome: 4 distinct principals authenticated from same IP within 1 hour

**Telemetry:**
- 12 authentication events (4 principals, 3 events each)
- 4 principal entities
- 4 session entities
- Context: `source_ip`, `user_agent`

**Coverage:**
- Identity provider: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "shared source IP indicates proxy or compromise": likelihood=0.8, confidence_cap=1.0

**Degraded Variants:**
- **7a. Source IP Field Missing**: Authentication events present, `source_ip` absent
  - Expected: likelihood=0.1 (cannot detect pattern), confidence_cap=0.2 (correlation impossible)
- **7b. Partial Principal Visibility**: Only 2 of 4 principals' events visible
  - Expected: likelihood=0.4 (partial pattern), confidence_cap=0.5 (scope unclear)
- **7c. Session Correlation Missing**: Events visible but session entities absent
  - Expected: likelihood=0.6 (IP pattern visible, session correlation unclear), confidence_cap=0.7

---

### 8. MFA Fatigue (Push Spam) Baseline

**Investigation Question**: Did this principal approve an MFA challenge after repeated denials?

**Setup:**
- Principal: grace@example.com
- Time range: 2026-01-10 09:00 to 2026-01-10 09:20
- Expected outcome: 15 MFA push challenges denied, then 1 approved, then successful login

**Telemetry:**
- 16 MFA challenge events (15 denied, 1 approved)
- 1 successful authentication event (after MFA approval)
- 3 entities (principal, 1 credential, 1 session)
- Context: `mfa_method`, `challenge_outcome`, `source_ip`

**Coverage:**
- Identity provider: complete
- MFA challenge logs: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "MFA fatigue attack succeeded": likelihood=0.95, confidence_cap=1.0

**Degraded Variants:**
- **8a. MFA Challenge Logs Missing**: Only successful auth event visible, no challenge denials
  - Expected: likelihood=0.2 (cannot verify fatigue pattern), confidence_cap=0.3 (critical logs missing)
- **8b. Challenge Outcome Field Missing**: MFA events present, `challenge_outcome` absent
  - Expected: likelihood=0.4 (event count visible, denials unclear), confidence_cap=0.5
- **8c. Partial Challenge Window**: First 10 challenges missing, only last 5 + approval visible
  - Expected: likelihood=0.6 (partial pattern), confidence_cap=0.7 (full scope unclear)

---

### 9. New MFA Method Added Baseline

**Investigation Question**: Was a new MFA method enrolled and immediately used?

**Setup:**
- Principal: henry@example.com
- Time range: 2026-01-11 10:00 to 2026-01-11 10:30
- Expected outcome: New phone number enrolled at 10:05, login with SMS MFA at 10:10

**Telemetry:**
- 1 credential change event (MFA enrollment)
- 1 MFA challenge event (SMS to new number)
- 1 successful authentication event
- 4 entities (principal, 2 credentials, 1 session)
- 2 relationships (new credential → principal)

**Coverage:**
- Identity provider: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "attacker added MFA method for persistence": likelihood=0.9, confidence_cap=1.0

**Degraded Variants:**
- **9a. Credential Change Events Missing**: Login visible, MFA enrollment event absent
  - Expected: likelihood=0.3 (cannot verify new method), confidence_cap=0.4
- **9b. MFA Method Details Missing**: Enrollment visible, method type/phone number absent
  - Expected: likelihood=0.6 (timing visible, attribution limited), confidence_cap=0.7
- **9c. Time Correlation Gap**: Enrollment and login timestamps both rounded to nearest hour
  - Expected: likelihood=0.5 (events present, suspicious timing unclear), confidence_cap=0.6

---

### 10. OAuth App Authorization Baseline

**Investigation Question**: Did this principal authorize a new OAuth application?

**Setup:**
- Principal: iris@example.com
- Time range: 2026-01-12 14:00 to 2026-01-12 14:05
- Expected outcome: OAuth consent granted to suspicious app "DataExporter" with broad scopes

**Telemetry:**
- 1 OAuth consent grant event
- 3 OAuth token usage events (app accessing user data)
- 3 entities (principal, 1 session, 1 business_object for OAuth app)
- Context: `oauth_client_id`, `scopes_granted`, `app_name`

**Coverage:**
- Identity provider: complete
- OAuth audit logs: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "malicious OAuth app authorized": likelihood=0.85, confidence_cap=1.0

**Degraded Variants:**
- **10a. OAuth Audit Logs Missing**: No consent grant events, only usage logs
  - Expected: likelihood=0.4 (usage visible, authorization unclear), confidence_cap=0.5
- **10b. Scopes Field Missing**: Consent event present, `scopes_granted` absent
  - Expected: likelihood=0.6 (grant visible, permission level unclear), confidence_cap=0.7
- **10c. App Metadata Missing**: Event present, `app_name` and `oauth_client_id` absent
  - Expected: likelihood=0.5 (grant visible, app identity unclear), confidence_cap=0.6

---

### 11. Admin Impersonation / Support Access Baseline

**Investigation Question**: Was temporary privileged access granted, used, then removed?

**Setup:**
- Principal: admin@example.com (granter)
- Target: judy@example.com (impersonated principal)
- Time range: 2026-01-13 11:00 to 2026-01-13 12:00
- Expected outcome: Support access granted (11:05), 12 actions taken as judy (11:10-11:45), access revoked (11:50)

**Telemetry:**
- 1 privilege grant event (impersonation permission added)
- 12 action events (admin acting as judy)
- 1 privilege revoke event (impersonation permission removed)
- 5 entities (2 principals, 2 sessions, 1 privilege grant record)
- Context: `acting_as`, `granted_by`, `revoked_by`

**Coverage:**
- Identity provider: complete
- Authorization system: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "support access abused": likelihood=0.8, confidence_cap=1.0

**Degraded Variants:**
- **11a. Authorization Logs Missing**: Action events visible, grant/revoke events absent
  - Expected: likelihood=0.5 (actions visible, authorization unclear), confidence_cap=0.6
- **11b. Acting-As Context Missing**: Events present, `acting_as` field absent
  - Expected: likelihood=0.3 (cannot distinguish impersonation from normal activity), confidence_cap=0.4
- **11c. Revoke Event Missing**: Grant and actions visible, revoke event absent
  - Expected: likelihood=0.6 (access grant visible, removal unclear), confidence_cap=0.7

---

### 12. Service Account Key Creation Baseline

**Investigation Question**: Was a new API key or client secret created and immediately used?

**Setup:**
- Principal: service-account-prod@example.com
- Time range: 2026-01-14 08:00 to 2026-01-14 08:15
- Expected outcome: New API key created at 08:02, 20 API calls using new key at 08:05-08:15

**Telemetry:**
- 1 credential change event (API key creation)
- 20 authentication events (API key usage)
- 3 entities (principal, 2 credentials, 1 session)
- Context: `credential_type`, `key_id`, `created_by`

**Coverage:**
- Identity provider: complete
- API audit logs: complete
- Overall status: complete

**Expected Confidence:**
- Hypothesis "service account key compromised": likelihood=0.85, confidence_cap=1.0

**Degraded Variants:**
- **12a. Key Creation Events Missing**: API usage visible, creation event absent
  - Expected: likelihood=0.4 (cannot verify new key), confidence_cap=0.5
- **12b. Key ID Missing**: Events present, `key_id` field absent (cannot correlate creation to usage)
  - Expected: likelihood=0.5 (timing visible, key correlation unclear), confidence_cap=0.6
- **12c. Created-By Field Missing**: Creation visible, actor who created key absent
  - Expected: likelihood=0.7 (key creation visible, attribution unclear), confidence_cap=0.8

---

## Metrics

### Repeatability
- Each scenario executed 10 times
- SHA256 hash of output must be identical across all runs
- Pass threshold: 100% identical outputs

### Evidence Linkage Completeness
- Every claim must reference at least one evidence_item
- Every evidence_item must reference at least one raw_ref
- Every raw_ref must have valid source pointer
- Pass threshold: 100% of claims have complete provenance chain

### Correctness of Missing-Data Reporting
- Baseline scenarios: overall_status = "complete", confidence_cap >= 0.9
- Degraded scenarios: overall_status = "partial" or "missing", confidence_cap < baseline
- Pass threshold: All scenarios report correct status

### Bounded Runtime
- Baseline scenarios: < 5 seconds per scenario
- Degraded scenarios: < 5 seconds per scenario
- Pass threshold: 95% of runs complete within time limit

## Implementation Notes

Each scenario requires:
1. NDJSON fixtures (entities.ndjson, events.ndjson, relationships.ndjson)
2. coverage.yaml (source availability metadata)
3. manifest.yaml (investigation question, time range, expected outcome)
4. expected_output.json (golden output for regression testing)

Degraded variants inherit baseline fixtures but modify coverage.yaml and expected_output.json.
