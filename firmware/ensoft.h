/* Fixed bench experiment, not a general-purpose write and not MTP.
 * I2C 08, model 44, AMD/GPU personality bit in register 14.
 * Registers 88 and 89 must both be exactly 88: software-enable code 2,
 * low six bits unchanged from the PcYes baseline.
 * Bits 7:6 become code 1 (byte 48). Both bytes are restored to 88 locally.
 * No OPERATION, D0/D5, unlock, OTP clock, or hard-shutdown code 0.
 */
static void es_prewrite(uint8_t reg) {
    char error[96];
    snprintf(error,sizeof(error),"ERR ENSOFT_PRECHECK %02X %s %d",(unsigned)reg,rt_stage,rt_code);
    reply(error);
}
static bool es_write(uint8_t reg,uint8_t value) {
    uint8_t bytes[2]={reg,value};
    rt_stage="IDLE_BEFORE";
    if (!rt_idle()) return false;
    rt_stage="WRITE";
    rt_code=i2c_write_timeout_us(i2c0,0x08,bytes,2,false,TIMEOUT_US);
    if (rt_code!=2) {bus_reset();return false;}
    rt_stage="STOP";
    return rt_idle();
}
static void en_soft(unsigned hold_ms) {
    uint8_t model=0,mode=0,a=0,b=0,ca=0,cb=0,st=0,ss=0,fa=0,fb=0;
    bool r96=false,ra9=false;
    if (!rt_read(0x0D,&model)) {es_prewrite(0x0D);return;}
    if (model!=0x44) {reply("ERR ENSOFT_MODEL");return;}
    if (!rt_read(0x14,&mode)) {es_prewrite(0x14);return;}
    if ((mode&0x20)==0) {
        char error[48];
        snprintf(error,sizeof(error),"ERR ENSOFT_MODE_VALUE %02X",(unsigned)mode);
        reply(error);return;
    }
    if (!rt_read(0x88,&a)) {es_prewrite(0x88);return;}
    if (!rt_read(0x89,&b)) {es_prewrite(0x89);return;}
    if (a!=0x88 || b!=0x88) {
        char error[64];
        snprintf(error,sizeof(error),"ERR ENSOFT_BASELINE %02X %02X",(unsigned)a,(unsigned)b);
        reply(error);return;
    }
    bool w1=es_write(0x88,0x48);
    sleep_ms(2);
    bool r1=rt_read(0x88,&ca);
    bool w2=es_write(0x89,0x48);
    sleep_ms(2);
    bool r2=rt_read(0x89,&cb);
    bool changed=w1 && r1 && ca==0x48 && w2 && r2 && cb==0x48;
    if (changed && hold_ms==10000) sleep_ms(10000);
    r96=rt_read(0x96,&st);
    ra9=rt_read(0xA9,&ss);
    /* Restoration never depends on USB or on the status reads above. */
    bool s1=es_write(0x88,0x88);
    sleep_ms(2);
    bool s2=es_write(0x89,0x88);
    sleep_ms(2);
    bool f1=rt_read(0x88,&fa);
    bool f2=rt_read(0x89,&fb);
    char response[160];
    snprintf(response,sizeof(response),
        "OK ENSOFT %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
        (unsigned)w1,(unsigned)w2,(unsigned)r1,(unsigned)ca,(unsigned)r2,(unsigned)cb,
        (unsigned)r96,(unsigned)st,(unsigned)ra9,(unsigned)ss,
        (unsigned)s1,(unsigned)s2,(unsigned)f1,(unsigned)fa,(unsigned)f2,(unsigned)fb,(unsigned)mode);
    reply(response);
}
