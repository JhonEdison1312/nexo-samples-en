#!/usr/bin/env python3
"""
ADDED FOR THIS SAMPLE
Spanish-language detector for the public tree.

Scans every tracked text file (src extracts, harness glue, EXPECTED_OUTPUT,
docs) for Spanish markers: accented characters and common Spanish words.
Allowlisted functional text is declared in tools/lang_allowlist.txt with a
reason per entry; anything else is a failure.

Usage: python3 tools/lang_check.py [--json]
Exit 0 = clean, 1 = violations found.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = REPO / 'tools' / 'lang_allowlist.txt'

ACCENT_RE = re.compile(r'[áéíóúÁÉÍÓÚñÑ¿¡]')
# Conservative list: words that are unambiguously Spanish and essentially never
# appear as standalone English words or common identifiers. A line needs an
# accent OR at least two distinct hits to be flagged, which keeps English
# prose and code identifiers from false-positiving.
SPANISH_WORDS = [
    'el', 'la', 'los', 'las', 'una', 'del', 'para', 'con', 'sin', 'sobre',
    'entre', 'desde', 'hasta', 'cuando', 'donde', 'porque', 'pero', 'como',
    'más', 'está', 'están', 'estan', 'fue', 'era', 'esto', 'esta', 'estos',
    'estas', 'ese', 'esa', 'hay', 'tiene', 'tienen', 'debe', 'deben', 'puede',
    'pueden', 'hacer', 'hace', 'cada', 'todo', 'toda', 'todos', 'todas',
    'otro', 'otra', 'otros', 'mismo', 'misma', 'también', 'tambien', 'después',
    'despues', 'antes', 'ahora', 'siempre', 'nunca', 'aquí', 'aqui', 'allí',
    'alli', 'entonces', 'así', 'asi', 'bien', 'según', 'segun', 'hacia',
    'mediante', 'luego', 'incluso', 'además', 'ademas', 'es', 'son', 'ser',
    'estoy', 'estamos', 'están', 'muy', 'ya', 'aún', 'aun', 'ni', 'tampoco',
    'aunque', 'mientras', 'durante', 'así', 'vez', 'veces', 'forma', 'parte',
    'ejemplo', 'nombre', 'fecha', 'hora', 'día', 'dias', 'días', 'mes',
    'año', 'anos', 'años', 'persona', 'personas', 'cosa', 'cosas', 'manera',
    'tipo', 'tipos', 'caso', 'casos', 'punto', 'puntos', 'lado', 'lado',
    'gracias', 'hola', 'adiós', 'adios', 'por', 'favor', 'vale', 'bueno',
    'malo', 'nuevo', 'nueva', 'viejo', 'vieja', 'primero', 'primera', 'último',
    'ultima', 'última', 'siguiente', 'anterior', 'actual', 'posible',
    'imposible', 'necesario', 'necesaria', 'importante', 'público', 'publica',
    'privado', 'privada', 'general', 'especial', 'normal', 'común', 'comun',
    'diferente', 'igual', 'semejante', 'contrario', 'respecto', 'acerca',
    'alrededor', 'dentro', 'fuera', 'encima', 'debajo', 'delante', 'detrás',
    'cerca', 'lejos', 'junto', 'juntos', 'separado', 'unido', 'libre',
    'ocupado', 'vacío', 'vacio', 'lleno', 'vacía', 'llena', 'abierto',
    'cerrado', 'alto', 'bajo', 'grande', 'pequeño', 'pequeno', 'largo',
    'corto', 'ancho', 'estrecho', 'fácil', 'facil', 'difícil', 'dificil',
    'simple', 'complicado', 'claro', 'oscuro', 'blanco', 'negro', 'rojo',
    'azul', 'verde', 'amarillo', 'grupos', 'estudiantes', 'asistencia',
    'grupo', 'alumno', 'alumnos', 'colegio', 'docente', 'docentes',
    'acudiente', 'acudientes', 'registra', 'presentes', 'ausencias',
    'encontraron', 'encontrar', 'registros', 'registro', 'pertenece',
    'pertenecen', 'usuario', 'usuarios', 'encontrado', 'inactivo',
    'restringido', 'configurada', 'configurado', 'partición', 'particiones',
    'eliminadas', 'eliminados', 'retención', 'fallo', 'falló', 'creada',
    'creado', 'existe', 'meses', 'dedos', 'dedo', 'huella', 'huellas',
    'evaluar', 'eliminar', 'decisión', 'decision', 'arquitectura', 'mantiene',
    'fuente', 'normalizada', 'normalizado', 'compat', 'hasta', 'desde',
    'según', 'mediante', 'no', 'sí', 'si', 'se', 'su', 'sus', 'lo', 'le',
    'les', 'me', 'te', 'nos', 'os', 'mi', 'mis', 'tu', 'tus', 'usted',
    'ustedes', 'ellos', 'ellas', 'nosotros', 'vosotros', 'esto', 'eso',
    'aquello', 'aquel', 'aquella', 'cuyo', 'cuya', 'dicho', 'dicha',
]
WORD_RE = re.compile(
    r'\b(' + '|'.join(sorted(set(SPANISH_WORDS), key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)
MIN_WORD_HITS = 2

# File types to scan (text only)
SCAN_SUFFIXES = {
    '.php', '.sql', '.cpp', '.h', '.hpp', '.c', '.cc', '.sh', '.bash',
    '.py', '.md', '.txt', '.yml', '.yaml', '.json', '.xml', '.conf',
    '.ini', '.example', '.env', '.tpl', '.dist', '.service',
}
SCAN_NAMES = {'Makefile', 'Dockerfile', 'LICENSE', 'README', 'EXPECTED_OUTPUT.txt',
              'PROVENANCE.md', 'SECURITY.md', 'VERIFICATION.md'}
# PROVENANCE.json is excluded: it quotes ORIGIN source text verbatim (including
# Spanish comments/identifiers) by design — that is the provenance record itself.
SCAN_EXCLUDE = {'PROVENANCE.json', 'docs/SUBSTITUTIONS.md', 'tools/lang_allowlist.txt'}

# Allowlist entries: (path_glob, regex_or_literal, reason)
def load_allowlist():
    entries = []
    if not ALLOWLIST_FILE.exists():
        return entries
    for raw in ALLOWLIST_FILE.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3:
            entries.append((parts[0], parts[1], '|'.join(parts[2:])))
    return entries


def iter_files():
    files = subprocess.run(
        ['git', 'ls-files'], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    for rel in files:
        if rel in SCAN_EXCLUDE:
            continue
        p = REPO / rel
        if not p.is_file():
            continue
        if p.suffix in SCAN_SUFFIXES or p.name in SCAN_NAMES or '.' not in p.name:
            try:
                p.read_text(encoding='utf-8')
            except (UnicodeDecodeError, ValueError):
                continue  # binary
            yield rel, p


def line_hits(text):
    """Yield (lineno, line, kind) for Spanish markers.

    A line is flagged when it has an accented character or at least
    MIN_WORD_HITS distinct conservative Spanish words.
    """
    for i, line in enumerate(text.split('\n'), 1):
        if ACCENT_RE.search(line):
            yield i, line, 'accent'
            continue
        hits = {m.group(0).lower() for m in WORD_RE.finditer(line)}
        if len(hits) >= MIN_WORD_HITS:
            yield i, line, 'words:' + ','.join(sorted(hits))


def main():
    as_json = '--json' in sys.argv
    allowlist = load_allowlist()
    violations = []
    allowed_hits = []

    for rel, p in iter_files():
        text = p.read_text(encoding='utf-8')
        for lineno, line, kind in line_hits(text):
            entry = next((e for e in allowlist
                          if rel == e[0] or (e[0].endswith('/') and rel.startswith(e[0]))), None)
            if entry:
                # allowlisted: '*' covers the whole file; otherwise the
                # marker pattern must appear in the line (accent hits are
                # covered by any entry for the file)
                if entry[1] == '*' or entry[1] in line or kind.startswith('accent'):
                    allowed_hits.append((rel, lineno, kind))
                    continue
            violations.append((rel, lineno, kind, line.strip()[:120]))

    if as_json:
        print(json.dumps({'violations': violations,
                          'allowed': allowed_hits}, indent=2, ensure_ascii=False))
    else:
        print(f"Scanned {sum(1 for _ in iter_files())} files; "
              f"allowlist entries: {len(allowlist)}")
        if allowed_hits:
            print(f"Allowlisted hits: {len(allowed_hits)}")
        if violations:
            print(f"\nVIOLATIONS ({len(violations)}):")
            for rel, lineno, kind, line in violations[:80]:
                print(f"  {rel}:{lineno} [{kind}] {line}")
            if len(violations) > 80:
                print(f"  ... and {len(violations) - 80} more")
            print("\nLANG CHECK: FAIL")
            return 1
        print("\nLANG CHECK: PASS")
        return 0


if __name__ == '__main__':
    sys.exit(main())
