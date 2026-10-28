/*
 * ARMOR - Wearable Badge Firmware (ESP32)
 * ---------------------------------------
 * Broadcasts & Unicasts ESP-NOW beacons to the specific ARMOR Machine Node.
 * Uses Auto-Channel detection to match the Machine Node's hotspot channel,
 * and Unicast MAC pairing to avoid collisions in a crowded hackathon room.
 * Receives 2-way range feedback from Machine Node and drives reactive
 * LED strobe & buzzer alarms:
 *   - Zone 2 (Danger / Breach < 1.2m): Rapid emergency strobe + buzzer alarm
 *   - Zone 1 (Safe Demo Zone 1.3m-3.4m): Calm 1 Hz heartbeat pulse, silent buzzer
 *   - Zone 0 (Out of Range > 3.5m / Node OFF): LED and buzzer completely OFF
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// ---------- Config ----------
const char* BADGE_ID    = "BADGE-EMP-402";
const char* TARGET_SSID = "ARMOR"; // Machine Node's WiFi network (used to auto-detect channel)

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

// ---------- Feedback payload (received from Machine Node) ----------
typedef struct {
  char    badge_id[32];
  int8_t  node_rssi;
  uint8_t zone;       // 0 = Out of Range, 1 = Safe Demo Zone, 2 = Danger / Breach
  bool    interlock;
} NodeFeedback;

BadgeBeacon beacon;
uint32_t seq = 0;
volatile bool lastAckReceived = false;

// Reactive state from Machine Node
volatile uint8_t  gNodeZone       = 0;
volatile int8_t   gNodeRssi       = 0;
volatile bool     gNodeInterlock  = false;
volatile uint32_t gLastFeedbackMs = 0;

void onDataSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  lastAckReceived = (status == ESP_NOW_SEND_SUCCESS);
}

void onNodeFeedback(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
  if (len < (int)sizeof(NodeFeedback)) return;
  NodeFeedback fb;
  memcpy(&fb, data, sizeof(fb));
  fb.badge_id[sizeof(fb.badge_id) - 1] = '\0';

  // Filter strictly for this badge
  if (strcmp(fb.badge_id, BADGE_ID) != 0) return;

  gNodeZone       = fb.zone;
  gNodeRssi       = fb.node_rssi;
  gNodeInterlock  = fb.interlock;
  gLastFeedbackMs = millis();
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
  delay(500);

  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  digitalWrite(PIN_LED, LOW);

  // Power-on confirmation: 2 short chirps & blinks
  for (int i = 0; i < 2; i++) {
    digitalWrite(PIN_LED, HIGH);
    digitalWrite(PIN_BUZZER, HIGH);
    delay(50);
    digitalWrite(PIN_LED, LOW);
    digitalWrite(PIN_BUZZER, LOW);
    delay(50);
  }

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
  Serial.println("  ARMOR - Wearable Badge Node (Reactive Range Signaling)");
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
  esp_now_register_recv_cb(onNodeFeedback);

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

  lastAckReceived = false;

  // Send Unicast directly to our paired Machine Node
  esp_now_send(targetNodeMac, (uint8_t*)&beacon, sizeof(beacon));

  // Also send broadcast so any backup listeners can hear
  esp_now_send(broadcastMac, (uint8_t*)&beacon, sizeof(beacon));

  // Allow brief window for transmission & feedback processing
  delay(10);

  // Determine effective zone with 1500 ms safety timeout
  uint8_t effectiveZone = 0;
  if (millis() - gLastFeedbackMs < 1500) {
    effectiveZone = gNodeZone;
  } else {
    effectiveZone = 0; // Timeout: Machine Node is OFF or Badge walked out of range
  }

  // Reactive Visual & Audible Signaling
  if (effectiveZone == 2) {
    // ZONE 2: DANGER / PROXIMITY BREACH (< 1.2 m, RSSI > -52 dBm)
    // Rapid emergency strobe + buzzer alarm
    digitalWrite(PIN_LED, HIGH);
    digitalWrite(PIN_BUZZER, HIGH);
    delay(30);
    digitalWrite(PIN_LED, LOW);
    digitalWrite(PIN_BUZZER, LOW);
    delay(30);
    digitalWrite(PIN_LED, HIGH);
    digitalWrite(PIN_BUZZER, HIGH);
    delay(30);
    digitalWrite(PIN_LED, LOW);
    digitalWrite(PIN_BUZZER, LOW);
    delay(100);
  } else if (effectiveZone == 1) {
    // ZONE 1: SAFE DEMO ZONE (1.3 m - 3.4 m, -53 dBm to -65 dBm)
    // Calm 1 Hz heartbeat pulse (LED blinks once every second), Buzzer SILENT
    digitalWrite(PIN_BUZZER, LOW);
    if (seq % 5 == 0) {
      digitalWrite(PIN_LED, HIGH);
      delay(40);
      digitalWrite(PIN_LED, LOW);
      delay(150);
    } else {
      digitalWrite(PIN_LED, LOW);
      delay(190);
    }
  } else {
    // ZONE 0: OUT OF DEMO RANGE (> 3.5 m, RSSI < -65 dBm) or NODE OFF
    // LED and Buzzer completely OFF
    digitalWrite(PIN_LED, LOW);
    digitalWrite(PIN_BUZZER, LOW);
    delay(190);
  }

  // Serial Monitor Status (1 Hz)
  if (seq % 5 == 0) {
    const char* zStr = (effectiveZone == 2) ? "DANGER / BREACH (<1.2m)" :
                       (effectiveZone == 1) ? "SAFE DEMO ZONE (1.3m-3.4m)" :
                                              "OUT OF DEMO RANGE / NODE OFF";
    Serial.printf("[BADGE #%u] Zone: %-28s | Node RSSI: %3d dBm | ACK: %-3s | Batt: %4.2f V | Ch: %d\r\n",
                  beacon.sequence_num,
                  zStr,
                  (effectiveZone > 0) ? gNodeRssi : 0,
                  lastAckReceived ? "YES" : "NO",
                  beacon.battery_voltage,
                  activeChannel);
  }
}
