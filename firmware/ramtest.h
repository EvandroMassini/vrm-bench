/* Fixed bench experiment, not a general-purpose write command.
 * I2C 08, IR3567B model 44, AMD/GPU personality bit, register 26 exactly FF.
 * Change only loop-1 high nibble F->E; always attempt FF restoration locally.
 */
/* The SDK can return the last RX byte before STOP completes.
 * Wait for controller inactivity and a continuous bus-free interval, bounded.
 * This does not retry transactions or generate recovery clocks.
 */
static const char *rt_stage="NONE";
static int rt_code=0;
static bool rt_idle(void) {
    uint64_t deadline=time_us_64()+TIMEOUT_US, high_since=0;
    while (time_us_64()<deadline) {
        uint64_t now=time_us_64();
        bool idle=!(i2c_get_hw(i2c0)->status & I2C_IC_STATUS_ACTIVITY_BITS)
            && gpio_get(SDA_PIN) && gpio_get(SCL_PIN);
        if (!idle) high_since=0;
        else {
            if (!high_since) high_since=now;
            if (now-high_since>=10) return true;
        }
        sleep_us(1);
    }
    rt_code=PICO_ERROR_TIMEOUT;
    return false;
}
static bool rt_read(uint8_t reg, uint8_t *value) {
    rt_stage="IDLE_BEFORE";
    if (!rt_idle()) return false;
    rt_stage="POINTER";
    rt_code=i2c_write_timeout_us(i2c0,0x08,&reg,1,true,TIMEOUT_US);
    if (rt_code!=1) {bus_reset();return false;}
    /* No idle wait between pointer and read: this is a repeated START. */
    rt_stage="READ";
    rt_code=i2c_read_timeout_us(i2c0,0x08,value,1,false,TIMEOUT_US);
    if (rt_code!=1) {bus_reset();return false;}
    rt_stage="STOP";
    return rt_idle();
}
static bool rt_write_at(uint8_t reg, uint8_t value) {
    uint8_t bytes[2]={reg,value};
    rt_stage="IDLE_BEFORE";
    if (!rt_idle()) return false;
    rt_stage="WRITE";
    rt_code=i2c_write_timeout_us(i2c0,0x08,bytes,2,false,TIMEOUT_US);
    if (rt_code!=2) {bus_reset();return false;}
    rt_stage="STOP";
    return rt_idle();
}
static bool rt_write(uint8_t value) {
    return rt_write_at(0x26, value);
}
static void rt_prewrite_error(uint8_t reg) {
    char error[96];
    snprintf(error,sizeof(error),"ERR RAMTEST_PRECHECK %02X %s %d",
        (unsigned)reg,rt_stage,rt_code);
    reply(error);
}
static void ram_test(unsigned hold_ms) {
    uint8_t model=0,mode=0,original=0,changed=0,final_value=0;
    if (!rt_read(0x0D,&model)) {rt_prewrite_error(0x0D);return;}
    if (model!=0x44) {reply("ERR RAMTEST_MODEL");return;}
    if (!rt_read(0x14,&mode)) {rt_prewrite_error(0x14);return;}
    /* Official Offset is a substring index from MSB: offset 2 -> bit 5. */
    if ((mode&0x20)==0) {
        char error[48];
        snprintf(error,sizeof(error),"ERR RAMTEST_MODE_VALUE %02X",(unsigned)mode);
        reply(error);return;
    }
    if (!rt_read(0x26,&original)) {rt_prewrite_error(0x26);return;}
    if (original!=0xFF) {reply("ERR RAMTEST_BASELINE");return;}
    bool write_ok=rt_write(0xEF);
    sleep_ms(2);
    bool changed_ok=rt_read(0x26,&changed);
    /* Only hold a confirmed change; restoration never depends on host USB. */
    if (write_ok && changed_ok && changed==0xEF && hold_ms==10000) sleep_ms(10000);
    /* Do not return, cancel, or depend on USB until restoration is attempted. */
    bool restore_ack=rt_write(original);
    sleep_ms(2);
    bool final_ok=rt_read(0x26,&final_value);
    char response[100];
    snprintf(response,sizeof(response),"OK RAMTEST %02X %02X %02X %02X %02X %02X %02X",
        (unsigned)write_ok,(unsigned)changed_ok,(unsigned)changed,
        (unsigned)restore_ack,(unsigned)final_ok,(unsigned)final_value,(unsigned)mode);
    reply(response);
}

/* Only two transitions are exposed by the command parser; no arbitrary address/data. */
static void ram_set(uint8_t expected,uint8_t target) {
    uint8_t model=0,mode=0,original=0,observed=0,final_value=0;
    if (!rt_read(0x0D,&model)) {rt_prewrite_error(0x0D);return;}
    if (model!=0x44) {reply("ERR RAMTEST_MODEL");return;}
    if (!rt_read(0x14,&mode)) {rt_prewrite_error(0x14);return;}
    if (!(mode&0x20)) {reply("ERR RAMSET_MODE");return;}
    if (!rt_read(0x26,&original)) {rt_prewrite_error(0x26);return;}
    if (original!=expected) {reply("ERR RAMSET_STALE");return;}
    bool ack=rt_write(target);
    sleep_ms(2);
    bool read_ok=rt_read(0x26,&observed);
    bool applied=ack && read_ok && observed==target;
    bool rollback=false;
    if (!applied) {
        /* Roll back a failed apply to FF. Never reapply EF after a failed restore. */
        rollback=true;
        rt_write(0xFF);
        sleep_ms(2);
    }
    bool final_ok=rt_read(0x26,&final_value);
    if (applied && (!final_ok || final_value!=target)) {
        applied=false;rollback=true;
        rt_write(0xFF);sleep_ms(2);
        final_ok=rt_read(0x26,&final_value);
    }
    char response[96];
    snprintf(response,sizeof(response),"OK RAMSET %02X %02X %02X %02X %02X",
        (unsigned)applied,(unsigned)rollback,(unsigned)final_ok,(unsigned)final_value,(unsigned)mode);
    reply(response);
}
