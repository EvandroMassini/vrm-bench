/* Comanche verify-button reload. Not a slot commit and not the Baxter clock address.
 * Baxter OTP_CLOCK_EN is register 153 (99h). Comanche OTP_CLOCK_EN is 113 (71h).
 * OTP_COMMAND is 208 (D0h) in both families. ProgramMTP writes the clock through
 * the Baxter address; this command does not.
 * Fixed bytes only: 71h must be 20h, then 24h; D0h receives 20h. User-slot opcodes
 * are 0100xxxx and are not sent. Outputs are soft-shutdown (88h/89h = 48h) for
 * the reload and restored to 88h locally before the USB reply.
 */
static void rl_prewrite(uint8_t reg) {
    char error[96];
    snprintf(error,sizeof(error),"ERR RELOAD_PRECHECK %02X %s %d",(unsigned)reg,rt_stage,rt_code);
    reply(error);
}
static void reload_image(void) {
    uint8_t model=0,mode=0,a=0,b=0,clock=0;
    uint8_t clock_seen=0,d0=0,a5=0,sample10=0,sample26=0,clock_final=0,fa=0,fb=0;
    if (!rt_read(0x0D,&model)) {rl_prewrite(0x0D);return;}
    if (model!=0x44) {reply("ERR RELOAD_MODEL");return;}
    if (!rt_read(0x14,&mode)) {rl_prewrite(0x14);return;}
    if ((mode&0x20)==0) {
        char error[48];
        snprintf(error,sizeof(error),"ERR RELOAD_MODE_VALUE %02X",(unsigned)mode);
        reply(error);return;
    }
    if (!rt_read(0x88,&a) || !rt_read(0x89,&b)) {rl_prewrite(0x88);return;}
    if (a!=0x88 || b!=0x88) {
        char error[64];
        snprintf(error,sizeof(error),"ERR RELOAD_BASELINE %02X %02X",(unsigned)a,(unsigned)b);
        reply(error);return;
    }
    if (!rt_read(0x71,&clock)) {rl_prewrite(0x71);return;}
    if (clock!=0x20) {
        char error[48];
        snprintf(error,sizeof(error),"ERR RELOAD_CLOCK %02X",(unsigned)clock);
        reply(error);return;
    }
    bool w88=rt_write_at(0x88,0x48);
    sleep_ms(2);
    bool r88=rt_read(0x88,&a);
    bool w89=rt_write_at(0x89,0x48);
    sleep_ms(2);
    bool r89=rt_read(0x89,&b);
    bool shut=w88 && r88 && a==0x48 && w89 && r89 && b==0x48;
    bool clock_ok=false,cmd_ok=false;
    if (shut) {
        clock_ok=rt_write_at(0x71,0x24);
        sleep_ms(2);
        bool clock_read=rt_read(0x71,&clock_seen);
        clock_ok=clock_ok && clock_read && clock_seen==0x24;
        if (clock_ok) {
            cmd_ok=rt_write_at(0xD0,0x20);
            sleep_ms(50);
            rt_read(0xD0,&d0);
            rt_read(0xA5,&a5);
            rt_read(0x10,&sample10);
            rt_read(0x26,&sample26);
        }
    }
    bool clock_restore=rt_write_at(0x71,0x20);
    sleep_ms(2);
    bool clock_final_ok=rt_read(0x71,&clock_final);
    bool s88=rt_write_at(0x88,0x88);
    sleep_ms(2);
    bool s89=rt_write_at(0x89,0x88);
    sleep_ms(2);
    bool f88=rt_read(0x88,&fa);
    bool f89=rt_read(0x89,&fb);
    char response[180];
    snprintf(response,sizeof(response),
        "OK RELOAD %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
        (unsigned)shut,(unsigned)clock_ok,(unsigned)clock_seen,(unsigned)cmd_ok,
        (unsigned)d0,(unsigned)a5,(unsigned)sample10,(unsigned)sample26,
        (unsigned)clock_restore,(unsigned)clock_final_ok,(unsigned)clock_final,
        (unsigned)(s88 && s89 && f88 && f89 && fa==0x88 && fb==0x88),(unsigned)fa,(unsigned)fb);
    reply(response);
}
