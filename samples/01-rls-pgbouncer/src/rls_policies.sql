-- ROW LEVEL SECURITY — POLICIES
-- =============================================================================

-- students
ALTER TABLE students ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS students_select ON students;
DROP POLICY IF EXISTS students_insert ON students;
DROP POLICY IF EXISTS students_update ON students;
DROP POLICY IF EXISTS students_delete ON students;
CREATE POLICY students_select ON students FOR SELECT USING(school_id = get_current_school_id());
CREATE POLICY students_insert ON students FOR INSERT WITH CHECK(school_id = get_current_school_id());
CREATE POLICY students_update ON students FOR UPDATE USING(school_id = get_current_school_id());
CREATE POLICY students_delete ON students FOR DELETE USING(school_id = get_current_school_id());
