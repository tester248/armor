/*
 * ARMOR - Wearable Badge Firmware (ESP32)
 * ---------------------------------------
 * Broadcasts ESP-NOW beacons: sender_mac, badge_id, sequence_num, battery_voltage.
 * No raw_rssi (RSSI is measured by the machine node receiver).
 * Buzzer sounds on threshold breach / unacknowledged breach.
 *
 * Libraries: none beyond ESP32 core (esp_now, WiFi).
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// ---------- Config ----------
const char* BADGE_ID = "BADGE-EMP-402";

#define PIN_BUZZER  25
#define PIN_LED     26
#define PIN_BATT_ADC 34   // battery voltage divider

// ---------- Beacon payload (must match machine node's BadgeBeacon struct) ----------
typedef struct {
  uint8_t  sender_mac[6];
  char     badge_id[32];
  uint32_t sequence_num;
  float    battery_voltage;
} BadgeBeacon;

BadgeBeacon beacon;
uint32_t seq = 0;

uint8_t broadcastMac[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

float readBattery() {
  int raw = analogRead(PIN_BATT_ADC);
  // Adjust divider ratio to your hardware
  return (raw / 4095.0f) * 3.3f * 2.0f;
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED, LOW);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW init failed");
    return;
  }

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, broadcastMac, 6);
  peer.channel = 0;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  uint8_t mac[6];
  WiFi.macAddress(mac);
  memcpy(beacon.sender_mac, mac, 6);
  strncpy(beacon.badge_id, BADGE_ID, sizeof(beacon.badge_id) - 1);
  beacon.badge_id[sizeof(beacon.badge_id) - 1] = '\0';
}

void loop() {
  beacon.sequence_num   = seq++;
  beacon.battery_voltage = readBattery();

  esp_err_t res = esp_now_send(broadcastMac, (uint8_t*)&beacon, sizeof(beacon));
  if (res != ESP_OK) {
    Serial.println("ESP-NOW send failed");
  }

  // Short beep every N beacons to indicate liveness (optional)
  delay(200);   // 5 Hz beacon rate
}
