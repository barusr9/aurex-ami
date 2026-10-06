# Stage 3 Validation Scripts

Runnable scripts for validating Stage 3 functionality, security, and deployments.

## validate_security_fixes.py

Comprehensive validation of all 5 critical security fixes applied to Stage 3.

**Usage:**
```bash
python3 validate_security_fixes.py
```

**Tests:**
- ✅ No localStorage token usage in UI
- ✅ HTTP-only auth cookie set on /login
- ✅ Session timeout enforced (24h default)
- ✅ Confirmation requires explicit "yes"/"confirm" and turn advancement
- ✅ LongTermMemory per-customer isolation
- ✅ No hardcoded secrets in source code
- ✅ Query classification security (no false negatives)

**Output:**
Prints detailed validation results. Exit code 0 = all tests passed, 1 = failures found.

---

## Future Scripts

Additional validation scripts can be added here:
- `test_performance.py` — Benchmark latency and throughput
- `test_integration.py` — End-to-end flow validation
- `load_test.py` — Concurrent user stress testing
- `security_audit.py` — Advanced security scanning
