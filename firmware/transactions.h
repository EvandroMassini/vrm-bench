/* Protocol 16: bounded byte-register transactions. No controller model table.
 * The host supplies validated recipes; all cleanup executes on the Pico.
 * op 0 assertion, 1 temporary RMW, 2 persistent RMW, 3 command + bounded poll.
 */
typedef struct { uint8_t op,reg,mask,value,delay,poll_mask,poll_value,attempts; } tx_step;
static tx_step tx_steps[64];
static unsigned tx_count=0,tx_expected=0,tx_address=0;
static uint8_t tx_id_reg,tx_id_mask,tx_id_value;
static bool tx_ready=false;
static bool tx_idle(void) {
    uint64_t end=time_us_64()+TIMEOUT_US,high=0;
    while(time_us_64()<end) {
        uint64_t now=time_us_64();
        if ((i2c_get_hw(i2c0)->status & I2C_IC_STATUS_ACTIVITY_BITS) || !gpio_get(SDA_PIN) || !gpio_get(SCL_PIN)) high=0;
        else { if(!high) high=now; if(now-high>=10) return true; }
        sleep_us(1);
    }
    return false;
}
static bool tx_read(uint8_t reg,uint8_t *v) {
    if(!tx_idle()) return false;
    if(i2c_write_timeout_us(i2c0,tx_address,&reg,1,true,TIMEOUT_US)!=1 ||
       i2c_read_timeout_us(i2c0,tx_address,v,1,false,TIMEOUT_US)!=1) {bus_reset();return false;}
    return tx_idle();
}
static bool tx_write(uint8_t reg,uint8_t value) {
    uint8_t data[2]={reg,value};
    if(!tx_idle()) return false;
    if(i2c_write_timeout_us(i2c0,tx_address,data,2,false,TIMEOUT_US)!=2) {bus_reset();return false;}
    return tx_idle();
}
static void tx_run(void) {
    uint8_t saved[64]={0},seen=0;
    bool touched[64]={false},success=true,restored=true,wrote=false;
    unsigned failed=255;
    uint64_t deadline=time_us_64()+10000000;
    if(!tx_ready || tx_count!=tx_expected) {tx_ready=false;reply("ERR TX_INCOMPLETE");return;}
    tx_ready=false; /* Consumed before the first bus operation: never retry a commit. */
    if(!tx_read(tx_id_reg,&seen) || (seen&tx_id_mask)!=tx_id_value) {reply("OK TX 00 FF 00 01");return;}
    /* Read restoration snapshots and validate all initial assertions before writes. */
    for(unsigned i=0;i<tx_count;++i) {
        tx_step s=tx_steps[i];
        if(s.op==1 || s.op==2) {
            if(!tx_read(s.reg,&saved[i])) {success=false;failed=i;break;}
        }
        if(s.op==0 && (!tx_read(s.reg,&seen) || (seen&s.mask)!=s.value)) {success=false;failed=i;break;}
    }
    if(success) for(unsigned i=0;i<tx_count;++i) {
        tx_step s=tx_steps[i];
        if(time_us_64()>deadline) {success=false;failed=i;break;}
        if(s.op==0) continue;
        uint8_t value=s.value;
        if(s.op==1 || s.op==2) {
            if(!tx_read(s.reg,&seen) || seen!=saved[i]) {success=false;failed=i;break;}
            value=(seen & (uint8_t)~s.mask) | s.value;
        }
        touched[i]=true;wrote=true; /* Even a timeout may have reached the target. */
        bool ok=tx_write(s.reg,value);
        sleep_ms(s.delay);
        if(ok && s.op!=3) ok=tx_read(s.reg,&seen) && seen==value;
        if(ok && s.op==3) {
            ok=false;
            for(unsigned n=0;n<s.attempts;++n) {
                if(time_us_64()>deadline || !tx_read(s.reg,&seen)) break;
                if((seen&s.poll_mask)==s.poll_value) {ok=true;break;}
                sleep_ms(10);
            }
        }
        if(!ok) {success=false;failed=i;break;}
    }
    for(int i=(int)tx_count-1;i>=0;--i) {
        tx_step s=tx_steps[i];
        if(touched[i] && (s.op==1 || (s.op==2 && !success))) {
            bool ok=tx_write(s.reg,saved[i]);sleep_ms(2);
            bool read_ok=tx_read(s.reg,&seen);
            if(!ok || !read_ok || seen!=saved[i]) restored=false;
        }
    }
    char out[64];snprintf(out,sizeof(out),"OK TX %02X %02X %02X %02X",success?1:0,failed,wrote?1:0,restored?1:0);reply(out);
}
static bool tx_command(const char *line) {
    unsigned a,b,c,d,e,f,g,h,i,j; char tail;
    if(strncmp(line,"TXBEGIN ",8)==0) {
        tx_ready=false;tx_count=0;
        if(sscanf(line,"TXBEGIN %x %x %x %x %x %c",&a,&b,&c,&d,&e,&tail)==5 &&
           a>=8 && a<=0x77 && a!=0x0C && b<=255 && c>0 && c<=255 && d<=255 && !(d&~c) && e>0 && e<=64) {
            tx_address=a;tx_id_reg=b;tx_id_mask=c;tx_id_value=d;tx_expected=e;tx_ready=true;reply("OK TXBEGIN");
        } else reply("ERR TXBEGIN");
        return true;
    }
    if(strncmp(line,"TXSTEP ",7)==0) {
        if(tx_ready && sscanf(line,"TXSTEP %x %x %x %x %x %x %x %x %x %c",&a,&b,&c,&d,&e,&f,&g,&h,&i,&tail)==9 &&
           a==tx_count && tx_count<tx_expected && b<=3 && c<=255 && d>0 && d<=255 && e<=255 && !(e&~d) && f<=255 &&
           g<=255 && h<=255 && !(h&~g) && i>0 && i<=20 && (b!=3 || (d==255 && g>0))) {
            /* Duplicate mutation registers make snapshots ambiguous; refuse them. */
            bool duplicate=false;
            for(j=0;j<tx_count;++j) if(b && b!=3 && tx_steps[j].op && tx_steps[j].reg==c) duplicate=true;
            if(!duplicate) {tx_steps[tx_count++]=(tx_step){(uint8_t)b,(uint8_t)c,(uint8_t)d,(uint8_t)e,(uint8_t)f,(uint8_t)g,(uint8_t)h,(uint8_t)i};reply("OK TXSTEP");return true;}
        }
        tx_ready=false;reply("ERR TXSTEP");return true;
    }
    if(strcmp(line,"TXRUN")==0) {tx_run();return true;}
    if(strcmp(line,"TXABORT")==0) {tx_ready=false;reply("OK TXABORT");return true;}
    return false;
}
