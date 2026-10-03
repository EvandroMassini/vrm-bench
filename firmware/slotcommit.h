/* One Comanche USER slot. OTP_USR_PTR is address 167 (A7h), low nibble.
 * Nibble 15 means 9 slots left and the opcode is 40h. Nibble 0..7 means
 * slots left = 8 - nibble and the opcode is 40h plus (nibble + 1). Nibble
 * 8..14 means none left: this command returns before any write.
 * Clock is Comanche 71h, set with 24h only when the live byte is 20h.
 * Baxter 99h is never written. MFR opcodes 58h-5Fh are never sent.
 * Outputs stay in code 1 for the program and the following 20h reload,
 * then 71h, 88h and 89h are restored locally before the USB reply.
 */
static int sc_user_left(unsigned nibble) {
    if (nibble==15) return 9;
    if (nibble<9) return 8-(int)nibble;
    return 0;
}
static int sc_mfr_left(unsigned bits) {
    if (bits==7) return 3;
    if (bits<3) return 2-(int)bits;
    return 0;
}
static void sc_prewrite(uint8_t reg) {
    char error[96];
    snprintf(error,sizeof(error),"ERR COMMIT_PRECHECK %02X %s %d",(unsigned)reg,rt_stage,rt_code);
    reply(error);
}
static void commit_user(void) {
    uint8_t model=0,mode=0,a=0,b=0,clock=0,pointer=0,mfr=0;
    uint8_t d0_program=0,d0_reload=0,a5=0,sample10=0,sample26=0,clock_final=0,fa=0,fb=0;
    if (!rt_read(0x0D,&model)) {sc_prewrite(0x0D);return;}
    if (model!=0x44) {reply("ERR COMMIT_MODEL");return;}
    if (!rt_read(0x14,&mode)) {sc_prewrite(0x14);return;}
    if ((mode&0x20)==0) {
        char error[48];
        snprintf(error,sizeof(error),"ERR COMMIT_MODE_VALUE %02X",(unsigned)mode);
        reply(error);return;
    }
    if (!rt_read(0x88,&a) || !rt_read(0x89,&b)) {sc_prewrite(0x88);return;}
    if (a!=0x88 || b!=0x88) {
        char error[64];
        snprintf(error,sizeof(error),"ERR COMMIT_BASELINE %02X %02X",(unsigned)a,(unsigned)b);
        reply(error);return;
    }
    if (!rt_read(0x71,&clock)) {sc_prewrite(0x71);return;}
    if (clock!=0x20) {
        char error[48];
        snprintf(error,sizeof(error),"ERR COMMIT_CLOCK %02X",(unsigned)clock);
        reply(error);return;
    }
    if (!rt_read(0xA7,&pointer) || !rt_read(0xA6,&mfr)) {sc_prewrite(0xA7);return;}
    int left=sc_user_left(pointer&0x0F);
    int mfr_left=sc_mfr_left(mfr&0x07);
    if (left<=0) {
        char error[64];
        snprintf(error,sizeof(error),"ERR COMMIT_NOSLOT %02X %02X %02X %02X",
            (unsigned)pointer,(unsigned)left,(unsigned)mfr,(unsigned)mfr_left);
        reply(error);return;
    }
    unsigned index=(unsigned)(9-left);
    if (index>8) {reply("ERR COMMIT_INDEX");return;}
    uint8_t opcode=(uint8_t)(0x40|index);
    uint8_t pointer_after=pointer;
    bool w88=rt_write_at(0x88,0x48);
    sleep_ms(2);
    bool r88=rt_read(0x88,&a);
    bool w89=rt_write_at(0x89,0x48);
    sleep_ms(2);
    bool r89=rt_read(0x89,&b);
    bool shut=w88 && r88 && a==0x48 && w89 && r89 && b==0x48;
    bool clock_ok=false,opcode_sent=false,program_ok=false,reload_sent=false,reload_ok=false;
    if (shut) {
        clock_ok=rt_write_at(0x71,0x24);
        sleep_ms(2);
        uint8_t clock_seen=0;
        bool clock_read=rt_read(0x71,&clock_seen);
        clock_ok=clock_ok && clock_read && clock_seen==0x24;
        if (clock_ok) {
            opcode_sent=rt_write_at(0xD0,opcode);
            if (opcode_sent) {
                sleep_ms(200);
                for (int attempt=0; attempt<11; ++attempt) {
                    if (!rt_read(0xD0,&d0_program)) break;
                    if ((d0_program&0xE0)==0) {program_ok=true;break;}
                    sleep_ms(10);
                }
                rt_read(0xA7,&pointer_after);
                if (program_ok) {
                    reload_sent=rt_write_at(0xD0,0x20);
                    sleep_ms(50);
                    bool reload_read=rt_read(0xD0,&d0_reload);
                    reload_ok=reload_sent && reload_read && (d0_reload&0xE0)==0;
                    rt_read(0xA5,&a5);
                    rt_read(0xA7,&pointer_after);
                    rt_read(0x10,&sample10);
                    rt_read(0x26,&sample26);
                }
            }
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
    int left_after=sc_user_left(pointer_after&0x0F);
    char response[220];
    snprintf(response,sizeof(response),
        "OK COMMIT %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
        (unsigned)shut,(unsigned)pointer,(unsigned)left,(unsigned)index,(unsigned)opcode,
        (unsigned)clock_ok,(unsigned)opcode_sent,(unsigned)program_ok,(unsigned)d0_program,
        (unsigned)reload_sent,(unsigned)reload_ok,(unsigned)d0_reload,(unsigned)a5,
        (unsigned)pointer_after,(unsigned)left_after,(unsigned)sample10,(unsigned)sample26,
        (unsigned)(clock_restore && clock_final_ok && clock_final==0x20),
        (unsigned)(s88 && s89 && f88 && f89 && fa==0x88 && fb==0x88),(unsigned)fa,(unsigned)fb);
    reply(response);
}
