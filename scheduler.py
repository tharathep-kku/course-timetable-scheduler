"""Course timetable solver (OR-Tools CP-SAT).

Reads every CSV in the data directory:
  room.csv, all_teachers.csv, teacher_courses.csv
  *_in_courses.csv   courses to place
  *_out_courses.csv  courses already fixed by other faculties (block teacher/room time)

Usage: python scheduler.py [--mode compact|flexible] [--data-dir Data/CSV] [--out-dir output] [--time-limit 120]
"""
import argparse
import glob
import math
import os
import re
from collections import defaultdict

import pandas as pd
from ortools.sat.python import cp_model

# ---- Settings ----
DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
SLOT_MIN = 30                 # minutes per slot
DAY_START, DAY_END = 8.5, 19.0  # flexible mode window (hours)
CORE = (9.0, 16.0)            # compact mode window; flexible mode penalizes time outside it
LUNCH = (12.5, 13.0)          # never schedule over lunch
MAX_SESSION_SLOTS = 6         # sessions longer than 3 h are split into parts
SCORE_CORE, SCORE_ELECTIVE = 1000, 100   # reward for placing a core / elective session
PENALTY_OUT_OF_CORE = 1
PENALTY_LAB_BEFORE_LEC = 10

NUM_SLOTS = int((DAY_END - DAY_START) * 60 / SLOT_MIN)
BUSY_RE = re.compile(r'(Mon|Tue|Wed|Thu|Fri)\w*\s+(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})')


def slot_of(hours):
    return round((hours - DAY_START) * 60 / SLOT_MIN)


def time_of(slot):
    minutes = round(DAY_START * 60 + slot * SLOT_MIN)
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def parse_hour(text):
    h, m = re.search(r'(\d{1,2})[:.](\d{2})', str(text)).groups()
    return int(h) + int(m) / 60


def parse_busy(text):
    """Find every 'Mon 10:00-12:00' in text -> {(day_idx, slot)}."""
    busy = set()
    for day, h1, m1, h2, m2 in BUSY_RE.findall(str(text)):
        start, end = slot_of(int(h1) + int(m1) / 60), slot_of(int(h2) + int(m2) / 60)
        busy |= {(DAYS.index(day), s) for s in range(start, end)}
    return busy


def parse_groups(value):
    """'AI_Y1;CY_Y1' -> ['group:AI_Y1', 'group:CY_Y1']; groups share busy/conflict tracking with teachers."""
    return ['group:' + g.strip() for g in str(value).split(';') if g.strip()] if pd.notna(value) else []


def read_csv(path):
    df = pd.read_csv(path, skipinitialspace=True)
    df.columns = df.columns.str.strip()
    return df


def read_all(data_dir, pattern):
    files = sorted(glob.glob(os.path.join(data_dir, pattern)))
    return pd.concat([read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()


def load(data_dir):
    rooms = read_csv(os.path.join(data_dir, 'room.csv'))
    rooms['room'] = rooms['room'].astype(str).str.strip()
    rooms['type'] = rooms['type'].str.strip().str.lower()

    tc = read_csv(os.path.join(data_dir, 'teacher_courses.csv')).astype(str)
    teachers_of = tc.groupby(tc['course_code'].str.strip())['teacher_id'].apply(lambda s: sorted(set(s.str.strip()))).to_dict()

    busy_of = defaultdict(set)
    max_slots_per_day = {}
    for row in read_csv(os.path.join(data_dir, 'all_teachers.csv')).to_dict('records'):
        tid = str(row['teacher_id']).strip()
        busy_of[tid] |= parse_busy(row.get('unavailable_times', ''))
        if row.get('max_hours_per_day', 0) > 0:
            max_slots_per_day[tid] = int(row['max_hours_per_day'] * 60 / SLOT_MIN)

    courses = read_all(data_dir, '*_in_courses.csv')
    for col in ('optional', 'require_lab_ai', 'require_lab_network', 'lec_online', 'lab_online'):
        courses[col] = courses[col].fillna(0) if col in courses else 0
    courses['course_code'] = courses['course_code'].astype(str).str.strip()

    fixed = read_all(data_dir, '*_out_courses.csv').drop_duplicates()
    return rooms, teachers_of, busy_of, max_slots_per_day, courses, fixed


def build_tasks(courses, teachers_of):
    tasks = []
    for row in courses.to_dict('records'):
        code, sec = row['course_code'], int(row['section'])
        lab_types = {t for t, col in (('lab ai', 'require_lab_ai'), ('lab network', 'require_lab_network')) if row[col] == 1}
        for kind, hours_col, online_col in (('Lec', 'lecture_hour', 'lec_online'), ('Lab', 'lab_hour', 'lab_online')):
            left, part = math.ceil(row[hours_col] * 60 / SLOT_MIN), 1
            while left > 0:
                dur = min(left, MAX_SESSION_SLOTS)
                tasks.append({
                    'uid': f'{code}_S{sec}_{kind}_P{part}', 'course': code, 'sec': sec, 'type': kind, 'dur': dur,
                    'std': row['enrollment_count'], 'teachers': teachers_of.get(code, []),
                    'groups': parse_groups(row.get('student_group')),
                    'online': row[online_col] == 1, 'core': row['optional'] == 0,
                    'lab_types': lab_types if kind == 'Lab' else set(),
                })
                left -= dur
                part += 1
    return tasks


def fixed_meetings(fixed, teachers_of):
    """Each out-course row is one meeting, ending at its `end` column if given;
    otherwise a section's hours are split evenly across its meetings."""
    meetings = []
    if fixed.empty:
        return meetings
    count = fixed.groupby(['course_code', 'section'])['day'].transform('size')
    for row, n in zip(fixed.to_dict('records'), count):
        code = str(row['course_code']).strip()
        start = slot_of(parse_hour(row['start']))
        if pd.notna(row.get('end')):
            dur = slot_of(parse_hour(row['end'])) - start
        else:
            dur = math.ceil((row['lecture_hour'] + row['lab_hour']) * 60 / SLOT_MIN / n)
        meetings.append({'course': code, 'sec': row['section'], 'day': DAYS.index(str(row['day']).strip()[:3]),
                         'start': start, 'dur': dur, 'room': str(row['room']).strip(),
                         'teachers': teachers_of.get(code, []), 'groups': parse_groups(row.get('student_group'))})
    return meetings


def solve(data_dir, mode='flexible', time_limit=120, workers=0):
    """Return (scheduled, unscheduled) DataFrames. workers=0 uses every CPU core (~150 MB RAM per worker)."""
    rooms, teachers_of, busy_of, max_slots_per_day, courses, fixed = load(data_dir)
    tasks = build_tasks(courses, teachers_of)
    meetings = fixed_meetings(fixed, teachers_of)

    room_names = set(rooms['room'])
    room_busy = set()
    for m in meetings:
        span = range(m['start'], m['start'] + m['dur'])
        for who in m['teachers'] + m['groups']:
            busy_of[who] |= {(m['day'], s) for s in span}
        if m['room'] in room_names:
            room_busy |= {(m['room'], m['day'], s) for s in span}

    first, last = (slot_of(CORE[0]), slot_of(CORE[1])) if mode == 'compact' else (0, NUM_SLOTS)
    core_first, core_last = slot_of(CORE[0]), slot_of(CORE[1])
    lunch = set(range(slot_of(LUNCH[0]), slot_of(LUNCH[1])))

    model = cp_model.CpModel()
    placements = {}  # var -> (task, day, start, room)
    room_use, person_use, teacher_day = defaultdict(list), defaultdict(list), defaultdict(list)
    scheduled, start_abs, reasons = {}, {}, {}
    objective = []

    for t in tasks:
        if t['online']:
            candidate_rooms = ['Online']
        else:
            ok = rooms[rooms['capacity'] >= t['std']]
            if t['type'] == 'Lab':
                ok = ok[ok['type'].isin(t['lab_types'])] if t['lab_types'] else ok[ok['type'].str.contains('lab')]
            candidate_rooms = list(ok['room'])
        busy = set().union(*(busy_of[x] for x in t['teachers'] + t['groups']))

        cands = []
        for d in range(len(DAYS)):
            for s in range(first, last - t['dur'] + 1):
                span = range(s, s + t['dur'])
                if lunch.intersection(span) or any((d, x) in busy for x in span):
                    continue
                for r in candidate_rooms:
                    if any((r, d, x) in room_busy for x in span):
                        continue
                    v = model.NewBoolVar(f"{t['uid']}_{r}_{d}_{s}")
                    cands.append(v)
                    placements[v] = (t, d, s, r)
                    for x in span:
                        if r != 'Online':
                            room_use[(r, d, x)].append(v)
                        for who in t['teachers'] + t['groups']:
                            person_use[(who, d, x)].append(v)
                    for tea in t['teachers']:
                        teacher_day[(tea, d)].append(v * t['dur'])
                    if s < core_first or s + t['dur'] > core_last:
                        objective.append(-PENALTY_OUT_OF_CORE * v)

        if not candidate_rooms:
            reasons[t['uid']] = 'No room with enough capacity / right type'
        elif not cands:
            reasons[t['uid']] = 'No free time slot (window, lunch, teacher/group busy)'
        else:
            reasons[t['uid']] = 'Did not fit (room/teacher/group conflicts)'

        b = model.NewBoolVar(f"sched_{t['uid']}")
        model.Add(sum(cands) == b)
        scheduled[t['uid']] = b
        start_abs[t['uid']] = sum(v * (d * NUM_SLOTS + s) for v in cands for _, d, s, _ in [placements[v]])
        objective.append((SCORE_CORE if t['core'] else SCORE_ELECTIVE) * b)

    for group in list(room_use.values()) + list(person_use.values()):
        model.AddAtMostOne(group)
    for (tea, d), load_terms in teacher_day.items():
        if tea in max_slots_per_day:
            model.Add(sum(load_terms) <= max_slots_per_day[tea])

    # Soft: every lecture part of a section should end before its lab starts.
    by_section = defaultdict(lambda: {'Lec': [], 'Lab': []})
    for t in tasks:
        by_section[(t['course'], t['sec'])][t['type']].append(t)
    for parts in by_section.values():
        for lec in parts['Lec']:
            for lab in parts['Lab']:
                late = model.NewBoolVar('')
                model.Add(start_abs[lec['uid']] + lec['dur'] <= start_abs[lab['uid']]).OnlyEnforceIf(
                    [scheduled[lec['uid']], scheduled[lab['uid']], late.Not()])
                objective.append(-PENALTY_LAB_BEFORE_LEC * late)

    model.Maximize(sum(objective))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f'Solver found no solution: {solver.StatusName(status)}')

    rows = [{'Day': DAYS[m['day']], 'Start': time_of(m['start']), 'End': time_of(m['start'] + m['dur']),
             'Room': m['room'], 'Course': m['course'], 'Sec': m['sec'], 'Type': 'Fixed',
             'Teacher': ','.join(m['teachers']), 'Note': 'Fixed'} for m in meetings]
    for v, (t, d, s, r) in placements.items():
        if solver.Value(v):
            notes = ['Online'] if t['online'] else []
            if s < core_first or s + t['dur'] > core_last:
                notes.append('Ext.Time')
            rows.append({'Day': DAYS[d], 'Start': time_of(s), 'End': time_of(s + t['dur']), 'Room': r,
                         'Course': t['course'], 'Sec': t['sec'], 'Type': t['type'],
                         'Teacher': ','.join(t['teachers']), 'Note': ', '.join(notes)})
    result = pd.DataFrame(rows, columns=['Day', 'Start', 'End', 'Room', 'Course', 'Sec', 'Type', 'Teacher', 'Note'])
    result = result.sort_values(['Day', 'Start', 'Room'], key=lambda c: c.map(DAYS.index) if c.name == 'Day' else c)

    unscheduled = pd.DataFrame(
        [{'Course': t['course'], 'Sec': t['sec'], 'Type': t['type'], 'Hours': t['dur'] * SLOT_MIN / 60,
          'Teachers': ','.join(t['teachers']), 'Reason': reasons[t['uid']]}
         for t in tasks if not solver.Value(scheduled[t['uid']])],
        columns=['Course', 'Sec', 'Type', 'Hours', 'Teachers', 'Reason'])
    return result, unscheduled


def main():
    p = argparse.ArgumentParser(description='Generate a course timetable with OR-Tools CP-SAT.')
    p.add_argument('--mode', choices=['compact', 'flexible'], default='flexible',
                   help=f'compact = {CORE[0]:g}-{CORE[1]:g} only; flexible = {DAY_START:g}-{DAY_END:g} with penalty outside core hours')
    p.add_argument('--data-dir', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data', 'CSV'))
    p.add_argument('--out-dir', default='output')
    p.add_argument('--time-limit', type=float, default=120, help='solver time limit in seconds')
    args = p.parse_args()

    result, unscheduled = solve(args.data_dir, args.mode, args.time_limit)
    os.makedirs(args.out_dir, exist_ok=True)
    schedule_path = os.path.join(args.out_dir, f'schedule_{args.mode}.csv')
    unscheduled_path = os.path.join(args.out_dir, f'unscheduled_{args.mode}.csv')
    result.to_csv(schedule_path, index=False, encoding='utf-8-sig')
    unscheduled.to_csv(unscheduled_path, index=False, encoding='utf-8-sig')

    print(f'Scheduled {len(result)} sessions -> {schedule_path}')
    if not unscheduled.empty:
        print(f'Unscheduled {len(unscheduled)} sessions -> {unscheduled_path}')
        print(unscheduled.to_string(index=False))


if __name__ == '__main__':
    main()
