/* ─────────────────────────────────────────────────────────────────────────────
   barrier_gate_esp32.ino  —  ESP32 controller for the CCTV dashboard's ไม้กั้น
   ─────────────────────────────────────────────────────────────────────────────

   จับคู่กับหน้า Dashboard (การ์ด "🚧 ไม้กั้นทางเข้า"):
     GET /         → health check   (dashboard เรียกทุก 10 วิ เพื่อโชว์ "เชื่อมต่อแล้ว")
     GET /open     → ยกไม้กั้นขึ้น + บี๊บสั้น + ไฟเขียว
     GET /close    → ลดไม้กั้นลง       + ไฟแดง
     GET /status   → {"status":"open"|"closed"}

   ตั้งค่าใน dashboard:  ENV  ESP32_URL = http://<ip-ที่ปรินต์ทาง Serial>

   ฮาร์ดแวร์ (อ้างอิง EquipmentList): ESP32 DEVKIT V1 + Buzzer/LED AD16-22SM
     - Servo (SG90 / MG996R) ต่อแขนไม้กั้น       → GPIO 13
     - Buzzer                                     → GPIO 14
     - LED สถานะ (เขียว=เปิด / แดง=ปิด ใช้ 2 ขา)  → GPIO 26 (open) , GPIO 27 (closed)
     * ถ้าใช้รีเลย์ขับมอเตอร์แทนเซอร์โว ดูหมายเหตุท้ายไฟล์

   ไลบรารีที่ต้องติดตั้งใน Arduino IDE:
     - ESP32 board package (Espressif)
     - "ESP32Servo" by Kevin Harrington
   ───────────────────────────────────────────────────────────────────────────── */

#include <WiFi.h>
#include <WebServer.h>
#include <ESP32Servo.h>

// ─── ตั้งค่า ──────────────────────────────────────────────────────────────────
const char *WIFI_SSID = "YOUR_WIFI_SSID";
const char *WIFI_PASS = "YOUR_WIFI_PASSWORD";

const int PIN_SERVO      = 13;
const int PIN_BUZZER     = 14;
const int PIN_LED_OPEN   = 26;
const int PIN_LED_CLOSED = 27;

const int ANGLE_CLOSED = 10;    // องศาแขนไม้กั้นตอนปิด (ขนานพื้น)
const int ANGLE_OPEN   = 95;    // องศาแขนไม้กั้นตอนเปิด (ตั้งขึ้น)
const int SERVO_STEP_MS = 8;    // หน่วงต่อ 1 องศา ทำให้แขนขยับนุ่ม ๆ

// ─── สถานะ ───────────────────────────────────────────────────────────────────
WebServer server(80);
Servo     gateServo;
String    gateStatus = "closed";
int       servoAngle = ANGLE_CLOSED;

// ─── ยูทิลิตี้ ────────────────────────────────────────────────────────────────
void beep(int ms, int times = 1) {
  for (int i = 0; i < times; i++) {
    digitalWrite(PIN_BUZZER, HIGH);
    delay(ms);
    digitalWrite(PIN_BUZZER, LOW);
    if (i < times - 1) delay(ms);
  }
}

void setLeds() {
  bool open = (gateStatus == "open");
  digitalWrite(PIN_LED_OPEN,   open ? HIGH : LOW);
  digitalWrite(PIN_LED_CLOSED, open ? LOW  : HIGH);
}

void moveServoTo(int target) {
  int step = (target > servoAngle) ? 1 : -1;
  while (servoAngle != target) {
    servoAngle += step;
    gateServo.write(servoAngle);
    delay(SERVO_STEP_MS);
  }
}

void gateOpen() {
  gateStatus = "open";
  setLeds();
  beep(60);
  moveServoTo(ANGLE_OPEN);
}

void gateClose() {
  gateStatus = "closed";
  setLeds();
  moveServoTo(ANGLE_CLOSED);
}

// ─── HTTP handlers ───────────────────────────────────────────────────────────
void sendJson(const String &body) {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", body);
}

void handleRoot()   { sendJson("{\"ok\":true,\"device\":\"barrier-gate\",\"status\":\"" + gateStatus + "\"}"); }
void handleStatus() { sendJson("{\"status\":\"" + gateStatus + "\"}"); }

void handleOpen() {
  gateOpen();
  sendJson("{\"ok\":true,\"status\":\"open\"}");
}

void handleClose() {
  gateClose();
  sendJson("{\"ok\":true,\"status\":\"closed\"}");
}

// ─── setup / loop ────────────────────────────────────────────────────────────
void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("[wifi] connecting");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(400);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[wifi] IP = ");
    Serial.println(WiFi.localIP());
    Serial.print("[dashboard] set  ESP32_URL = http://");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[wifi] FAILED — check SSID / password");
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_OPEN, OUTPUT);
  pinMode(PIN_LED_CLOSED, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);

  gateServo.setPeriodHertz(50);
  gateServo.attach(PIN_SERVO, 500, 2400);
  servoAngle = ANGLE_CLOSED;
  gateServo.write(servoAngle);
  gateStatus = "closed";
  setLeds();

  connectWifi();

  server.on("/",       HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/open",   HTTP_GET, handleOpen);
  server.on("/close",  HTTP_GET, handleClose);
  server.onNotFound([]() { server.send(404, "text/plain", "not found"); });
  server.begin();
  Serial.println("[http] server started on :80");
  beep(40, 2);   // ready
}

void loop() {
  server.handleClient();

  // Auto-reconnect WiFi if it drops
  static unsigned long lastCheck = 0;
  if (millis() - lastCheck > 10000) {
    lastCheck = millis();
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[wifi] lost — reconnecting");
      connectWifi();
    }
  }
}

/* ─────────────────────────────────────────────────────────────────────────────
   หมายเหตุ — ใช้รีเลย์ขับมอเตอร์ไม้กั้นแทนเซอร์โว
   ─────────────────────────────────────────────────────────────────────────────
   1) แทน PIN_SERVO ด้วยขา 2 เส้นไปโมดูลรีเลย์  (เช่น GPIO 13 = ทิศเปิด, GPIO 12 = ทิศปิด)
   2) ใน gateOpen(): digitalWrite(RELAY_OPEN, HIGH); delay(travelTime); digitalWrite(RELAY_OPEN, LOW);
   3) ใน gateClose(): เช่นเดียวกันกับ RELAY_CLOSE
   4) ควรมี limit switch กันโมเตอร์ดันสุดค้าง
   ───────────────────────────────────────────────────────────────────────────── */
