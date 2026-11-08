CREATE OR REPLACE FUNCTION fn_drop_old_partitions(p_retention_months INTEGER DEFAULT 24)
RETURNS INTEGER AS $$
DECLARE
    v_count     INTEGER := 0;
    v_cutoff    DATE;
    v_rec       RECORD;
    v_part_date DATE;
BEGIN
    v_cutoff := date_trunc('month', NOW()::date - (p_retention_months || ' months')::INTERVAL)::date;

    FOR v_rec IN
        SELECT c.relname AS part_name, p.relname AS parent_name
        FROM pg_inherits i
        JOIN pg_class c ON i.inhrelid = c.oid
        JOIN pg_class p ON i.inhparent = p.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public'
          AND c.relname != p.relname || '_default'
          AND c.relname ~ '_[0-9]{4}_[0-9]{2}$'
    LOOP
        -- Extract date from the _YYYY_MM name suffix
        BEGIN
            v_part_date := to_date(
                split_part(v_rec.part_name, '_', array_length(string_to_array(v_rec.part_name, '_'), 1) - 1) ||
                '-' ||
                split_part(v_rec.part_name, '_', array_length(string_to_array(v_rec.part_name, '_'), 1)),
                'YYYY-MM'
            );
        EXCEPTION WHEN OTHERS THEN
            CONTINUE;
        END;

        IF v_part_date < v_cutoff THEN
            -- DETACH first (safe), then DROP
            EXECUTE format('ALTER TABLE %I DETACH PARTITION %I', v_rec.parent_name, v_rec.part_name);
            EXECUTE format('DROP TABLE IF EXISTS %I', v_rec.part_name);
            v_count := v_count + 1;
        END IF;
    END LOOP;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_catalog;
