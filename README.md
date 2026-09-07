# CCTV: Smart Industrial Safety & Surveillance System
ระบบอัจฉริยะเพื่อการเฝ้าระวังและความปลอดภัยในงานอุตสาหกรรม (Industrial Safety AI)

ระบบตรวจจับอุปกรณ์ความปลอดภัยส่วนบุคคล (PPE) โดยเน้นการตรวจจับรองเท้าเซฟตี้ (Boots) และบุคคลที่ไม่สวมใส่รองเท้าเซฟตี้ (no_boots) แบบเรียลไทม์จากสตรีมกล้อง CCTV, วิดีโอ YouTube และรูปภาพ ด้วยโมเดล **YOLO11s** ที่ผ่านการฝึกฝน 150 Epochs

---

## คุณสมบัติเด่น (Features)
- **Real-time PPE Detection**: ตรวจจับ หมวกนิรภัย (Helmet), เสื้อสะท้อนแสง (Vest), ถุงมือ (Gloves), และรองเท้าเซฟตี้ (Boots)
- **Footwear Compliance Check**: แยกแยะระหว่างผู้ที่สวมรองเท้าเซฟตี้ (กรอบสีเขียว) และผู้ที่สวมรองเท้าทั่วไป/ไม่สวมรองเท้าเซฟตี้ (กรอบสีแดง)
- **Multi-source Inference**: รองรับทั้งสตรีมวิดีโอจาก YouTube, วิดีโอไฟล์ในเครื่อง, ภาพนิ่ง และลิงก์รูปภาพออนไลน์ (Google Search Image URLs)
- **Automated Logging**: บันทึกสถิติผลการตรวจจับเป็นไฟล์ตาราง Excel (.xlsx) และ CSV พร้อมสรุป Metrics

---

## ประสิทธิภาพโมเดล (Model Performance)
- **Base Model**: YOLO11s (Ultralytics)
- **Dataset**: 2,261 ภาพ (Train 70% / Val 20% / Test 10%)
- **Epochs**: 150 Epochs บน NVIDIA GeForce RTX 3050 Ti Laptop GPU
- **Overall mAP@50**: **79.3%**
- **Boots Class mAP@50**: **87.4%**
- **Max Precision**: **91.4%**

---

## วิธีการใช้งาน (Usage)

### 1. ติดตั้ง Dependencies
```bash
pip install ultralytics opencv-python yt-dlp pandas openpyxl
```

### 2. รันการตรวจจับวิดีโอ (Inference)
```bash
# รันวิดีโอเริ่มต้น (Default video)
python inference_video.py

# รันด้วยลิงก์ YouTube ที่ต้องการ
python inference_video.py --url "https://youtu.be/Mol0lrRBy3g" --frames 300

# รันตรวจจับด้วยลิงก์รูปภาพ
python inference_video.py --url "https://example.com/image.jpg"
```

---

## โครงสร้างโปรเจกต์
```text
├── inference_video.py         # สคริปต์ตรวจจับวิดีโอและรูปภาพ
├── train_yolo.py              # สคริปต์ฝึกสอนโมเดล YOLO11s
├── split_dataset.py           # สคริปต์แบ่งชุดข้อมูล 70/20/10
├── dataset.yaml               # กำหนดคลาสและพาธของข้อมูล
├── experiment_results.xlsx    # ตารางบันทึกผลการทดลอง (Excel)
├── experiment_results.csv     # ตารางบันทึกผลการทดลอง (CSV)
└── runs/                      # น้ำหนักโมเดลที่เทรนเสร็จ (weights/best.pt)
```
