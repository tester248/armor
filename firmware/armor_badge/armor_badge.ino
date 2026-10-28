/*
 * ARMOR - Wearable Badge Firmware (ESP32)
 * ---------------------------------------
 * Broadcasts & Unicasts ESP-NOW beacons to the specific ARMOR Machine Node.
 * Uses Auto-Channel detection to match the Machine Node's hotspot channel,
 * and Unicast MAC pairing to avoid collisions in a crowded hackathon room.
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// ---------- Config ----------
const char* BADGE_ID   = "BADGE-EMP-402";
const char* TARGET_SSID= "ARMOR"; // Machine Node's WiFi network (used to auto-detect channel)

// Target Machine Node Hardware MAC Address (b0:3f:d3:71:02:d8)
uint8_t targetNodeMac[] = {0xB0, 0x3F, 0xD3, 0x71, 0x02, 0xD8};
uint8_t broadcastMac[]  = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

uint8_t activeChannel = 6; // Default channel (auto-updated via scan at boot)

#define PIN_BUZZER   25
#define PIN_LED      26
#define PIN_BATT_ADC 34   // Battery voltage divider

// ---------- Beacon payload (must match machine node's BadgeBeacon struct) ----------
typedef struct {
  uint8_t  sender_mac[6];
  char     badge_id[32];
  uint32_t sequence_num;
  float    battery_voltage;
} BadgeBeacon;

BadgeBeacon beacon;
uint32_t seq = 0;
volatile bool lastAckReceived = false;

void onDataSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  lastAckReceived = (status == ESP_NOW_SEND_SUCCESS);
}

float readBattery() {
  int raw = analogRead(PIN_BATT_ADC);
  return (raw / 4095.0f) * 3.3f * 2.0f;
}

int32_t scanForTargetChannel(const char* ssid) {
  Serial.printf("[SCAN] Scanning 2.4 GHz channels for '%s'...\r\n", ssid);
  int n = WiFi.scanNetworks(false, false);
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i) == ssid) {
      int32_t ch = WiFi.channel(i);
      Serial.printf("[SCAN] Found '%s' on Channel %d (RSSI: %d dBm)\r\n", ssid, ch, WiFi.RSSI(i));
      WiFi.scanDelete();
      return ch;
    }
  }
  WiFi.scanDelete();
  return -1;
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
  delay(100);

  // Auto-detect the channel of the ARMOR hotspot
  int32_t detectedChannel = scanForTargetChannel(TARGET_SSID);
  if (detectedChannel > 0) {
    activeChannel = (uint8_t)detectedChannel;
    Serial.printf("[WiFi] Automatically synced to Channel %d\r\n", activeChannel);
  } else {
    Serial.printf("[WiFi] Hotspot '%s' not found during scan. Using default Channel %d\r\n",
                  TARGET_SSID, activeChannel);
  }

  // Set local radio channel to match
  esp_wifi_set_promiscuous(true);
  esp_wifi_set_channel(activeChannel, WIFI_SECOND_CHAN_NONE);
  esp_wifi_set_promiscuous(false);

  // Read hardware MAC address
  uint8_t mac[6];
  esp_wifi_get_mac(WIFI_IF_STA, mac);
  memcpy(beacon.sender_mac, mac, 6);
  strncpy(beacon.badge_id, BADGE_ID, sizeof(beacon.badge_id) - 1);
  beacon.badge_id[sizeof(beacon.badge_id) - 1] = '\0';

  Serial.println("\r\n=======================================================");
  Serial.println("  ARMOR - Wearable Badge Node (Paired Unicast Broadcaster) ");
  Serial.printf("  Badge ID : %s\r\n", BADGE_ID);
  Serial.printf("  Badge MAC: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
                mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  Serial.printf("  Target Node MAC: %02X:%02X:%02X:%02X:%02X:%02X\r\n",
                targetNodeMac[0], targetNodeMac[1], targetNodeMac[2],
                targetNodeMac[3], targetNodeMac[4], targetNodeMac[5]);
  Serial.printf("  Channel  : %d\r\n", activeChannel);
  Serial.println("=======================================================");

  if (esp_now_init() != ESP_OK) {
    Serial.println("[ESP-NOW] Init FAILED");
    return;
  }
  esp_now_register_send_cb(onDataSent);

  // Register Unicast Peer (Machine Node)
  esp_now_peer_info_t peerNode = {};
  memcpy(peerNode.peer_addr, targetNodeMac, 6);
  peerNode.channel = activeChannel;
  peerNode.encrypt = false;
  if (esp_now_add_peer(&peerNode) == ESP_OK) {
    Serial.println("[ESP-NOW] Machine Node unicast peer registered OK");
  } else {
    Serial.println("[ESP-NOW] Warning: Failed to add Machine Node peer");
  }

  // Register Broadcast Peer (Channel must be 0 for broadcast in ESP-NOW)
  esp_now_peer_info_t peerBcast = {};
  memcpy(peerBcast.peer_addr, broadcastMac, 6);
  peerBcast.channel = 0;
  peerBcast.encrypt = false;
  esp_now_add_peer(&peerBcast);
}

void loop() {
  beacon.sequence_num    = seq++;
  beacon.battery_voltage = readBattery();

  // Reset ACK status for this cycle
  lastAckReceived = false;

  // Send Unicast directly to our paired Machine Node
  esp_now_send(targetNodeMac, (uint8_t*)&beacon, sizeof(beacon));

  // Also send broadcast so any backup listeners can hear
  esp_now_send(broadcastMac, (uint8_t*)&beacon, sizeof(beacon));

  // Allow brief window for 802.11 hardware ACK callback
  delay(10);

  // Visual Confirmation: Flash LED ONLY when the Machine Node acknowledges receipt
  if (lastAckReceived) {
    digitalWrite(PIN_LED, HIGH);
    delay(25);
    digitalWrite(PIN_LED, LOW);
    delay(165);
  } else {
    digitalWrite(PIN_LED, LOW);
    delay(190);
  }

  if (seq % 5 == 0) {
    // Print 1 Hz heartbeat to Serial Monitor
    Serial.printf("[BEACON #%u] %s | Batt: %.2f V | Ch: %d\r\n",
                  beacon.sequence_num,
                  lastAckReceived ? "ACK RECEIVED from Node (Paired & Active)" : "NO ACK (Node OFF / Out of Range)",
                  beacon.battery_voltage,
                  activeChannel);
  }
}
