"""Run: python test_scheduler.py"""
import os
import tempfile

from scheduler import parse_busy, slot_of, solve

FILES = {
    'room.csv': 'room,capacity,type,building\nR1,50,lecture,B\nL1,50,lab,B\n',
    'all_teachers.csv': 'teacher_id,unavailable_times,max_hours_per_day\n'
                        'T1,"[\'Mon 08:30-19:00\', \'Tue 08:30-19:00\']",0\n',
    'teacher_courses.csv': 'teacher_id,course_code\nT1,A\nT1,B\nT1,F\n',
    'x_in_courses.csv': 'course_code,course_name,credit,lecture_hour,lab_hour,section,enrollment_count,student_group\n'
                        'A,a,3,2,2,1,40,\nB,b,3,2,0,1,40,\nC,c,1,0,2,1,999,\nD,d,3,2,0,1,40,G1\n',
    # G keeps group G1 busy every day except Wed; F (with an explicit end) blocks Wed 9:00-10:30 for T1 and G1.
    'x_out_courses.csv': 'course_code,course_name,credit,lecture_hour,lab_hour,section,day,start,room,end,student_group\n'
                         'F,f,3,3,0,1,Wed,9:00,R1,10:30,G1\n'
                         + ''.join(f'G,g,3,7,0,1,{day},9:00,X,16:00,G1\n' for day in ['Mon', 'Tue', 'Thu', 'Fri']),
}


def overlaps(df, col):
    seen = set()
    for row in df.itertuples():
        for key in row.Teacher.split(',') if col == 'Teacher' else [row.Room]:
            start, end = slot_of(int(row.Start[:2]) + int(row.Start[3:]) / 60), slot_of(int(row.End[:2]) + int(row.End[3:]) / 60)
            for s in range(start, end):
                if (key, row.Day, s) in seen:
                    return True
                seen.add((key, row.Day, s))
    return False


assert parse_busy("['Mon 10:00-11:00']") == {(0, slot_of(10)), (0, slot_of(10.5))}
assert parse_busy('[]') == set()

with tempfile.TemporaryDirectory() as d:
    for name, text in FILES.items():
        with open(os.path.join(d, name), 'w') as f:
            f.write(text)
    result, unscheduled = solve(d, 'compact', time_limit=10)

placed = result[result['Type'] != 'Fixed']
assert set(placed['Course']) == {'A', 'B', 'D'}, result
assert result[result['Course'] == 'F']['End'].tolist() == ['10:30'], 'explicit end column'
d_row = placed[placed['Course'] == 'D'].iloc[0]
assert d_row['Day'] == 'Wed' and d_row['Start'] >= '10:30', 'student group busy'
placed = placed[placed['Course'] != 'D']
assert list(unscheduled['Course']) == ['C'] and 'capacity' in unscheduled['Reason'][0]
assert not placed['Day'].isin(['Mon', 'Tue']).any(), 'teacher busy Mon/Tue'
assert not overlaps(result, 'Room') and not overlaps(result, 'Teacher'), result
assert ((placed['Start'] >= '09:00') & (placed['End'] <= '16:00')).all(), 'compact window'
a = placed[placed['Course'] == 'A'].set_index('Type')
day = {'Wed': 2, 'Thu': 3, 'Fri': 4}
assert (day[a.at['Lec', 'Day']], a.at['Lec', 'End']) <= (day[a.at['Lab', 'Day']], a.at['Lab', 'Start']), 'lecture before lab'
print('ok')
