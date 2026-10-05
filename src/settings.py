"""What the application remembers between sessions: the language and the
names of the wave and weight columns last chosen in the settings tab."""

import json
import os


def _path():
    base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'SurveyTabulator', 'settings.json')


def load():
    try:
        with open(_path(), encoding='utf-8') as f:
            stored = json.load(f)
    except (OSError, ValueError):
        return {}
    return stored if isinstance(stored, dict) else {}


def update(**values):
    stored = load()
    stored.update(values)
    try:
        path = _path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(stored, f, ensure_ascii=False)
    except OSError:
        pass    # the choice still applies to this session
