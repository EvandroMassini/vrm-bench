/* One RAM byte, address chosen by the host, always checked against the expected value.
 * Blocked: outside 10h–90h, personality 14h, mask-zero bytes, OTP clock 71h, enables 88h/89h.
 * A failed apply rolls back to the expected byte before the USB reply. MTP is not touched.
 */
static bool pbyte_blocked(uint8_t reg) {
    if (reg<0x10 || reg>0x90) return true;
    switch (reg) {
        case 0x14: case 0x4F: case 0x50: case 0x71:
        case 0x88: case 0x89: case 0x8C:
            return true;
        default:
            return false;
    }
}
static void pbyte(uint8_t reg, uint8_t expected, uint8_t target) {
    uint8_t model=0, mode=0, original=0, observed=0, final_value=0;
    if (pbyte_blocked(reg)) {reply("ERR PBYTE_BLOCKED");return;}
    if (expected==target) {reply("ERR PBYTE_SAME");return;}
    if (!rt_read(0x0D,&model)) {rt_prewrite_error(0x0D);return;}
    if (model!=0x44) {reply("ERR RAMTEST_MODEL");return;}
    if (!rt_read(0x14,&mode)) {rt_prewrite_error(0x14);return;}
    if (!(mode&0x20)) {reply("ERR PBYTE_MODE");return;}
    if (!rt_read(reg,&original)) {rt_prewrite_error(reg);return;}
    if (original!=expected) {reply("ERR PBYTE_STALE");return;}
    bool ack=rt_write_at(reg,target);
    sleep_ms(2);
    bool read_ok=rt_read(reg,&observed);
    bool applied=ack && read_ok && observed==target;
    bool rollback=false;
    if (!applied) {
        rollback=true;
        rt_write_at(reg,expected);
        sleep_ms(2);
    }
    bool final_ok=rt_read(reg,&final_value);
    if (applied && (!final_ok || final_value!=target)) {
        applied=false;rollback=true;
        rt_write_at(reg,expected);sleep_ms(2);
        final_ok=rt_read(reg,&final_value);
    }
    char response[96];
    snprintf(response,sizeof(response),"OK PBYTE %02X %02X %02X %02X %02X %02X",
        (unsigned)reg,(unsigned)applied,(unsigned)rollback,(unsigned)final_ok,
        (unsigned)final_value,(unsigned)mode);
    reply(response);
}
