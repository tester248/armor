/*
 * ARMOR - Machine Node Firmware (ESP32) + Blynk IoT Remote Control
 * -----------------------------------------------------------------
 * Core 0: 100 Hz sensor acquisition (ADXL345/INA219/DS18B20) + Hardware Motor Actuation
 * Core 1: WiFi + MQTT Gateway + Blynk IoT Cloud + ESP-NOW Receive (Badge Proximity)
 *
 * Actuator: RS-555 DC Motor via L298N & 2-Channel Relay Module (Active-LOW)
 * Control : Remote Start/Stop via Blynk App (V0) & Automated Lockout via MQTT Safety Topic
 * Telemetry: 1 Hz publish to MQTT & Blynk Virtual Pins (V1=Voltage, V2=Current, V3=Temp, V4=Vib)
 */

#define BLYNK_TEMPLATE_ID   "TMPL3B8QvHAyQ"
#define BLYNK_TEMPLATE_NAME "Machinocare 2.0"
#define BLYNK_AUTH_TOKEN    "u3s1O3o9R0fQuM52EQ5lvGPwTr0JSLg1"

#define BLYNK_PRINT Serial
#include <WiFi.h>
#include <BlynkSimpleEsp32.h>
#include <PubSubClient.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <Wire.h>
#include <SPI.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_INA219.h>
#include <ArduinoJson.h>
#include <time.h>

// ---------- WiFi & MQTT Config ----------
// MQTT_BROKER must be the laptop running the ARMOR FastAPI backend.
// Reserve a static DHCP lease for that laptop so this address does not drift.
const char* WIFI_SSID     = "ARMOR";
const char* WIFI_PASSWORD = "12345678";
// const char* MQTT_BROKER   = "10.24.103.35";   // Backend host (laptop) on the hotspot
const char* MQTT_BROKER   = "10.24.103.187";   // Backend host (laptop) on the hotspot
const uint16_t MQTT_PORT  = 1883;
const char* DEVICE_ID     = "machino_node_01";

// ---------- Pinout (Authoritative) ----------
#define PIN_ENA     25   // L298N ENA (Hardware PWM)
#define PIN_IN1     26   // L298N IN1
#define PIN_IN2     27   // L298N IN2
#define PIN_RELAY   32   // Master 12 V Motor Power Cutoff Relay
#define PIN_RELAY2  33   // Auxiliary Relay

// Active-LOW relay module logic
#define RELAY_ON    LOW   // Optocoupler active -> Relay closes NO to COM
#define RELAY_OFF   HIGH  // Optocoupler inactive -> Circuit open

#define ADXL_CS     5
#define ADXL_SCK    18
#define ADXL_MOSI   23
#define ADXL_MISO   19

#define I2C_SDA     21
#define I2C_SCL     22

#define DS18B20_PIN 15

// ---------- ADXL345 Registers ----------
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

// Shared telemetry (Written by Core 0, Read by Core 1)
volatile float gRms          = 0.0f;
volatile float gCrestFactor  = 0.0f;
volatile float gVoltageV     = 0.0f;
volatile float gCurrentMa    = 0.0f;
volatile float gTempC        = 0.0f;

// Motor state & dual control (Blynk App + Safety Lockout)
volatile bool blynkMotorRequested = false; // User command from Blynk Switch (V0)
volatile bool gInterlock          = false; // Safety lock (MQTT or proximity breach)
volatile bool motorRunning        = false; // Physical motor output state

// RSSI / EMA (ESP-NOW Wearable Badge Receiver)
static const float EMA_ALPHA       = 0.35f;
static const float RSSI_ENTER      = -65.0f;  // breach when smoothed RSSI is above this
static const float RSSI_EXIT       = -70.0f;  // hysteresis: clear only below this
static const float RSSI_AT_1M      = -45.0f;  // calibrate at the venue (RSSI at 1 metre)
static const float PATH_LOSS_N     = 2.2f;    // indoor path-loss exponent
volatile float gEmaRssi = 0.0f;
volatile bool gEmaInit = false;

// Last badge heard over ESP-NOW. The callback runs in the WiFi task, so the
// shared fields are copied under a critical section.
portMUX_TYPE gBadgeMux = portMUX_INITIALIZER_UNLOCKED;
char     gBadgeId[32]  = "";
uint8_t  gBadgeMac[6]  = {0};
float    gBadgeBattery = 0.0f;
bool     gBadgeSeen    = false;
volatile uint32_t gBadgeLastTime = 0;

// Vibration RMS window: 100 samples at 100 Hz = 1 second, values in g.
static const int VIB_WINDOW = 100;
float vSumX = 0.0f, vSumY = 0.0f, vSumZ = 0.0f;
float vSumSqX = 0.0f, vSumSqY = 0.0f, vSumSqZ = 0.0f;
float vMinX = 1e9f, vMaxX = -1e9f;
float vMinY = 1e9f, vMaxY = -1e9f;
float vMinZ = 1e9f, vMaxZ = -1e9f;
int   vCount = 0;

// ---------- ADXL Helpers ----------
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

void checkAndRecoverADXL() {
  if (adxlRead(ADXL_REG_POWER_CTL) != 0x08) {
    adxlWrite(ADXL_REG_BW_RATE, 0x0A);
    adxlWrite(ADXL_REG_DATA_FORMAT, 0x0B);
    adxlWrite(ADXL_REG_POWER_CTL, 0x00);
    delayMicroseconds(50);
    adxlWrite(ADXL_REG_POWER_CTL, 0x08);
    delayMicroseconds(50);
  }
}

bool initADXL() {
  pinMode(ADXL_CS, OUTPUT);
  digitalWrite(ADXL_CS, HIGH);
  SPI.begin(ADXL_SCK, ADXL_MISO, ADXL_MOSI, ADXL_CS);
  delay(50);
  if (adxlRead(ADXL_REG_DEVID) != 0xE5) return false;
  adxlWrite(ADXL_REG_BW_RATE, 0x0A);       // 100 Hz
  adxlWrite(ADXL_REG_DATA_FORMAT, 0x0B);   // +/-16g full resolution
  adxlWrite(ADXL_REG_POWER_CTL, 0x00);
  delay(10);
  adxlWrite(ADXL_REG_POWER_CTL, 0x08);     // Measurement mode
  delay(10);
  return true;
}

void readAxes(float &ax, float &ay, float &az) {
  checkAndRecoverADXL();
  uint8_t x0 = adxlRead(0x32), x1 = adxlRead(0x33);
  uint8_t y0 = adxlRead(0x34), y1 = adxlRead(0x35);
  uint8_t z0 = adxlRead(0x36), z1 = adxlRead(0x37);
  const float scale = 0.0039f;  // ADXL345 FULL_RES: 3.9 mg/LSB, output in g
  ax = (int16_t)((x1 << 8) | x0) * scale;
  ay = (int16_t)((y1 << 8) | y0) * scale;
  az = (int16_t)((z1 << 8) | z0) * scale;
}

// RMS of the dynamic acceleration over a 1-second window. Subtracting each
// axis mean removes the 1 g gravity component; crest factor is peak/RMS.
void accumulateVibration(float ax, float ay, float az) {
  vSumX += ax; vSumY += ay; vSumZ += az;
  vSumSqX += ax * ax; vSumSqY += ay * ay; vSumSqZ += az * az;
  if (ax < vMinX) vMinX = ax;
  if (ax > vMaxX) vMaxX = ax;
  if (ay < vMinY) vMinY = ay;
  if (ay > vMaxY) vMaxY = ay;
  if (az < vMinZ) vMinZ = az;
  if (az > vMaxZ) vMaxZ = az;
  vCount++;

  if (vCount < VIB_WINDOW) return;

  const float n = (float)VIB_WINDOW;
  const float mx = vSumX / n;
  const float my = vSumY / n;
  const float mz = vSumZ / n;
  const float varX = vSumSqX / n - mx * mx;
  const float varY = vSumSqY / n - my * my;
  const float varZ = vSumSqZ / n - mz * mz;
  const float rms = sqrtf(fmaxf(0.0f, varX) + fmaxf(0.0f, varY) + fmaxf(0.0f, varZ));

  const float px = fmaxf(fabsf(vMaxX - mx), fabsf(vMinX - mx));
  const float py = fmaxf(fabsf(vMaxY - my), fabsf(vMinY - my));
  const float pz = fmaxf(fabsf(vMaxZ - mz), fabsf(vMinZ - mz));
  const float peak = sqrtf(px * px + py * py + pz * pz);

  gRms = rms;
  gCrestFactor = (rms > 0.01f) ? (peak / rms) : 0.0f;

  vSumX = vSumY = vSumZ = 0.0f;
  vSumSqX = vSumSqY = vSumSqZ = 0.0f;
  vMinX = vMinY = vMinZ = 1e9f;
  vMaxX = vMaxY = vMaxZ = -1e9f;
  vCount = 0;
}

// ---------- Blynk Handlers ----------
BLYNK_WRITE(V0) {
  int switchVal = param.asInt();
  blynkMotorRequested = (switchVal == 1);
  Serial.printf("[BLYNK] Remote Switch V0: %s\r\n", blynkMotorRequested ? "POWER ON" : "POWER OFF");
}

BLYNK_CONNECTED() {
  Serial.println("[BLYNK] Connected to Blynk Cloud! Syncing V0 state...");
  Blynk.syncVirtual(V0);
}

// ---------- MQTT Callbacks ----------
void mqttCallback(char* topic, byte* payload, unsigned int len) {
  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, payload, len)) return;
  const char* cmd = doc["command"] | "";

  if (strcmp(cmd, "LOCKOUT") == 0) {
    gInterlock = true;
    Serial.println("[SAFETY] LOCKOUT commanded via MQTT! Motor stopped.");
    if (Blynk.connected()) {
      Blynk.virtualWrite(V0, 0); // Reset button in Blynk app
    }
  } else if (strcmp(cmd, "RESET") == 0) {
    gInterlock = false;
    Serial.println("[SAFETY] Lockout RESET via MQTT.");
  } else if (strcmp(cmd, "START") == 0) {
    blynkMotorRequested = true;
    if (Blynk.connected()) {
      Blynk.virtualWrite(V0, 1);
    }
  } else if (strcmp(cmd, "STOP") == 0) {
    blynkMotorRequested = false;
    if (Blynk.connected()) {
      Blynk.virtualWrite(V0, 0);
    }
  }
}

void ensureMqtt() {
  if (mqtt.connected()) return;

  // Do not block the telemetry loop with a connect attempt every 10 ms.
  static uint32_t lastAttempt = 0;
  uint32_t now = millis();
  if (now - lastAttempt < 5000) return;
  lastAttempt = now;

  String clientId = String("armor-node-") + DEVICE_ID;
  if (mqtt.connect(clientId.c_str())) {
    String topic = String("machinocare/v1/devices/") + DEVICE_ID + "/interlock";
    mqtt.subscribe(topic.c_str(), 1);
    Serial.printf("[MQTT] Connected to broker %s & Subscribed to interlock topic\r\n", MQTT_BROKER);
  } else {
    Serial.printf("[MQTT] Connect failed to broker %s, rc=%d\r\n", MQTT_BROKER, mqtt.state());
  }
}

// ---------- ESP-NOW (Wearable Badge Beacon) ----------
typedef struct {
  uint8_t  sender_mac[6];
  char     badge_id[32];
  uint32_t sequence_num;
  float    battery_voltage;
} BadgeBeacon;

void onEspNowRecv(const esp_now_recv_info_t* info, const uint8_t* data, int len) {
  if (len < (int)sizeof(BadgeBeacon)) return;

  BadgeBeacon beacon;
  memcpy(&beacon, data, sizeof(beacon));
  beacon.badge_id[sizeof(beacon.badge_id) - 1] = '\0';

  int rssi = (info && info->rx_ctrl) ? info->rx_ctrl->rssi : 0;
  if (!gEmaInit) { gEmaRssi = (float)rssi; gEmaInit = true; }
  else            { gEmaRssi = EMA_ALPHA * rssi + (1.0f - EMA_ALPHA) * gEmaRssi; }

  const uint8_t* src = (info && info->src_addr) ? info->src_addr : beacon.sender_mac;
  portENTER_CRITICAL(&gBadgeMux);
  strncpy(gBadgeId, beacon.badge_id, sizeof(gBadgeId) - 1);
  gBadgeId[sizeof(gBadgeId) - 1] = '\0';
  memcpy(gBadgeMac, src, sizeof(gBadgeMac));
  gBadgeBattery = beacon.battery_voltage;
  gBadgeSeen = true;
  gBadgeLastTime = millis();
  portEXIT_CRITICAL(&gBadgeMux);
}

// ---------- Core 0: Safety & Motor Actuation + Sensor Loop ----------
void core0Task(void* pv) {
  const TickType_t period = pdMS_TO_TICKS(10); // 100 Hz sampling
  TickType_t last = xTaskGetTickCount();

  while (true) {
    // --- Safe Motor Actuation ---
    bool shouldRun = blynkMotorRequested && !gInterlock;
    if (shouldRun) {
      digitalWrite(PIN_RELAY, RELAY_ON);   // Connect 12 V via relay
      digitalWrite(PIN_IN1, HIGH);
      digitalWrite(PIN_IN2, LOW);
      analogWrite(PIN_ENA, 170);           // ~67 % duty PWM speed
      motorRunning = true;
    } else {
      analogWrite(PIN_ENA, 0);             // Stop PWM
      digitalWrite(PIN_IN1, LOW);
      digitalWrite(PIN_IN2, LOW);
      digitalWrite(PIN_RELAY, RELAY_OFF);  // Cut 12 V via relay
      motorRunning = false;
    }

    // --- Sensor Acquisition ---
    float ax, ay, az;
    readAxes(ax, ay, az);
    accumulateVibration(ax, ay, az);

    gVoltageV  = ina219.getBusVoltage_V();
    gCurrentMa = ina219.getCurrent_mA();

    // DS18B20 conversion takes ~750 ms. Request it without blocking and read
    // the result on a later iteration so the 100 Hz sampling loop stays intact.
    static uint32_t lastTempRequest = 0;
    static bool tempConversionPending = false;
    uint32_t nowMs = millis();

    if (!tempConversionPending && (nowMs - lastTempRequest >= 1000)) {
      tempSensor.requestTemperatures();
      lastTempRequest = nowMs;
      tempConversionPending = true;
    }
    if (tempConversionPending && (nowMs - lastTempRequest >= 800)) {
      float tc = tempSensor.getTempCByIndex(0);
      if (tc != DEVICE_DISCONNECTED_C && tc != 85.0f && tc > -50.0f) {
        gTempC = tc;
      }
      tempConversionPending = false;
    }

    vTaskDelayUntil(&last, period);
  }
}

// ---------- Core 1: Network, Blynk, MQTT & Telemetry ----------
void core1Task(void* pv) {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);

  Serial.printf("[WiFi] Connecting to SSID: '%s'...\r\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int retry = 0;
  while (WiFi.status() != WL_CONNECTED && retry < 30) {
    delay(400);
    Serial.print(".");
    retry++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\r\n[WiFi] Connected to '%s'! IP: %s\r\n", WIFI_SSID, WiFi.localIP().toString().c_str());
    // Wall-clock time for telemetry timestamps (UTC).
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    Blynk.config(BLYNK_AUTH_TOKEN);
    Blynk.connect();
  } else {
    Serial.println("\r\n[WiFi] Connection timeout. Make sure phone hotspot is ON (and 'Maximize Compatibility' / 2.4 GHz is enabled). Continuing in offline mode...");
  }

  // ESP-NOW init
  if (esp_now_init() == ESP_OK) {
    esp_now_register_recv_cb(onEspNowRecv);
    Serial.println("[ESP-NOW] Initialized successfully");
  } else {
    Serial.println("[ESP-NOW] Init FAILED");
  }

  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(mqttCallback);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(2);

  uint32_t lastTelemetry = 0;
  uint32_t lastBreachCheck = 0;
  uint32_t lastWiFiRetry = 0;
  uint32_t lastBreachPublish = 0;
  bool breachLatched = false;

  while (true) {
    uint32_t now = millis();

    if (WiFi.status() == WL_CONNECTED) {
      ensureMqtt();
      mqtt.loop();
      Blynk.run();
    } else {
      if (now - lastWiFiRetry >= 10000) {
        lastWiFiRetry = now;
        Serial.println("[WiFi] Re-attempting connection to 'ARMOR'...");
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
      }
    }

    // 1 Hz Telemetry
    if (now - lastTelemetry >= 1000) {
      lastTelemetry = now;

      bool badgeActive = gBadgeSeen && (now - gBadgeLastTime < 2500);
      float distEst = gEmaInit ? powf(10.0f, (RSSI_AT_1M - gEmaRssi) / (10.0f * PATH_LOSS_N)) : 99.0f;
      char badgeStr[48];
      if (badgeActive) {
        snprintf(badgeStr, sizeof(badgeStr), "%s (%ddBm, ~%.1fm)", gBadgeId, (int)roundf(gEmaRssi), distEst);
      } else {
        snprintf(badgeStr, sizeof(badgeStr), "NOT SEEN");
      }

      char mqttStr[48];
      if (mqtt.connected()) {
        snprintf(mqttStr, sizeof(mqttStr), "CONNECTED (%s)", MQTT_BROKER);
      } else {
        snprintf(mqttStr, sizeof(mqttStr), "OFFLINE");
      }

      Serial.printf("[TELEMETRY] Temp: %4.1f C | Bus: %5.2f V | Current: %5.1f mA | Motor: %-7s | Blynk: %-7s | MQTT: %-25s | Badge: %s\r\n",
                    gTempC, gVoltageV, gCurrentMa,
                    motorRunning ? "RUNNING" : "STOPPED",
                    Blynk.connected() ? "ONLINE" : "OFFLINE",
                    mqttStr,
                    badgeStr);

      // Push Live Telemetry to Blynk Virtual Pins
      if (Blynk.connected()) {
        Blynk.virtualWrite(V1, gVoltageV);
        Blynk.virtualWrite(V2, gCurrentMa);
        Blynk.virtualWrite(V3, gTempC);
        Blynk.virtualWrite(V4, gRms);
      }

      // Publish Telemetry to MQTT
      if (mqtt.connected()) {
        StaticJsonDocument<320> doc;
        doc["device_id"]   = DEVICE_ID;
        time_t epochSec = time(nullptr);
        if (epochSec > 1700000000) {           // NTP synced
          doc["timestamp"] = (uint64_t)epochSec * 1000ULL;
        }
        doc["motor_state"] = gInterlock ? "LOCKED" : (motorRunning ? "RUNNING" : "IDLE");
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

    // 10 Hz Proximity Breach Check (edge-triggered, repeat every 10 s while inside)
    if (now - lastBreachCheck >= 100) {
      lastBreachCheck = now;

      if (gEmaInit) {
        bool inside = breachLatched ? (gEmaRssi > RSSI_EXIT)
                                    : (gEmaRssi > RSSI_ENTER);

        if (!inside) {
          breachLatched = false;
        } else if (!breachLatched || (now - lastBreachPublish >= 10000)) {
          breachLatched = true;
          lastBreachPublish = now;

          char badgeId[32];
          uint8_t mac[6];
          float battery;
          portENTER_CRITICAL(&gBadgeMux);
          strncpy(badgeId, gBadgeId, sizeof(badgeId) - 1);
          badgeId[sizeof(badgeId) - 1] = '\0';
          memcpy(mac, gBadgeMac, sizeof(mac));
          battery = gBadgeBattery;
          portEXIT_CRITICAL(&gBadgeMux);

          char macStr[18];
          snprintf(macStr, sizeof(macStr), "%02X:%02X:%02X:%02X:%02X:%02X",
                   mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

          float distance = powf(10.0f, (RSSI_AT_1M - gEmaRssi) / (10.0f * PATH_LOSS_N));

          if (mqtt.connected()) {
            StaticJsonDocument<384> doc;
            doc["device_id"]      = DEVICE_ID;
            doc["worker_id"]      = badgeId;
            doc["badge_id"]       = badgeId;
            doc["badge_mac"]      = macStr;
            doc["rssi_raw"]       = (int)roundf(gEmaRssi);
            doc["rssi_smoothed"]  = gEmaRssi;
            doc["distance_est_m"] = distance;
            doc["battery_v"]      = battery;
            time_t epochSec = time(nullptr);
            if (epochSec > 1700000000) {
              doc["timestamp"] = (uint64_t)epochSec * 1000ULL;
            }
            char buf[512];
            serializeJson(doc, buf);
            mqtt.publish("machinocare/v1/events/proximity", buf, false);
            Serial.printf("[SAFETY] Badge %s (%s) at %.2f m (RSSI %.1f)\r\n",
                          badgeId, macStr, distance, gEmaRssi);
          }
        }
      }
    }

    delay(10);
  }
}

// ---------- setup & loop ----------
void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\r\n=======================================================");
  Serial.println("  ARMOR - Machine Node + Blynk IoT Remote Actuation    ");
  Serial.println("=======================================================");

  // Relay Pins (Safe initialization: start OFF)
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_RELAY2, OUTPUT);
  digitalWrite(PIN_RELAY, RELAY_OFF);
  digitalWrite(PIN_RELAY2, RELAY_OFF);

  // Motor Driver Pins (Start stopped)
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);

  // PWM setup
  ledcAttach(PIN_ENA, 5000, 8);
  analogWrite(PIN_ENA, 0);

  // Sensors
  Wire.begin(I2C_SDA, I2C_SCL);
  ina219.begin();
  tempSensor.begin();
  tempSensor.setWaitForConversion(false);  // keep the 100 Hz loop non-blocking

  if (!initADXL()) {
    Serial.println("[ADXL345] Init FAILED (check wiring)");
  } else {
    Serial.println("[ADXL345] Init OK");
  }

  // Dual-Core FreeRTOS Tasks
  xTaskCreatePinnedToCore(core0Task, "core0", 4096, NULL, 2, NULL, 0);
  xTaskCreatePinnedToCore(core1Task, "core1", 8192, NULL, 1, NULL, 1);
  Serial.println("[SYSTEM] Core 0 (Actuation & Sensors) + Core 1 (Network, Blynk, MQTT) running");
}

void loop() {
  delay(100);
}