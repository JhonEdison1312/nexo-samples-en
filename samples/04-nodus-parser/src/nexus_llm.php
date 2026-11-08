<?php
/**
 * =============================================================================
 * nexus/nexus_llm.php — Semantic LLM parser (OpenAI-compatible API).
 * =============================================================================
 *
 * The LLM does NOT reply to the user or touch the DB: it translates free text
 * into a taxonomy intent + entities. The output enters the intent pipeline
 * (DSM -> SCP -> planner -> RBAC -> read-only SQL), so a wrong parse can never
 * write or bypass authorization.
 *
 * Provider-agnostic via env:
 *   NLU_LLM_URL    OpenAI-compatible base URL (default https://api.groq.com/openai/v1)
 *   NLU_LLM_KEY    API key (empty => LLM disabled)
 *   NLU_LLM_MODEL  model (default qwen/qwen3.8-27b — Groq free 1k req/day,
 *                  8k tokens/min; alternatives on the account:
 *                  openai/gpt-oss-20b, openai/gpt-oss-120b)
 *   NLU_LLM_MODE   off | on  ('primary'/'fallback' accepted as 'on' for
 *                  env compatibility)
 *   NLU_LLM_TIMEOUT_MS  (default 6000)
 *   NLU_LLM_REASONING_EFFORT  optional — "none" disables reasoning on
 *                  qwen3 models; empty = not sent
 */

function nxLlmCfg(): array {
    static $c = null;
    if ($c !== null) return $c;
    $mode = strtolower((string)(getenv('NLU_LLM_MODE') ?: 'on'));
    $c = [
        'url'   => rtrim((string)(getenv('NLU_LLM_URL') ?: 'https://api.groq.com/openai/v1'), '/'),
        'key'   => (string)(getenv('NLU_LLM_KEY') ?: ''),
        // GROQ_MODEL accepted as alias — avoids the silent failure of
        // setting the provider name on Render and not seeing it applied
        'model' => (string)(getenv('NLU_LLM_MODEL') ?: getenv('GROQ_MODEL') ?: 'qwen/qwen3.8-27b'),
        'mode'  => $mode === 'off' ? 'off' : 'on',
        'ms'    => max(500, (int)(getenv('NLU_LLM_TIMEOUT_MS') ?: 6000)),
    ];
    return $c;
}

function nxLlmEnabled(): bool {
    $c = nxLlmCfg();
    return $c['key'] !== '' && $c['mode'] !== 'off';
}

/* ============================================================================
 * Shared transport — quota budget.
 * ----------------------------------------------------------------------------
 * Groq free: 8,000 tokens/min and 1,000 req/day PER KEY (shared by all users
 * of the institution). A 429 is not retried blindly: we wait for Retry-After
 * only when it is short (parser) and open a Redis cooldown so subsequent
 * turns go straight to the deterministic fallback instead of hitting the
 * limit again.
 * ========================================================================== */
function nxLlmRedis() {
    static $r = false;
    if ($r !== false) return $r;
    $r = null;
    try { if (function_exists('getRedisConnection')) $r = getRedisConnection(); } catch (Throwable $e) { $r = null; }
    return $r;
}

function nxLlmCooling(): bool {
    static $localUntil = 0;
    if (getenv('NX_LLM_IGNORE_COOLDOWN') === '1') return false;
    if (time() < $localUntil) return true;
    try {
        $rd = nxLlmRedis();
        $until = $rd ? (int)$rd->get('nx:llm:cooldown_until') : 0;
        if ($until > time()) { $localUntil = $until; return true; }
    } catch (Throwable $e) {}
    return false;
}

function nxLlmSetCooldown(int $secs): void {
    $until = time() + max(2, min(90, $secs));
    try { $rd = nxLlmRedis(); if ($rd) $rd->setex('nx:llm:cooldown_until', max(2, min(90, $secs)), (string)$until); } catch (Throwable $e) {}
}

/** Last provider failure — trace diagnostics (no sensitive data). */
function nxLlmLastError(?string $set = null): ?string {
    static $last = null;
    if ($set !== null) $last = $set;
    return $last;
}

/**
 * POST /chat/completions -> decoded array or null.
 * $retry429: one retry if the provider asks to wait <= 2.5 s.
 */
function nxLlmPost(array $payload, bool $retry429 = false): ?array {
    if (!nxLlmEnabled()) { nxLlmLastError('disabled'); return null; }
    if (nxLlmCooling()) { nxLlmLastError('cooldown'); return null; }
    // per-request budget: if the parser already consumed 40 s, the composer
    // cannot ask for another 55 — nginx would cut the whole request (empty
    // response). The excess degrades to a deterministic template.
    static $spentMs = 0.0;
    $budget = max(5000, (int)(getenv('NX_LLM_BUDGET_MS') ?: 45000));
    $c = nxLlmCfg();
    $remain = $budget - $spentMs;
    if ($remain < 3000) { nxLlmLastError('budget_exhausted'); return null; }
    $timeoutMs = min($c['ms'], (int)$remain);
    if (($re = (string)getenv('NLU_LLM_REASONING_EFFORT')) !== '' && !isset($payload['reasoning_effort']))
        $payload['reasoning_effort'] = $re;
    for ($attempt = 0; $attempt < ($retry429 ? 2 : 1); $attempt++) {
        $hdr = [];
        $ch = curl_init($c['url'] . '/chat/completions');
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST => true,
            CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'Authorization: Bearer ' . $c['key']],
            CURLOPT_POSTFIELDS => json_encode($payload, JSON_UNESCAPED_UNICODE),
            CURLOPT_TIMEOUT_MS => $timeoutMs,
            CURLOPT_CONNECTTIMEOUT_MS => min(1500, $c['ms']),
            CURLOPT_HEADERFUNCTION => function ($ch, $line) use (&$hdr) {
                $p = strpos($line, ':');
                if ($p !== false) $hdr[strtolower(trim(substr($line, 0, $p)))] = trim(substr($line, $p + 1));
                return strlen($line);
            },
        ]);
        $t0 = microtime(true);
        $res = curl_exec($ch);
        $spentMs += (microtime(true) - $t0) * 1000;
        $code = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        if ($res !== false && $code === 200) {
            $d = json_decode((string)$res, true);
            return is_array($d) ? $d : null;
        }
        if ($code === 429) {
            $ra = (float)($hdr['retry-after'] ?? 0);
            if ($ra <= 0 && is_string($res) && preg_match('/try again in ([\d.]+)(ms|s)/i', $res, $m))
                $ra = $m[2] === 'ms' ? (float)$m[1] / 1000 : (float)$m[1];
            if ($retry429 && $attempt === 0 && $ra > 0 && $ra <= 2.5) { usleep((int)($ra * 1e6) + 150000); continue; }
            nxLlmSetCooldown((int)ceil($ra > 0 ? $ra : 12));
            nxLlmLastError('429');
            return null;
        }
        nxLlmLastError($res === false ? 'timeout' : "http_{$code}");
        return null;
    }
    return null;
}

/** JSON content of the assistant message (or null). */
function nxLlmJsonContent(?array $d): ?array {
    $content = $d['choices'][0]['message']['content'] ?? '';
    if (!is_string($content) || $content === '') return null;
    // some models wrap JSON in ```json … ``` or prepend <think>
    $content = preg_replace('/^.*?<\/think>/s', '', $content);
    $content = trim(preg_replace('/^```(?:json)?|```$/m', '', $content));
    $j = json_decode($content, true);
    if (!is_array($j) && preg_match('/\{.*\}/s', $content, $m)) $j = json_decode($m[0], true);
    return is_array($j) ? $j : null;
}

/* Chat intent taxonomy — whitelist that validates LLM output. */
const NX_LLM_FORMAL = [
    'day_summary','attendance_today','late_today','count_events','list_events',
    'student_field','student_summary','group_summary','risk_students',
    'trackings','permissions','citations','devices_status',
    'notifications_unread','audit_query','students_count','groups_list',
    'teachers_list','schedule_info','export_data','derive_action',
    'about_me','help','capabilities','security_probe',
    'random_student','staff_lookup','start_operation','count_present',
    'count_trackings','students_in_group','top_offenders','pending_returns',
    'sos_alerts','biometric_spam','group_student_count','birthdays_today',
    'my_activity','failed_messages','risk_config','attendance_ranking',
    'groups_compare',
    'session_summary','pending_tasks','whatsapp_status','frequency_table',
    'system_incidents','guardian_replies',
    // intents derived from the data model (table × interrogative)
    'risk_reason','incident_excuses','exit_detail','trip_info',
    'school_calendar','staff_contact','teacher_schedule','student_consent',
    'tracking_detail','citations_by','alert_resolution','enrollment_stats',
    'reports_log','sos_detail','guardian_messages','device_detail',
    'attendance_trend',
];
const NX_LLM_INFORMAL = [
    'greeting','greeting_time','wellbeing','wellbeing_reply','joke','fun_fact',
    'about_nexus','name_meaning','creator','age','thanks','goodbye','yes','no',
    'apology','compliment','insult','bored','love','human_check','do_for_me',
    'emotion_sad','weather','news_sports','food_music','meaning_life',
    'confused','repeat','insult_back','sing','dance','story','motivation',
    'time','date','out_of_scope','colombia_capital','colombia_department',
    'colombia_president','colombia_history','colombia_geography',
    'colombia_culture','colombia_fun_fact','foreign_culture','math_operation',
];

/* ============================================================================
 * LLM #2 — RESPONSE COMPOSER
 * ----------------------------------------------------------------------------
 * Rewrites the deterministic reply (truth verified by NEXO) into natural
 * Spanish. NEVER generates data: it only reformulates `verified_reply`. The
 * cards, rows and numbers are rendered by the pipeline — the model never
 * touches them.
 *
 * Config: NLU_LLM_COMPOSE = off | data | all
 *   off  -> composer disabled (0 quota)
 *   data -> only operational intents + clarify (smalltalk already sounds natural)
 *   all  -> any reply
 * ========================================================================== */
function nxLlmComposeMode(): string {
    // SEC-4: defecto 'off' — mandar verified_reply+facts (contiene datos de
    // minors) to the LLM provider is an explicit decision, not implicit. Whoever
    // active 'data'/'all' accepts the flow documented in DECISIONES.md.
    $m = strtolower((string)(getenv('NLU_LLM_COMPOSE') ?: 'off'));
    return in_array($m, ['off','data','all'], true) ? $m : 'off';
}

function nxLlmComposerPrompt(): string {
    return <<<'PROMPT'
Compositor de respuestas del asistente escolar NEXO. Recibes la pregunta del usuario, verified_reply (verdad absoluta del sistema) y facts (lo que ve en las tablas). Reescribe en español colombiano natural y breve. Devuelve {"reply":"..."}.
REGLAS:
- Conserva TODAS las cifras, nombres y fechas de verified_reply. No agregues ninguna que no esté ahí o en facts.
- facts.rows>0 → NUNCA digas que no hay datos o que no se registró nada.
- Nada de causas ni contexto inventado ("el día apenas empieza", "falló la red", "aún no").
- Ni preguntas ni ofertas, salvo si facts.offer existe: cierra preguntando exactamente eso.
- Sin juicios de valor ("excelente","buena noticia","todo en orden") ni tratamientos ("profe"). Sin jerga técnica; nombra el período como dijo el usuario.
- 1–3 frases. Si verified_reply ya es natural, devuélvelo casi igual. Solo el JSON.
PROMPT;
}

/** Facts visible to the composer: what the user sees in the card. */
function nxLlmComposeFacts(array $out): array {
    $facts = ['rows' => 0];
    foreach (($out['cards'] ?? []) ?: [] as $i => $card) {
        $n = count($card['rows'] ?? []);
        $facts['rows'] += $n;
        if ($i === 0 && $n) {
            $cols = array_slice((array)($card['columns'] ?? []), 0, 8);
            $facts['table'] = [
                'title'   => (string)($card['title'] ?? ''),
                'columns' => $cols,
                // SEC-4: minors data never leaves the perimeter — each
                // cell is classified by its header; PII or unknown header
                // -> '·'. Numbers/figures pass (the guard needs them).
                'first_rows' => array_map(
                    fn($r) => array_map(
                        fn($c, $j) => nxComposeCellSafe((string)$c, (string)($cols[$j] ?? '')),
                        array_slice((array)$r, 0, 8), array_keys(array_slice((array)$r, 0, 8))),
                    array_slice((array)$card['rows'], 0, 4)),
            ];
        }
    }
    if (!empty($out['_offer']['label'])) $facts['offer'] = (string)$out['_offer']['label'];
    if (!empty($out['denied'])) $facts['status'] = 'denied';
    return $facts;
}

/**
 * Post-generation guard: the composer may NOT contradict or inflate the
 * verified truth. Rejects (-> original reply) if:
 *   · a figure absent from verified_reply/facts/question appears,
 *   · it denies data when the table has rows,
 *   · it asks/offers something with no real offer,
 *   · it inserts value judgments or invented causes.
 */
function nxLlmComposeGuard(string $new, string $verified, array $facts, string $userText): bool {
    $norm = fn($t) => function_exists('nxNorm') ? nxNorm($t) : mb_strtolower($t);
    $hay = $norm($verified . ' ' . json_encode($facts, JSON_UNESCAPED_UNICODE) . ' ' . $userText);
    preg_match_all('/\d+(?:[.,]\d+)?/u', $new, $nums);
    preg_match_all('/\d+(?:[.,]\d+)?/u', $hay, $known);
    $knownSet = array_flip(array_map(fn($x) => str_replace(',', '.', $x), $known[0]));
    foreach ($nums[0] as $n) {
        $n2 = str_replace(',', '.', $n);
        if (!isset($knownSet[$n2]) && !isset($knownSet[rtrim(rtrim($n2, '0'), '.')])) return false;
    }
    $nn = $norm($new); $nv = $norm($verified);
    $denial = '/\b(no (hay|tengo|cuento|encontr\w*|se (registr|encontr)\w*|existen|aparece\w*)|sin (datos|informacion|registros)|ningun[oa]?|aun no|todavia no)\b/u';
    if (($facts['rows'] ?? 0) > 0 && preg_match($denial, $nn) && !preg_match($denial, $nv)) return false;
    if (empty($facts['offer']) && str_contains($new, '?') && !str_contains($verified, '?')) return false;
    if (preg_match('/\b(buena noticia|excelente|tranquil\w*|todo en orden|todo limpio|profe\b|apenas (empieza|arranca|comienza)|la red|travesur\w*|no se cargo)\b/u', $nn)
        && !preg_match('/\b(buena noticia|excelente|tranquil\w*|todo en orden|todo limpio|profe\b)\b/u', $nv)) return false;
    return true;
}

/**
 * Reformulates $out['reply'] via the composer. Returns the new text or null
 * (disabled / not applicable / LLM down / guard rejected -> the caller
 * keeps the original).
 */
function nxLlmComposeReply(string $userText, array $out): ?string {
    $mode = nxLlmComposeMode();
    if ($mode === 'off' || !nxLlmEnabled()) return null;
    $intent = (string)($out['intent'] ?? '');
    // _natural = "reply already drafted": in smalltalk/repair it saves quota,
    // but in data intents the composer DOES reformulate — the templated
    // answer is exactly what sounds "generic" to the user.
    if (!empty($out['_natural'])
        && !in_array($intent, NX_LLM_FORMAL, true)
        && !str_contains($intent, '.')) return null;
    if ($mode === 'data'
        && !in_array($intent, NX_LLM_FORMAL, true)
        && !in_array($intent, ['clarify','composed_chat','plan_failure','out_of_scope'], true)
        && !str_contains($intent, '.')) return null;
    $reply = trim((string)($out['reply'] ?? ''));
    if ($reply === '' || mb_strlen($reply) > 1500) return null;

    $facts = nxLlmComposeFacts($out);
    $c = nxLlmCfg();
    $d = nxLlmPost([
        'model' => $c['model'],
        'temperature' => 0.2,
        'max_tokens' => 170,
        'response_format' => ['type' => 'json_object'],
        'messages' => [
            ['role' => 'system', 'content' => nxLlmComposerPrompt()],
            ['role' => 'user', 'content' => json_encode([
                'user_text' => mb_substr($userText, 0, 300),
                'verified_reply' => $reply,
                'facts' => $facts,
            ], JSON_UNESCAPED_UNICODE)],
        ],
    ]);
    $j = nxLlmJsonContent($d);
    $new = is_array($j) ? trim((string)($j['reply'] ?? '')) : '';
    if ($new === '') return null;
    if (!nxLlmComposeGuard($new, $reply, $facts, $userText)) { nxLlmLastError('composer_guard'); return null; }
    return mb_substr($new, 0, 2000);
}

/** Prompt version — invalidates the parser cache when it changes. */
function nxLlmPromptVersion(): string {
    static $v = null;
    return $v ??= substr(sha1(nxLlmSystemPrompt() . nxLlmCfg()['model']), 0, 10);
}

function nxLlmSystemPrompt(): string {
    // Compact on purpose (~800 tokens, measured on Groq): the deterministic
    // validator (nxIntentVeto/nxDomainRescue/nxSlots) fixes systematic
    // confusions afterwards, so the prompt only carries the contract and what
    // the model decides best. Keep in sync with NX_LLM_FORMAL U
    // NX_LLM_INFORMAL and the entity allowlist of nxLlmClassify —
    // test/coverage_matrix.php requires every RBAC intent here.
    return <<<'PROMPT'
Clasificas mensajes del personal de un colegio (NEXO) en UN intent y extraes entidades. SOLO JSON {"intent","confidence","safety":"ok|risky","entities":{}}

DATOS: day_summary|attendance_today|late_today|count_present|count_events|list_events|frequency_table=conteo por día/grupo/estudiante|top_offenders=estudiantes con más faltas|attendance_ranking=rankear/comparar GRUPOS o grados|groups_compare=COMPARAR dos grupos nombrados (group+group2)|attendance_trend=mejoró/empeoró/qué día falta más|students_count|group_student_count|students_in_group=nómina de un grupo|student_field=un dato de un estudiante|student_summary=ficha completa|group_summary|groups_list|teachers_list|staff_lookup=funcionario o su jornada/perfil|staff_contact=correo/teléfono|schedule_info|teacher_schedule=horario de UN docente|risk_students|risk_reason=motivo del riesgo|risk_config|trackings=lista|tracking_detail=caso de UN estudiante|count_trackings|permissions|pending_returns|exit_detail=salida de UN estudiante|trip_info=salida pedagógica|citations|citations_by=enviadas por un docente|incident_excuses=excusas/justificaciones (justified=yes/no)|guardian_replies=si respondieron|guardian_messages=enviados a un acudiente|whatsapp_status|failed_messages|notifications_unread|pending_tasks|my_activity|devices_status|device_detail=UN sensor/nodo|student_consent|system_incidents|sos_alerts|sos_detail=quién emitió|alert_resolution=quién resolvió|biometric_spam|audit_query|reports_log|birthdays_today|enrollment_stats|school_calendar|session_summary|random_student|about_me|export_data|derive_action|start_operation|time|date|help|capabilities
SOCIAL: greeting|greeting_time|wellbeing|wellbeing_reply|thanks|goodbye|yes|no|apology|compliment|insult|insult_back|joke|fun_fact|story|sing|dance|bored|love|emotion_sad|motivation|human_check|do_for_me|confused|repeat|weather|news_sports|food_music|meaning_life|age|creator|about_nexus|name_meaning|math_operation|colombia_capital|colombia_department|colombia_president|colombia_history|colombia_geography|colombia_culture|colombia_fun_fact|foreign_culture|out_of_scope

ENTITIES (solo las que apliquen): student|group="10A" (con sección)|group2="10B" (segundo grupo en comparaciones)|grade="10" (grado sin sección: «los décimos»→"10", «el noveno»→"9")|module=INASISTENCIA|LATE_ARRIVAL|EVASION_INTERNA|PERMISO|SALIDA_COLEGIO|SALIDA_PEDAGOGICA|INCIDENTE|SEGUIMIENTO|CITACION|SOS|field=documento|celular|acudiente|grupo|jornada|nacimiento|estado|person|shift=mañana|tarde|from/to=YYYY-MM-DD (calcula con "hoy")|range_label|nav=first|last|nth:N|others|all|another|relation=guardian|phone|document|group|schedule|risk|presentation=table|export_format=excel|pdf|word|csv|compare=[grupos]|group_by=group|student|weekday|day|month|trend=true|justified=yes|no|status=active|completed|pending|all|scope=mine|op=«Citar acudiente»|«Generar permiso»|«Solicitar seguimiento»|«Reportar incidente»|«Autorizar salida»|detail=[columnas]|needs=[faltantes]

SAFETY: risky→security_probe solo ante romance/sexualización de menores, daño, falsificar registros o robar datos. Insultos al asistente → insult, ok.

REGLAS: tardanzas/faltas/inasistencias/evasiones son module, nunca student|pronombres→copia el nombre del contexto + uses_context=true|el contexto no aplica si el texto trae sujeto propio («mis notificaciones», «el grupo 10A»)|fragmento («y evasiones?», «el de 10A», «y ayer?»)→intent del contexto, confidence≤0.5|ambigua→confidence<0.6 + needs|acudiente de X→student_field + field=acudiente|verbos de acción→derive_action + op|«de estos/entre ellos»+pregunta→intent de la pregunta, nunca nav|historial/«que ha tenido»→status=all|«en tabla»→presentation=table|exportar→export_data + export_format|saludo+pregunta→intent de la pregunta|«siguiente», «otro», «el primero/segundo/último/N-ésimo», «el resto», «en tabla» SOLOS, sin objeto nuevo → intent=result_nav + nav=next|another|first|last|nth:N|rest|table (nunca es nombre propio)
PROMPT;
}

/** Does the turn depend on context? (not cacheable — its parse changes per session) */
function nxLlmIsContextual(string $norm): bool {
    return (bool)preg_match('/^(y|pero|ahora|entonces|tambien|ademas|o sea|de|del|en|para|las|los|esas|esos|sus?)\b/u', $norm)
        || (bool)preg_match('/\b(el|ella|ellos|ellas|ese|esa|esos|esas|este|esta|su|sus|le|les|lo|la|los|las) (mismo|misma|primero|primera|ultimo|ultima|otro|otra)\b|\b(su|sus|ese|esa|esos|esas|aquel|aquella|el mismo|la misma)\b/u', $norm);
}

/**
 * POST {NLU_LLM_URL}/chat/completions (OpenAI-compatible) -> array with the
 * same shape nxDialogueResolve expects (intent/confidence/entities/top3),
 * or null if the provider did not respond / returned something invalid.
 */
function nxLlmClassify(string $text, ?array $ctx = null): ?array {
    $c = nxLlmCfg();
    if (!nxLlmEnabled()) return null;
    $norm = function_exists('nxNorm') ? nxNorm($text) : mb_strtolower(trim($text));
    // cache of autonomous parses (no anaphora or names): "how is the
    // school day going" from 20 teachers costs ONE call per day, not twenty
    $cacheKey = null;
    if (!nxLlmIsContextual($norm) && getenv('NX_LLM_NO_CACHE') !== '1') {
        $cacheKey = 'nx:parse:' . nxLlmPromptVersion() . ':' . sha1($norm);
        try {
            $rd = nxLlmRedis();
            $hit = $rd ? $rd->get($cacheKey) : null;
            if (is_string($hit) && $hit !== '') {
                $j = json_decode($hit, true);
                if (is_array($j) && !empty($j['intent'])) return $j + ['source' => 'llm_cache'];
            }
        } catch (Throwable $e) {}
    }
    // COMPACT context (§7.4): last turns + active entities + active
    // set. Long-term memory is held server-side by the DSM; sending 40
    // messages per turn exhausted the 8K tokens/min in two questions.
    $tz = new DateTimeZone('America/Bogota');
    $now = new DateTimeImmutable('now', $tz);
    $dias = [1=>'lunes','martes','miércoles','jueves','viernes','sábado','domingo'];
    $userMsg = ['hoy' => $now->format('Y-m-d') . ' (' . $dias[(int)$now->format('N')] . ')', 'text' => $text];
    if ($ctx) {
        $cx = [];
        $maxTurns = max(2, min(8, (int)(getenv('NLU_LLM_CTX_TURNS') ?: 4)));
        foreach (array_slice($ctx['turns'] ?? [], -$maxTurns) as $t) {
            $cx['turns'][] = ['u' => mb_substr((string)($t['u'] ?? ''), 0, 90),
                              'a' => mb_substr((string)($t['a'] ?? ''), 0, 90)];
        }
        foreach (['student','group','grade','person','module','range_label'] as $k)
            if (!empty($ctx['entities'][$k]) && is_scalar($ctx['entities'][$k])) $cx['entities'][$k] = $ctx['entities'][$k];
        if (!empty($ctx['last_result']))
            $cx['last_result'] = ['type'=>$ctx['last_result']['type'] ?? null,
                'label'=>$ctx['last_result']['label'] ?? null,
                'count'=>$ctx['last_result']['count'] ?? null];
        if ($cx) $userMsg['contexto'] = $cx;
    }
    $d = nxLlmPost([
        'model' => $c['model'],
        'temperature' => 0,
        'max_tokens' => 170,
        'response_format' => ['type' => 'json_object'],
        'messages' => [
            ['role' => 'system', 'content' => nxLlmSystemPrompt()],
            ['role' => 'user', 'content' => json_encode($userMsg, JSON_UNESCAPED_UNICODE)],
        ],
    ], true);
    $j = nxLlmJsonContent($d);
    if (!is_array($j) || empty($j['intent']) || !is_string($j['intent'])) return null;

    $intent = trim($j['intent']);
    $valid = in_array($intent, NX_LLM_FORMAL, true) || in_array($intent, NX_LLM_INFORMAL, true);
    if (!$valid) $intent = 'out_of_scope';
    $conf = max(0.0, min(1.0, (float)($j['confidence'] ?? 0.5)));

    // entities: key allowlist + sanitizing (the LLM is untrusted input)
    static $keys = ['student','group','group2','module','field','days','from','to',
                    'person','grade','shift','search','range_label',
                    'nav','position','relation','presentation','export_format',
                    'compare','topic','target_role','op',
                    'group_by','trend','justified','status','scope','detail','needs'];
    static $enums = [
        'group_by'   => ['group','student','weekday','day','month'],
        'justified'  => ['yes','no'],
        'status'     => ['active','completed','pending','all'],
        'scope'      => ['mine','all'],
        'relation'   => ['guardian','phone','document','group','schedule','risk'],
        'presentation'=>['table','summary'],
        'export_format'=>['excel','pdf','word','csv'],
    ];
    $ent = [];
    foreach ((array)($j['entities'] ?? []) as $k => $v) {
        if (!in_array($k, $keys, true) || $v === null || $v === '') continue;
        if ($k === 'days') { $ent[$k] = max(0, (int)$v); continue; }
        if ($k === 'position') { $ent[$k] = ($v === 'last') ? 'last' : max(1, (int)$v); continue; }
        if ($k === 'trend') { $ent[$k] = (bool)$v; continue; }
        if (($k === 'compare' || $k === 'detail' || $k === 'needs') && is_array($v)) {
            $ent[$k] = array_slice(array_map(fn($x)=>mb_substr(trim((string)$x),0,60), $v), 0, 6);
            continue;
        }
        $v = mb_substr(trim((string)$v), 0, 120);
        // closed enums: value outside the domain -> discarded, not invented
        if (isset($enums[$k]) && !in_array(strtolower($v), $enums[$k], true)) continue;
        // dates: strict ISO, never future or older than 3 years — a
        // model that does not know what day it is cannot move the range to 2024
        if ($k === 'from' || $k === 'to') {
            $dt = DateTimeImmutable::createFromFormat('!Y-m-d', $v, new DateTimeZone('America/Bogota'));
            $today = new DateTimeImmutable('today', new DateTimeZone('America/Bogota'));
            if (!$dt || $dt->format('Y-m-d') !== $v || $dt > $today || $dt < $today->modify('-3 years')) continue;
        }
        // group can never be a scope literal ("ALL", "mine", "all")
        if ($k === 'group' && preg_match('/^(all|todos|todas|mis|ninguno|ninguna|cada)$/iu', $v)) continue;
        // student/person: the LLM sometimes pastes domain vocabulary as
        // a name ("student:'arrivals'", "you take ... dates"). Trailing
        // stopwords are trimmed and it is discarded if no real name remains.
        if (($k === 'student' || $k === 'person') && function_exists('nxStudentStopwords')) {
            $w = array_values(array_filter(explode(' ', nxNorm($v))));
            $stop = nxStudentStopwords();
            while ($w && in_array(end($w), $stop, true)) array_pop($w);
            while ($w && in_array($w[0], $stop, true)) array_shift($w);
            if (!$w) continue;
            $v = implode(' ', $w);
        }
        $ent[$k] = $v;
    }
    if (!empty($j['uses_context'])) $ent['_uses_context'] = true;
    $safety = (isset($j['safety']) && $j['safety'] === 'risky') ? 'risky' : 'ok';
    $res = [
        'domain' => in_array($intent, NX_LLM_FORMAL, true) ? 'formal' : 'informal',
        'intent' => $intent,
        'confidence' => round($conf, 4),
        'top3' => [],
        'entities' => $ent,
        'safety' => $safety,
        'source' => 'llm',
    ];
    // only autonomous, safe parses and no absolute dates/names
    // (relative ranges are recomputed by nxSlots every day)
    if ($cacheKey && $conf >= 0.8 && $safety === 'ok' && empty($ent['_uses_context'])
        && empty($ent['student']) && empty($ent['person']) && empty($ent['from']) && empty($ent['to'])) {
        try { $rd = nxLlmRedis(); if ($rd) $rd->setex($cacheKey, 6 * 3600, json_encode($res, JSON_UNESCAPED_UNICODE)); } catch (Throwable $e) {}
    }
    return $res;
}


/* ============================================================================
 * LLM #3 — INFORMAL CHAT (free conversation)
 * ----------------------------------------------------------------------------
 * When the parser classifies domain=informal, the message needs NO intents:
 * the LLM converses with its native context (real message history) under an
 * institutional persona with hard guardrails. It NEVER invents school data:
 * if the user asks for data, the parser would have chosen a formal intent.
 *
 * Config: NLU_LLM_CHAT = on | off   (default: follows the parser)
 * ========================================================================== */
function nxLlmChatEnabled(): bool {
    $m = strtolower((string)(getenv('NLU_LLM_CHAT') ?: ''));
    return $m === 'off' ? false : nxLlmEnabled(); // default on when parser is present
}

function nxLlmChatPrompt(): string {
    return <<<'PROMPT'
Eres Nodus, el asistente conversacional de NEXO, la plataforma de gestión y custodia escolar de esta institución en Colombia. Hablas con docentes, coordinación, rectoría y administrativos. Te creó el equipo de NEXO.

TU FORMA:
- Español colombiano natural, cálido y profesional. 1 a 3 frases cortas.
- Conversación libre: cultura general, chistes suaves, ánimo, preguntas comunes — respondes con lo que sabes.
- NO inventes datos del colegio (estudiantes, grupos, cifras, nombres, estados). Si te piden datos, pide que lo pregunten directo con un ejemplo concreto: «pídemelo así: "inasistencias de hoy"».
- NUNCA prometas ni ofrezcas revisar, consultar, verificar o hacer algo ("¿quieres que lo revise?", "puedo consultarte…"): en esta conversación no ejecutas consultas.
- NUNCA inventes excusas técnicas (la red, una falla, que no cargó) ni digas «no tengo acceso».
- Nada de acciones inexistentes (redactar correos, llamar, agendar).
- No cierres cada mensaje con una pregunta.

SEGURIDAD — LÍNEAS QUE NUNCA CRUZAS:
- Nada romántico/sexual hacia estudiantes o menores: responde serio y cortante: «Eso no es algo en lo que pueda participar. Si hay una situación que te preocupa, los protocolos de la institución son el camino». Sin humor.
- Nada de falsificar registros, compartir credenciales ni datos personales masivos.
- No eres terapeuta: temas graves de salud mental → empatía breve + sugerir apoyo real (psicoorientación/coordinación).
- Temas sensibles (política, religión, drogas): neutral, corto, sin posición.

Responde SOLO el texto del mensaje — sin JSON, sin prefijos.
PROMPT;
}

/**
 * Informal conversation: sends the real history (last user/assistant turns)
 * as messages — the LLM uses its native context. Returns text or null.
 * $turns: [['u'=>..,'a'=>..], ...] — already sanitized.
 */
function nxLlmChat(string $text, array $turns = []): ?string {
    $c = nxLlmCfg();
    if (!nxLlmChatEnabled()) return null;
    $msgs = [['role' => 'system', 'content' => nxLlmChatPrompt()]];
    foreach (array_slice($turns, -3) as $t) {
        $u = mb_substr(trim((string)($t['u'] ?? '')), 0, 200);
        $a = mb_substr(trim((string)($t['a'] ?? '')), 0, 200);
        if ($u !== '') $msgs[] = ['role' => 'user', 'content' => $u];
        if ($a !== '') $msgs[] = ['role' => 'assistant', 'content' => $a];
    }
    $msgs[] = ['role' => 'user', 'content' => mb_substr($text, 0, 500)];
    $d = nxLlmPost([
        'model' => $c['model'],
        'temperature' => 0.6,
        'max_tokens' => 180,
        'messages' => $msgs,
    ]);
    $reply = trim((string)($d['choices'][0]['message']['content'] ?? ''));
    $reply = trim(preg_replace('/^.*?<\/think>/s', '', $reply));
    // the persona is non-negotiable: no offering queries or technical excuses
    $n = function_exists('nxNorm') ? nxNorm($reply) : mb_strtolower($reply);
    if (preg_match('/\b(quieres que (lo |la |te )?(revise|consulte|verifique|busque)|puedo (consultar|revisar|verificar)te|la red|no se cargo|travesur\w*|no tengo acceso)\b/u', $n))
        return null;
    return $reply === '' ? null : mb_substr($reply, 0, 1200);
}

/** SEC-4: safe cell for facts -> provider. PII by header -> '·'; figures pass. */
function nxComposeCellSafe(string $v, string $col): string {
    $norm = function_exists('nxNorm') ? 'nxNorm' : 'mb_strtolower';
    static $pii = '/nombre|estudiant|alumn|document|doc\b|acudient|padre|madre|apoderad|tutor|'
        . 'tel|celular|phone|email|correo|direcci|apellid|fecha_nac|nacimiento|edad|'
        . 'huella|foto|identific|grupo|curso|salon|profesor|docente|hora|ingreso|salida/u';
    if ($col === '' || preg_match($pii, $norm($col))) {
        // PII column or no header -> always masked, no exception
        // numeric (a document is also digits)
        return '·';
    }
    return mb_substr($v, 0, 40);
}


