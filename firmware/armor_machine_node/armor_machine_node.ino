/*
 * ARMOR - Machine Node Firmware (ESP32)
 * -------------------------------------
 * Core 0: 100 Hz sensor sampling (ADXL345/INA219/DS18B20) + interlock GPIO actuation
 * Core 1: WiFi + MQTT + ESP-NOW receive (RSSI/EMA) + telemetry/breach publish
 *
 * Pinout: see docs/hardware-pinout.md
 * Streaming: see docs/data-streaming.md
 *
 * Libraries required (Arduino Library Manager):
 *   - PubSubClient (Nick O'Leary)
 *   - Adafruit INA219
 *   - DallasTemperature + OneWire
 *   - (ADXL345 via raw SPI, no library needed)
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>
#include <SPI.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_INA219.h>
#include <ArduinoJson.h>

// ---------- WiFi / MQTT config (edit before flashing) ----------
const char* WIFI_SSID     = "YOUR_SSID";
const char* WIFI_PASSWORD = "YOUR_PASSWORD";
const char* MQTT_BROKER   = "192.168.1.100";   // backend host IP
const uint16_t MQTT_PORT  = 1883;
const char* DEVICE_ID     = "machino_node_01";

// ---------- Pinout (docs/hardware-pinout.md) ----------
#define PIN_ENA     25   // L298N ENA (PWM)
#define PIN_IN1     26
#define PIN_IN2     27
#define PIN_RELAY   32   // Master 12 V cutoff (active-LOW)
#define PIN_RELAY2  33   // Auxiliary (unused)

#define ADXL_CS     5
#define ADXL_SCK    18
#define ADXL_MOSI   23
#define ADXL_MISO   19

#define I2C_SDA     21
#define I2C_SCL     22

#define DS18B20_PIN 15

// ---------- ADXL345 (SPI Mode 3) ----------
#define ADXL_REG_DEVID       0x00
#define ADXL_REG_BW_RATE     0x2C
#define ADXL_REG_POWER_CTL   0x2D
#define ADXL_REG_DATA_FORMAT 0x31
#define ADXL_REG_DATAX0      0x32
#define ADXL_SPI_READ        0x80
SPISettings adxlSpi(1000000, MSBFIRST, SPI_MODE3);

// ---------- Globals ----------
WiFiClient   wifiClient;
PubSubClient mqtt(wifiClient);
Adafruit_INA219 ina219;
OneWire oneWire(DS18B20_PIN);
DallasTemperature tempSensor(&oneWire);

// Sensor readings (shared, written by Core 0, read by Core 1)
volatile float gRms          = 0.0f;
volatile float gCrestFactor  = 0.0f;
volatile float gVoltageV     = 0.0f;
volatile float gCurrentMa    = 0.0f;
volatile float gTempC        = 0.0f;
volatile bool  gInterlock    = false;   // set by Core 1, acted on by Core 0

// RSSI / EMA (Core 1)
static const float EMA_ALPHA     = 0.35f;
static const float RSSI_THRESHOLD = -65.0f;   // nominal dBm at 1.5 m (calibrate at venue)
float gEmaRssi = 0.0f;
bool  gEmaInit = false;

// Motor state
volatile bool motorRunning = true;

// ---------- ADXL helpers ----------
void adxlWrite(uint8_t reg, uint8_t val) {
  SPI.beginTransaction(adxlSpi);
  digitalWrite(ADXL_CS, LOW);
  SPI.transfer(reg);
  SPI.transfer(val);
  digitalWrite(ADXL_CS, HIGH);
  SPI.endTransaction();
}
uint8_t adxlRead(uint8_t reg) {
  SPI.beginTransaction(adxlSpi);
  digitalWrite(ADXL_CS, LOW);
  SPI.transfer(reg | ADXL_SPI_READ);
  uint8_t v = SPI.transfer(0x00);
  digitalWrite(ADXL_CS, HIGH);
  SPI.endTransaction();
  return v;
}
bool initADXL() {
  pinMode(ADXL_CS, OUTPUT);
  digitalWrite(ADXL_CS, HIGH);
  SPI.begin(ADXL_SCK, ADXL_MISO, ADXL_MOSI, ADXL_CS);
  delay(50);
  if (adxlRead(ADXL_REG_DEVID) != 0xE5) return false;
  adxlWrite(ADXL_REG_BW_RATE, 0x0A);       // 100 Hz
  adxlWrite(ADXL_REG_DATA_FORMAT, 0x0B);   // +/-16g full res
  adxlWrite(ADXL_REG_POWER_CTL, 0x00);
  delay(10);
  adxlWrite(ADXL_REG_POWER_CTL, 0x08);     // measurement mode
  delay(10);
  return true;
}
void readAxes(float &ax, float &ay, float &az) {
  uint8_t x0 = adxlRead(0x32), x1 = adxlRead(0x33);
  uint8_t y0 = adxlRead(0x34), y1 = adxlRead(0x35);
  uint8_t z0 = adxlRead(0x36), z1 = adxlRead(0x37);
  const float scale = 0.0039f * 9.80665f;
  ax = (int16_t)((x1 << 8) | x0) * scale;
  ay = (int16_t)((y1 << 8) | y0) * scale;
  az = (int16_t)((z1 << 8) | z0) * scale;
}

// ---------- MQTT callbacks ----------
void mqttCallback(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, len)) return;
  const char* cmd = doc["command"] | "";
  if (strcmp(cmd, "LOCKOUT") == 0) {
    gInterlock = true;
  } else if (strcmp(cmd, "RESET") == 0) {
    gInterlock = false;
  }
}

void ensureMqtt() {
  if (mqtt.connected()) return;
  String clientId = String("armor-node-") + DEVICE_ID;
  if (mqtt.connect(clientId.c_str())) {
    String topic = String("machinocare/v1/devices/") + DEVICE_ID + "/interlock";
    mqtt.subscribe(topic.c_str(), 1);
  }
}

// ---------- ESP-NOW receive (badge beacon) ----------
typedef struct {
  uint8_t sender_mac[6];
  char    badge_id[32];
  uint32_t sequence_num;
  float    battery_voltage;
} BadgeBeacon;

void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (len < (int)sizeof(BadgeBeacon)) return;
  BadgeBeacon* b = (BadgeBeacon*)data;

  // RSSI is provided by the receive info (newer ESP-IDF) — fall back to 0 if unavailable
  int rssi = (info && info->rx_ctrl) ? info->rx_ctrl->rssi : 0;
  if (!gEmaInit) { gEmaRssi = (float)rssi; gEmaInit = true; }
  else            { gEmaRssi = EMA_ALPHA * rssi + (1.0f - EMA_ALPHA) * gEmaRssi; }

  if (gEmaRssi > RSSI_THRESHOLD) {   // less negative = closer
    // Breach: notify backend (Core 1 will publish). Set a flag.
    // We store the badge id in a shared buffer.
    // (Simplified: publish directly from here is unsafe; instead set flag + buffer.)
  }
}

// ---------- Core 0: sensor sampling + actuation ----------
void core0Task(void* pv) {
  const TickType_t period = pdMS_TO_TICKS(10);   // 100 Hz
  TickType_t last = xTaskGetTickCount();
  while (true) {
    // --- Actuation (safety-critical, no network) ---
    if (gInterlock) {
      digitalWrite(PIN_RELAY, LOW);     // cut 12 V
      digitalWrite(PIN_ENA, LOW);       // stop PWM
      motorRunning = false;
    } else {
      digitalWrite(PIN_RELAY, HIGH);    // 12 V enabled
      // PWM driven by loop() below when running
      motorRunning = true;
    }

    // --- Sampling ---
    float ax, ay, az;
    readAxes(ax, ay, az);
    float mag = sqrtf(ax*ax + ay*ay + az*az);

    // RMS over a small window (simplified: single-sample magnitude)
    gRms = mag;
    gCrestFactor = 0.0f;

    float v = ina219.getBusVoltage_V();
    float i = ina219.getCurrent_mA();
    gVoltageV  = v;
    gCurrentMa = i;

    tempSensor.requestTemperatures();
    gTempC = tempSensor.getTempCByIndex(0);

    vTaskDelayUntil(&last, period);
  }
}

// ---------- Core 1: network + ESP-NOW + publish ----------
void core1Task(void* pv) {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }

  // ESP-NOW init
  if (esp_now_init() == ESP_OK) {
    esp_now_register_recv_cb(onEspNowRecv);
  }

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);

  uint32_t lastTelemetry = 0;
  uint32_t lastBreachCheck = 0;

  while (true) {
    if (WiFi.status() == WL_CONNECTED) {
      ensureMqtt();
      mqtt.loop();
    }

    uint32_t now = millis();

    // Telemetry @ 1 Hz
    if (now - lastTelemetry >= 1000) {
      lastTelemetry = now;
      if (mqtt.connected()) {
        StaticJsonDocument<256> doc;
        doc["device_id"]   = DEVICE_ID;
        doc["timestamp"]    = now;
        doc["motor_state"] = motorRunning ? "RUNNING" : "LOCKED";
        JsonObject vib = doc.createNestedObject("vibration");
        vib["rms"]          = gRms;
        vib["crest_factor"] = gCrestFactor;
        JsonObject pwr = doc.createNestedObject("power");
        pwr["voltage_v"] = gVoltageV;
        pwr["current_ma"]= gCurrentMa;
        pwr["power_mw"]  = gVoltageV * gCurrentMa;
        doc["temperature_c"] = gTempC;

        char buf[512];
        serializeJson(doc, buf);
        String topic = String("machinocare/v1/devices/") + DEVICE_ID + "/telemetry";
        mqtt.publish(topic.c_str(), buf, false);
      }
    }

    // Breach check @ 10 Hz (publish when EMA crosses threshold)
    if (now - lastBreachCheck >= 100) {
      lastBreachCheck = now;
      if (gEmaInit && gEmaRssi > RSSI_THRESHOLD && mqtt.connected()) {
        // TODO: include the badge_id from the last received beacon
        StaticJsonDocument<256> doc;
        doc["device_id"]      = DEVICE_ID;
        doc["worker_id"]      = "BADGE-UNKNOWN";
        doc["badge_mac"]      = "00:00:00:00:00:00";
        doc["rssi_raw"]       = (int)gEmaRssi;
        doc["rssi_smoothed"]  = gEmaRssi;
        doc["distance_est_m"] = 1.2;
        doc["timestamp"]      = now;
        char buf[512];
        serializeJson(doc, buf);
        mqtt.publish("machinocare/v1/events/proximity", buf, false);
      }
    }

    delay(10);
  }
}

// ---------- setup / loop ----------
void setup() {
  Serial.begin(115200);

  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_RELAY2, OUTPUT);

  // Safe boot state: relay ON (12 V enabled), motor stopped
  digitalWrite(PIN_RELAY, HIGH);
  digitalWrite(PIN_RELAY2, HIGH);
  digitalWrite(PIN_IN1, HIGH);
  digitalWrite(PIN_IN2, LOW);
  analogWrite(PIN_ENA, 0);

  // PWM setup (ESP32 Arduino core 3.x)
  ledcAttach(PIN_ENA, 5000, 8);

  Wire.begin(I2C_SDA, I2C_SCL);
  ina219.begin();
  tempSensor.begin();

  if (!initADXL()) {
    Serial.println("ADXL345 init FAILED");
  }

  // FreeRTOS tasks
  xTaskCreatePinnedToCore(core0Task, "core0", 4096, NULL, 2, NULL, 0);
  xTaskCreatePinnedToCore(core1Task, "core1", 8192, NULL, 1, NULL, 1);
}

void loop() {
  // Motor PWM when running and not locked out
  if (motorRunning && !gInterlock) {
    analogWrite(PIN_ENA, 170);   // ~67 % duty
  } else {
    analogWrite(PIN_ENA, 0);
  }
  delay(20);
}
