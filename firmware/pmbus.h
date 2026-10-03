/* PMBus MFR_ID (99h) SMBus Block Read, count 1..32, optional received PEC.
   Single-master, open-drain. No configuration data or write commands. */
static const char *pm_error;
static absolute_time_t pm_deadline;
static bool pm_clock(void) {
    if (time_reached(pm_deadline)) { pm_error="ERR PMBUS_TIMEOUT"; return false; }
    if (!raise_clock()) { pm_error="ERR SCL_TIMEOUT"; return false; }
    return true;
}
static bool pm_start(void) {
    release_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!pm_clock()) return false;
    if (!gpio_get(SDA_PIN)) { pm_error="ERR BUS_CONFLICT"; return false; }
    low_pin(SDA_PIN);
    sleep_us(half_period_us);
    low_pin(SCL_PIN);
    return true;
}
static bool pm_stop(void) {
    low_pin(SCL_PIN);
    low_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!pm_clock()) return false;
    release_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!gpio_get(SDA_PIN)) { pm_error="ERR BUS_BUSY"; return false; }
    return true;
}
static bool pm_send(unsigned byte, const char *nack) {
    for (int bit=7;bit>=0;--bit) {
        bool one=((byte>>bit)&1u)!=0;
        if (one) release_pin(SDA_PIN); else low_pin(SDA_PIN);
        sleep_us(half_period_us);
        if (!pm_clock()) return false;
        if (one && !gpio_get(SDA_PIN)) { pm_error="ERR BUS_CONFLICT"; return false; }
        low_pin(SCL_PIN);
    }
    release_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!pm_clock()) return false;
    bool ack=!gpio_get(SDA_PIN);
    low_pin(SCL_PIN);
    if (!ack) {
        pm_error=nack;
        pm_stop();
        return false;
    }
    return true;
}
static bool pm_octet(uint8_t *byte) {
    *byte=0;
    release_pin(SDA_PIN);
    for (int bit=7;bit>=0;--bit) {
        sleep_us(half_period_us);
        if (!pm_clock()) return false;
        *byte=(uint8_t)((*byte<<1)|(gpio_get(SDA_PIN)?1:0));
        low_pin(SCL_PIN);
    }
    return true;
}
static bool pm_ack(bool ack) {
    if (ack) low_pin(SDA_PIN); else release_pin(SDA_PIN);
    sleep_us(half_period_us);
    if (!pm_clock()) return false;
    low_pin(SCL_PIN);
    release_pin(SDA_PIN);
    return true;
}
static void pm_read(unsigned address, unsigned command, bool pec, bool split, unsigned raw_count) {
    i2c_deinit(i2c0);
    gpio_init(SDA_PIN); gpio_init(SCL_PIN);
    gpio_disable_pulls(SDA_PIN); gpio_disable_pulls(SCL_PIN);
    release_pin(SDA_PIN); release_pin(SCL_PIN);
    pm_error=NULL;
    pm_deadline=make_timeout_time_ms(250);
    uint8_t count=0, data[32], checksum=0;
    char response[110], encoded[65];
    for (int i=0;i<100;++i) {
        if (!gpio_get(SDA_PIN)||!gpio_get(SCL_PIN)) {pm_error="ERR BUS_BUSY";goto done;}
        sleep_us(10);
    }
    if (!pm_start() || !pm_send(address<<1,"ERR PMBUS_ADDR_W") ||
        !pm_send(command,"ERR PMBUS_COMMAND")) goto done;
    if (split) {
        if (!pm_stop()) goto done;
        sleep_us(half_period_us);
    }
    if (!pm_start() || !pm_send((address<<1)|1,"ERR PMBUS_ADDR_R")) goto done;
    if (raw_count) {
        count=raw_count;
    } else {
        if (!pm_octet(&count)) goto done;
        if (count>=1 && count<=32 && !pm_ack(true)) goto done;
    }
    if (count<1 || count>32) {
        pm_error="ERR PMBUS_COUNT";
        if (pm_ack(false)) pm_stop();
        goto done;
    }
    for (unsigned i=0;i<count;++i) {
        if (!pm_octet(&data[i]) || !pm_ack(pec || i+1<count)) goto done;
    }
    if (pec && (!pm_octet(&checksum) || !pm_ack(false))) goto done;
    if (!pm_stop()) goto done;
    for (unsigned i=0;i<count;++i) snprintf(encoded+2*i,3,"%02X",data[i]);
    if (pec) snprintf(response,sizeof(response),"OK BLOCK %02X %s %02X",count,encoded,checksum);
    else snprintf(response,sizeof(response),"OK BLOCK %02X %s --",count,encoded);
done:
    release_pin(SDA_PIN); release_pin(SCL_PIN);
    bus_init();
    reply(pm_error?pm_error:response);
}

// Digital observations only, not a voltage measurement or protocol analyzer.
// D3 writes only the volatile read pointer; D4 reads the selected register.
// No configurable opcode, D0/D5, unlock, or MTP programming operation.
static uint8_t pointer_crc(uint8_t a,uint8_t r,uint8_t pointer_command) {
    uint8_t bytes[3]={a,pointer_command,r},crc=0;
    for(unsigned i=0;i<3;++i) {
        crc^=bytes[i];
        for(unsigned j=0;j<8;++j) crc=(uint8_t)((crc<<1)^((crc&0x80)?7:0));
    }
    return crc;
}
static void register_read(unsigned address,unsigned reg,unsigned pointer_command,unsigned read_command) {
    i2c_deinit(i2c0);
    gpio_init(SDA_PIN);gpio_init(SCL_PIN);
    gpio_disable_pulls(SDA_PIN);gpio_disable_pulls(SCL_PIN);
    release_pin(SDA_PIN);release_pin(SCL_PIN);
    pm_error=NULL;pm_deadline=make_timeout_time_ms(250);
    for(unsigned i=0;i<100;++i) {
        if(!gpio_get(SDA_PIN)||!gpio_get(SCL_PIN)) {pm_error="ERR BUS_BUSY";goto finish_pointer;}
        sleep_us(10);
    }
    if(!pm_start() || !pm_send(address<<1,"ERR POINTER_ADDRESS") ||
       !pm_send(pointer_command,"ERR POINTER_COMMAND") || !pm_send(reg,"ERR POINTER_REGISTER") ||
       !pm_send(pointer_crc((uint8_t)(address<<1),(uint8_t)reg,(uint8_t)pointer_command),"ERR POINTER_PEC") || !pm_stop()) goto finish_pointer;
finish_pointer:
    release_pin(SDA_PIN);release_pin(SCL_PIN);bus_init();
    if(pm_error) {reply(pm_error);return;}
    pm_read(address,read_command,true,false,1);
}

static void observe_lines(void) {
    i2c_deinit(i2c0);
    gpio_init(SDA_PIN); gpio_init(SCL_PIN);
    gpio_disable_pulls(SDA_PIN); gpio_disable_pulls(SCL_PIN);
    release_pin(SDA_PIN); release_pin(SCL_PIN);
    unsigned sda_low=0,scl_low=0,changes=0;
    unsigned previous=(gpio_get(SDA_PIN)?1:0)|(gpio_get(SCL_PIN)?2:0);
    for (unsigned i=0;i<10000;++i) {
        unsigned current=(gpio_get(SDA_PIN)?1:0)|(gpio_get(SCL_PIN)?2:0);
        if (!(current&1)) ++sda_low;
        if (!(current&2)) ++scl_low;
        if (current!=previous) ++changes;
        previous=current;
        sleep_us(10);
    }
    char response[100];
    snprintf(response,sizeof(response),"OK LINES 10000 %u %u %u %u",sda_low,scl_low,changes,previous);
    bus_init(); reply(response);
}
