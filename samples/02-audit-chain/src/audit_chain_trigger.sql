-- Audit chain: HMAC-SHA256 hash function (VF-003: no fallback to default)
CREATE OR REPLACE FUNCTION fn_calculate_audit_hash(
    p_prev_hash    TEXT,
    p_school_id    UUID,
    p_actor_id     UUID,
    p_event_type   TEXT,
    p_description  TEXT,
    p_ip_address   TEXT,
    p_created_at   TIMESTAMPTZ
) RETURNS TEXT AS $$
DECLARE
    v_secret  TEXT;
    v_payload TEXT;
BEGIN
    v_secret := current_setting('app.nexo_hmac_secret', true);
    IF v_secret IS NULL OR v_secret = '' OR v_secret = 'default-secret-change-me' THEN
        RAISE EXCEPTION 'app.nexo_hmac_secret is not configured. Aborting to prevent audit chain compromise.';
    END IF;
    v_payload := COALESCE(p_prev_hash,'GENESIS')
        || '|' || COALESCE(p_school_id::TEXT,'NULL')
        || '|' || COALESCE(p_actor_id::TEXT,'NULL')
        || '|' || COALESCE(p_event_type,'')
        || '|' || COALESCE(p_description,'')
        || '|' || COALESCE(p_ip_address,'')
        || '|' || COALESCE(p_created_at::TEXT,'');
    RETURN encode(hmac(v_payload, v_secret, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog;

-- Audit chain trigger
CREATE OR REPLACE FUNCTION fn_audit_chain_trigger()
RETURNS TRIGGER AS $$
DECLARE
    v_prev_hash TEXT;
    v_prev_id   UUID;
BEGIN
    SELECT log_id, chain_hash INTO v_prev_id, v_prev_hash
    FROM global_audit_logs
    WHERE (school_id IS NOT DISTINCT FROM NEW.school_id)
    ORDER BY created_at DESC, log_id DESC LIMIT 1 FOR UPDATE;
    NEW.prev_audit_id := v_prev_id;
    NEW.chain_hash := fn_calculate_audit_hash(
        v_prev_hash, NEW.school_id, NEW.performed_by_user_id,
        NEW.action_type, NEW.action_details::TEXT,
        NEW.ip_address::TEXT, NEW.created_at
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_chain ON global_audit_logs;
CREATE TRIGGER trg_audit_chain BEFORE INSERT ON global_audit_logs
    FOR EACH ROW EXECUTE FUNCTION fn_audit_chain_trigger();

-- Audit chain validation
CREATE OR REPLACE FUNCTION fn_validate_audit_chain(p_school_id UUID DEFAULT NULL)
RETURNS JSONB AS $$
DECLARE
    v_expected_hash TEXT;
    v_prev_hash     TEXT;
    v_record        RECORD;
    v_broken_at     UUID := NULL;
    v_count         INTEGER := 0;
    v_valid_count   INTEGER := 0;
BEGIN
    v_prev_hash := NULL;
    FOR v_record IN
        SELECT log_id, school_id, performed_by_user_id, action_type,
               action_details, ip_address, created_at, chain_hash, prev_audit_id
        FROM global_audit_logs
        WHERE (p_school_id IS NULL OR school_id = p_school_id)
        ORDER BY created_at ASC, log_id ASC
    LOOP
        v_count := v_count + 1;
        v_expected_hash := fn_calculate_audit_hash(
            v_prev_hash, v_record.school_id, v_record.performed_by_user_id,
            v_record.action_type, v_record.action_details::TEXT,
            v_record.ip_address::TEXT, v_record.created_at
        );
        IF v_record.chain_hash = v_expected_hash THEN
            v_valid_count := v_valid_count + 1;
        ELSE
            v_broken_at := v_record.log_id;
            EXIT;
        END IF;
        v_prev_hash := v_record.chain_hash;
    END LOOP;
    IF v_broken_at IS NOT NULL THEN
        RETURN jsonb_build_object('status','compromised','broken_at_audit_id',v_broken_at,
            'total_checked',v_count,'valid_up_to',v_valid_count - 1);
    ELSE
        RETURN jsonb_build_object('status','ok','total_records',v_count,'school_id',p_school_id);
    END IF;
END;
$$ LANGUAGE plpgsql;
