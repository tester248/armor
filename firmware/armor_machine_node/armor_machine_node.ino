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

// ---------- WiFi & MQTT Config ----------
const char* WIFI_SSID     = "ARMOR";
const char* WIFI_PASSWORD = "12345678";
const char* MQTT_BROKER   = "10.24.103.187";   // Backend host IP on hotspot
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
static const float EMA_ALPHA      = 0.35f;
static const float RSSI_THRESHOLD = -65.0f;
float gEmaRssi = 0.0f;
bool  gEmaInit = false;

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
  const float scale = 0.0039f * 9.80665f;
  ax = (int16_t)((x1 << 8) | x0) * scale;
  ay = (int16_t)((y1 << 8) | y0) * scale;
  az = (int16_t)((z1 << 8) | z0) * scale;
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
  String clientId = String("armor-node-") + DEVICE_ID;
  if (mqtt.connect(clientId.c_str())) {
    String topic = String("machinocare/v1/devices/") + DEVICE_ID + "/interlock";
    mqtt.subscribe(topic.c_str(), 1);
    Serial.println("[MQTT] Connected & Subscribed to interlock topic");
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
  int rssi = (info && info->rx_ctrl) ? info->rx_ctrl->rssi : 0;
  if (!gEmaInit) { gEmaRssi = (float)rssi; gEmaInit = true; }
  else            { gEmaRssi = EMA_ALPHA * rssi + (1.0f - EMA_ALPHA) * gEmaRssi; }
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
    gRms = sqrtf(ax*ax + ay*ay + az*az);
    gCrestFactor = 0.0f;

    gVoltageV  = ina219.getBusVoltage_V();
    gCurrentMa = ina219.getCurrent_mA();

    tempSensor.requestTemperatures();
    float tc = tempSensor.getTempCByIndex(0);
    if (tc != DEVICE_DISCONNECTED_C && tc != 85.0f && tc > -50.0f) {
      gTempC = tc;
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

  uint32_t lastTelemetry = 0;
  uint32_t lastBreachCheck = 0;
  uint32_t lastWiFiRetry = 0;

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

      Serial.printf("[TELEMETRY] Temp: %4.1f C | Bus: %5.2f V | Current: %5.1f mA | Vib: %4.2f | Motor: %-7s | Blynk: %-7s | MQTT: %-9s\r\n",
                    gTempC, gVoltageV, gCurrentMa, gRms,
                    motorRunning ? "RUNNING" : "STOPPED",
                    Blynk.connected() ? "ONLINE" : "OFFLINE",
                    mqtt.connected() ? "CONNECTED" : "OFFLINE");

      // Push Live Telemetry to Blynk Virtual Pins
      if (Blynk.connected()) {
        Blynk.virtualWrite(V1, gVoltageV);
        Blynk.virtualWrite(V2, gCurrentMa);
        Blynk.virtualWrite(V3, gTempC);
        Blynk.virtualWrite(V4, gRms);
      }

      // Publish Telemetry to MQTT
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

    // 10 Hz Proximity Breach Check
    if (now - lastBreachCheck >= 100) {
      lastBreachCheck = now;
      if (gEmaInit && gEmaRssi > RSSI_THRESHOLD && mqtt.connected()) {
        StaticJsonDocument<256> doc;
        doc["device_id"]      = DEVICE_ID;
        doc["worker_id"]      = "BADGE-EMP-402";
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
