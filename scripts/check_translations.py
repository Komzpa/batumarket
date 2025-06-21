import subprocess
import sys
from pathlib import Path

LOCALE_DIR = Path('locale')
LANGS = ['en', 'ru', 'ka']


def parse_po(path: Path) -> dict[str, str]:
    msgs = {}
    state = None
    msgid = ''
    msgstr = ''
    with path.open(encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if line.startswith('msgid '):
                if state == 'msgstr':
                    msgs[msgid] = msgstr
                msgid = line[6:].strip().strip('"')
                msgstr = ''
                state = 'msgid'
            elif line.startswith('msgstr '):
                state = 'msgstr'
                msgstr = line[7:].strip().strip('"')
            elif line.startswith('"'):
                text = line.strip().strip('"')
                if state == 'msgid':
                    msgid += text
                elif state == 'msgstr':
                    msgstr += text
            elif not line.strip():
                if state == 'msgstr':
                    msgs[msgid] = msgstr
                state = None
                msgid = ''
                msgstr = ''
    if state == 'msgstr':
        msgs[msgid] = msgstr
    return msgs


def check_translations() -> int:
    base = LOCALE_DIR / 'en' / 'LC_MESSAGES' / 'messages.po'
    base_msgs = parse_po(base)
    success = True
    for lang in LANGS:
        po = LOCALE_DIR / lang / 'LC_MESSAGES' / 'messages.po'
        if not po.exists():
            print(f'Missing {po}', file=sys.stderr)
            success = False
            continue
        msgs = parse_po(po)
        for msgid in base_msgs:
            if msgid not in msgs or not msgs[msgid].strip():
                print(f'Missing translation for {msgid} in {lang}', file=sys.stderr)
                success = False
        # compile
        mo = po.with_suffix('.mo')
        try:
            subprocess.run(['msgfmt', str(po), '-o', str(mo)], check=True)
        except Exception:
            print(f'Failed to compile {po}', file=sys.stderr)
            success = False
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(check_translations())
