-- ADDED FOR THIS SAMPLE
\echo 'Insert 3 audit logs...'
INSERT INTO global_audit_logs (school_id, performed_by_user_id, action_type, description, ip_address, prev_audit_id, chain_hash)
VALUES
    ('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174010', 'LOGIN', 'User logged in', '192.168.1.1', NULL, hash_hmac('sha256', 'GENESIS|123e4567-e89b-12d3-a456-426614174000|123e4567-e89b-12d3-a456-426614174010|LOGIN|User logged in|192.168.1.1|2024-01-01 00:00:00', 'demo-secret')),
    ('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174010', 'UPDATE', 'User updated profile', '192.168.1.1', (SELECT log_id FROM global_audit_logs WHERE action_type='LOGIN' LIMIT 1), 'PLACEHOLDER_HASH_2'),
    ('123e4567-e89b-12d3-a456-426614174000', '123e4567-e89b-12d3-a456-426614174010', 'LOGOUT', 'User logged out', '192.168.1.1', (SELECT log_id FROM global_audit_logs WHERE action_type='UPDATE' LIMIT 1), 'PLACEHOLDER_HASH_3');

\echo 'Chain verification: PASS (simulated - in real code would recompute all hashes)'
SELECT log_id, action_type, LEFT(chain_hash, 16) as hash_preview FROM global_audit_logs ORDER BY created_at;

\echo 'Tamper with middle log...'
UPDATE global_audit_logs SET description = 'MALICIOUS CHANGE' WHERE action_type = 'UPDATE';

\echo 'Chain verification: FAIL - tampering detected (simulated)'
SELECT log_id, action_type, description FROM global_audit_logs ORDER BY created_at;
