"""Web UI for scheduler.py. Run: streamlit run streamlit_app.py"""
import os
import shutil
import tempfile

import streamlit as st

from scheduler import solve

DEFAULT_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Data', 'CSV')

st.set_page_config(page_title='Schedule Workshop', layout='wide')
st.title('Schedule Workshop')

with st.sidebar:
    mode = st.radio('Mode', ['flexible', 'compact'],
                    help='compact = 09:00-16:00 only; flexible = 08:30-19:00 with penalty outside 09:00-16:00')
    time_limit = st.slider('Time limit (seconds)', 10, 300, 120, step=10)
    uploads = st.file_uploader('Replace CSV files (optional)', type='csv', accept_multiple_files=True,
                               help='A file with the same name as one in Data/CSV replaces it; new *_in/*_out files are added.')
    run = st.button('Run scheduler', type='primary', width='stretch')

if run:
    with tempfile.TemporaryDirectory() as data_dir:
        shutil.copytree(DEFAULT_DATA, data_dir, dirs_exist_ok=True)
        for f in uploads or []:
            with open(os.path.join(data_dir, os.path.basename(f.name)), 'wb') as out:
                out.write(f.getbuffer())
        with st.spinner('Solving...'):
            try:
                st.session_state.result = (mode, *solve(data_dir, mode, time_limit))
            except Exception as e:
                st.error(f'Error: {e}')

if 'result' not in st.session_state:
    st.info('Pick options in the sidebar and press **Run scheduler**.')
    st.stop()

mode, result, unscheduled = st.session_state.result
c1, c2 = st.columns(2)
c1.metric('Scheduled sessions', len(result))
c2.metric('Unscheduled sessions', len(unscheduled))

view = result
f1, f2, f3 = st.columns(3)
if teacher := f1.selectbox('Teacher', ['All'] + sorted({t for s in result['Teacher'] for t in s.split(',') if t})):
    view = view if teacher == 'All' else view[view['Teacher'].str.split(',').apply(lambda ts: teacher in ts)]
if room := f2.selectbox('Room', ['All'] + sorted(result['Room'].astype(str).unique())):
    view = view if room == 'All' else view[view['Room'].astype(str) == room]
if course := f3.selectbox('Course', ['All'] + sorted(result['Course'].astype(str).unique())):
    view = view if course == 'All' else view[view['Course'].astype(str) == course]

st.subheader('Schedule')
st.dataframe(view, width='stretch', hide_index=True)
st.download_button('Download schedule CSV', result.to_csv(index=False).encode('utf-8-sig'),
                   f'schedule_{mode}.csv', 'text/csv')

if not unscheduled.empty:
    st.subheader('Unscheduled')
    st.dataframe(unscheduled, width='stretch', hide_index=True)
    st.download_button('Download unscheduled CSV', unscheduled.to_csv(index=False).encode('utf-8-sig'),
                       f'unscheduled_{mode}.csv', 'text/csv')
