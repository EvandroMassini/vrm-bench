#ifdef ARDUINO
#include <Arduino.h>
#endif
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/i2c.h"

#define SDA_PIN 4
#define SCL_PIN 5
#define TIMEOUT_US 25000

static void reply(const char *text) {
#ifdef ARDUINO
    Serial.println(text);
#else
    puts(text);
#endif
}

static unsigned bus_khz = 100;
static unsigned half_period_us = 5;

static void bus_init(void) {
    i2c_init(i2c0, bus_khz * 1000);
    gpio_set_function(SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(SCL_PIN, GPIO_FUNC_I2C);
    gpio_disable_pulls(SDA_PIN);
    gpio_disable_pulls(SCL_PIN);
}
static void bus_reset(void) {
    i2c_deinit(i2c0);
    bus_init();
}
#include "probe.h"
#include "pmbus.h"
#include "ramtest.h"
#include "ensoft.h"
#include "parambyte.h"
#include "reload.h"
#include "slotcommit.h"
static unsigned telemetry_length(unsigned c) {
    switch(c) {
        case 0xD6: case 0x19: case 0x20: case 0x78: case 0x7D: case 0x7E: case 0x80: return 1;
        case 0x79: case 0x88: case 0x89: case 0x8B: case 0x8C:
        case 0x8D: case 0x8E: case 0x96: case 0x97: return 2;
        default: return 0;
    }
}
static int hex_byte(const char *s, unsigned *out) {
    if (strlen(s) != 2) return 0;
    for (int i=0; i<2; ++i)
        if (!((s[i]>='0' && s[i]<='9') || (s[i]>='A' && s[i]<='F') ||
              (s[i]>='a' && s[i]<='f'))) return 0;
    *out = (unsigned)strtoul(s, NULL, 16);
    return 1;
}
static void command(char *line) {
    if (strcmp(line, "HELLO") == 0) {
        reply("OK INFINEON-PICO 15 RAMTEST");
        return;
    }
    if (strcmp(line,"RAMSET 08 26 FF EF")==0) {ram_set(0xFF,0xEF);return;}
    if (strcmp(line,"RAMSET 08 26 EF FF")==0) {ram_set(0xEF,0xFF);return;}
    if (strcmp(line,"RAMHOLD 08 26 FF EF 10000 RESTORE")==0) {ram_test(10000);return;}
    if (strcmp(line,"RAMTEST 08 26 FF EF RESTORE")==0) {ram_test(0);return;}
    if (strcmp(line,"ENSOFT 08 88 89 88 48 RESTORE")==0) {en_soft(0);return;}
    if (strcmp(line,"ENHOLD 08 88 89 88 48 10000 RESTORE")==0) {en_soft(10000);return;}
    if (strcmp(line,"RELOAD 08 71 20 24 D0 20")==0) {reload_image();return;}
    if (strcmp(line,"COMMIT 08 USER")==0) {commit_user();return;}
    if (strncmp(line,"PBYTE ",6)==0) {
        char rv[3], ev[3], nv[3], tail;
        unsigned reg, expected, target;
        if (sscanf(line,"PBYTE 08 %2s %2s %2s %c",rv,ev,nv,&tail)==3 &&
            hex_byte(rv,&reg) && hex_byte(ev,&expected) && hex_byte(nv,&target)) {
            pbyte((uint8_t)reg,(uint8_t)expected,(uint8_t)target);
            return;
        }
        reply("ERR COMMAND");
        return;
    }
    if (strncmp(line,"REG ",4)==0) {
        char av[3], rv[3], tail; unsigned a,r;
        if (sscanf(line,"REG %2s %2s %c",av,rv,&tail)==2 && hex_byte(av,&a) && hex_byte(rv,&r) &&
            a>=8 && a<=0x77 && a!=0x0C) { register_read(a,r); return; }
        reply("ERR COMMAND"); return;
    }
    if (strncmp(line,"TEL ",4)==0) {
        char av[3], cv[3], tail;
        unsigned a,c;
        if (sscanf(line,"TEL %2s %2s %c",av,cv,&tail)==2 &&
            hex_byte(av,&a) && hex_byte(cv,&c) &&
            a>=8 && a<=0x77 && a!=0x0C && telemetry_length(c)) {
            pm_read(a,c,true,false,telemetry_length(c)); return;
        }
        reply("ERR COMMAND"); return;
    }
    if (strcmp(line, "LINES") == 0) { observe_lines(); return; }
    // Bounded tokens: PM address command pec stop. Only identification commands.
    if (strncmp(line,"PM ",3)==0) {
        char av[3], cv[3], pv[3], sv[3], tail;
        unsigned a,c,p,t;
        if (sscanf(line,"PM %2s %2s %2s %2s %c",av,cv,pv,sv,&tail)==4 &&
            hex_byte(av,&a) && hex_byte(cv,&c) && hex_byte(pv,&p) && hex_byte(sv,&t) &&
            a>=8 && a<=0x77 && a!=0x0C && c>=0x98 && c<=0x9B && p<=1 && t<=1 && !(p && t)) {
            pm_read(a,c,p==1,t==1,0); return;
        }
        reply("ERR COMMAND"); return;
    }
    if (strncmp(line,"RAW ",4)==0) {
        char av[3], cv[3], nv[3], sv[3], tail;
        unsigned a,c,n,t;
        if (sscanf(line,"RAW %2s %2s %2s %2s %c",av,cv,nv,sv,&tail)==4 &&
            hex_byte(av,&a) && hex_byte(cv,&c) && hex_byte(nv,&n) && hex_byte(sv,&t) &&
            a>=8 && a<=0x77 && a!=0x0C && (n==1 || n==2) && t<=1) {
            pm_read(a,c,false,t==1,n); return;
        }
        reply("ERR COMMAND"); return;
    }
    char *verb = strtok(line, " ");
    char *addr = strtok(NULL, " ");
    char *reg = strtok(NULL, " ");
    char *extra = strtok(NULL, " ");
    unsigned a, r;
    if (verb && strcmp(verb,"SPEED")==0 && addr && !reg && hex_byte(addr,&a) &&
        (a==10 || a==50 || a==100)) {
        bus_khz=a; half_period_us=500/a;
        i2c_set_baudrate(i2c0, a*1000);
        char response[24]; snprintf(response,sizeof(response),"OK SPEED %02X",a);
        reply(response); return;
    }
    if (verb && strcmp(verb, "MID")==0 && addr && reg && !extra &&
        hex_byte(addr,&a) && hex_byte(reg,&r) && a>=8 && a<=0x77 && a!=0x0C && r<=1) {
        pm_read(a,0x99,r==1,false,0);
        return;
    }
    if (verb && strcmp(verb, "PROBE") == 0 && addr && !reg &&
        hex_byte(addr, &a) && a>=8 && a<=0x77 && a!=0x0C) {
        reply(probe_address(a));
        return;
    }
    if (!verb || strcmp(verb, "READ") || !addr || !reg || extra ||
        !hex_byte(addr, &a) || !hex_byte(reg, &r) ||
        a<8 || a>0x77 || a==0x0C) {
        reply("ERR COMMAND");
        return;
    }
    if (!gpio_get(SDA_PIN) || !gpio_get(SCL_PIN)) {
        reply("ERR BUS_LOW");
        return;
    }
    uint8_t register_byte = (uint8_t)r, value;
    int result = i2c_write_timeout_us(i2c0, a, &register_byte, 1, true, TIMEOUT_US);
    if (result != 1) {
        bus_reset();
        reply("ERR I2C_POINTER");
        return;
    }
    result = i2c_read_timeout_us(i2c0, a, &value, 1, false, TIMEOUT_US);
    if (result != 1) {
        bus_reset();
        reply("ERR I2C_READ");
        return;
    }
    char response[8];
    snprintf(response, sizeof(response), "OK %02X", value);
    reply(response);
}
static char line[80];
static size_t length = 0;
static bool overflow = false;

static void consume(int c) {
    if (c == '\r') return;
    if (c == '\n') {
        line[length] = 0;
        if (overflow) reply("ERR LENGTH");
        else command(line);
        length = 0;
        overflow = false;
    } else if (!overflow) {
        if (length < sizeof(line)-1) line[length++] = (char)c;
        else overflow = true;
    }
}

#ifdef ARDUINO
void setup(void) {
    Serial.begin(115200);
    bus_init();
}
void loop(void) {
    if (Serial.available()) consume(Serial.read());
}
#else
int main(void) {
    stdio_init_all();
    bus_init();
    while (true) {
        int c = getchar_timeout_us(10000);
        if (c != PICO_ERROR_TIMEOUT) consume(c);
    }
}
#endif
