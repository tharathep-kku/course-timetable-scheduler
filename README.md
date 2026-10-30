# Schedule Workshop

โปรแกรมนี้จัดตารางเรียนและตารางสอน (ห้อง + เวลา + อาจารย์) ให้อัตโนมัติ ใช้ [Google OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver) ในการแก้ปัญหา

## โครงสร้าง

```
.
├── scheduler.py        # ตัวจัดตาราง
├── test_scheduler.py   # ทดสอบด้วยข้อมูลจำลองขนาดเล็ก
├── requirements.txt
└── Data/CSV/           # ข้อมูลนำเข้า
```

## วิธีรัน

```bash
pip install -r requirements.txt
python scheduler.py                    # โหมด flexible, ข้อมูลจาก Data/CSV, ผลลัพธ์ลง output/
python scheduler.py --mode compact     # จัดเฉพาะ 09:00–16:00
python scheduler.py --data-dir path/to/csv --out-dir results --time-limit 300
python test_scheduler.py               # ต้องพิมพ์ ok
```

| ตัวเลือก | ค่าเริ่มต้น | ความหมาย |
|---|---|---|
| `--mode` | `flexible` | `compact` จัดได้แค่ 09:00–16:00 ส่วน `flexible` จัดได้ 08:30–19:00 แต่เวลานอก 09:00–16:00 จะโดนหักคะแนน |
| `--data-dir` | `Data/CSV` | โฟลเดอร์ที่เก็บ CSV |
| `--out-dir` | `output` | โฟลเดอร์ที่เก็บผลลัพธ์ |
| `--time-limit` | `120` | เวลาสูงสุดที่ solver ใช้ (วินาที) |

ค่าอื่น ๆ เช่น ช่วงเวลาทำการ, พักเที่ยง, ขนาด slot, คะแนนและ penalty ปรับได้ที่หัวไฟล์ `scheduler.py` (ส่วน `Settings`)

### รันเป็นเว็บ (Streamlit)

```bash
streamlit run streamlit_app.py
```

เลือกโหมดและเวลาได้จากแถบด้านซ้าย จะอัปโหลด CSV มาแทนไฟล์ใน `Data/CSV` ก็ได้ ถ้าชื่อไฟล์ตรงกันจะใช้ไฟล์ที่อัปโหลดแทน ส่วนผลลัพธ์กดดาวน์โหลดได้จากหน้าเว็บ

ถ้าจะ deploy ขึ้นเว็บ ให้ใช้ [Streamlit Community Cloud](https://share.streamlit.io) โดยเลือก repo นี้และตั้ง main file เป็น `streamlit_app.py`

### รันบน Google Colab

อัปโหลด `scheduler.py` และโฟลเดอร์ `Data/CSV` ขึ้น Colab แล้วรัน:

```
!pip install ortools
!python scheduler.py --mode flexible
```

## ข้อมูลนำเข้า (`Data/CSV`)

| ไฟล์ | คอลัมน์ | ความหมาย |
|---|---|---|
| `room.csv` | room, capacity, type, building | `type` เป็น `lecture`, `lab`, `lab ai` หรือ `lab network` |
| `all_teachers.csv` | teacher_id, unavailable_times, max_hours_per_day | เวลาที่อาจารย์ไม่ว่าง เช่น `['Mon 10:00-12:00', 'Fri 15:30-18:30']` ถ้า `max_hours_per_day` เป็น 0 แปลว่าไม่จำกัดชั่วโมงสอนต่อวัน |
| `teacher_courses.csv` | teacher_id, course_code | อาจารย์ผู้สอนของแต่ละวิชา (วิชาเดียวมีอาจารย์ได้หลายคน) |
| `*_in_courses.csv` | course_code, course_name, credit, lecture_hour, lab_hour, section, enrollment_count, [optional, require_lab_ai, require_lab_network, lec_online, lab_online, student_group] | วิชาที่ต้องจัดตาราง ถ้าไม่มีคอลัมน์ในวงเล็บ จะถือว่าเป็น 0 หรือว่าง |
| `*_out_courses.csv` | course_code, lecture_hour, lab_hour, section, day, start, room, [end, student_group] | วิชาที่คณะอื่นกำหนดวัน เวลา และห้องไว้แล้ว |

**คอลัมน์ที่ใส่หรือไม่ใส่ก็ได้**
- `student_group` คือกลุ่มนักศึกษาที่เรียนคาบนั้น เช่น `AI_Y1` ถ้ามีหลายกลุ่มให้คั่นด้วย `;` เช่น `AI_Y1;CY_Y1` คาบที่มีกลุ่มเดียวกันจะไม่ถูกจัดซ้อนเวลากัน ถ้าใส่ในไฟล์ `*_out_courses` ด้วย เวลานั้นของกลุ่มจะถูกกันไว้ ถ้าเว้นว่างไว้ จะไม่เช็กการชนกันของกลุ่มนักศึกษา
- `end` คือเวลาเลิกของแต่ละครั้งที่เรียน ถ้าไม่ใส่ โปรแกรมจะเอาชั่วโมงรวมของ section มาหารเท่ากันตามจำนวนแถว เช่น 3 ชม. และมี 2 แถว จะได้ครั้งละ 1.5 ชม.

ถ้าจะเพิ่มภาควิชาใหม่ ให้วางไฟล์ `<ชื่อ>_in_courses.csv` และ `<ชื่อ>_out_courses.csv` ไว้ในโฟลเดอร์เดียวกัน โปรแกรมจะอ่านเองโดยไม่ต้องแก้โค้ด

## ผลลัพธ์

- `output/schedule_<mode>.csv` คือตารางที่จัดได้ คอลัมน์ Day, Start, End, Room, Course, Sec, Type, Teacher, Note ช่อง Note บอกว่าเป็น `Fixed`, `Online` หรือ `Ext.Time` (อยู่นอก 09:00–16:00)
- `output/unscheduled_<mode>.csv` คือคาบที่จัดไม่ลง พร้อมเหตุผล

## กฎการจัด

**Hard constraint**
- ห้องเดียวกันใช้ซ้อนเวลากันไม่ได้ อาจารย์คนเดียวกันสอนซ้อนเวลากันไม่ได้ และกลุ่มนักศึกษาเดียวกันเรียนซ้อนเวลากันไม่ได้
- ห้ามจัดทับพักเที่ยง 12:30–13:00
- ห้องต้องจุนักศึกษาได้พอ
- คาบ Lab ต้องอยู่ในห้องประเภท lab ถ้าวิชากำหนด `require_lab_ai` หรือ `require_lab_network` ต้องใช้ห้องที่มี `type` ตรงกัน
- ห้ามจัดทับเวลาที่อาจารย์ไม่ว่าง และชั่วโมงสอนต่อวันต้องไม่เกิน `max_hours_per_day`
- วิชาใน `*_out_courses` ถูกล็อกไว้ตามไฟล์ โปรแกรมจะกันเวลาของอาจารย์ผู้สอนไว้ และกันห้องไว้ด้วยถ้าห้องนั้นอยู่ใน `room.csv`
- คาบออนไลน์ใช้ห้อง `Online` ซึ่งไม่ชนกับห้องอื่น

**Soft constraint (objective)**
- จัดวิชาบังคับ (`optional = 0`) ได้ 1000 คะแนน และวิชาเลือกได้ 100 คะแนน
- หักคะแนนเมื่อจัดนอก 09:00–16:00 (เฉพาะโหมด flexible)
- หักคะแนนเมื่อ Lab ของ section อยู่ก่อน Lecture

**รายละเอียดอื่น**
- 1 slot เท่ากับ 30 นาที
- คาบที่ยาวเกิน 3 ชม. ถูกแบ่งเป็นหลายช่วง ทั้ง Lecture และ Lab
- แต่ละแถวใน `*_out_courses` นับเป็น 1 ครั้งที่เรียน

## ข้อจำกัดที่ทราบ

- ข้อมูลใน `Data/CSV` ตอนนี้ยังไม่มีคอลัมน์ `student_group` เลยยังไม่ได้เช็กการชนกันของกลุ่มนักศึกษา
- จากข้อมูลปัจจุบันมี Lab ที่จัดไม่ลงเพราะไม่มีห้องที่จุนักศึกษาได้ ได้แก่ CP002001 (250 และ 150 คน) และวิชาที่ต้องใช้ `lab ai` แต่มีนักศึกษามากกว่า 30 คน
