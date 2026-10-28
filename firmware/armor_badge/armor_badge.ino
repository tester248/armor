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
const uint8_t WIFI_CHANNEL = 6;   // Must match the Machine Node's WiFi channel (Hotspot channel)

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
  delay(1000);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED, LOW);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();

  // Fix: Set Wi-Fi radio to the same channel as Machine Node's WiFi AP
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  // Read hardware MAC address
  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  memcpy(beacon.sender_mac, mac, 6);
  strncpy(beacon.badge_id, BADGE_ID, sizeof(beacon.badge_id) - 1);
  beacon.badge_id[sizeof(beacon.badge_id) - 1] = '\0';

  Serial.println("\r\n=======================================================");
  Serial.println("  ARMOR - Wearable Badge Node (ESP-NOW Broadcaster)    ");
  Serial.printf("  Badge ID: %s | MAC: %02X:%02X:%02X:%02X:%02X:%02X | Ch: %d\r\n",
                BADGE_ID, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], WIFI_CHANNEL);
  Serial.println("=======================================================");

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESP-NOW] Init FAILED");
    return;
  }
  Serial.println("[ESP-NOW] Broadcast ready");

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, broadcastMac, 6);
  peer.channel = WIFI_CHANNEL;
  peer.encrypt = false;
  esp_now_add_peer(&peer);
}

void loop() {
  beacon.sequence_num   = seq++;
  beacon.battery_voltage = readBattery();

  // Pulse LED briefly on beacon transmission
  digitalWrite(PIN_LED, HIGH);
  esp_err_t res = esp_now_send(broadcastMac, (uint8_t*)&beacon, sizeof(beacon));
  delay(20);
  digitalWrite(PIN_LED, LOW);

  if (res != ESP_OK) {
    Serial.println("[ESP-NOW] Send failed");
  } else if (seq % 5 == 0) {
    // Print 1 Hz heartbeat to Serial Monitor
    Serial.printf("[BEACON #%u] Broadcast sent | Batt: %.2f V\r\n",
                  beacon.sequence_num, beacon.battery_voltage);
  }

  delay(180);   // ~5 Hz beacon rate total (20ms + 180ms)
}
