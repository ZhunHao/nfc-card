#ifndef CARD_LED_PAIRS_H
#define CARD_LED_PAIRS_H
#include <stdint.h>
/* Transcribed from fab/card-v1/netlist.xml (Eeschema 10.0.6, 2026-09-15).
 * Dn pin 2 is anode, pin 1 cathode. CP0..4 connect via R1..5 pin 2;
 * resistor pin 1 connects U2 pins 17,18,19,2,3 = PA1..5.
 * Rows: anode CP, cathode CP, output PORTA mask, high PORTA mask.
 * check_board_fixture.py independently traces every row through the netlist.
 */
static const uint8_t card_led_pairs[20][4] = {
    {0,1,0x06,0x02}, {0,2,0x0a,0x02}, {0,3,0x12,0x02}, {0,4,0x22,0x02},
    {1,0,0x06,0x04}, {1,2,0x0c,0x04}, {1,3,0x14,0x04}, {1,4,0x24,0x04},
    {2,0,0x0a,0x08}, {2,1,0x0c,0x08}, {2,3,0x18,0x08}, {2,4,0x28,0x08},
    {3,0,0x12,0x10}, {3,1,0x14,0x10}, {3,2,0x18,0x10}, {3,4,0x30,0x10},
    {4,0,0x22,0x20}, {4,1,0x24,0x20}, {4,2,0x28,0x20}, {4,3,0x30,0x20}
};
#endif
