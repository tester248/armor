# ARMOR — Hardware Pinout & Wiring (Authoritative)

Single source of truth for the ESP32 machine node and wearable badge wiring.
Supersedes the GPIO 23 Enable note in the merged build spec (Enable is GPIO 25;
GPIO 23 is ADXL345 MOSI — see the conflict note below).

## 1. ESP32 Machine Node

### L298N Motor Driver
| Terminal | ESP32 GPIO | Function |
|---|---|---|
| ENA | GPIO 25 | Hardware PWM (5 kHz, 8-bit). Speed control. Remove jumper cap. |
| IN1 | GPIO 26 | Direction A (HIGH = forward) |
| IN2 | GPIO 27 | Direction B (LOW = forward) |

### 2-Channel Relay Module (active-LOW)
| Terminal | ESP32 GPIO | Function |
|---|---|---|
| IN1 | GPIO 32 | Master 12 V motor power cutoff / E-Stop (hard lockout) |
| IN2 | GPIO 33 | Auxiliary / spare relay trigger |

### INA219 Current Sensor (I2C, addr 0x40)
| Terminal | ESP32 GPIO |
|---|---|
| SDA | GPIO 21 |
| SCL | GPIO 22 |

### DS18B20 Temp Probe (1-Wire)
| Terminal | ESP32 GPIO | Notes |
|---|---|---|
| DATA | GPIO 15 | 4.7 kΩ pull-up to 3.3 V |

### ADXL345 Accelerometer (SPI Mode 3, 1 MHz)
| Terminal | ESP32 GPIO |
|---|---|
| CS | GPIO 5 |
| SCL / SCK | GPIO 18 |
| SDA / MOSI | GPIO 23 |
| SDO / MISO | GPIO 19 |
| INT1, INT2 | N/C |

### Conflict resolution
The merged build spec text said "L298N Enable pin (GPIO 23)". That collides with
ADXL345 MOSI (GPIO 23). The authoritative design uses **ENA = GPIO 25** (PWM) plus a
**relay on GPIO 32** for the hard 12 V cutoff. Update any code/docs that still say
"Enable on GPIO 23".

## 2. Lockout actuation (two layers)
1. **Hard (relay, GPIO 32, active-LOW):** cuts 12 V to the L298N — motor stops
   regardless of ENA. This is the safety-critical path; target < 50 ms GPIO action.
2. **Soft (ENA, GPIO 25):** PWM driven LOW to stop motor drive.

On `LOCKOUT`: relay LOW + ENA LOW. On `RESET`: relay HIGH (drive stays stopped until a
`START` is received). `START`/`STOP` arrive on the same topic; the firmware should only
run the motor when `motor_requested && !interlock`. `BENCH_ON` / `BENCH_OFF` also arrive
there and suppress ESP-NOW proximity lockouts during calibration.

## 3. Power & ground
- 3.3 V rail: INA219 VCC, DS18B20 VDD, ADXL345 VCC, 4.7 kΩ pull-up (leg 2).
- 5 V rail: relay module VCC (coil power) from ESP32 VIN/5 V.
- Common ground: INA219, DS18B20, ADXL345, relay, L298N GND, ESP32 GND.
- High-current path: 12 V adapter (+) → INA219 Vin+ → Relay 1 COM → Relay 1 NO →
  L298N +12 V. Adapter GND → L298N GND. L298N OUT1/OUT2 → RS-555 motor.
- L298N onboard 5 V jumper kept in place (internal 5 V regulator from 12 V).

## 4. Wearable Badge (ESP32)
- ESP-NOW broadcaster only: broadcasts `sender_mac`, `badge_id`, `sequence_num`,
  `battery_voltage`. No `raw_rssi` (RSSI is measured by the machine node receiver).
- Buzzer + status LEDs on the badge for proximity alerts.
- Powered by LiPo + charger module.
