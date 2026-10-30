# Course Timetable Scheduler

Automatically generates class and teaching timetables (room + time + instructor) using [Google OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver).

## Structure

```
.
├── scheduler.py        # Scheduler
├── streamlit_app.py    # Web UI
├── test_scheduler.py   # Tests on small mock data
├── requirements.txt
└── Data/CSV/           # Input data
```

## Usage

```bash
pip install -r requirements.txt
python scheduler.py                    # flexible mode, data from Data/CSV, output to output/
python scheduler.py --mode compact     # schedule only within 09:00–16:00
python scheduler.py --data-dir path/to/csv --out-dir results --time-limit 300
python test_scheduler.py               # should print ok
```

| Option | Default | Description |
|---|---|---|
| `--mode` | `flexible` | `compact` schedules only within 09:00–16:00; `flexible` allows 08:30–19:00 but penalizes slots outside 09:00–16:00 |
| `--data-dir` | `Data/CSV` | Folder containing the CSV files |
| `--out-dir` | `output` | Folder for results |
| `--time-limit` | `120` | Maximum solver time (seconds) |

Other settings such as working hours, lunch break, slot size, scores and penalties can be adjusted in the `Settings` section at the top of `scheduler.py`.

### Run as a web app (Streamlit)

```bash
streamlit run streamlit_app.py
```

Choose between the sample data or uploading your own CSV files. File names and columns are validated before solving, and the expected formats are shown on the page. The web version runs the solver with 4 workers to stay within Streamlit Cloud's memory limit.

To deploy, use [Streamlit Community Cloud](https://share.streamlit.io): select this repo and set the main file to `streamlit_app.py`.

### Run on Google Colab

Upload `scheduler.py` and the `Data/CSV` folder to Colab, then run:

```
!pip install ortools
!python scheduler.py --mode flexible
```

## Input Data (`Data/CSV`)

| File | Columns | Description |
|---|---|---|
| `room.csv` | room, capacity, type, building | `type` is `lecture`, `lab`, `lab ai`, or `lab network` |
| `all_teachers.csv` | teacher_id, unavailable_times, max_hours_per_day | Times the instructor is unavailable, e.g. `['Mon 10:00-12:00', 'Fri 15:30-18:30']`. A `max_hours_per_day` of 0 means no daily limit |
| `teacher_courses.csv` | teacher_id, course_code | Instructors for each course (a course may have multiple instructors) |
| `*_in_courses.csv` | course_code, course_name, credit, lecture_hour, lab_hour, section, enrollment_count, [optional, require_lab_ai, require_lab_network, lec_online, lab_online, student_group] | Courses to be scheduled. Bracketed columns default to 0 or empty if missing |
| `*_out_courses.csv` | course_code, lecture_hour, lab_hour, section, day, start, room, [end, student_group] | Courses whose day, time and room are already fixed by other faculties |

**Optional columns**
- `student_group` — the student group(s) attending the session, e.g. `AI_Y1`. Separate multiple groups with `;`, e.g. `AI_Y1;CY_Y1`. Sessions sharing a group will not overlap. If set in `*_out_courses`, those times are blocked for the group. If left empty, student-group conflicts are not checked.
- `end` — end time of each session. If omitted, the section's total hours are split evenly across its rows, e.g. 3 hours over 2 rows gives 1.5 hours each.

To add a new department, place `<name>_in_courses.csv` and `<name>_out_courses.csv` in the same folder. They are picked up automatically with no code changes.

## Output

- `output/schedule_<mode>.csv` — the generated timetable with columns Day, Start, End, Room, Course, Sec, Type, Teacher, Note. Note is `Fixed`, `Online`, or `Ext.Time` (outside 09:00–16:00).
- `output/unscheduled_<mode>.csv` — sessions that could not be placed, with reasons.

## Scheduling Rules

**Hard constraints**
- No overlapping use of the same room, instructor, or student group.
- No sessions during the 12:30–13:00 lunch break.
- Room capacity must fit the enrollment.
- Lab sessions must be in a lab room; courses with `require_lab_ai` or `require_lab_network` need a room of the matching `type`.
- Instructors' unavailable times are respected, and daily teaching hours must not exceed `max_hours_per_day`.
- Courses in `*_out_courses` are locked as given; their instructors' times are blocked, and their rooms are blocked too if listed in `room.csv`.
- Online sessions use the `Online` room, which never conflicts with other rooms.

**Soft constraints (objective)**
- +1000 points per scheduled required course (`optional = 0`), +100 per elective.
- Penalty for slots outside 09:00–16:00 (flexible mode only).
- Penalty when a section's Lab comes before its Lecture.

**Other details**
- 1 slot = 30 minutes.
- Sessions longer than 3 hours are split into multiple blocks (both Lecture and Lab).
- Each row in `*_out_courses` counts as one session.

## Known Limitations

- The current data in `Data/CSV` has no `student_group` column, so student-group conflicts are not yet checked.
- With the current data, some labs cannot be scheduled because no room is large enough: CP002001 (250 and 150 students), and courses requiring `lab ai` with more than 30 students.
