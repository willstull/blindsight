# Live Integration Decision Framework

## Status

Decision deferred until replay evaluation harness is working. Live integration is **optional** for demonstrating the system.

## Rationale for Deferral

Replay datasets prove the architecture without dependency on:
- External system availability
- Authentication complexity
- Data sensitivity concerns
- Network access requirements

If replay evaluation succeeds, live integration becomes a "nice-to-have" rather than requirement.

## Decision Criteria

If pursuing live integration, evaluate candidates on:

### 1. Authentication Feasibility
- Can I get API credentials without organizational approval process?
- Is authentication mechanism simple (API key, OAuth with personal account)?
- Can authentication be completed within 1-2 days?

### 2. API Stability
- Is API documented and stable?
- Are there rate limits I need to handle?
- Is API pagination straightforward?
- Can I query historical data (not just real-time)?

### 3. Testability
- Can I generate test scenarios in the live system?
- Can I control event timing (e.g., trigger auth events on demand)?
- Can I clean up test data afterward?
- Is there a sandbox/dev environment?

### 4. Ground Truth Scenarios
- Can I create known-outcome scenarios (e.g., trigger failed logins, change password)?
- Can I verify events appear in logs within reasonable latency?
- Can I script scenario generation (not manual clicking)?

### 5. Data Sensitivity
- Can I use non-production data?
- Are there PII/privacy concerns with logging?
- Can I demo results without exposing real identities?

### 6. Time Investment
- Can I integrate in < 1 week?
- Is debugging straightforward (good error messages)?
- Are there client libraries (Python SDK)?

## Candidate Sources

### Option 1: Okta (Identity Provider)

**Pros:**
- Free developer account available
- Well-documented REST API
- Python SDK exists (`okta-sdk-python`)
- Can create test users and trigger events
- Clear authentication (API token)

**Cons:**
- Free tier has usage limits
- Requires email verification for new accounts
- Logs may have latency (not real-time)
- Limited to identity events (no resource access)

**Feasibility Score: 8/10**

**Integration Effort:** 3-5 days
- Day 1: Account setup, API key generation
- Day 2: Implement LiveOktaPlane adapter
- Day 3: Map Okta events to canonical ActionEvent
- Day 4: Test with scripted scenarios
- Day 5: Coverage report generation for Okta limitations

**Test Scenario Capability:**
- Create test user
- Trigger successful login
- Trigger failed login (wrong password)
- Change password
- Enroll MFA
- Suspend user

All scriptable via API.

---

### Option 2: AWS CloudTrail (Cloud Audit)

**Pros:**
- Free tier includes CloudTrail events
- Rich event data (API calls, resource access)
- Well-documented JSON format
- Python SDK (boto3) mature and stable
- Can query via CloudTrail Lake or S3

**Cons:**
- Requires AWS account (may have costs beyond free tier)
- Events span identity + resource planes (complex)
- S3 storage required for historical queries
- IAM permissions setup can be complex
- Event delivery latency (5-15 minutes)

**Feasibility Score: 6/10**

**Integration Effort:** 5-7 days
- Day 1-2: AWS account setup, IAM role creation
- Day 3: Implement CloudTrail query logic
- Day 4: Event normalization (many event types)
- Day 5-6: Test scenarios (S3 access, EC2 start/stop)
- Day 7: Coverage report for CloudTrail limitations

**Test Scenario Capability:**
- Trigger S3 GetObject (file access)
- Start/stop EC2 instance
- Assume IAM role
- Failed API call (insufficient permissions)

All scriptable via boto3, but requires AWS resources.

---

### Option 3: Azure AD (Identity Provider)

**Pros:**
- Free developer account (Microsoft 365 Developer Program)
- Graph API well-documented
- Can create test users and trigger events
- Python SDK (msal + requests)
- Supports sign-in logs query

**Cons:**
- Microsoft 365 Developer Program requires application/approval
- API permissions can be confusing (delegated vs application)
- Log retention limited on free tier
- Rate limits strict
- Documentation sprawling

**Feasibility Score: 5/10**

**Integration Effort:** 6-8 days
- Day 1-2: Microsoft 365 Developer account approval
- Day 3: App registration, permission grants
- Day 4-5: Implement LiveAzureADPlane adapter
- Day 6: Event normalization (Azure AD schema complex)
- Day 7-8: Test scenarios and debug

**Test Scenario Capability:**
- Create test user
- Trigger sign-in
- Trigger MFA prompt
- Change password

Scriptable, but Graph API complexity adds friction.

---

## Decision Matrix

| Criterion | Okta | AWS CloudTrail | Azure AD |
|-----------|------|----------------|----------|
| Auth Feasibility | 9/10 | 7/10 | 6/10 |
| API Stability | 9/10 | 9/10 | 7/10 |
| Testability | 8/10 | 6/10 | 6/10 |
| Ground Truth | 9/10 | 7/10 | 7/10 |
| Data Sensitivity | 9/10 | 8/10 | 8/10 |
| Time Investment | 8/10 | 5/10 | 4/10 |
| **Total** | **52/60** | **42/60** | **38/60** |

## Recommendation

**If pursuing live integration**: Okta

**Rationale:**
- Fastest path to working adapter (3-5 days)
- Free developer account, no approval wait
- Clean API with Python SDK
- Good test scenario scriptability
- Stays within identity plane (simplifies scope)

**If NOT pursuing live integration**: Continue with replay datasets only

Replay evaluation proves:
- Tool contracts work
- Normalization logic correct
- Coverage reporting accurate
- Gap-aware scoring functions
- Case store correlation queries work

Live integration adds:
- Real API error handling
- Network latency considerations
- Rate limit handling
- Production-like edge cases

But does NOT add:
- Fundamentally different architecture
- New evaluation methodology
- Proof that system works (replay already proves this)

## Decision Timeline

**Week 8-9** (after Milestone 2 complete):
- Evaluate replay scenario results
- If all scenarios pass: decide whether live integration adds sufficient value
- If pursuing: allocate 1 week for Okta integration
- If not pursuing: focus on writeup, documentation, presentation prep

## Success Criteria for Live Integration (if pursued)

1. LiveOktaPlane implements PlaneAdapter interface
2. Passes contract validation tests (same tests as replay adapter)
3. One scripted scenario with known outcome succeeds
4. Coverage report accurately reflects Okta API limitations
5. Error handling for API failures (rate limits, network errors)
6. Documentation updated with live integration notes

## Risk Mitigation

If live integration fails or takes too long:
- Replay evaluation already proves the system
- Fall back to replay-only demonstration
- Document live integration attempt in "Future Work" section
- No impact on project success criteria
