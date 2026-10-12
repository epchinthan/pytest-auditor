"""Shared report categories, grouped by the purpose of each check."""

GROUPS = {
    'Assertions & verification': 'T001 T002 T004 T019 T020 T021 T029 T030 T033 T034 T040',
    'Parametrization': 'T003 T008 T009 T010 T024 T028 T037 T038 T039',
    'Fixtures': 'T006 T036 T043 N004',
    'Async tests': 'T007 T022 T023',
    'Exceptions & warnings': 'T013 T018 T025 T026 T027 T031 T044 T045 T046 T047',
    'Debugging & maintainability': 'T012 T017 T032 N008',
    'Marks & skipped tests': 'T014 T015 T041 T042 S004',
    'Naming & test discovery': 'T016 T035 N001 N002 N003 N005 N006 N007',
    'Isolation & side effects': 'T005',
    'File parsing': 'F001 F002',
    'Security': 'F003',
    'Analysis notes': 'INFO',
}
CATEGORIES = {code: category for category, codes in GROUPS.items() for code in codes.split()}
PREFIX_CATEGORIES = {
    'FX': 'Fixtures', 'MK': 'Mocking', 'PW': 'Browser reliability',
    'SA': 'Isolation & side effects', 'OR': 'Suite organization',
    'S': 'Suite organization', 'M': 'Marks & skipped tests',
}


def category_for(code):
    if code in CATEGORIES:
        return CATEGORIES[code]
    for prefix, category in PREFIX_CATEGORIES.items():
        if code.startswith(prefix) and code[len(prefix):].isdigit():
            return category
    return 'Other findings'
