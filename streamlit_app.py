"""Web UI for scheduler.py. Run: streamlit run streamlit_app.py"""
import fnmatch
import io
import os
import tempfile
import zipfile

import pandas as pd
import streamlit as st

from scheduler import read_csv, solve

DEFAULT_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data', 'CSV')
WORKERS = 4  # Streamlit Community Cloud has ~2.7 GB RAM; each solver worker uses ~150-250 MB

# file pattern, required, columns that must exist, optional columns, what it is
SPEC = [
    ('room.csv', True, ['room', 'capacity', 'type'], ['building'],
     'ห้องเรียน 1 แถวต่อ 1 ห้อง `type` ต้องเป็น `lecture`, `lab`, `lab ai` หรือ `lab network`'),
    ('all_teachers.csv', True, ['teacher_id'], ['unavailable_times', 'max_hours_per_day'],
     "อาจารย์ 1 แถวต่อ 1 คน `unavailable_times` เช่น `['Mon 10:00-12:00', 'Fri 15:30-18:30']` "
     "ส่วน `max_hours_per_day` ถ้าใส่ 0 หรือเว้นว่าง แปลว่าไม่จำกัด"),
    ('teacher_courses.csv', True, ['teacher_id', 'course_code'], [],
     'อาจารย์ผู้สอนของแต่ละวิชา 1 แถวต่อ 1 คู่ ถ้าวิชาเดียวมีอาจารย์หลายคน ให้ใส่หลายแถว'),
    ('*_in_courses.csv', True, ['course_code', 'lecture_hour', 'lab_hour', 'section', 'enrollment_count'],
     ['course_name', 'credit', 'optional', 'require_lab_ai', 'require_lab_network', 'lec_online', 'lab_online',
      'student_group'],
     'วิชาที่ให้โปรแกรมจัด 1 แถวต่อ 1 section ตั้งชื่อเช่น `ai_in_courses.csv` (มีได้หลายไฟล์) '
     'คอลัมน์ที่เป็น 0/1 ถ้าเว้นว่างจะถือเป็น 0 ส่วน `optional` = 1 หมายถึงวิชาเลือก'),
    ('*_out_courses.csv', False, ['course_code', 'lecture_hour', 'lab_hour', 'section', 'day', 'start', 'room'],
     ['end', 'student_group'],
     'วิชาที่ล็อกวัน เวลา และห้องไว้แล้ว 1 แถวต่อ 1 ครั้งที่เรียน `day` เป็น `Mon`-`Fri` และ `start`/`end` เป็นเวลา เช่น `13:00`'),
]


def spec_of(name):
    return next((s for s in SPEC if fnmatch.fnmatch(name, s[0])), None)


def check(files):
    """files: {name: bytes}. Return a list of problems (empty = OK)."""
    problems = []
    for pattern, required, *_ in SPEC:
        if required and not any(fnmatch.fnmatch(n, pattern) for n in files):
            problems.append(f'ขาดไฟล์ `{pattern}`')
    for name, data in files.items():
        spec = spec_of(name)
        if not spec:
            problems.append(f'`{name}`: ชื่อไฟล์ไม่ตรงกับไฟล์ที่รองรับ ระบบจะไม่อ่านไฟล์นี้')
            continue
        try:
            cols = set(read_csv(io.BytesIO(data)).columns)
        except UnicodeDecodeError:
            problems.append(f'`{name}`: อ่านภาษาไทยไม่ได้ ให้เปิดใน Excel แล้ว Save As เป็น "CSV UTF-8"')
            continue
        except Exception as e:
            problems.append(f'`{name}`: อ่านไฟล์ไม่ได้ ({e})')
            continue
        if missing := [c for c in spec[2] if c not in cols]:
            problems.append(f'`{name}`: ขาดคอลัมน์ ' + ', '.join(f'`{c}`' for c in missing))
    return problems


def sample_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for name in sorted(os.listdir(DEFAULT_DATA)):
            z.write(os.path.join(DEFAULT_DATA, name), name)
    return buf.getvalue()


st.set_page_config(page_title='Schedule Workshop', layout='wide')
st.title('Schedule Workshop')

with st.sidebar:
    source = st.radio('ข้อมูล', ['ข้อมูลตัวอย่าง', 'อัปโหลดไฟล์เอง'])
    uploads = []
    if source == 'อัปโหลดไฟล์เอง':
        uploads = st.file_uploader('ไฟล์ CSV (เลือกได้หลายไฟล์)', type='csv', accept_multiple_files=True)
    mode = st.radio('Mode', ['flexible', 'compact'],
                    help='compact = จัดได้แค่ 09:00-16:00 / flexible = 08:30-19:00 แต่นอก 09:00-16:00 โดนหักคะแนน')
    time_limit = st.slider('Time limit (วินาที)', 30, 300, 120, step=10)
    run = st.button('Run scheduler', type='primary', width='stretch')

with st.expander('ต้องเตรียมไฟล์อะไรบ้าง', expanded='result' not in st.session_state):
    st.markdown('อัปโหลดเป็นไฟล์ **CSV (UTF-8)** ชื่อไฟล์ต้องตรงตามตาราง ชื่อคอลัมน์ต้องตรงทุกตัวอักษร '
                'ส่วนลำดับคอลัมน์จะเรียงยังไงก็ได้')
    st.dataframe(pd.DataFrame([{'ไฟล์': p, 'ต้องมี': 'ใช่' if req else 'ไม่จำเป็น',
                                'คอลัมน์ที่ต้องมี': ', '.join(cols), 'คอลัมน์เสริม': ', '.join(opt)}
                               for p, req, cols, opt, _ in SPEC]), hide_index=True, width='stretch')
    for p, *_, desc in SPEC:
        st.markdown(f'- **{p}**: {desc}')
    st.markdown('`student_group` คือกลุ่มนักศึกษา เช่น `AI_Y1;CY_Y1` คาบที่มีกลุ่มเดียวกันจะไม่ถูกจัดซ้อนเวลากัน')
    st.download_button('ดาวน์โหลดไฟล์ตัวอย่าง (.zip)', sample_zip(), 'sample_csv.zip', 'application/zip')

if run:
    if source == 'ข้อมูลตัวอย่าง':
        files = {n: open(os.path.join(DEFAULT_DATA, n), 'rb').read() for n in os.listdir(DEFAULT_DATA)}
    else:
        files = {os.path.basename(f.name): f.getvalue() for f in uploads or []}
    if problems := check(files):
        st.error('ไฟล์ยังไม่ถูกต้อง:\n\n' + '\n'.join(f'- {p}' for p in problems))
        st.stop()
    with tempfile.TemporaryDirectory() as data_dir:
        for name, data in files.items():
            with open(os.path.join(data_dir, name), 'wb') as out:
                out.write(data)
        with st.spinner('กำลังจัดตาราง... (ใช้เวลาไม่เกิน time limit)'):
            try:
                st.session_state.result = (mode, *solve(data_dir, mode, time_limit, WORKERS))
            except Exception as e:
                st.error(f'จัดตารางไม่สำเร็จ: {e}')
                st.stop()

if 'result' not in st.session_state:
    st.stop()

mode, result, unscheduled = st.session_state.result
c1, c2 = st.columns(2)
c1.metric('จัดได้ (คาบ)', len(result))
c2.metric('จัดไม่ลง (คาบ)', len(unscheduled))

view = result
f1, f2, f3 = st.columns(3)
teacher = f1.selectbox('อาจารย์', ['ทั้งหมด'] + sorted({t for s in result['Teacher'] for t in s.split(',') if t}))
room = f2.selectbox('ห้อง', ['ทั้งหมด'] + sorted(result['Room'].astype(str).unique()))
course = f3.selectbox('วิชา', ['ทั้งหมด'] + sorted(result['Course'].astype(str).unique()))
if teacher != 'ทั้งหมด':
    view = view[view['Teacher'].str.split(',').apply(lambda ts: teacher in ts)]
if room != 'ทั้งหมด':
    view = view[view['Room'].astype(str) == room]
if course != 'ทั้งหมด':
    view = view[view['Course'].astype(str) == course]

st.subheader('ตารางที่จัดได้')
st.dataframe(view, width='stretch', hide_index=True)
st.download_button('ดาวน์โหลด schedule CSV', result.to_csv(index=False).encode('utf-8-sig'),
                   f'schedule_{mode}.csv', 'text/csv')

if not unscheduled.empty:
    st.subheader('คาบที่จัดไม่ลง')
    st.dataframe(unscheduled, width='stretch', hide_index=True)
    st.download_button('ดาวน์โหลด unscheduled CSV', unscheduled.to_csv(index=False).encode('utf-8-sig'),
                       f'unscheduled_{mode}.csv', 'text/csv')
